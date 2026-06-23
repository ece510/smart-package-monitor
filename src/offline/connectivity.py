#!/usr/bin/env python3
"""
Smart Package Monitor — Connectivity Check
ECE 510 | IIT | Team 1

Small helper to detect whether the Raspberry Pi currently has a network
link. Kept separate from store.py/bt_server.py so a future cloud or
dashboard uploader (teammate's task) can reuse the same check to decide
when to push data online instead of waiting for a Bluetooth pickup.
"""

import socket

DEFAULT_HOST = "8.8.8.8"  # Google public DNS — reachable on any working link
DEFAULT_PORT = 53
DEFAULT_TIMEOUT = 2.0


def is_online(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
              timeout: float = DEFAULT_TIMEOUT) -> bool:
    """
    Return True if a TCP connection to (host, port) succeeds within
    `timeout` seconds. Used as a cheap "do we have a network path right
    now" check — not a guarantee that any particular service is reachable.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
