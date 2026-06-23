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
"""

import json
import socket
import threading

RFCOMM_CHANNEL = 1  # must match the channel sdptool advertises (see WIRING.md)

BANNER = "SPM-BT ready | commands: STATUS, SYNC, ALL, CLEAR"


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
                command = line.strip().upper()
                if command:
                    self._dispatch(client_sock, command)

    def _dispatch(self, client_sock, command: str):
        if command == "STATUS":
            client_sock.send((json.dumps(self._store.stats()) + "\n").encode("utf-8"))

        elif command == "SYNC":
            rows = self._store.fetch_unsynced()
            for row in rows:
                client_sock.send((_row_to_json(row) + "\n").encode("utf-8"))
            self._store.mark_synced([row["id"] for row in rows])
            client_sock.send((json.dumps({"done": len(rows)}) + "\n").encode("utf-8"))

        elif command == "ALL":
            rows = self._store.fetch_all()
            for row in rows:
                client_sock.send((_row_to_json(row) + "\n").encode("utf-8"))
            client_sock.send((json.dumps({"done": len(rows)}) + "\n").encode("utf-8"))

        elif command == "CLEAR":
            cleared = self._store.purge_synced()
            client_sock.send((json.dumps({"cleared": cleared}) + "\n").encode("utf-8"))

        else:
            client_sock.send((json.dumps({"error": f"unknown command '{command}'"}) + "\n")
                              .encode("utf-8"))
