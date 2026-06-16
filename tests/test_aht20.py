#!/usr/bin/env python3
"""
Smart Package Monitor — AHT20 temperature/humidity bring-up test
ECE 510 | IIT | Team 1

Run on the Raspberry Pi:  python3 tests/test_aht20.py

Expected behaviour:
  - Reads temperature (°C) and relative humidity (%) every 2 seconds.
  - In a normal indoor environment, expect 18–28 °C and 20–70 % RH.
  - Prints PASS if readings are within a plausible range, FAIL otherwise.
  - Press Ctrl+C to stop.

Wiring:
  AHT20 VIN → RPi Pin 1 (3.3 V)
  AHT20 GND → RPi Pin 9 (GND)
  AHT20 SDA → RPi Pin 3 (GPIO2, SDA1)
  AHT20 SCL → RPi Pin 5 (GPIO3, SCL1)
  I2C address: 0x38 (fixed)
"""

import sys
import time

DEBUG = True  # set to False to suppress verbose output

# ── I2C address and command bytes (AHT20 datasheet v1.1) ────────────────────
AHT20_ADDR     = 0x38
CMD_INIT       = [0xBE, 0x08, 0x00]   # initialization command
CMD_TRIGGER    = [0xAC, 0x33, 0x00]   # trigger measurement command
STATUS_BUSY    = 0x80   # bit 7 of status byte
STATUS_CALIB   = 0x08   # bit 3 — calibration bit must be 1

MEASURE_DELAY  = 0.08   # 80 ms — worst-case measurement time per datasheet


def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"  [DBG] {msg}")


def _parse_reading(data: list) -> tuple[float, float]:
    """Parse the 6-byte response from AHT20 into (temperature_c, humidity_pct)."""
    # Byte 0:    status byte (ignore for now)
    # Bytes 1-2: humidity raw (20 bits, top 4 bits of byte 3 are humidity LSBs)
    # Bytes 3-5: temperature raw (20 bits, bottom 4 bits of byte 3 are temp MSBs)
    raw_hum  = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4))
    raw_temp = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5])

    humidity    = (raw_hum  / 1048576.0) * 100.0          # % RH
    temperature = (raw_temp / 1048576.0) * 200.0 - 50.0   # °C

    return temperature, humidity


def main() -> None:
    try:
        import smbus2
    except ImportError:
        print("[FAIL] smbus2 is not installed. Run: pip install smbus2")
        sys.exit(1)

    bus = None
    try:
        bus = smbus2.SMBus(1)
    except Exception as exc:
        print(f"[FAIL] Cannot open I2C bus: {exc}")
        print("       Is I2C enabled? Run: sudo raspi-config -> Interface -> I2C -> Enable")
        sys.exit(1)

    print("===========================================")
    print("  AHT20 Temperature/Humidity — Bring-Up Test")
    print("===========================================")

    # Initialize the sensor
    try:
        bus.write_i2c_block_data(AHT20_ADDR, CMD_INIT[0], CMD_INIT[1:])
        _dbg(f"Sent initialization command {[hex(b) for b in CMD_INIT]}")
        time.sleep(0.01)  # 10 ms settle

        # Read status byte and verify calibration bit
        status = bus.read_byte(AHT20_ADDR)
        _dbg(f"Status byte after init: 0x{status:02X}")
        if not (status & STATUS_CALIB):
            print("[FAIL] AHT20 calibration bit is not set after init.")
            print("       The sensor may not be properly powered or is not an AHT20.")
            sys.exit(1)
        print("[PASS] AHT20 initialized and calibrated")
    except Exception as exc:
        print(f"[FAIL] Cannot communicate with AHT20 at 0x{AHT20_ADDR:02X}: {exc}")
        print("       Re-run tests/i2c_scan.sh to check if the device is visible on the bus.")
        sys.exit(1)

    print("")
    print("Reading temperature (°C) and humidity (%RH) every 2 s  [Ctrl+C to stop]")
    print("-" * 55)

    samples = 0
    passes  = 0
    try:
        while True:
            # Trigger measurement
            bus.write_i2c_block_data(AHT20_ADDR, CMD_TRIGGER[0], CMD_TRIGGER[1:])
            _dbg("Measurement triggered")

            # Wait for measurement to complete
            time.sleep(MEASURE_DELAY)

            # Poll busy bit
            for _ in range(10):
                status = bus.read_byte(AHT20_ADDR)
                if not (status & STATUS_BUSY):
                    break
                time.sleep(0.01)
            else:
                print("[WARN] AHT20 still busy after 100 ms — skipping sample")
                time.sleep(1.0)
                continue

            # Read 6 bytes of measurement data
            data = bus.read_i2c_block_data(AHT20_ADDR, 0x00, 6)
            _dbg(f"Raw bytes: {[hex(b) for b in data]}")

            temp_c, hum_pct = _parse_reading(data)
            samples += 1

            # Plausibility check for indoor environment
            if -10.0 <= temp_c <= 60.0 and 0.0 <= hum_pct <= 100.0:
                status_str = "PASS"
                passes += 1
            else:
                status_str = "WARN (out of plausible range)"

            print(f"  [{status_str}]  Temperature: {temp_c:.2f} °C   Humidity: {hum_pct:.2f} %RH")
            time.sleep(2.0 - MEASURE_DELAY)   # maintain ~2 s interval

    except KeyboardInterrupt:
        print("-" * 55)
        print(f"\nStopped after {samples} samples.  {passes}/{samples} within plausible range.")
        if passes == samples and samples > 0:
            print("[PASS] AHT20 test complete.")
        elif samples == 0:
            print("[WARN] No samples collected before interruption.")
        else:
            print("[WARN] Some readings were out of expected range.")
    finally:
        if bus:
            bus.close()


if __name__ == "__main__":
    main()
