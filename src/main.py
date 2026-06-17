import sys
import time
import threading
import subprocess
from sensors.sensors import SensorMonitor


try:
    import serial
except ImportError:
    print("Error: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)

# Arduino Configuration
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

# Sensor Monitor
sensor_monitor = SensorMonitor()

# Thread-safe state variables
state_lock = threading.Lock()
current_state = "INIT"  # States: INIT, NORMAL, ALARM, SHUTDOWN
is_running = True

def arduino_thread():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        print(f"[Arduino] Connected to {SERIAL_PORT}")
        time.sleep(2) # Wait for Arduino to reboot upon serial connection
    except Exception as e:
        print(f"[Arduino Error] Could not connect: {e}")
        return

    # Ensure white LED is ON initially
    ser.write(b'X')
    ser.write(b'W')

    last_state = None

    while True:
        with state_lock:
            state = current_state
            running = is_running

        if not running:
            # Turn everything off before exit
            ser.write(b'X')
            ser.write(b'w')
            ser.close()
            break

        if state == "INIT":
            if last_state != "INIT":
                ser.write(b'X')
                ser.write(b'W')
                last_state = "INIT"
            time.sleep(0.1)

        elif state == "NORMAL":
            if last_state != "NORMAL":
                ser.write(b'X')
                ser.write(b'W')
                ser.write(b'G') # Green ON
                last_state = "NORMAL"
            time.sleep(0.1)

        elif state == "ALARM":
            # Blinking Red Logic
            ser.write(b'X')
            ser.write(b'W')
            ser.write(b'R') # Red ON
            time.sleep(0.5)

        # Sensor Alert State
        elif state == "SENSOR_ALERT":
            # Solid Yellow ON — sensor out of range
            if last_state != "SENSOR_ALERT":
                ser.write(b'X')
                ser.write(b'W')
                ser.write(b'Y')   # Yellow ON
                last_state = "SENSOR_ALERT"
            time.sleep(0.1)
            
                
        # ser.write(b'X')
        # ser.write(b'W') # Red OFF (White stays ON)
        # time.sleep(0.5)
        # last_state = "ALARM"

        elif state == "SHUTDOWN":
            if last_state != "SHUTDOWN":
                ser.write(b'X')
                ser.write(b'W')
                ser.write(b'R') # Solid Red ON
                last_state = "SHUTDOWN"
            time.sleep(0.1)

def main():
    global current_state, is_running
    
    print("===========================================")
    print("  Smart Package Monitor - Master Controller")
    print("===========================================")
    sensor_monitor.start()          # ← add this before t.start()

    # Start Arduino background thread
    t = threading.Thread(target=arduino_thread, daemon=True)
    t.start()

    print("[Main] Launching box_surveillance.py...")
    
    try:
        # Run the surveillance script unbuffered (-u) so we can read outputs instantly
        # Replace the subprocess.Popen call with this — add a timeout
        process = subprocess.Popen(
            ["python3", "-u", "/home/ece510/smart-package-monitor/src/vision/box_surveillance.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Make stdout non-blocking
        import fcntl
        import os
        fd = process.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        while True:
            # Try to read a line without blocking
            try:
                line = process.stdout.readline()
            except (IOError, OSError):
                line = ""

            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                print(f"> {line}")

                if "Starting surveillance loop..." in line:
                    with state_lock:
                        current_state = "NORMAL"
                elif "TRIGGER:" in line or "ALARM:" in line:
                    with state_lock:
                        current_state = "ALARM"
                elif "Recovery successful!" in line:
                    with state_lock:
                        current_state = "NORMAL"
                elif "shutting down system" in line:
                    with state_lock:
                        current_state = "SHUTDOWN"

            # ← This now runs every iteration regardless of camera output
            with state_lock:
                cs = current_state
            if cs not in ("ALARM", "SHUTDOWN"):
                if sensor_monitor.is_alert():
                    with state_lock:
                        current_state = "SENSOR_ALERT"
                elif cs == "SENSOR_ALERT":
                    with state_lock:
                        current_state = "NORMAL"

            time.sleep(0.1)  # small sleep to avoid busy-spinning
    except KeyboardInterrupt:
        print("[Main] Caught keyboard interrupt. Stopping system...")
    finally:
        with state_lock:
            is_running = False
        sensor_monitor.stop() # Stop the sensor monitor
        t.join(timeout=3)
        print("[Main] Exited cleanly.")

if __name__ == "__main__":
    main()
