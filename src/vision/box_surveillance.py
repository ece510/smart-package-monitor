import cv2
import time
import os
import json
import numpy as np
from skimage.metrics import structural_similarity as ssim

# --- Configuration ---
CAMERA_INDEX = 0
CAPTURE_DIR = os.path.expanduser("/home/ece510/smart-package-monitor/src/vision/surveillance_captures")
MOVEMENT_THRESHOLD_PX = 30
SSIM_THRESHOLD = 0.70
RECOVERY_SSIM_THRESHOLD = 0.60
ONNX_MODEL = "/home/ece510/smart-package-monitor/src/vision/custom_box_model.onnx"
INPUT_WIDTH = 640
INPUT_HEIGHT = 640
CONF_THRESHOLD = 0.5

os.makedirs(CAPTURE_DIR, exist_ok=True)
HAS_DISPLAY = os.name != 'posix' or 'DISPLAY' in os.environ

def calculate_ssim(img1, img2):
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    gray2_resized = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
    score, _ = ssim(gray1, gray2_resized, full=True)
    return score

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
    if len(indices) > 0:
        for i in indices.flatten():
            final_boxes.append(boxes[i])
            
    return final_boxes

def save_snapshot(frame, label):
    ts = time.strftime("%Y%m%d-%H%M%S")
    filepath = os.path.join(CAPTURE_DIR, f"capture_{label}_{ts}.jpg")
    cv2.imwrite(filepath, frame)
    print(f"[{time.strftime('%H:%M:%S')}] Saved picture: {filepath}")

def main():
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
    if not ret: return
    orig_h, orig_w = frame.shape[:2]

    # --- INITIALIZATION ---
    print("\n--- AUTO-DETECTION INITIALIZATION ---")
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
    net.setInput(blob)
    preds = net.forward()
    
    boxes = format_yolov8_output(preds, orig_w, orig_h)
    detected_objects = {}
    annotated_frame = frame.copy()
    
    for idx, box in enumerate(boxes):
        x, y, w, h = box
        detected_objects[str(idx)] = (x, y, w, h)
        cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (255, 0, 255), 3)
        cv2.putText(annotated_frame, f"[ID: {idx}] Box", (x, max(y - 10, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 3)
            
    ref_path = "./home/ece510/smart-package-monitor/src/vision/reference_frame_detected.jpg"
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

    try:
        tracker = cv2.TrackerCSRT.create()
    except AttributeError:
        tracker = cv2.TrackerCSRT_create()
        
    tracker.init(frame, roi)
    original_reference_crop = frame[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2])].copy()
    reference_crop = original_reference_crop.copy() # The current active reference
    initial_center = get_center(roi)
    
    # State Machine Variables
    alarm_state = False
    alarm_start_time = 0
    pics_taken = 0
    
    print("\nStarting surveillance loop...")
    if not HAS_DISPLAY:
        print("Running in headless mode. Press Ctrl+C in the terminal to quit.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret: break
            display_frame = frame.copy()
            current_time = time.time()
            
            if alarm_state:
                elapsed = current_time - alarm_start_time
                cv2.putText(display_frame, f"ALARM: EVALUATING IN {max(0, 10 - int(elapsed))}s", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                
                # Take pictures at 0s, 5s, 10s
                if elapsed >= 0 and pics_taken == 0:
                    save_snapshot(display_frame, "alarm_0s")
                    pics_taken = 1
                elif elapsed >= 5 and pics_taken == 1:
                    save_snapshot(display_frame, "alarm_5s")
                    pics_taken = 2
                elif elapsed >= 10 and pics_taken == 2:
                    save_snapshot(display_frame, "alarm_10s")
                    pics_taken = 3
                    
                    # Evaluation Phase
                    print("10 seconds passed. Evaluating scene using YOLO...")
                    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (INPUT_WIDTH, INPUT_HEIGHT), swapRB=True, crop=False)
                    net.setInput(blob)
                    preds = net.forward()
                    yolo_boxes = format_yolov8_output(preds, orig_w, orig_h)
                    
                    best_match_box = None
                    best_ssim = 0
                    
                    for box in yolo_boxes:
                        x, y, w, h = box
                        if y >= 0 and y+h <= orig_h and x >= 0 and x+w <= orig_w:
                            crop = frame[y:y+h, x:x+w]
                            if crop.shape[0] > 0 and crop.shape[1] > 0:
                                sim = calculate_ssim(original_reference_crop, crop)
                                if sim > best_ssim:
                                    best_ssim = sim
                                    best_match_box = box
                                    
                    if best_match_box and best_ssim >= RECOVERY_SSIM_THRESHOLD:
                        print(f"Recovery successful! Found a box with SSIM {best_ssim:.2f} compared to original.")
                        roi = best_match_box
                        try:
                            tracker = cv2.TrackerCSRT.create()
                        except AttributeError:
                            tracker = cv2.TrackerCSRT_create()
                        tracker.init(frame, roi)
                        
                        # Save the second reference picture and run with it
                        reference_crop = frame[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2])].copy()
                        initial_center = get_center(roi)
                        alarm_state = False
                        print("Resuming normal surveillance with new reference.")
                    else:
                        print(f"Recovery failed. Best box had SSIM {best_ssim:.2f} (Required: {RECOVERY_SSIM_THRESHOLD}).")
                        print("Taking 4th picture and shutting down system.")
                        save_snapshot(display_frame, "shutdown_4th")
                        break # Exit program
                        
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
                    dist = np.sqrt((current_center[0] - initial_center[0])**2 + (current_center[1] - initial_center[1])**2)
                    if dist > MOVEMENT_THRESHOLD_PX:
                        trigger_reason = f"Movement Detected ({dist:.1f}px)"
                        
                    # Check Damage
                    elif y >= 0 and y+h <= orig_h and x >= 0 and x+w <= orig_w:
                        current_crop = frame[y:y+h, x:x+w]
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
                    
            if HAS_DISPLAY:
                cv2.imshow("Surveillance Feed", display_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if HAS_DISPLAY: cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
