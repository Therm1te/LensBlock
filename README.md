# LensBlock

> A dual-mode visual privacy suite preventing unauthorized recording of sensitive information.

LensBlock is a desktop security daemon that uses your webcam to monitor the immediate physical environment for visual recording devices (e.g., cell phones). It operates in two protection modes:

* **Shield Mode** — Locks down all monitors with an opaque full-screen overlay.
* **Censorship Mode** — Selectively blurs detected threats in real-time, keeping the rest of the feed visible for video calls.

---

## Features

### Shield Mode (v1)

* **Zero-Trust Visual Shield** — Instantly obfuscates all connected monitors when a recording device enters the camera's field of view.
* **Penalty Lockout Timer** — Configurable delay that holds the system in lockdown for *X* seconds even after the threat is removed.
* **Multi-Monitor Enforcement** — Aggressively intercepts focus and scales across any number of active displays.
* **Virtual Camera Lockout** — During shield lockdown, the virtual camera feed is replaced with a centered "PRIVACY BLOCKED" graphic.

### Censorship Mode (v2)

* **Real-Time Object Blurring** — Detects threats and applies a heavy Gaussian blur to only the threat region, keeping the rest of the frame clean for Zoom/Teams calls.
* **Temporal Buffer (Hysteresis)** — Tracked threats persist for 10 frames after YOLO loses detection, eliminating flicker. Uses IoU-based matching to track objects across frames.
* **ROI Safety Margin** — Every bounding box is expanded by 20% in all directions, ensuring fast-moving objects can't leak pixels outside the blur zone.
* **Frame-Drop Prevention** — If inference exceeds 50ms, the last safely-censored frame is re-sent to the virtual camera. Zero "naked" frames ever reach the stream.
* **Irreversible Blur** — Triple-stacked `(99, 99)` Gaussian kernel that cannot be reversed by AI sharpening or deblurring tools.

### Common Features

* **High-Performance Inference** — Uses `YOLOv8` backed by `ONNX Runtime` with optional DirectML GPU acceleration.
* **Forensic Auditing** — Every threat incident is logged into an SQLite evidence database (`lensblock_audit.db`) with timestamps, confidence scores, and duration.
* **Native Resolution** — The virtual camera matches the hardware camera's actual resolution, preventing stretching or aspect ratio distortion.

### Real-Time Configuration

* **Model Selection** — Switch between ONNX detection models on the fly via a dropdown menu (auto-discovers `.onnx` files in `models/`).
* **Camera Selection** — Dropdown with real device names (via `QMediaDevices`) and a **Refresh** button to detect newly connected cameras, including virtual cameras through a DirectShow fallback.
* **Live Sensitivity Tuning** — Adjust detection confidence threshold and persistence frames in real time without restarting.

### Global Hotkey Unlock

* **Ctrl + Alt + L** — System-wide hotkey (via `pynput`) that instantly dismisses the shield overlay and pauses monitoring. Works even when the application is not focused or the shield is covering the screen.

### Virtual Camera Bridge

* **App Sharing via `pyvirtualcam`** — Broadcasts the live camera feed to a virtual device (e.g., "OBS Virtual Camera") at the camera's native resolution.
* In **Shield Mode**, the virtual camera shows a "PRIVACY BLOCKED" graphic during lockdown.
* In **Censorship Mode**, the virtual camera shows the live feed with threats blurred out.
* Even when monitoring is paused, the virtual camera continues streaming so you remain visible in meetings.

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
| **Protection Mode** button | Toggle between 🛡️ Shield Mode and 🔍 Censorship Mode. |
| **Enable Forensic Logging** | Toggle SQLite audit trail. |
| **Start on Boot** | Auto-launch with Windows. |
| **View Recent Logs** button | Shows the last 5 threat incidents from the database. |
| **Live Preview** | Blurred camera feed at the bottom of the dashboard. |

### Global Hotkey

Press **`Ctrl + Alt + L`** at any time to:

1. Instantly dismiss the shield overlay.
2. Pause all AI monitoring.
3. Status changes to **UNLOCKED**.

Resume monitoring from the tray menu (**Resume Monitoring**).

### Shield Mode vs Censorship Mode

| | Shield Mode | Censorship Mode |
|---|---|---|
| **Trigger** | Full-screen blackout on all monitors | Selective blur on threat regions only |
| **Virtual Camera** | "PRIVACY BLOCKED" graphic | Live feed with threats blurred |
| **Use Case** | Protecting local screen from visual spying | Staying in a video call while hiding devices |
| **Logging** | ✅ Forensic audit | ✅ Forensic audit (tagged as "censored") |

### Virtual Camera (Zoom / Teams Integration)

1. Install [OBS Studio](https://obsproject.com/) and activate the **Virtual Camera** (`Tools → Start Virtual Camera`).
2. Launch LensBlock — look for `"Virtual Camera started: OBS Virtual Camera (WxH)"` in the console.
3. In Zoom/Teams, select **"OBS Virtual Camera"** as your camera input.
4. In **Shield Mode**, your coworkers see a "PRIVACY BLOCKED" image during lockdown.
5. In **Censorship Mode**, your coworkers see your live feed with phones/threats blurred out in real time.

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
* **Native Resolution Pass-through** — The virtual camera is initialized to the hardware camera's actual resolution (`actual_width × actual_height`), preventing aspect ratio distortion.
* **Thread Safety** — All background processing runs in a `QThread`. Communication with the UI happens exclusively through `pyqtSignal` emissions, preventing cross-thread access violations.
* **Soft Pause** — Pausing monitoring only flips a boolean flag. The camera thread continues draining frames to keep the buffer fresh and the virtual camera fed.
* **Temporal Coherence** — Censorship mode uses IoU-based threat tracking with a 10-frame cooldown to eliminate detection flicker, plus a 50ms frame-drop guard to prevent raw frames from leaking.

---

## License

See [LICENSE](LICENSE) for details.
