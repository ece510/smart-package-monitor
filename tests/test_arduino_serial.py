#!/usr/bin/env python3
"""
Smart Package Monitor — Arduino indicator controller bring-up test
ECE 510 | IIT | Team 1

Run on the Raspberry Pi:  python3 tests/test_arduino_serial.py

Expected behaviour:
  - Connects to the Arduino at /dev/ttyACM0 (9600 baud).
  - Sends a demo sequence: G, Y, R (LEDs), W/w (white LED), then 0-3 (7-seg).
  - Pauses between each command so the effect is visible.
  - Prints PASS if all writes succeed with no serial error.

Requirements:
  - Flash indicator_controller.ino to the Arduino FIRST using Arduino IDE.
  - Port: /dev/ttyACM0 (or ttyACM1 if another USB-serial device is present).
  - Board: Arduino Uno

Wiring:
  Arduino Uno USB-B → any USB-A port on the Raspberry Pi.
"""

import sys
import time

DEBUG = True  # set to False for quieter output

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE   = 9600
PAUSE       = 1.0   # seconds between commands (visible LED changes)


def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"  [DBG] {msg}")


DEMO_SEQUENCE = [
    # (command_byte, description)
    (b'X', "All indicators OFF"),
    (b'G', "Green  LED → ON  (package OK)"),
    (b'Y', "Yellow LED → ON  (WARNING)"),
    (b'R', "Red    LED → ON  (CRITICAL)"),
    (b'W', "White  LED → ON  (CV illumination)"),
    (b'w', "White  LED → OFF"),
    (b'0', "7-seg  → digit 0  (alert count)"),
    (b'1', "7-seg  → digit 1"),
    (b'2', "7-seg  → digit 2"),
    (b'3', "7-seg  → digit 3"),
    (b'X', "All indicators OFF — test done"),
]


def main() -> None:
    try:
        import serial
    except ImportError:
        print("[FAIL] pyserial is not installed. Run: pip install pyserial")
        sys.exit(1)

    print("===========================================")
    print("  Arduino Serial — Indicator Bring-Up Test")
    print("===========================================")
    print("")

    # Open serial connection
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        _dbg(f"Opened {SERIAL_PORT} at {BAUD_RATE} baud")
    except serial.SerialException as exc:
        print(f"[FAIL] Cannot open {SERIAL_PORT}: {exc}")
        print("       • Is the Arduino plugged in via USB-B cable?")
        print("       • Run: ls /dev/ttyACM*  to see available ports.")
        print(f"       • Change SERIAL_PORT at the top of this script if needed.")
        print("       • Is indicator_controller.ino flashed on the Arduino?")
        sys.exit(1)

    # Arduino resets on serial open — wait for boot message
    _dbg("Waiting 2 s for Arduino to reset and boot...")
    time.sleep(2.0)

    # Read and display the Arduino boot message if available
    if ser.in_waiting:
        boot_msg = ser.readline().decode("utf-8", errors="replace").strip()
        _dbg(f"Arduino says: {boot_msg}")

    print("Starting demo sequence. Watch the LEDs on the Arduino.\n")
    print(f"  {'Command':<8} {'Action'}")
    print(f"  {'-'*7}  {'-'*40}")

    errors = 0
    for cmd_byte, description in DEMO_SEQUENCE:
        try:
            written = ser.write(cmd_byte)
            if written != 1:
                print(f"  [{cmd_byte.decode():<6}]  WARN — expected to write 1 byte, wrote {written}")
                errors += 1
            else:
                print(f"  [{cmd_byte.decode():<6}]  {description}")
        except serial.SerialException as exc:
            print(f"  [{cmd_byte.decode():<6}]  FAIL — serial error: {exc}")
            errors += 1
        time.sleep(PAUSE)

    ser.close()
    print("")
    print("-" * 50)
    if errors == 0:
        print("[PASS] All serial commands sent successfully.")
        print("       If the LEDs and display changed as expected, the Arduino firmware")
        print("       and wiring are correct.")
    else:
        print(f"[FAIL] {errors} command(s) had errors. Check connections and firmware.")
    print("===========================================")


if __name__ == "__main__":
    main()
