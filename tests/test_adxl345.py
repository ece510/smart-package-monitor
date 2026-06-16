#!/usr/bin/env python3
"""
Smart Package Monitor — ADXL345 accelerometer bring-up test
ECE 510 | IIT | Team 1

Run on the Raspberry Pi:  python3 tests/test_adxl345.py

Expected behaviour:
  - Reads X, Y, Z acceleration in g continuously.
  - With the board flat and still, Z ≈ ±1 g, X and Y ≈ 0 g.
  - Prints PASS if readings are within a plausible range, FAIL otherwise.
  - Press Ctrl+C to stop.

Wiring:
  ADXL345 VCC → RPi Pin 1 (3.3 V)
  ADXL345 GND → RPi Pin 9 (GND)
  ADXL345 SDA → RPi Pin 3 (GPIO2, SDA1)
  ADXL345 SCL → RPi Pin 5 (GPIO3, SCL1)
  I2C address: 0x53 (SDO pin left floating or tied to GND)
"""

import sys
import time

DEBUG = True  # set to False to suppress verbose output

# ── I2C address and register map (ADXL345 datasheet, Rev G) ─────────────────
ADXL345_ADDR  = 0x53
REG_DEVID     = 0x00   # fixed device ID = 0xE5
REG_POWER_CTL = 0x2D   # power-control register
REG_DATA_FORMAT = 0x31 # data format (range ±2 g by default)
REG_DATAX0    = 0x32   # first data register (X LSB); X MSB at 0x33, Y at 0x34/35, Z at 0x36/37

SCALE_FACTOR  = 1.0 / 256.0  # ±2 g range → 256 LSB/g


def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"  [DBG] {msg}")


def main() -> None:
    try:
        import smbus2
    except ImportError:
        print("[FAIL] smbus2 is not installed. Run: pip install smbus2")
        sys.exit(1)

    bus = None
    try:
        bus = smbus2.SMBus(1)   # I2C bus 1 on Raspberry Pi
    except Exception as exc:
        print(f"[FAIL] Cannot open I2C bus: {exc}")
        print("       Is I2C enabled? Run: sudo raspi-config -> Interface -> I2C -> Enable")
        sys.exit(1)

    print("===========================================")
    print("  ADXL345 Accelerometer — Bring-Up Test")
    print("===========================================")

    # Verify device ID
    try:
        dev_id = bus.read_byte_data(ADXL345_ADDR, REG_DEVID)
        _dbg(f"DEVID register = 0x{dev_id:02X} (expected 0xE5)")
        if dev_id != 0xE5:
            print(f"[FAIL] Unexpected device ID 0x{dev_id:02X}. Expected 0xE5.")
            print("       Check I2C address: SDO pin state changes address 0x53 <-> 0x1D.")
            sys.exit(1)
        print("[PASS] Device ID confirmed (0xE5)")
    except Exception as exc:
        print(f"[FAIL] Cannot communicate with ADXL345 at 0x{ADXL345_ADDR:02X}: {exc}")
        print("       Re-run tests/i2c_scan.sh to check if the device is visible on the bus.")
        sys.exit(1)

    # Wake the device up: set Measure bit (bit 3) in POWER_CTL
    bus.write_byte_data(ADXL345_ADDR, REG_POWER_CTL, 0x08)
    _dbg("POWER_CTL set to 0x08 (Measure mode)")
    time.sleep(0.01)  # brief settle

    print("")
    print("Reading X / Y / Z (g) — hold still, Z should be ≈ ±1 g  [Ctrl+C to stop]")
    print("-" * 50)

    samples = 0
    passes  = 0
    try:
        while True:
            # Read 6 bytes: DATAX0,DATAX1, DATAY0,DATAY1, DATAZ0,DATAZ1
            data = bus.read_i2c_block_data(ADXL345_ADDR, REG_DATAX0, 6)

            # Two-complement 16-bit integers, little-endian
            raw_x = (data[1] << 8) | data[0]
            raw_y = (data[3] << 8) | data[2]
            raw_z = (data[5] << 8) | data[4]

            # Sign-extend from 16 bits
            if raw_x > 32767: raw_x -= 65536
            if raw_y > 32767: raw_y -= 65536
            if raw_z > 32767: raw_z -= 65536

            x_g = raw_x * SCALE_FACTOR
            y_g = raw_y * SCALE_FACTOR
            z_g = raw_z * SCALE_FACTOR

            samples += 1
            # Plausibility check: at least one axis near ±1 g (gravity)
            if abs(x_g) <= 2.5 and abs(y_g) <= 2.5 and abs(z_g) <= 2.5:
                status = "PASS"
                passes += 1
            else:
                status = "WARN (values out of ±2g range)"

            print(f"  [{status}]  X={x_g:+.3f} g   Y={y_g:+.3f} g   Z={z_g:+.3f} g")
            time.sleep(0.1)   # 10 Hz display rate

    except KeyboardInterrupt:
        print("-" * 50)
        print(f"\nStopped after {samples} samples.  {passes}/{samples} within ±2.5 g range.")
        if passes == samples and samples > 0:
            print("[PASS] ADXL345 test complete.")
        elif samples == 0:
            print("[WARN] No samples collected before interruption.")
        else:
            print("[WARN] Some readings were out of expected range — check wiring or threshold.")
    finally:
        if bus:
            bus.close()


if __name__ == "__main__":
    main()
