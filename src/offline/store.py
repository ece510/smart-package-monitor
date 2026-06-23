#!/usr/bin/env python3
"""
Smart Package Monitor — Offline Reading Store
ECE 510 | IIT | Team 1

SQLite-backed buffer for sensor readings and alert events. Used when the
Raspberry Pi has no network connection: readings pile up here until a
nearby device connects over Bluetooth (see bt_server.py) and pulls them.
"""

import sqlite3
import threading
from datetime import datetime, timezone

DEFAULT_DB_PATH = "spm_buffer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,
    accel_x_g    REAL,
    accel_y_g    REAL,
    accel_z_g    REAL,
    temp_c       REAL,
    hum_pct      REAL,
    is_alert     INTEGER NOT NULL DEFAULT 0,
    alert_reason TEXT,
    synced       INTEGER NOT NULL DEFAULT 0
);
"""

INDEX = "CREATE INDEX IF NOT EXISTS idx_unsynced ON readings(synced);"


class ReadingStore:
    """
    Thread-safe SQLite buffer of sensor readings / alert events.

    One writer (OfflineLogger, on the sensor-polling thread) and one
    reader (BluetoothForwarder, on the BT accept thread) share the same
    connection, so all access goes through self._lock.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(SCHEMA)
            self._conn.execute(INDEX)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    # ── Writing ──────────────────────────────────────────────────────────────

    def add_reading(self, readings: dict, is_alert: bool = False, reasons=None) -> int:
        """
        Insert one row. `readings` may be a partial dict (any of
        accel_x_g/accel_y_g/accel_z_g/temp_c/hum_pct) or empty (e.g. a
        vision-only "CV" alert with no sensor values attached).
        Returns the new row id.
        """
        reasons = reasons or []
        ts = datetime.now(timezone.utc).isoformat()
        alert_reason = ",".join(reasons) if reasons else None

        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO readings
                    (ts, accel_x_g, accel_y_g, accel_z_g, temp_c, hum_pct,
                     is_alert, alert_reason, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    ts,
                    readings.get("accel_x_g"),
                    readings.get("accel_y_g"),
                    readings.get("accel_z_g"),
                    readings.get("temp_c"),
                    readings.get("hum_pct"),
                    1 if is_alert else 0,
                    alert_reason,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    # ── Reading ──────────────────────────────────────────────────────────────

    def fetch_unsynced(self, limit: int = None) -> list:
        query = "SELECT * FROM readings WHERE synced = 0 ORDER BY id ASC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        with self._lock:
            return self._conn.execute(query).fetchall()

    def fetch_all(self) -> list:
        with self._lock:
            return self._conn.execute("SELECT * FROM readings ORDER BY id ASC").fetchall()

    def mark_synced(self, ids: list) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            self._conn.execute(
                f"UPDATE readings SET synced = 1 WHERE id IN ({placeholders})", ids
            )
            self._conn.commit()

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            pending = self._conn.execute(
                "SELECT COUNT(*) FROM readings WHERE synced = 0"
            ).fetchone()[0]
        return {"total": total, "pending": pending}

    def purge_synced(self) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM readings WHERE synced = 1")
            self._conn.commit()
            return cur.rowcount
