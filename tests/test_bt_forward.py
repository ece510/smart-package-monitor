#!/usr/bin/env python3
"""
Smart Package Monitor — Bluetooth forwarder bring-up script
ECE 510 | IIT | Team 1

Manual bring-up test, run ON THE RASPBERRY PI (needs pybluez2 + BlueZ).
Seeds the offline store with a few sample rows, starts the
BluetoothForwarder, and waits for a nearby device to connect and pull
them.

Run from smart_package/code, on the Pi:
    python3 tests/test_bt_forward.py

Then, on a phone:
  1. Pair the phone with the Pi via bluetoothctl (power on, agent on,
     discoverable on, pairable on, scan on, pair <phone MAC>).
  2. Open a "Serial Bluetooth Terminal" style app and connect to the Pi
     ("SmartPackageMonitor-Offline" service).
  3. Send: STATUS   -> see {"pending": 3, "total": 3}
  4. Send: SYNC     -> receive the 3 buffered rows as JSON lines, then
                       {"done": 3}.
  5. Send: STATUS   -> {"pending": 0, "total": 3}  (rows now marked synced)
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from offline.store import ReadingStore  # noqa: E402
from offline.bt_server import BluetoothForwarder  # noqa: E402

SEED_DB_PATH = os.path.join(os.path.dirname(__file__), "_bringup_spm_buffer.db")


def seed(store: ReadingStore):
    store.add_reading(
        {"accel_x_g": 0.02, "accel_y_g": -0.01, "accel_z_g": 0.98,
         "temp_c": 21.4, "hum_pct": 38.2},
        is_alert=False,
    )
    store.add_reading(
        {"accel_x_g": 0.85, "accel_y_g": 0.02, "accel_z_g": 1.10,
         "temp_c": 22.0, "hum_pct": 40.0},
        is_alert=True,
        reasons=["ACCEL"],
    )
    store.add_reading({}, is_alert=True, reasons=["CV"])


def main():
    if os.path.exists(SEED_DB_PATH):
        os.remove(SEED_DB_PATH)

    store = ReadingStore(SEED_DB_PATH)
    seed(store)
    print(f"[bring-up] Seeded {store.stats()['total']} rows into {SEED_DB_PATH}")

    forwarder = BluetoothForwarder(store)
    forwarder.start()

    print("[bring-up] Pair a phone with this Pi, connect to "
          "'SmartPackageMonitor-Offline', and send STATUS / SYNC / ALL / CLEAR.")
    print("[bring-up] Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(5)
            print(f"[bring-up] store stats: {store.stats()}")
    except KeyboardInterrupt:
        pass
    finally:
        forwarder.stop()
        store.close()


if __name__ == "__main__":
    main()
