# LensBlock

> A visual privacy shield preventing unauthorized recording of sensitive information.

LensBlock is a desktop security daemon that uses your webcam to monitor the immediate physical environment for visual recording devices (e.g., cell phones). When a threat is detected entering the secure monitoring zone, it instantly deploys a **Secure Enclave** — locking down all active monitors with an opaque full-screen overlay to prevent data exfiltration.

---

## Features

### Core Security

* **Zero-Trust Visual Shield** — Instantly obfuscates all connected monitors when a recording device enters the camera's field of view.
* **Penalty Lockout Timer** — Configurable delay that holds the system in lockdown for *X* seconds even after the threat is removed, deterring rapid peek attempts.
* **High-Performance Inference** — Uses `YOLOv26` backed by `ONNX Runtime` with optional DirectML GPU acceleration.
* **Multi-Monitor Enforcement** — Aggressively intercepts focus and scales across any number of active displays simultaneously.
* **Forensic Auditing** — Every threat incident is logged into an SQLite evidence database (`lensblock_audit.db`) with timestamps, confidence scores, and duration.

### Real-Time Configuration

* **Model Selection** — Switch between ONNX detection models on the fly via a dropdown menu (auto-discovers `.onnx` files in `models/`).
* **Camera Selection** — Dropdown with real device names (via `QMediaDevices`) and a **Refresh** button to detect newly connected cameras, including virtual cameras through a DirectShow fallback.
* **Live Sensitivity Tuning** — Adjust detection confidence threshold and persistence frames in real time without restarting.

### Global Hotkey Unlock

* **Ctrl + Alt + L** — System-wide hotkey (via `pynput`) that instantly dismisses the shield overlay and pauses monitoring. Works even when the application is not focused or the shield is covering the screen.

### Virtual Camera Bridge

* **App Sharing via `pyvirtualcam`** — Broadcasts the live camera feed to a virtual device (e.g., "OBS Virtual Camera"), allowing Zoom, Teams, and other apps to use the LensBlock-protected feed.
* Even when monitoring is paused, the virtual camera continues streaming so you remain visible in meetings.

### Debug Mode

* **Live YOLO Visualization** — A resizable always-on-top window showing the raw camera feed with bounding boxes, class labels, and confidence percentages for all detected objects.
* **Information Overlay** — Real-time FPS counter, system status (`Monitoring` / `Shield Active`), and total detection count rendered directly on the debug frame.
* **Threat Highlighting** — Cell phones are boxed in **red**, all other detected objects in **green**.
* Automatically pauses threat evaluation while active so the shield won't trigger during development or testing.

### Persistent Stream Architecture

* The hardware camera is initialized **once at startup** and never released until the app closes, eliminating MSMF deadlocks and frozen frames when toggling monitoring.
* Pause/Resume is handled via a soft boolean flag — the camera buffer stays fresh at all times.

---

## System Requirements

* **Python** 3.11.x (required for `onnxruntime-directml` compatibility)
* **Windows** 10/11
* A connected webcam or video input device
* [Microsoft Visual C++ Redistributable (2015-2022)](https://aka.ms/vs/17/release/vc_redist.x64.exe)
* *(Optional)* [OBS Studio](https://obsproject.com/) with Virtual Camera activated — required for the virtual camera bridge

---

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Therm1te/LensBlock.git
   cd LensBlock
   ```

2. **Create and activate a virtual environment:**

   ```powershell
   py -3.11 -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```powershell
   pip install -r requirements.txt
   ```

4. **Prepare the ML model:**
   Ensure a YOLOv26 ONNX model (e.g., `yolov26.onnx`) is placed inside the `models/` directory.

---

## Configuration (`config.yaml`)

All settings can be adjusted live from the dashboard, but the following file stores persisted defaults:

```yaml
detection:
  confidence_threshold: 0.75       # 0.0–1.0, confidence required to classify a threat
  lockout_duration_seconds: 10     # Penalty timer after threat removal
  persistence_frames: 1            # Consecutive threat frames before triggering lockdown
  model_path: models/yolov26.onnx  # Active ONNX model path

logging:
  enable_forensic_logging: true    # Toggle SQLite audit logging

system:
  camera_index: 0                  # Default camera device index
  start_on_boot: false             # Auto-start with Windows
```

---

## Usage

### Launch

```powershell
python main.py
```

LensBlock starts as a **system tray daemon**. A shield icon will appear in your Windows system tray.

### System Tray Actions

| Action | How |
|---|---|
| Open Dashboard | Double-click the tray icon |
| Pause / Resume | Right-click → **Pause Monitoring** / **Resume Monitoring** |
| Exit | Right-click → **Exit LensBlock** |

### Dashboard Controls

| Control | Description |
|---|---|
| **Camera Source** dropdown | Select from detected cameras. Click **Refresh** to rescan for new devices. |
| **ONNX Model** dropdown | Switch detection models on the fly. |
| **Detection Sensitivity** slider | Set the confidence threshold (50%–90%). |
| **Persistence Threshold** slider | Number of consecutive frames required to trigger (1–5). |
| **Enable Forensic Logging** | Toggle SQLite audit trail. |
| **Start on Boot** | Auto-launch with Windows. |
| **Enable Debug View** button | Opens the YOLO debug window (pauses monitoring). |
| **View Recent Logs** button | Shows the last 5 threat incidents from the database. |
| **Live Preview** | Blurred camera feed at the bottom of the dashboard. |

### Global Hotkey

Press **`Ctrl + Alt + L`** at any time to:

1. Instantly dismiss the shield overlay.
2. Pause all AI monitoring.
3. Status changes to **UNLOCKED**.

Resume monitoring from the tray menu (**Resume Monitoring**).

### Debug Mode

1. Open the Dashboard.
2. Click **Enable Debug View**.
3. A resizable window opens showing the live YOLO feed with:
   * Bounding boxes and confidence labels on all detected objects.
   * FPS, system status, and detection count overlay.
4. Monitoring is paused while debug mode is active — no shield will trigger.
5. Click **Disable Debug View** to return to normal armed operation.

### Virtual Camera (Zoom / Teams Integration)

1. Install [OBS Studio](https://obsproject.com/) and activate the **Virtual Camera** (`Tools → Start Virtual Camera`).
2. Launch LensBlock — look for `"Virtual Camera started: OBS Virtual Camera"` in the console.
3. In Zoom/Teams, select **"OBS Virtual Camera"** as your camera input.
4. Your protected feed is now streaming to the meeting. When you pause monitoring, the clean (unannotated) feed continues flowing.

---

## Architecture

```
LensBlock/
├── main.py                    # Application entry point & system tray management
├── config.py                  # YAML configuration handler
├── config.yaml                # Persisted settings
│
├── core/
│   ├── engine.py              # YOLOv8 ONNX inference (detect + detect_debug)
│   └── camera.py              # Persistent OpenCV camera stream with soft pause
│
├── security/
│   ├── controller.py          # QThread: inference loop, threat state machine, virtual cam
│   ├── hotkey_manager.py      # pynput global hotkey listener (Ctrl+Alt+L)
│   └── logger.py              # SQLite forensic audit logger
│
├── ui/
│   ├── dashboard.py           # Settings dashboard (dropdowns, sliders, debug toggle)
│   ├── shield.py              # Multi-monitor "Secure Enclave" lock screen
│   └── debug_view.py          # Resizable YOLO debug visualization window
│
├── models/                    # ONNX model weights
├── media/                     # Application icons and assets
└── requirements.txt           # Python dependencies
```

### Key Design Decisions

* **Persistent Camera Handle** — `CameraStream` opens the device once and holds it for the lifetime of the application. This prevents MSMF backend deadlocks that occur when repeatedly opening/closing `cv2.VideoCapture` on Windows.
* **Thread Safety** — All background processing runs in a `QThread`. Communication with the UI happens exclusively through `pyqtSignal` emissions, preventing cross-thread access violations.
* **Soft Pause** — Pausing monitoring only flips a boolean flag. The camera thread continues draining frames to keep the buffer fresh and the virtual camera fed.

---

## License

See [LICENSE](LICENSE) for details.
