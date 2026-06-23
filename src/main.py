import sys
import time
import threading
import subprocess
from sensors.sensors import SensorMonitor
from offline.store import ReadingStore
from offline.logger import OfflineLogger
from offline.bt_server import BluetoothForwarder


# Sensor Monitor
sensor_monitor = SensorMonitor()

# Offline store-and-forward: buffers readings/alerts in SQLite and serves
# them over Bluetooth (RFCOMM/SPP) to a nearby device when the Pi has no
# network connection. See src/offline/ for details.
reading_store = ReadingStore()
offline_logger = OfflineLogger(sensor_monitor, reading_store)
bt_forwarder = BluetoothForwarder(reading_store)

# Thread-safe state variables
state_lock = threading.Lock()
current_state = "INIT"  # States: INIT, NORMAL, ALARM, SENSOR_ALERT, SHUTDOWN
is_running = True


def main():
    global current_state, is_running

    print("===========================================")
    print("  Smart Package Monitor - Master Controller")
    print("===========================================")
    sensor_monitor.start()
    offline_logger.start()
    bt_forwarder.start()

    print("[Main] Launching box_surveillance.py...")

    try:
        # Run the surveillance script unbuffered (-u) so we can read outputs instantly
        process = subprocess.Popen(
            ["python3", "-u", "/home/ece510/smart-package-monitor/src/vision/box_surveillance.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                print(f"> {line}") # Echo script output to terminal

                # Parse output to determine system state (drives the dashboard)
                if "Starting surveillance loop..." in line:
                    with state_lock:
                        current_state = "NORMAL"

                elif "TRIGGER:" in line or "ALARM:" in line:
                    with state_lock:
                        current_state = "ALARM"
                    # Record the vision alert so it survives an offline period
                    reading_store.add_reading({}, is_alert=True, reasons=["CV"])

                elif "Recovery successful!" in line:
                    with state_lock:
                        current_state = "NORMAL"

                elif "shutting down system" in line:
                    with state_lock:
                        current_state = "SHUTDOWN"


            # Check sensor state (only escalate to SENSOR_ALERT if not already in ALARM/SHUTDOWN)
            with state_lock:
                cs = current_state
            if cs not in ("ALARM", "SHUTDOWN"):
                if sensor_monitor.is_alert():
                    with state_lock:
                        current_state = "SENSOR_ALERT"
                elif cs == "SENSOR_ALERT":
                    # sensors recovered — go back to NORMAL
                    with state_lock:
                        current_state = "NORMAL"

    except KeyboardInterrupt:
        print("[Main] Caught keyboard interrupt. Stopping system...")
    finally:
        with state_lock:
            is_running = False
        bt_forwarder.stop()
        offline_logger.stop()
        sensor_monitor.stop()
        print("[Main] Exited cleanly.")

if __name__ == "__main__":
    main()
