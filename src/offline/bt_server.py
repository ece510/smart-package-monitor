#!/usr/bin/env python3
"""
Smart Package Monitor — Bluetooth Forwarder (RFCOMM/SPP server)
ECE 510 | IIT | Team 1

Forward half of the store-and-forward pipeline. Listens on an RFCOMM
channel so a nearby device (e.g. a phone running a generic "Serial
Bluetooth Terminal" app) can connect, pull buffered readings out of the
ReadingStore, and acknowledge them.

In Lab 3 the Pi was the RFCOMM *client*, connecting out to an HC-06. Here
the Pi is the RFCOMM *server*: it listens on a channel and waits for the
nearby device to connect in, the same role the HC-06 played then.

Uses Python's stdlib `socket.AF_BLUETOOTH` / `BTPROTO_RFCOMM` (Linux only)
rather than a third-party Bluetooth package — the PyPI sdist for the
common wrapper (pybluez2 0.46) is missing C headers needed to build it.
The SDP "Serial Port" record that lets phones discover this service via
the standard SPP UUID is registered by the system itself (see
RFCOMM_CHANNEL below and the systemd `bluetooth.service` override that
runs `sdptool add --channel=1 SP` whenever bluetoothd starts) rather than
from Python, since registering it requires root and is a one-time,
service-lifecycle concern, not a per-connection one.

Line protocol (newline-terminated ASCII/JSON, one command per line):
    STATUS  -> {"pending": N, "total": M}
    SYNC    -> one JSON line per unsynced row, then {"done": N};
               those rows are marked synced once all are sent.
    ALL     -> one JSON line per row in the store (no synced flag change).
    CLEAR   -> deletes already-synced rows, replies {"cleared": N}.
    RESET   -> deletes every row regardless of synced flag, replies
               {"cleared": N}. Used by the Android app's "Clear history"
               button, since the app only ever reads via ALL (never marks
               rows as synced), so CLEAR alone can't clear what it shows.
    PHOTOS  -> one JSON line per available photo (reference frame, if any,
               then the most recent incident's captures), then
               {"done": N}.
    PHOTO <name> -> the named photo's bytes, base64-encoded on one line,
               framed as {"photo": name, "size": N, "encoding": "base64",
               "kind": ..., "label": ...} then the base64 line then
               {"done": 1}; or a single {"error": ...} line (no trailer)
               if name isn't recognized.
    ALLPHOTOS -> every available photo, back to back: for each, the same
               header+base64 framing PHOTO uses (no per-photo {"done"}),
               followed by one final {"done": N} once all have been sent.
               Lets the client fetch the whole set over a single RFCOMM
               connection instead of reconnecting per photo.
"""

import base64
import io
import json
import os
import socket
import threading

try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False

# Photos are only ever viewed by the client app over a slow Bluetooth SPP
# link, so there's no reason to ship full-resolution camera JPEGs (these can
# run several MB each — observed at ~37 MB total for one incident's worth of
# captures, which is minutes over RFCOMM). Re-encode at send time rather than
# relying on capture-time downscaling, so this also shrinks photos that were
# already saved at full resolution before this fix existed.
SEND_MAX_WIDTH = 960
SEND_JPEG_QUALITY = 70
_warned_no_pillow = False

RFCOMM_CHANNEL = 1  # must match the channel sdptool advertises (see WIRING.md)

BANNER = "SPM-BT ready | commands: STATUS, SYNC, ALL, CLEAR, RESET, PHOTOS, PHOTO, ALLPHOTOS"

# These two paths MUST stay in sync with src/vision/box_surveillance.py
# (CAPTURE_DIR and the reference frame path in main()). Duplicated here
# rather than imported, since box_surveillance.py pulls in heavy CV deps
# (cv2, numpy, skimage) we don't want in the BT server thread.
CAPTURE_DIR = os.path.expanduser(
    "/home/ece510/smart-package-monitor/src/vision/surveillance_captures"
)
REFERENCE_FRAME_PATH = (
    "/home/ece510/smart-package-monitor/src/vision/reference_frame_detected.jpg"
)

# Labels emitted by box_surveillance.save_snapshot(), chronological within one
# incident. Used to size "the latest incident" (the trailing group of captures).
INCIDENT_LABELS = ("alarm_0s", "alarm_5s", "alarm_10s", "shutdown_4th")
MAX_INCIDENT_PHOTOS = len(INCIDENT_LABELS)


def _row_to_json(row) -> str:
    return json.dumps(
        {
            "id": row["id"],
            "ts": row["ts"],
            "accel_x_g": row["accel_x_g"],
            "accel_y_g": row["accel_y_g"],
            "accel_z_g": row["accel_z_g"],
            "temp_c": row["temp_c"],
            "hum_pct": row["hum_pct"],
            "is_alert": bool(row["is_alert"]),
            "alert_reason": row["alert_reason"],
        }
    )


def _list_photo_meta() -> list:
    """Reference frame (if present) + the most recent incident's captures
    (trailing <=4 by chronological order). No DB linkage between alert rows
    and capture filenames exists, so this is pure filesystem inspection — a
    known simplification, sufficient for the demo.

    Sorted by mtime, NOT by filename string: capture labels (alarm_0s,
    alarm_5s, alarm_10s, shutdown_4th) don't sort lexicographically in
    chronological order ("alarm_10s" < "alarm_5s" as strings, since '1' <
    '5'), so a plain `sorted()` on filenames mixes captures from different
    incidents. mtime reflects actual write order regardless of label text.
    """
    meta = []
    if os.path.isfile(REFERENCE_FRAME_PATH):
        meta.append({
            "name": os.path.basename(REFERENCE_FRAME_PATH),
            "kind": "reference",
            "size": os.path.getsize(REFERENCE_FRAME_PATH),
        })
    try:
        candidates = [
            f for f in os.listdir(CAPTURE_DIR)
            if f.startswith("capture_") and f.endswith(".jpg")
        ]
        captures = sorted(candidates, key=lambda f: os.path.getmtime(os.path.join(CAPTURE_DIR, f)))
    except OSError:
        captures = []
    for fname in captures[-MAX_INCIDENT_PHOTOS:]:
        meta.append({
            "name": fname,
            "kind": "incident",
            "label": _label_from_capture_name(fname),
            "size": os.path.getsize(os.path.join(CAPTURE_DIR, fname)),
        })
    return meta


def _label_from_capture_name(fname: str) -> str:
    """capture_alarm_0s_20260624-101500.jpg -> 'alarm_0s'. Falls back to ''
    if the name doesn't match a known label."""
    for label in INCIDENT_LABELS:
        if fname.startswith(f"capture_{label}_"):
            return label
    return ""


def _compressed_photo_bytes(path: str) -> bytes:
    """Re-encodes the photo at `path` as a downscaled, lower-quality JPEG for
    transfer over Bluetooth, regardless of how it was originally saved. Falls
    back to the raw file bytes (and prints a one-time warning) if Pillow
    isn't installed or re-encoding fails for any reason — a slow transfer is
    better than a broken one."""
    global _warned_no_pillow
    if not _HAS_PILLOW:
        if not _warned_no_pillow:
            print("[BluetoothForwarder] Pillow not installed — sending photos "
                  "at full size. Run: pip3 install Pillow")
            _warned_no_pillow = True
        with open(path, "rb") as f:
            return f.read()

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > SEND_MAX_WIDTH:
                new_height = round(img.height * SEND_MAX_WIDTH / img.width)
                img = img.resize((SEND_MAX_WIDTH, new_height), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=SEND_JPEG_QUALITY)
            return buf.getvalue()
    except Exception as e:
        print(f"[BluetoothForwarder] Could not re-encode '{path}' ({e}); "
              "sending original bytes.")
        with open(path, "rb") as f:
            return f.read()


def _resolve_photo_path(name: str):
    """Maps an allow-listed bare filename to its on-disk path, or None if
    the name isn't one we're currently serving. Defense-in-depth against
    path traversal: name must be a bare basename and must appear in the
    freshly computed allow-list (never joined from arbitrary client input)."""
    if not name or name != os.path.basename(name) or "/" in name or "\\" in name:
        return None
    allowed = {m["name"] for m in _list_photo_meta()}
    if name not in allowed:
        return None
    if name == os.path.basename(REFERENCE_FRAME_PATH):
        return REFERENCE_FRAME_PATH
    return os.path.join(CAPTURE_DIR, name)


class BluetoothForwarder:
    """
    Runs a daemon thread that accepts RFCOMM connections on
    RFCOMM_CHANNEL and serves buffered readings from a ReadingStore over
    a simple line protocol. Handles one client connection at a time
    (sufficient for a single nearby "data mule" device picking up
    readings).
    """

    def __init__(self, store):
        self._store = store
        self._running = False
        self._thread = None
        self._server_sock = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        print("[BluetoothForwarder] Started.")

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        print("[BluetoothForwarder] Stopped.")

    # ── Server loop ──────────────────────────────────────────────────────────

    def _serve_loop(self):
        try:
            self._server_sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            self._server_sock.bind(("00:00:00:00:00:00", RFCOMM_CHANNEL))
            self._server_sock.listen(1)
            print(f"[BluetoothForwarder] Listening on RFCOMM channel {RFCOMM_CHANNEL}.")
        except OSError as e:
            print(f"[BluetoothForwarder] Could not start RFCOMM server: {e}")
            return

        while self._running:
            try:
                client_sock, client_info = self._server_sock.accept()
            except OSError:
                break  # socket closed by stop()

            print(f"[BluetoothForwarder] Connection from {client_info}")
            try:
                self._handle_client(client_sock)
            except OSError as e:
                print(f"[BluetoothForwarder] Client connection dropped: {e}")
            finally:
                client_sock.close()

    def _handle_client(self, client_sock):
        client_sock.send((BANNER + "\n").encode("utf-8"))
        buffer = ""
        while self._running:
            data = client_sock.recv(1024)
            if not data:
                break
            buffer += data.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                command = line.strip()
                if command:
                    self._dispatch(client_sock, command)

    def _dispatch(self, client_sock, command: str):
        # Only the verb is case-insensitive — PHOTO's filename argument must
        # keep its original case to match the on-disk filename exactly.
        verb = command.split(" ", 1)[0].upper()
        print(f"[BluetoothForwarder] Command: {command}")

        if verb == "STATUS":
            client_sock.send((json.dumps(self._store.stats()) + "\n").encode("utf-8"))

        elif verb == "SYNC":
            rows = self._store.fetch_unsynced()
            for row in rows:
                client_sock.send((_row_to_json(row) + "\n").encode("utf-8"))
            self._store.mark_synced([row["id"] for row in rows])
            client_sock.send((json.dumps({"done": len(rows)}) + "\n").encode("utf-8"))

        elif verb == "ALL":
            rows = self._store.fetch_all()
            for row in rows:
                client_sock.send((_row_to_json(row) + "\n").encode("utf-8"))
            client_sock.send((json.dumps({"done": len(rows)}) + "\n").encode("utf-8"))

        elif verb == "CLEAR":
            cleared = self._store.purge_synced()
            client_sock.send((json.dumps({"cleared": cleared}) + "\n").encode("utf-8"))

        elif verb == "RESET":
            cleared = self._store.purge_all()
            client_sock.send((json.dumps({"cleared": cleared}) + "\n").encode("utf-8"))

        elif verb == "PHOTOS":
            meta = _list_photo_meta()
            for m in meta:
                client_sock.send((json.dumps(m) + "\n").encode("utf-8"))
            client_sock.send((json.dumps({"done": len(meta)}) + "\n").encode("utf-8"))

        elif verb == "PHOTO":
            requested = command[len("PHOTO "):].strip()
            self._send_photo(client_sock, requested)

        elif verb == "ALLPHOTOS":
            meta = _list_photo_meta()
            sent = 0
            total_bytes = 0
            for m in meta:
                photo_bytes = self._write_one_photo(client_sock, m["name"])
                if photo_bytes is not None:
                    sent += 1
                    total_bytes += photo_bytes
            client_sock.send((json.dumps({"done": sent}) + "\n").encode("utf-8"))
            print(f"[BluetoothForwarder] ALLPHOTOS: sent {sent} photos, "
                  f"{total_bytes} bytes")

        else:
            client_sock.send((json.dumps({"error": f"unknown command '{command}'"}) + "\n")
                              .encode("utf-8"))

    def _send_photo(self, client_sock, name: str):
        path = _resolve_photo_path(name)
        if path is None:
            client_sock.send(
                (json.dumps({"error": f"unknown photo '{name}'"}) + "\n").encode("utf-8")
            )
            return
        if self._write_photo_frames(client_sock, name, path) is None:
            client_sock.send(
                (json.dumps({"error": f"could not read '{name}'"}) + "\n").encode("utf-8")
            )
            return
        client_sock.send((json.dumps({"done": 1}) + "\n").encode("utf-8"))

    def _write_one_photo(self, client_sock, name: str):
        """Used by ALLPHOTOS: writes one photo's header+base64 frames (no
        per-photo {"done"} trailer — the caller sends one trailer for the
        whole batch). Returns None (and sends nothing for this photo) if
        the name can't be resolved or the file can't be read, so one
        missing/raced file doesn't abort the rest of the batch. Otherwise
        returns the number of bytes sent for this photo."""
        path = _resolve_photo_path(name)
        if path is None:
            return None
        return self._write_photo_frames(client_sock, name, path)

    def _write_photo_frames(self, client_sock, name: str, path: str):
        """Sends a photo's header line + base64 payload line (no trailer).
        Shared by PHOTO (which appends its own {"done": 1}) and ALLPHOTOS
        (which appends one {"done": N} after the whole batch). Returns the
        number of (compressed) bytes sent, or None if the file couldn't be
        read."""
        try:
            raw = _compressed_photo_bytes(path)
        except OSError:
            return None

        meta = next((m for m in _list_photo_meta() if m["name"] == name), None)
        header = {
            "photo": name,
            "size": len(raw),
            "encoding": "base64",
            "kind": meta["kind"] if meta else None,
            "label": meta.get("label") if meta else None,
        }
        client_sock.send((json.dumps(header) + "\n").encode("utf-8"))
        client_sock.send((base64.b64encode(raw).decode("ascii") + "\n").encode("utf-8"))
        return len(raw)
