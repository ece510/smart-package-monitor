# Smart Package Monitor — Wiring & Pinout Reference

This document is the single source of truth for how every component is physically
connected. Follow it exactly before running any test in `tests/`. Wiring was designed
for the prototype described in the ECE 510 progress report (Team 1).

**Architecture in one line:** the **Raspberry Pi 4** reads the I²C sensors and the USB
camera and runs all software; the **Arduino Uno** is a dumb indicator controller driven
by the Pi over a USB serial link.

```
                       +---------------------------+
   I2C (3.3V) sensors  |                           |  USB serial (/dev/ttyACM0)
   ADXL345  0x53  -----+        Raspberry Pi 4      +-----------+   Arduino Uno
   AHT20    0x38  -----+   (brain: sensors, CV,     |           |  (indicators)
                       |    Flask dashboard)        |           +--> Green  LED  D2
   Logitech Brio 105 --+ USB                        |           +--> Yellow LED  D3
   USB-C power bank ---+ power                       |           +--> Red    LED  D4
                       +---------------------------+            +--> White  LED  D5 (opt)
                                                                +--> 7-seg a-g  D6-D12 (opt)
```

---

## 1. Raspberry Pi 4 — I²C sensor bus (shared)

Both sensors hang off the **same I²C-1 bus** and are powered from **3.3 V** (these
ADXL345 / AHT20 breakout modules are 3.3 V parts — do **not** use the 5 V pins).
The modules already carry their own SDA/SCL pull-up resistors, so no external
resistors are needed on the bus.

| Signal | Sensor pin | RPi physical pin | RPi BCM | Notes |
|--------|------------|------------------|---------|-------|
| Power  | VCC / VIN  | **Pin 1**        | 3V3     | Shared by both sensors |
| Ground | GND        | **Pin 9**        | GND     | Shared by both sensors |
| I²C data | SDA      | **Pin 3**        | GPIO2 (SDA1) | Pull-ups on module |
| I²C clock | SCL     | **Pin 5**        | GPIO3 (SCL1) | — |

Use a small breadboard power/ground rail to fan out 3V3, GND, SDA and SCL to both
modules. Sensor I²C addresses:

- **ADXL345** (accelerometer): `0x53`
- **AHT20** (temperature / humidity): `0x38`

**Enable I²C on the Pi (once):**
```bash
sudo raspi-config        # Interface Options -> I2C -> Enable
sudo reboot
```

**Verify the bus:** `i2cdetect -y 1` must show `53` and `38`. See `tests/i2c_scan.sh`.

---

## 2. Arduino Uno — status indicators

The Arduino connects to the Pi with a **USB-B cable** and enumerates as
`/dev/ttyACM0` at **9600 baud**. It runs `arduino/indicator_controller/`. The Pi
sends single-character commands; the Arduino drives the LEDs and the optional
7-segment display.

| Component | Arduino pin | Resistor | Serial command | Status |
|-----------|-------------|----------|----------------|--------|
| Green LED (OK)        | D2  | 220 Ω | `G` | Core |
| Yellow LED (WARNING)  | D3  | 220 Ω | `Y` | Core |
| Red LED (CRITICAL)    | D4  | 220 Ω | `R` | Core |
| White LED (CV light)  | D5  | 220 Ω | `W` = on, `w` = off | **Optional** |
| 7-segment a–g         | D6–D12 | 220 Ω/segment | `0`–`9` | **Optional** |

**LED wiring (each LED):** Arduino digital pin → 220 Ω resistor → LED anode (long leg);
LED cathode (short leg) → Arduino GND.

**7-segment (common-cathode) wiring:** common cathode pin → Arduino GND; segment pins
a,b,c,d,e,f,g → D6,D7,D8,D9,D10,D11,D12 each through its own 220 Ω resistor. If your
display is **common-anode**, tie the common pin to 5 V and invert the segment logic in
the firmware.

### Serial protocol (Pi → Arduino, 9600 8N1)
| Byte | Action |
|------|--------|
| `G` | Green LED on, others off |
| `Y` | Yellow LED on, others off |
| `R` | Red LED on, others off |
| `W` / `w` | White LED on / off |
| `0`–`9` | Show digit on 7-segment (alert count) |
| `X` | All indicators off |

---

## 3. Raspberry Pi USB peripherals

| Device | Connection | Linux device | Accessed by |
|--------|------------|--------------|-------------|
| Logitech Brio 105 webcam | USB-A | `/dev/video0` | `cv2.VideoCapture(0)` |
| Arduino Uno | USB-A → USB-B | `/dev/ttyACM0` | `pyserial` @ 9600 |
| 10 000 mAh power bank | USB-C | — | Powers the Pi (5 V / 3 A) |

---

## 4. Quick bring-up checklist (run on the Pi over SSH)

1. `bash tests/i2c_scan.sh` → expect `0x53` and `0x38`.
2. `python3 tests/test_adxl345.py` → X/Y/Z change when the box is moved.
3. `python3 tests/test_aht20.py` → plausible room temperature and humidity.
4. `python3 tests/test_camera.py` → a sharp JPG is saved under `captures/`.
5. Flash `indicator_controller.ino`, then `python3 tests/test_arduino_serial.py`
   → LEDs cycle G → Y → R and the 7-seg counts 0..3.

If every step prints **PASS**, the hardware is correctly wired and teammates can SSH
in and start developing.
