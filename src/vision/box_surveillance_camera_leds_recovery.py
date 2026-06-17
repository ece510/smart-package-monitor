import cv2
import time
import os
import json
import numpy as np
from skimage.metrics import structural_similarity as ssim

try:
    import serial
except ImportError:
    serial = None

# --- Configuration ---
CAMERA_INDEX = 0
CAPTURE_DIR = os.path.expanduser("/home/ece510/smart-package-monitor/src/vision/surveillance_captures")
MOVEMENT_THRESHOLD_PX = 100
SSIM_THRESHOLD = 0.70  # similarity respect reference image
RECOVERY_SSIM_THRESHOLD = 0.65
ONNX_MODEL = "/home/ece510/smart-package-monitor/src/vision/custom_box_model.onnx"
INPUT_WIDTH = 640
INPUT_HEIGHT = 640
CONF_THRESHOLD = 0.7  # detects boxes in the scene

# --- Arduino / LED Configuration ---
# This file is only for testing the camera system.
# It controls ONLY camera-related LED states and does not use SensorMonitor.
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600
ENABLE_CAMERA_LEDS = True

# During ALARM, the camera periodically tries to find the box again.
# This keeps the original recovery idea, but makes the short camera-cover case robust.
ALARM_TOTAL_EVALUATION_TIME = 10.0
RECOVERY_CHECK_INTERVAL = 1.0
RECOVERY_FIRST_CHECK_AFTER = 1.0

os.makedirs(CAPTURE_DIR, exist_ok=True)
HAS_DISPLAY = os.name != 'posix' or 'DISPLAY' in os.environ


class CameraLedController:
    """
    Controls only the LEDs related to the camera surveillance state.

    Arduino command convention used by the existing project:
        X -> turn all LEDs off
        W -> white ON
        G -> green ON
        R -> red ON
        w -> white OFF

    Camera states:
        INIT     -> white
        NORMAL   -> white + green
        ALARM    -> white + blinking red
        SHUTDOWN -> white + solid red
    """

    def __init__(self, port=SERIAL_PORT, baud_rate=BAUD_RATE, enabled=ENABLE_CAMERA_LEDS):
        self.enabled = enabled and serial is not None
        self.ser = None
        self.current_state = None
        self.red_is_on = False
        self.last_blink_time = 0.0
        self.blink_interval = 0.5

        if not enabled:
            print("[Camera LEDs] Disabled.")
            return

        if serial is None:
            print("[Camera LEDs] pyserial not installed. Camera will run without LEDs.")
            print("[Camera LEDs] Install with: pip install pyserial")
            return

        try:
            self.ser = serial.Serial(port, baud_rate, timeout=2)
            print(f"[Camera LEDs] Connected to Arduino on {port}")
            time.sleep(2)  # Wait for Arduino reset after opening serial connection
            self.set_init()
        except Exception as e:
            print(f"[Camera LEDs] Could not connect to Arduino: {e}")
            print("[Camera LEDs] Camera will run without LED control.")
            self.enabled = False
            self.ser = None

    def _write(self, command):
        if not self.enabled or self.ser is None:
            return
        try:
            self.ser.write(command)
        except Exception as e:
            print(f"[Camera LEDs] Serial write failed: {e}")
            self.enabled = False

    def set_init(self):
        if self.current_state == "INIT":
            return
        self._write(b'X')
        self._write(b'W')
        self.current_state = "INIT"
        self.red_is_on = False
        print("[Camera LEDs] INIT: white ON")

    def set_normal(self):
        if self.current_state == "NORMAL":
            return
        self._write(b'X')
        self._write(b'W')
        self._write(b'G')
        self.current_state = "NORMAL"
        self.red_is_on = False
        print("[Camera LEDs] NORMAL: white + green ON")

    def set_alarm(self):
        if self.current_state != "ALARM":
            print("[Camera LEDs] ALARM: white + blinking red")
        self.current_state = "ALARM"
        self.red_is_on = False
        self.last_blink_time = 0.0

    def update_alarm_blink(self, now=None):
        if self.current_state != "ALARM":
            return

        if now is None:
            now = time.time()

        if now - self.last_blink_time >= self.blink_interval:
            self.last_blink_time = now
            self.red_is_on = not self.red_is_on

            self._write(b'X')
            self._write(b'W')
            if self.red_is_on:
                self._write(b'R')

    def set_shutdown(self):
        if self.current_state == "SHUTDOWN":
            return
        self._write(b'X')
        self._write(b'W')
        self._write(b'R')
        self.current_state = "SHUTDOWN"
        self.red_is_on = True
        print("[Camera LEDs] SHUTDOWN: white + solid red ON")

    def close(self, turn_off=True):
        if self.ser is None:
            return

        try:
            if turn_off:
                self._write(b'X')
                self._write(b'w')
            self.ser.close()
            print("[Camera LEDs] Serial connection closed.")
        except Exception as e:
            print(f"[Camera LEDs] Error while closing serial connection: {e}")


def calculate_ssim(img1, img2):
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    gray2_resized = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
    score, _ = ssim(gray1, gray2_resized, full=True)
    return score


def calculate_color_similarity(img1, img2):
    hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
    hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    hsv2_resized = cv2.resize(hsv2, (hsv1.shape[1], hsv1.shape[0]))
    hist1 = cv2.calcHist([hsv1], [0, 1], None, [50, 60], [0, 180, 0, 256])
    hist2 = cv2.calcHist([hsv2_resized], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
    return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)


def get_center(roi):
    return (roi[0] + roi[2] // 2, roi[1] + roi[3] // 2)


def format_yolov8_output(output, original_width, original_height):
    output = output[0]
    output = np.transpose(output)

    boxes = []
    scores = []
    class_ids = []

    x_factor = original_width / INPUT_WIDTH
    y_factor = original_height / INPUT_HEIGHT

    for row in output:
        classes_scores = row[4:]
        max_score = np.max(classes_scores)
        if max_score >= CONF_THRESHOLD:
            class_id = np.argmax(classes_scores)
            x, y, w, h = row[0], row[1], row[2], row[3]

            left = int((x - w / 2) * x_factor)
            top = int((y - h / 2) * y_factor)
            width = int(w * x_factor)
            height = int(h * y_factor)

            boxes.append([left, top, width, height])
            scores.append(float(max_score))
            class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, scores, CONF_THRESHOLD, 0.45)

    final_boxes = []
    final_scores = []
    if len(indices) > 0:
        for i in indices.flatten():
            final_boxes.append(boxes[i])
            final_scores.append(scores[i])

    return final_boxes, final_scores


def save_snapshot(frame, label):
    ts = time.strftime("%Y%m%d-%H%M%S")
    filepath = os.path.join(CAPTURE_DIR, f"capture_{label}_{ts}.jpg")
    cv2.imwrite(filepath, frame)
    print(f"[{time.strftime('%H:%M:%S')}] Saved picture: {filepath}")


def create_tracker():
    try:
        return cv2.TrackerCSRT.create()
    except AttributeError:
        return cv2.TrackerCSRT_create()


def find_matching_box_with_yolo(net, frame, original_reference_crop, orig_w, orig_h):
    """
    Looks for the original box in the current frame using YOLO + SSIM/color similarity.
    Returns (best_match_box, best_score).
    """
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
    net.setInput(blob)
    preds = net.forward()
    yolo_boxes, _ = format_yolov8_output(preds, orig_w, orig_h)

    best_match_box = None
    best_score = 0

    for box in yolo_boxes:
        x, y, w, h = box
        if y >= 0 and y + h <= orig_h and x >= 0 and x + w <= orig_w:
            crop = frame[y:y + h, x:x + w]
            if crop.shape[0] > 0 and crop.shape[1] > 0:
                sim = calculate_ssim(original_reference_crop, crop)
                color_sim = calculate_color_similarity(original_reference_crop, crop)
                total_score = (sim * 0.5) + (color_sim * 0.5)

                if total_score > best_score:
                    best_score = total_score
                    best_match_box = box

    return best_match_box, best_score


def main():
    led_controller = CameraLedController()
    final_camera_state = "INIT"
    cap = None

    try:
        if not os.path.exists(ONNX_MODEL):
            print(f"Error: '{ONNX_MODEL}' not found!")
            return

        print(f"Loading custom YOLOv8 model ({ONNX_MODEL}) via OpenCV DNN...")
        net = cv2.dnn.readNetFromONNX(ONNX_MODEL)

        print("Initializing camera...")
        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        if not cap.isOpened():
            print("Error: Could not open camera.")
            return

        time.sleep(2)
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read from camera.")
            return

        orig_h, orig_w = frame.shape[:2]

        # --- INITIALIZATION ---
        print("\n--- AUTO-DETECTION INITIALIZATION ---")
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
        net.setInput(blob)
        preds = net.forward()

        boxes, scores = format_yolov8_output(preds, orig_w, orig_h)
        detected_objects = {}
        annotated_frame = frame.copy()

        for idx, (box, score) in enumerate(zip(boxes, scores)):
            x, y, w, h = box
            detected_objects[str(idx)] = (x, y, w, h)
            cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.putText(
                annotated_frame,
                f"[ID: {idx}] Box ({score:.2f})",
                (x, max(y - 10, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                3,
            )

        ref_path = "/home/ece510/smart-package-monitor/src/vision/reference_frame_detected.jpg"
        cv2.imwrite(ref_path, annotated_frame)
        print(f"Saved picture to '{ref_path}'.")

        roi = None
        while True:
            print("Enter ID to track (or 'manual'):")
            user_input = input().strip().lower()
            if user_input in detected_objects:
                roi = detected_objects[user_input]
                break
            elif user_input == 'manual':
                print("Enter x y width height: ")
                coords = input()
                x, y, w, h = map(int, coords.strip().split())
                roi = (x, y, w, h)
                break
            else:
                print("Invalid input.")

        print(f"Tracking ROI: {roi}")

        tracker = create_tracker()
        tracker.init(frame, roi)
        original_reference_crop = frame[
            int(roi[1]):int(roi[1] + roi[3]),
            int(roi[0]):int(roi[0] + roi[2])
        ].copy()
        reference_crop = original_reference_crop.copy()  # The current active reference
        initial_center = get_center(roi)

        # State Machine Variables
        alarm_state = False
        alarm_start_time = 0
        pics_taken = 0
        last_recovery_check_time = 0

        print("\nStarting surveillance loop...")
        led_controller.set_normal()
        final_camera_state = "NORMAL"

        if not HAS_DISPLAY:
            print("Running in headless mode. Press Ctrl+C in the terminal to quit.")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            display_frame = frame.copy()
            current_time = time.time()

            if alarm_state:
                led_controller.update_alarm_blink(current_time)

                elapsed = current_time - alarm_start_time
                cv2.putText(
                    display_frame,
                    f"ALARM: EVALUATING IN {max(0, int(ALARM_TOTAL_EVALUATION_TIME) - int(elapsed))}s",
                    (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    3,
                )

                # Take pictures at 0s, 5s, 10s, same behavior as the original camera script.
                if elapsed >= 0 and pics_taken == 0:
                    save_snapshot(display_frame, "alarm_0s")
                    pics_taken = 1
                elif elapsed >= 5 and pics_taken == 1:
                    save_snapshot(display_frame, "alarm_5s")
                    pics_taken = 2
                elif elapsed >= ALARM_TOTAL_EVALUATION_TIME and pics_taken == 2:
                    save_snapshot(display_frame, "alarm_10s")
                    pics_taken = 3

                # IMPORTANT RECOVERY LOGIC:
                # While alarm is active, periodically try to find the box again.
                # Therefore, if the camera is covered for 1 second and then uncovered,
                # the system can recover and return to NORMAL instead of staying broken.
                should_check_recovery = (
                    elapsed >= RECOVERY_FIRST_CHECK_AFTER
                    and current_time - last_recovery_check_time >= RECOVERY_CHECK_INTERVAL
                )

                if should_check_recovery:
                    last_recovery_check_time = current_time
                    print("Checking if the box is visible again using YOLO...")
                    best_match_box, best_score = find_matching_box_with_yolo(
                        net, frame, original_reference_crop, orig_w, orig_h
                    )

                    if best_match_box and best_score >= RECOVERY_SSIM_THRESHOLD:
                        print(f"Recovery successful! Found a box with Combined Score {best_score:.2f}")
                        roi = best_match_box
                        tracker = create_tracker()
                        tracker.init(frame, roi)

                        reference_crop = frame[
                            int(roi[1]):int(roi[1] + roi[3]),
                            int(roi[0]):int(roi[0] + roi[2])
                        ].copy()
                        initial_center = get_center(roi)
                        alarm_state = False
                        led_controller.set_normal()
                        final_camera_state = "NORMAL"
                        print("Resuming normal surveillance with new reference.")
                    elif elapsed >= ALARM_TOTAL_EVALUATION_TIME:
                        print(f"Recovery failed. Best box had SSIM {best_score:.2f} (Required: {RECOVERY_SSIM_THRESHOLD}).")
                        print("Taking 4th picture and shutting down system.")
                        save_snapshot(display_frame, "shutdown_4th")
                        led_controller.set_shutdown()
                        final_camera_state = "SHUTDOWN"
                        break  # Exit program

            else:
                # NORMAL SURVEILLANCE
                success, current_roi = tracker.update(frame)
                trigger_reason = None

                if success:
                    x, y, w, h = [int(v) for v in current_roi]
                    current_center = get_center((x, y, w, h))
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                    cv2.putText(display_frame, "SURVEILLED BOX", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                    # Check Movement
                    dist = np.sqrt((current_center[0] - initial_center[0]) ** 2 + (current_center[1] - initial_center[1]) ** 2)
                    if dist > MOVEMENT_THRESHOLD_PX:
                        trigger_reason = f"Movement Detected ({dist:.1f}px)"

                    # Check Damage
                    elif y >= 0 and y + h <= orig_h and x >= 0 and x + w <= orig_w:
                        current_crop = frame[y:y + h, x:x + w]
                        if current_crop.shape[0] > 0 and current_crop.shape[1] > 0:
                            similarity = calculate_ssim(reference_crop, current_crop)
                            cv2.putText(display_frame, f"SSIM: {similarity:.2f}", (x, y + h + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                            if similarity < SSIM_THRESHOLD:
                                trigger_reason = f"Damage Detected (SSIM: {similarity:.2f})"
                else:
                    trigger_reason = "Box Lost!"

                if trigger_reason:
                    print(f"[{time.strftime('%H:%M:%S')}] TRIGGER: {trigger_reason}. Entering Alarm State!")
                    cv2.putText(display_frame, trigger_reason, (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    alarm_state = True
                    alarm_start_time = current_time
                    pics_taken = 0
                    last_recovery_check_time = 0
                    led_controller.set_alarm()
                    final_camera_state = "ALARM"

            if HAS_DISPLAY:
                cv2.imshow("Surveillance Feed", display_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("\n[Camera] Keyboard interrupt. Stopping camera surveillance...")

    finally:
        if cap is not None:
            cap.release()
        if HAS_DISPLAY:
            cv2.destroyAllWindows()

        # If the camera reached shutdown, leave solid red visible briefly before closing.
        # Otherwise, turn LEDs off on clean exit.
        if final_camera_state == "SHUTDOWN":
            time.sleep(3)
            led_controller.close(turn_off=False)
        else:
            led_controller.close(turn_off=True)


if __name__ == "__main__":
    main()
