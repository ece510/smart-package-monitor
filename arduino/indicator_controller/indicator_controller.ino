/*
 * Smart Package Monitor — Indicator Controller
 * ECE 510: Internet of Things and Cyber Physical Systems
 * Illinois Institute of Technology — Team 1
 *
 * Description:
 *   Receives single-character commands from the Raspberry Pi over a USB serial link
 *   (9600 baud) and drives the physical status indicators:
 *     G → Green  LED on (package OK)
 *     Y → Yellow LED on (WARNING condition)
 *     R → Red    LED on (CRITICAL condition)
 *     W → White  LED on  (illumination for camera — optional)
 *     w → White  LED off
 *     0-9 → show digit on 7-segment display (alert count — optional)
 *     X → all indicators off
 *
 * Hardware connections (breadboard):
 *   Green  LED  → D2 → 220 Ω → anode;  cathode → GND
 *   Yellow LED  → D3 → 220 Ω → anode;  cathode → GND
 *   Red    LED  → D4 → 220 Ω → anode;  cathode → GND
 *   White  LED  → D5 → 220 Ω → anode;  cathode → GND  [optional]
 *   7-seg a–g   → D6–D12 → 220 Ω each (common-cathode; cathode → GND) [optional]
 *
 * Author: Team 1 (Gorka Zamorano Oro — Arduino firmware)
 * Date:   June 2026
 */

// ── Pin definitions ─────────────────────────────────────────────────────────
const int PIN_LED_GREEN  = 2;
const int PIN_LED_YELLOW = 3;
const int PIN_LED_RED    = 4;
const int PIN_LED_WHITE  = 5;   // optional: CV illumination

// 7-segment segments a–g (common-cathode, LOW = segment off, HIGH = on)
const int SEG_PINS[] = {6, 7, 8, 9, 10, 11, 12};   // a, b, c, d, e, f, g
const int NUM_SEGS = 7;

// Segment encoding for digits 0–9 (a,b,c,d,e,f,g)
// 1 = segment on, 0 = segment off
const byte DIGIT_MAP[10][7] = {
  {1, 1, 1, 1, 1, 1, 0},  // 0
  {0, 1, 1, 0, 0, 0, 0},  // 1
  {1, 1, 0, 1, 1, 0, 1},  // 2
  {1, 1, 1, 1, 0, 0, 1},  // 3
  {0, 1, 1, 0, 0, 1, 1},  // 4
  {1, 0, 1, 1, 0, 1, 1},  // 5
  {1, 0, 1, 1, 1, 1, 1},  // 6
  {1, 1, 1, 0, 0, 0, 0},  // 7
  {1, 1, 1, 1, 1, 1, 1},  // 8
  {1, 1, 1, 1, 0, 1, 1},  // 9
};

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  // Configure LED pins as outputs
  pinMode(PIN_LED_GREEN,  OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED,    OUTPUT);
  pinMode(PIN_LED_WHITE,  OUTPUT);

  // Configure 7-segment pins as outputs
  for (int i = 0; i < NUM_SEGS; i++) {
    pinMode(SEG_PINS[i], OUTPUT);
  }

  // Start with everything off
  allOff();

  Serial.println("Smart Package Monitor — indicator controller ready.");
}

// ── Main loop ────────────────────────────────────────────────────────────────
void loop() {
  if (Serial.available() > 0) {
    char cmd = (char)Serial.read();
    dispatchCommand(cmd);
  }
}

// ── Command dispatcher ───────────────────────────────────────────────────────
void dispatchCommand(char cmd) {
  switch (cmd) {
    case 'G':
      setStatusLED(PIN_LED_GREEN);
      break;
    case 'Y':
      setStatusLED(PIN_LED_YELLOW);
      break;
    case 'R':
      setStatusLED(PIN_LED_RED);
      break;
    case 'W':
      digitalWrite(PIN_LED_WHITE, HIGH);
      break;
    case 'w':
      digitalWrite(PIN_LED_WHITE, LOW);
      break;
    case 'X':
      allOff();
      break;
    default:
      // Handle digit characters 0–9 for the 7-segment display
      if (cmd >= '0' && cmd <= '9') {
        showDigit(cmd - '0');
      }
      break;
  }
}

// ── Helper: turn on one status LED, turn the other two off ──────────────────
void setStatusLED(int activePin) {
  digitalWrite(PIN_LED_GREEN,  (activePin == PIN_LED_GREEN)  ? HIGH : LOW);
  digitalWrite(PIN_LED_YELLOW, (activePin == PIN_LED_YELLOW) ? HIGH : LOW);
  digitalWrite(PIN_LED_RED,    (activePin == PIN_LED_RED)    ? HIGH : LOW);
}

// ── Helper: display a digit 0–9 on the 7-segment display ────────────────────
void showDigit(int digit) {
  if (digit < 0 || digit > 9) return;
  for (int i = 0; i < NUM_SEGS; i++) {
    digitalWrite(SEG_PINS[i], DIGIT_MAP[digit][i] ? HIGH : LOW);
  }
}

// ── Helper: all indicators off ───────────────────────────────────────────────
void allOff() {
  digitalWrite(PIN_LED_GREEN,  LOW);
  digitalWrite(PIN_LED_YELLOW, LOW);
  digitalWrite(PIN_LED_RED,    LOW);
  digitalWrite(PIN_LED_WHITE,  LOW);
  for (int i = 0; i < NUM_SEGS; i++) {
    digitalWrite(SEG_PINS[i], LOW);
  }
}
