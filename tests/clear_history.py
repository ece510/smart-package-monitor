#!/usr/bin/env python3
"""
Smart Package Monitor — standalone history wipe
ECE 510 | IIT | Team 1

Wipes every row from the offline SQLite buffer directly, without needing
the app, Bluetooth, or main.py running. Safe to run while main.py is up
too (SQLite handles the extra connection; a single DELETE is fast enough
that brief lock contention is a non-issue).

Useful when the app's Bluetooth RESET command can't complete (e.g. a
dropped/overlapping connection) and leaves stale rows behind — this bypasses
Bluetooth entirely, so it always succeeds.

Run from smart_package/code:
    python3 tests/clear_history.py [path-to-db]

Defaults to "spm_buffer.db" relative to the current directory — the same
relative path main.py uses, so run this from the same directory you run
`python3 src/main.py` from (typically ~/smart-package-monitor).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from offline.store import ReadingStore  # noqa: E402


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "spm_buffer.db"
    store = ReadingStore(db_path)
    cleared = store.purge_all()
    print(f"Cleared {cleared} row(s) from '{db_path}'.")
    print(f"Stats now: {store.stats()}")
    store.close()


if __name__ == "__main__":
    main()
