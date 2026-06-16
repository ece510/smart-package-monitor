#!/usr/bin/env bash
# Smart Package Monitor — I2C bus verification
# Run on the Raspberry Pi: bash tests/i2c_scan.sh
#
# Expected output: both 0x53 (ADXL345) and 0x38 (AHT20) must appear.

echo "======================================"
echo "  I2C Bus Scan — Smart Package Monitor"
echo "======================================"
echo ""

# Check i2cdetect is available
if ! command -v i2cdetect &> /dev/null; then
    echo "[ERROR] i2cdetect not found."
    echo "        Install with: sudo apt install -y i2c-tools"
    exit 1
fi

echo "[INFO] Scanning I2C bus 1 (GPIO2/3 on Raspberry Pi)..."
echo ""
i2cdetect -y 1
echo ""

# Check for expected addresses
ADXL345="53"   # ADXL345 accelerometer
AHT20="38"     # AHT20 temperature/humidity sensor

SCAN=$(i2cdetect -y 1 2>/dev/null)

FOUND_ADXL=$(echo "$SCAN" | grep -oi " ${ADXL345}" | head -1)
FOUND_AHT20=$(echo "$SCAN" | grep -oi " ${AHT20}" | head -1)

echo "--------------------------------------"
if [ -n "$FOUND_ADXL" ]; then
    echo "[PASS] ADXL345 detected at 0x${ADXL345}"
else
    echo "[FAIL] ADXL345 NOT found at 0x${ADXL345}"
    echo "       Check SDA/SCL/VCC/GND wiring on the accelerometer."
fi

if [ -n "$FOUND_AHT20" ]; then
    echo "[PASS] AHT20 detected at 0x${AHT20}"
else
    echo "[FAIL] AHT20 NOT found at 0x${AHT20}"
    echo "       Check SDA/SCL/VCC/GND wiring on the temp/humidity sensor."
fi
echo "======================================"
