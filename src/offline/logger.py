#!/usr/bin/env python3
"""
Smart Package Monitor — Offline Logger
ECE 510 | IIT | Team 1

Background thread that bridges SensorMonitor -> ReadingStore: every poll
interval it reads the latest sensor status and writes one row to the
SQLite buffer, so readings survive even with no network connection.
"""

import time
import threading

POLL_INTERVAL = 2.0  # seconds — matches SensorMonitor.POLL_INTERVAL


class OfflineLogger:
    """
    Runs a daemon thread that periodically copies SensorMonitor's latest
    reading + alert status into a ReadingStore.
    """

    def __init__(self, sensor_monitor, store, poll_interval: float = POLL_INTERVAL):
        self._sensor_monitor = sensor_monitor
        self._store = store
        self._poll_interval = poll_interval
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[OfflineLogger] Started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[OfflineLogger] Stopped.")

    def _loop(self):
        while self._running:
            readings, alert, reasons = self._sensor_monitor.get_status()
            if readings:
                self._store.add_reading(readings, is_alert=alert, reasons=reasons)
            time.sleep(self._poll_interval)
