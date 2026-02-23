# LensBlock
>
> A visual privacy shield preventing unauthorized recording of sensitive information.

LensBlock is an enterprise-grade desktop security daemon that uses your webcam to monitor the immediate physical environment for visual recording devices (e.g., cell phones). When a threat is detected entering the secure monitoring zone, it instantly deploys a "Secure Enclave", locking down all active monitors with an opaque full-screen overlay to prevent data exfiltration.

## Features

* **Zero-Trust Visual Shield**: Instantly obfuscates all connected monitors when a recording device enters the camera's field of view.
* **Penalty Lockout Timer**: configurable delay that holds the system in lockdown for *X* seconds even after the threat is removed, deterring rapid peek attempts.
* **High-Performance Inference**: Uses `YOLOv8` backed by `ONNX Runtime` to perform real-time object detection with minimal CPU overhead.
* **Forensic Auditing**: Every localized threat is logged cleanly into an SQLite evidence database (`lensblock_audit.db`).
* **Multi-Monitor Enforcement**: Powered by a robust `PyQt6` architecture that aggressively intercepts focus and scales across any arbitrary number of active displays.
* **Invisible Daemon**: Once armed, it lives seamlessly in your Windows System Tray.

## System Requirements

* Python 3.11.x (Explicitly required to maintain `onnxruntime-directml` compatibility)
* Windows 10/11
* A connected generic webcam or video input device.
* [Microsoft Visual C++ Redistributable (2015-2022)](https://aka.ms/vs/17/release/vc_redist.x64.exe) installed system-wide.

## Installation & Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Therm1te/LensBlock.git
   cd LensBlock
   ```

2. **Establish the Virtual Environment:**
   LensBlock requires strict dependency pinning (specifically `NumPy 1.26.4`) to prevent DLL crashes with the C-API.

   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Core Requirements:**

   ```powershell
   pip install -r requirements.txt
   ```

4. **Prepare Machine Learning Model:**
   Download the default YOLOv8 Nano ONNX weights.
   Ensure that the file `yolov8n.onnx` is placed securely within the `models/` directory.

## Configuration (`config.yaml`)

You can adjust the core security constraints inside the configuration manifest.

```yaml
detection:
  confidence_threshold: 0.55       # (0.0 to 1.0) Confidence required before classifying an object as a threat.
  lockout_duration_seconds: 10     # How long the penalty shield persists after the device is lowered.
  persistence_frames: 1            # Consecutive frames the threat must appear before triggering lockdown.
logging:
  enable_forensic_logging: true    # Toggle SQLite audit logging.
system:
  run_on_startup: false            
```

## Usage

Simply launch the daemon via the main entry point:

```powershell
python main.py
```

Upon execution, LensBlock's tray icon will appear armed and monitoring. Double-click the tray icon to open the Settings Dashboard and verify your background video feed is being intercepted correctly.

## Architecture

LensBlock strictly compartmentalizes UI operations, threading, and inference:

* `core/engine.py`: Defines the `YoloV8Engine` mapping inference execution limits.
* `core/camera.py`: Asynchronous OpenCV frame buffering.
* `security/controller.py`: The `QThread` maintaining the mathematical state machine of active threats and locking delays.
* `ui/shield.py` & `ui/dashboard.py`: Strict `PyQt6` UI abstractions.
