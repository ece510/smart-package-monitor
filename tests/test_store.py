#!/usr/bin/env python3
"""
Smart Package Monitor — ReadingStore unit test
ECE 510 | IIT | Team 1

Pure-SQLite test for the offline buffer. Runs anywhere (no I2C, no
Bluetooth, no Raspberry Pi needed) — useful for developing on a laptop
before deploying to the Pi.

Run from smart_package/code:
    python tests/test_store.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from offline.store import ReadingStore  # noqa: E402

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "_test_spm_buffer.db")


def main():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    store = ReadingStore(TEST_DB_PATH)

    # -- add_reading: normal reading, no alert --
    id1 = store.add_reading(
        {"accel_x_g": 0.01, "accel_y_g": -0.02, "accel_z_g": 1.0,
         "temp_c": 22.5, "hum_pct": 45.0},
        is_alert=False,
    )
    assert id1 == 1, f"expected first row id 1, got {id1}"

    # -- add_reading: alert reading with reasons --
    id2 = store.add_reading(
        {"accel_x_g": 0.9, "temp_c": 70.0},
        is_alert=True,
        reasons=["ACCEL", "TEMP"],
    )
    assert id2 == 2, f"expected second row id 2, got {id2}"

    # -- add_reading: vision-only alert, no sensor values --
    id3 = store.add_reading({}, is_alert=True, reasons=["CV"])
    assert id3 == 3

    stats = store.stats()
    assert stats == {"total": 3, "pending": 3}, f"unexpected stats: {stats}"

    # -- fetch_unsynced returns all 3, in order --
    unsynced = store.fetch_unsynced()
    assert [r["id"] for r in unsynced] == [1, 2, 3]
    assert unsynced[1]["alert_reason"] == "ACCEL,TEMP"
    assert unsynced[2]["is_alert"] == 1
    assert unsynced[2]["accel_x_g"] is None  # CV alert has no sensor values

    # -- mark_synced removes rows from the unsynced set --
    store.mark_synced([1, 2])
    stats = store.stats()
    assert stats == {"total": 3, "pending": 1}, f"unexpected stats after sync: {stats}"

    remaining = store.fetch_unsynced()
    assert [r["id"] for r in remaining] == [3]

    # -- fetch_all still returns everything regardless of synced flag --
    all_rows = store.fetch_all()
    assert len(all_rows) == 3

    # -- purge_synced deletes the 2 synced rows, leaves the 1 pending row --
    cleared = store.purge_synced()
    assert cleared == 2, f"expected 2 purged rows, got {cleared}"
    assert store.stats() == {"total": 1, "pending": 1}

    # -- purge_all deletes everything, synced or not (used by BT RESET) --
    cleared_all = store.purge_all()
    assert cleared_all == 1, f"expected 1 purged row, got {cleared_all}"
    assert store.stats() == {"total": 0, "pending": 0}

    store.close()
    os.remove(TEST_DB_PATH)

    print("[test_store] All assertions passed.")


if __name__ == "__main__":
    main()
