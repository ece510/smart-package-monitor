#!/usr/bin/env python3
"""
Smart Package Monitor — OfflineLogger unit test
ECE 510 | IIT | Team 1

Pure-SQLite test for the sensor-to-store bridge thread. Uses a fake
SensorMonitor stub (no I2C, no Bluetooth, no Raspberry Pi needed) so it
runs anywhere, the same way test_store.py does.

Run from smart_package/code:
    python tests/test_offline_logger.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from offline.store import ReadingStore  # noqa: E402
from offline.logger import OfflineLogger  # noqa: E402

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "_test_spm_logger.db")

POLL_INTERVAL = 0.05  # fast poll so the test doesn't have to sleep long


class FakeSensorMonitor:
    """Stands in for sensors.SensorMonitor: returns whatever get_status()
    is told to, instead of reading real I2C hardware."""

    def __init__(self):
        self._status = ({}, False, [])

    def set_status(self, readings: dict, alert: bool, reasons: list):
        self._status = (readings, alert, reasons)

    def get_status(self) -> tuple:
        readings, alert, reasons = self._status
        return dict(readings), alert, list(reasons)


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def main():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    store = ReadingStore(TEST_DB_PATH)
    sensor_monitor = FakeSensorMonitor()
    logger = OfflineLogger(sensor_monitor, store, poll_interval=POLL_INTERVAL)

    # -- empty readings ({}) must NOT be written --
    sensor_monitor.set_status({}, False, [])
    logger.start()
    time.sleep(POLL_INTERVAL * 4)
    assert store.stats()["total"] == 0, \
        f"expected no rows while readings are empty, got {store.stats()}"

    # -- a normal (non-alert) reading gets logged --
    sensor_monitor.set_status({"accel_x_g": 0.01, "temp_c": 22.0}, False, [])
    ok = _wait_until(lambda: store.stats()["total"] >= 1)
    assert ok, "OfflineLogger did not write the first reading in time"

    row = store.fetch_all()[0]
    assert row["accel_x_g"] == 0.01
    assert row["temp_c"] == 22.0
    assert row["is_alert"] == 0
    assert row["alert_reason"] is None

    # -- an alert reading with reasons gets logged with alert flag set --
    sensor_monitor.set_status({"accel_x_g": 0.9}, True, ["ACCEL"])
    ok = _wait_until(lambda: store.stats()["total"] >= 2)
    assert ok, "OfflineLogger did not write the alert reading in time"

    alert_row = store.fetch_all()[1]
    assert alert_row["is_alert"] == 1
    assert alert_row["alert_reason"] == "ACCEL"

    logger.stop()
    store.close()
    os.remove(TEST_DB_PATH)

    print("[test_offline_logger] All assertions passed.")


if __name__ == "__main__":
    main()
