#!/usr/bin/env python3
"""
Smart Package Monitor — photo listing/path-safety unit test
ECE 510 | IIT | Team 1

Pure-filesystem test for bt_server.py's PHOTOS/PHOTO helpers. Runs anywhere
(no I2C, no Bluetooth, no camera needed) by monkey-patching CAPTURE_DIR /
REFERENCE_FRAME_PATH to point at a temp directory.

Run from smart_package/code:
    python tests/test_photo_listing.py
"""

import base64
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import offline.bt_server as bt_server  # noqa: E402


class _FakeSocket:
    """Captures everything BluetoothForwarder would .send() over RFCOMM,
    so ALLPHOTOS framing can be asserted without a real socket/Bluetooth."""

    def __init__(self):
        self.lines = []

    def send(self, data: bytes):
        self.lines.append(data.decode("utf-8").rstrip("\n"))


def main():
    tmp = tempfile.mkdtemp()
    capture_dir = os.path.join(tmp, "captures")
    os.makedirs(capture_dir)
    ref_path = os.path.join(tmp, "reference_frame_detected.jpg")

    with open(ref_path, "wb") as f:
        f.write(b"FAKE_REF_JPEG_BYTES")

    # Two incidents' worth of captures. Names are deliberately NOT in
    # chronological string order across labels ("alarm_10s" < "alarm_5s"
    # lexicographically) to exercise the mtime-based sort.
    names = [
        "capture_alarm_0s_20260620-100000.jpg",   # old incident
        "capture_alarm_5s_20260620-100005.jpg",
        "capture_alarm_10s_20260620-100010.jpg",
        "capture_shutdown_4th_20260620-100012.jpg",
        "capture_alarm_0s_20260624-101500.jpg",   # latest incident (no shutdown — recovered)
        "capture_alarm_5s_20260624-101505.jpg",
        "capture_alarm_10s_20260624-101510.jpg",
    ]
    for i, n in enumerate(names):
        p = os.path.join(capture_dir, n)
        with open(p, "wb") as f:
            f.write(b"FAKE_JPEG_BYTES_" + n.encode())
        # Force a distinct, increasing mtime per file in creation order
        # (some filesystems have coarse mtime resolution if written
        # back-to-back).
        mtime = time.time() + i
        os.utime(p, (mtime, mtime))

    bt_server.CAPTURE_DIR = capture_dir
    bt_server.REFERENCE_FRAME_PATH = ref_path

    # -- _list_photo_meta: reference first, then the last 4 by mtime --
    meta = bt_server._list_photo_meta()
    assert len(meta) == 5, f"expected 5 rows (1 ref + 4 incident), got {len(meta)}: {meta}"
    assert meta[0]["kind"] == "reference"
    assert meta[0]["name"] == "reference_frame_detected.jpg"

    incident_names = [m["name"] for m in meta[1:]]
    # By mtime, the trailing 4 writes are: the OLD incident's shutdown_4th
    # (its 0s/5s/10s already fell off the window) + the NEW incident's
    # 0s/5s/10s. One stale leftover from the previous incident mixing in is
    # the accepted "known simplification" (no DB linkage), not a bug.
    assert incident_names == [
        "capture_shutdown_4th_20260620-100012.jpg",
        "capture_alarm_0s_20260624-101500.jpg",
        "capture_alarm_5s_20260624-101505.jpg",
        "capture_alarm_10s_20260624-101510.jpg",
    ], incident_names

    labels = [m.get("label") for m in meta[1:]]
    assert labels == ["shutdown_4th", "alarm_0s", "alarm_5s", "alarm_10s"], labels

    # -- _resolve_photo_path: allow-listed names resolve, everything else doesn't --
    assert bt_server._resolve_photo_path("reference_frame_detected.jpg") == ref_path
    assert bt_server._resolve_photo_path("capture_alarm_0s_20260624-101500.jpg") == \
        os.path.join(capture_dir, "capture_alarm_0s_20260624-101500.jpg")

    # Path-traversal / arbitrary-file attempts must all be rejected.
    assert bt_server._resolve_photo_path("../../etc/passwd") is None
    assert bt_server._resolve_photo_path("/etc/shadow") is None
    assert bt_server._resolve_photo_path("..\\..\\windows\\win.ini") is None
    assert bt_server._resolve_photo_path("nope.jpg") is None
    # A real capture filename, but one that fell outside the trailing window
    # (belongs to the old incident) — must NOT resolve, even though the file
    # exists on disk, because it's not in the current allow-list.
    assert bt_server._resolve_photo_path("capture_alarm_0s_20260620-100000.jpg") is None

    # -- ALLPHOTOS: one header+base64 pair per photo, single trailing {"done"} --
    forwarder = bt_server.BluetoothForwarder(store=None)
    fake_sock = _FakeSocket()
    forwarder._dispatch(fake_sock, "ALLPHOTOS")

    expected_count = len(meta)
    # 2 lines per photo (header + base64) + 1 final trailer.
    assert len(fake_sock.lines) == expected_count * 2 + 1, fake_sock.lines

    for i, m in enumerate(meta):
        header = json.loads(fake_sock.lines[i * 2])
        payload = fake_sock.lines[i * 2 + 1]
        assert header["photo"] == m["name"], header
        assert header["encoding"] == "base64"
        assert header["kind"] == m["kind"]
        assert header.get("label") == m.get("label")
        assert "done" not in header  # no per-photo trailer in a batch
        raw = base64.b64decode(payload)
        assert raw == b"FAKE_REF_JPEG_BYTES" or raw.startswith(b"FAKE_JPEG_BYTES_")

    trailer = json.loads(fake_sock.lines[-1])
    assert trailer == {"done": expected_count}, trailer

    print("[test_photo_listing] All assertions passed.")


if __name__ == "__main__":
    main()
