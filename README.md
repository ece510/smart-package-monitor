# Smart Package Monitor

IoT system that records and reports the physical and environmental conditions of a
fragile shipment from dispatch to delivery. Built for **ECE 510 — Internet of Things
and Cyber Physical Systems** at the Illinois Institute of Technology (Dr. Jafar Saniie).

A self-contained unit rides inside the package. A **Raspberry Pi 4** reads an
accelerometer and a temperature/humidity sensor, inspects the package interior with a
USB camera (computer vision), serves a live web dashboard, and sends alerts. An
**Arduino Uno** acts as a simple status-indicator controller driven over USB serial.

> Team 1 — Alejandro Calatrava Torras (lead), Guillermo Sánchez Recuero, Gorka Zamorano Oro.

---

## Hardware

| Component | Interface | Connected to |
|-----------|-----------|--------------|
| Raspberry Pi 4 (4 GB) | — | Central processor / web server |
| Arduino Uno R3 | USB serial | RPi USB (`/dev/ttyACM0`) |
| ADXL345 accelerometer | I²C `0x53` | RPi I²C-1 |
| AHT20 temp/humidity | I²C `0x38` | RPi I²C-1 |
| Logitech Brio 105 webcam | USB | RPi (`/dev/video0`) |
| RGB status LEDs + opt. 7-seg | GPIO | Arduino |
| 10 000 mAh power bank | USB-C | RPi power |

**Full pin-by-pin wiring is in [`WIRING.md`](WIRING.md). Read it before touching anything.**

---

## Getting started (Raspberry Pi)

### 1. Connect to the Pi over SSH
```bash
ssh pi@<PI_IP_ADDRESS>      # ask Guillermo for the IP and password
```

### 2. Clone and set up the Python environment
```bash
git clone https://github.com/Siidebox/smart-package-monitor.git
cd smart-package-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Enable I²C (only the first time)
```bash
sudo raspi-config        # Interface Options -> I2C -> Enable
sudo reboot
```

---

## Verifying the hardware

Run these from the repo root on the Pi. Each script prints a clear **PASS/FAIL** so you
know immediately whether your wiring works.

```bash
bash   tests/i2c_scan.sh          # 1. I2C bus: expect 0x53 and 0x38
python3 tests/test_adxl345.py     # 2. Accelerometer X/Y/Z
python3 tests/test_aht20.py       # 3. Temperature / humidity
python3 tests/test_camera.py      # 4. Camera capture -> captures/
python3 tests/test_arduino_serial.py   # 5. Arduino LEDs + 7-seg
```

For the Arduino test, first flash `arduino/indicator_controller/indicator_controller.ino`
using the Arduino IDE (board: Arduino Uno, port: `/dev/ttyACM0`).

---

## Repository layout

```
smart-package-monitor/
├── README.md                       # this file
├── WIRING.md                       # pin-by-pin wiring reference
├── requirements.txt                # Python dependencies
├── arduino/
│   └── indicator_controller/       # Arduino firmware (LEDs + 7-seg)
├── tests/                          # hardware bring-up test scripts
└── src/                            # application code (in progress)
    ├── sensors/   # sensor daemon, I2C reads        (Guillermo)
    ├── alerts/    # alert engine, SQLite, email      (Guillermo)
    ├── vision/    # OpenCV / SSIM integrity pipeline  (Week 2)
    └── web/       # Flask + SocketIO dashboard        (Gorka)
```

## Work split

| Member | Area | Folders |
|--------|------|---------|
| Alejandro | Hardware wiring, enclosure, integration | `arduino/`, `WIRING.md` |
| Guillermo | RPi software: sensors, alerts, logging, email | `src/sensors`, `src/alerts` |
| Gorka | Web dashboard, Arduino firmware, testing | `src/web`, `arduino/` |

## Workflow

1. `git pull` before you start.
2. Work on a branch: `git checkout -b feature/<your-thing>`.
3. Commit small, push, open a pull request.
4. Keep `WIRING.md` updated if you change any physical connection.
