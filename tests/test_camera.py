#!/usr/bin/env python3
"""
Smart Package Monitor — USB camera bring-up test (Logitech Brio 105)
ECE 510 | IIT | Team 1

Run on the Raspberry Pi:  python3 tests/test_camera.py

Expected behaviour:
  - Opens /dev/video0 at 640×480 (fast preview mode).
  - Discards a few warm-up frames, then captures one frame.
  - Saves it to captures/camera_test_<timestamp>.jpg and prints PASS.
  - Fails clearly if the camera is not found or the frame is empty.

Wiring:
  Logitech Brio 105 → any USB-A port on the Raspberry Pi.
  Enumerates as /dev/video0 (or video1 if something else is plugged first).
"""

import os
import sys
import time
from datetime import datetime

DEBUG = True

CAMERA_INDEX  = 0           # try 1 if FAIL and another device is on /dev/video0
WARMUP_FRAMES = 5           # frames to discard before capturing (exposure settle)
CAPTURE_DIR   = "captures"  # relative to the repo root
CAPTURE_W     = 640
CAPTURE_H     = 480


def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"  [DBG] {msg}")


def main() -> None:
    try:
        import cv2
    except ImportError:
        print("[FAIL] opencv-python is not installed. Run: pip install opencv-python")
        sys.exit(1)

    print("===========================================")
    print("  Camera Capture — Bring-Up Test")
    print("===========================================")

    # Ensure output directory exists
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    _dbg(f"Output directory: {os.path.abspath(CAPTURE_DIR)}")

    # Open camera
    _dbg(f"Opening VideoCapture({CAMERA_INDEX})")
    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        print(f"[FAIL] Cannot open camera at index {CAMERA_INDEX}.")
        print("       • Is the Logitech Brio 105 plugged into a USB port?")
        print("       • Try: ls /dev/video*  to see available devices.")
        print(f"       • Change CAMERA_INDEX at the top of this script if needed.")
        sys.exit(1)

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    _dbg(f"Camera opened. Resolution: {actual_w}×{actual_h}")

    # Discard warm-up frames so auto-exposure settles
    _dbg(f"Discarding {WARMUP_FRAMES} warm-up frames...")
    for i in range(WARMUP_FRAMES):
        ret, _ = cap.read()
        if not ret:
            print(f"[FAIL] Camera failed to return a frame during warm-up (frame {i+1}).")
            cap.release()
            sys.exit(1)
        time.sleep(0.05)

    # Capture the real frame
    _dbg("Capturing frame...")
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None or frame.size == 0:
        print("[FAIL] Captured frame is empty or invalid.")
        print("       Check that the camera lens is not covered.")
        sys.exit(1)

    # Save to disk
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = os.path.join(CAPTURE_DIR, f"camera_test_{timestamp}.jpg")
    success    = cv2.imwrite(filename, frame)

    if not success:
        print(f"[FAIL] Failed to write image to {filename}.")
        sys.exit(1)

    h, w = frame.shape[:2]
    file_size_kb = os.path.getsize(filename) / 1024

    print(f"[PASS] Frame captured: {w}×{h} pixels")
    print(f"[PASS] Saved to: {os.path.abspath(filename)}  ({file_size_kb:.1f} KB)")
    print("")
    print("Transfer the image to your laptop to verify it looks sharp:")
    print(f"  scp pi@<PI_IP>:{os.path.abspath(filename)} .")


if __name__ == "__main__":
    main()
