# Custom Box Surveillance (YOLOv8 ONNX + OpenCV)

This project trains a custom YOLOv8 AI model to recognize your specific cardboard boxes on your Windows PC, and then exports that AI to run completely headlessly and crash-free on your Raspberry Pi 4 using OpenCV's DNN engine.

## Phase 1: Train the AI (On your Windows PC)

1. **Download a Dataset**: 
   - Go to [Roboflow Universe](https://universe.roboflow.com/) and search for "Cardboard Box" or "Damaged Box".
   - Find a dataset you like, click "Download Dataset", and select **YOLOv8** format.
   - Extract the downloaded folder into this `adventurous-planck` directory.

2. **Install PC Requirements**:
   Open a terminal on your Windows machine in this folder and run:
   ```bash
   pip install -r requirements_pc.txt
   ```

3. **Run the Training**:
   Open `train_custom_yolo.py` and ensure the `data='...'` line points to the `data.yaml` file from the dataset you just downloaded.
   Run the training:
   ```bash
   python train_custom_yolo.py
   ```
   *This might take an hour or so! When it finishes, it will export a file called `best.onnx` inside `runs/detect/custom_box_model/weights/`.*

4. **Copy the AI**:
   Rename `best.onnx` to `custom_box_model.onnx` and copy it to your Raspberry Pi!

---

## Phase 2: Run Surveillance (On your Raspberry Pi)

1. **Copy the Scripts**: 
   Copy `box_surveillance.py`, `requirements.txt`, and your new `custom_box_model.onnx` to your Raspberry Pi.

2. **System Dependencies**:
   ```bash
   sudo apt update
   sudo apt install -y v4l-utils libgl1
   ```

3. **Install Python Requirements**:
   ```bash
   python3 -m venv surveil_env
   source surveil_env/bin/activate
   pip install -r requirements.txt
   ```
   *(Note: Do not install `ultralytics` or `torch` here! The ONNX model doesn't need them).*

4. **Run the Script**:
   ```bash
   python3 box_surveillance.py
   ```
   - On the first run, the AI will auto-detect your custom boxes, saving the image to `reference_frame_detected.jpg`.
   - Open that image, find the ID of the box you want to track, and type it into your terminal.
