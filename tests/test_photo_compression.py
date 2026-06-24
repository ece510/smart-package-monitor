#!/usr/bin/env python3
"""
Smart Package Monitor — photo compression unit test
ECE 510 | IIT | Team 1

Verifies that bt_server._compressed_photo_bytes() actually shrinks a
real (large) JPEG before it's sent over Bluetooth, and that it falls back
to the original bytes for a file Pillow can't decode (rather than raising).

Run from smart_package/code:
    python tests/test_photo_compression.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import offline.bt_server as bt_server  # noqa: E402

try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False


def main():
    if not _HAS_PILLOW:
        print("[test_photo_compression] Pillow not installed — skipping "
              "(fallback-path behavior is covered by test_photo_listing.py).")
        return

    tmp = tempfile.mkdtemp()

    # A large, full-resolution-style JPEG (well above SEND_MAX_WIDTH).
    big_path = os.path.join(tmp, "big.jpg")
    Image.new("RGB", (4000, 3000), color=(120, 180, 90)).save(
        big_path, format="JPEG", quality=95
    )
    original_size = os.path.getsize(big_path)

    compressed = bt_server._compressed_photo_bytes(big_path)
    assert len(compressed) < original_size, (
        f"expected compression to shrink the file: original={original_size}, "
        f"compressed={len(compressed)}"
    )

    # The re-encoded bytes must still decode, and be downscaled to <= SEND_MAX_WIDTH.
    import io
    with Image.open(io.BytesIO(compressed)) as decoded:
        assert decoded.width <= bt_server.SEND_MAX_WIDTH, decoded.width

    # A non-image file must fall back to the original bytes unchanged.
    bad_path = os.path.join(tmp, "not_an_image.jpg")
    with open(bad_path, "wb") as f:
        f.write(b"NOT_ACTUALLY_A_JPEG")
    fallback = bt_server._compressed_photo_bytes(bad_path)
    assert fallback == b"NOT_ACTUALLY_A_JPEG", fallback

    print("[test_photo_compression] All assertions passed.")


if __name__ == "__main__":
    main()
