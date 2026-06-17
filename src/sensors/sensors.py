#!/usr/bin/env python3
"""
Smart Package Monitor — Sensor Monitor
ECE 510 | IIT | Team 1

Reads ADXL345 (accelerometer) and AHT20 (temp/humidity) over I2C.
Triggers SENSOR_ALERT state if any value exceeds safe thresholds.
"""

import time
import threading

try:
    import smbus2
except ImportError:
    smbus2 = None

# ── ADXL345 constants (from test_adxl345.py) ────────────────────────────────
ADXL345_ADDR    = 0x53
REG_POWER_CTL   = 0x2D
REG_DATAX0      = 0x32
SCALE_FACTOR    = 1.0 / 256.0

# ── AHT20 constants (from test_aht20.py) ────────────────────────────────────
AHT20_ADDR      = 0x38
CMD_INIT        = [0xBE, 0x08, 0x00]
CMD_TRIGGER     = [0xAC, 0x33, 0x00]
STATUS_BUSY     = 0x80
STATUS_CALIB    = 0x08
MEASURE_DELAY   = 0.08

# ── Alert thresholds ─────────────────────────────────────────────────────────
# Accelerometer: flag if any axis exceeds ±2.5 g (movement/shock)
ACCEL_G_LIMIT   = 0.5

# Temperature: flag outside 0–60 °C
TEMP_MIN_C      = 0.0
TEMP_MAX_C      = 60.0

# Humidity: flag outside 0–100 % (also catches sensor errors)
HUM_MIN_PCT     = 0.0
HUM_MAX_PCT     = 100.0

# ── Polling interval ─────────────────────────────────────────────────────────
POLL_INTERVAL   = 2.0   # seconds


def _parse_aht20(data: list) -> tuple:
    raw_hum  = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4))
    raw_temp = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5])
    humidity    = (raw_hum  / 1048576.0) * 100.0
    temperature = (raw_temp / 1048576.0) * 200.0 - 50.0
    return temperature, humidity


class SensorMonitor:
    """
    Runs a background thread that polls ADXL345 and AHT20.
    Sets self.sensor_alert = True when any reading is out of range.
    Thread-safe via self._lock.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self.sensor_alert = False      # True → main.py should trigger Yellow LED
        self.last_readings = {}        # latest sensor values for logging/web
        self._running    = False
        self._thread     = None
        self._bus        = None

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self):
        if smbus2 is None:
            print("[SensorMonitor] smbus2 not installed — sensor monitoring disabled.")
            return
        try:
            self._bus = smbus2.SMBus(1)
        except Exception as e:
            print(f"[SensorMonitor] Cannot open I2C bus: {e}")
            return

        self._init_adxl345()
        self._init_aht20()

        self._running = True
        self._thread  = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print("[SensorMonitor] Started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._bus:
            self._bus.close()
        print("[SensorMonitor] Stopped.")

    def is_alert(self) -> bool:
        with self._lock:
            return self.sensor_alert

    def get_readings(self) -> dict:
        with self._lock:
            return dict(self.last_readings)

    # ── Initialisation helpers ───────────────────────────────────────────────

    def _init_adxl345(self):
        try:
            self._bus.write_byte_data(ADXL345_ADDR, REG_POWER_CTL, 0x08)
            print("[SensorMonitor] ADXL345 initialised.")
        except Exception as e:
            print(f"[SensorMonitor] ADXL345 init failed: {e}")

    def _init_aht20(self):
        try:
            self._bus.write_i2c_block_data(AHT20_ADDR, CMD_INIT[0], CMD_INIT[1:])
            time.sleep(0.01)
            status = self._bus.read_byte(AHT20_ADDR)
            if not (status & STATUS_CALIB):
                print("[SensorMonitor] AHT20 calibration bit not set — check wiring.")
            else:
                print("[SensorMonitor] AHT20 initialised.")
        except Exception as e:
            print(f"[SensorMonitor] AHT20 init failed: {e}")

    # ── Polling loop ─────────────────────────────────────────────────────────

    def _poll_loop(self):
        while self._running:
            alert = False
            readings = {}

            # -- ADXL345 read --
            try:
                data  = self._bus.read_i2c_block_data(ADXL345_ADDR, REG_DATAX0, 6)
                raw_x = (data[1] << 8) | data[0]
                raw_y = (data[3] << 8) | data[2]
                raw_z = (data[5] << 8) | data[4]
                if raw_x > 32767: raw_x -= 65536
                if raw_y > 32767: raw_y -= 65536
                if raw_z > 32767: raw_z -= 65536

                x_g = raw_x * SCALE_FACTOR
                y_g = raw_y * SCALE_FACTOR
                z_g = raw_z * SCALE_FACTOR

                readings["accel_x_g"] = round(x_g, 3)
                readings["accel_y_g"] = round(y_g, 3)
                readings["accel_z_g"] = round(z_g, 3)

                print(f"[ACCEL] X={x_g:+.3f}g  Y={y_g:+.3f}g  Z={z_g:+.3f}g")

                if abs(x_g) > ACCEL_G_LIMIT or abs(y_g) > ACCEL_G_LIMIT or abs(z_g) > ACCEL_G_LIMIT:
                    print(f"[SensorMonitor] ACCEL ALERT: X={x_g:+.3f} Y={y_g:+.3f} Z={z_g:+.3f} g")
                    alert = True

            except Exception as e:
                print(f"[SensorMonitor] ADXL345 read error: {e}")

            # -- AHT20 read --
            try:
                self._bus.write_i2c_block_data(AHT20_ADDR, CMD_TRIGGER[0], CMD_TRIGGER[1:])
                time.sleep(MEASURE_DELAY)

                for _ in range(10):
                    status = self._bus.read_byte(AHT20_ADDR)
                    if not (status & STATUS_BUSY):
                        break
                    time.sleep(0.01)

                data = self._bus.read_i2c_block_data(AHT20_ADDR, 0x00, 6)
                temp_c, hum_pct = _parse_aht20(data)

                readings["temp_c"]  = round(temp_c, 2)
                readings["hum_pct"] = round(hum_pct, 2)

                if not (TEMP_MIN_C <= temp_c <= TEMP_MAX_C):
                    print(f"[SensorMonitor] TEMP ALERT: {temp_c:.2f} °C (limit {TEMP_MIN_C}–{TEMP_MAX_C} °C)")
                    alert = True

                if not (HUM_MIN_PCT <= hum_pct <= HUM_MAX_PCT):
                    print(f"[SensorMonitor] HUMIDITY ALERT: {hum_pct:.2f} % (limit {HUM_MIN_PCT}–{HUM_MAX_PCT} %)")
                    alert = True

            except Exception as e:
                print(f"[SensorMonitor] AHT20 read error: {e}")

            # -- Update shared state --
            with self._lock:
                self.sensor_alert  = alert
                self.last_readings = readings

            time.sleep(POLL_INTERVAL)