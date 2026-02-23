**Product Name:** LensBlock

**Version:** 1.0 (Local MVP)

**Track:** Computer Vision (AI Bootcamp Final Project)

**1. Product Overview**

**Vision:** To close the \"Analog Loophole\" in data security by
providing an automated, intelligent defense against visual data
exfiltration and negligent insider leaks.

**Objective:** Build an edge-native, UI-based computer vision
application that monitors a user\'s physical environment via webcam and
instantly obfuscates the screen if a recording device
(smartphone/camera) is detected.

**2. Target Audience & Use Cases**

- **Security Operations Centers (SOCs):** Analysts working with
  classified data who must strictly adhere to a \"Clean Desk / No
  Photography\" policy.

- **Remote Corporate Workers:** Employees handling PII/PHI (Medical or
  Financial records) in uncontrolled environments.

- **Online Proctored Exams:** Ensuring students do not use phones to
  capture test questions.

**3. Technical Specifications & Stack**

- **Core Language:** Python 3.11

- **AI / Vision Model:** YOLOv8-Nano (COCO pre-trained, focusing on
  Class ID 67: cell phone).

- **Inference Engine:** ONNX Runtime (onnxruntime-directml).

  - *Hardware Target:* Capable of hardware acceleration on AMD RX 6600XT
    via DirectML, with seamless CPU fallback for low-end devices
    (onnxruntime).

- **Video Processing:** OpenCV (cv2).

- **Data Processing:** NumPy

- **Graphical User Interface (GUI):** PyQt6 (System tray support,
  settings dashboard, overlay window).

- **Local Database:** SQLite3 (Serverless, local file-based logging).

**4. Core Features (v1.0 Requirements)**

**Feature 1: Real-Time Threat Detection Pipeline**

- **Description:** A background thread dedicated to capturing video
  frames and running object detection.

- **Acceptance Criteria:**

  - Must capture video at a minimum of 30 FPS.

  - Model inference must execute in \<50ms per frame.

  - Must run asynchronously without freezing the UI thread.

**Feature 2: Heuristic Validation & Persistence Check**

- **Description:** A logic layer to prevent false positives caused by
  fast movements, shadows, or changing lighting conditions.

- **Acceptance Criteria:**

  - Must implement a Confidence Threshold (e.g., minimum 60% confidence
    to register a detection).

  - Must implement a rolling buffer (Persistence Check): The object must
    be detected in x consecutive frames (or x out of y frames) before a
    threat state is triggered.

  - Must reliably drop the threat state when the object is removed,
    regardless of room lighting.

**Feature 3: Dynamic Obfuscation Interface (The Shield)**

- **Description:** The visual response mechanism that protects the
  screen data.

- **Acceptance Criteria:**

  - An overlay window must sit above all other applications (\"Always on
    Top\").

  - Upon a verified threat, the overlay opacity must shift to 100%
    (Solid Black or Heavy Blur) in \<100ms.

  - Must automatically revert to 0% opacity (transparent) when the
    threat is neutralized.

  - Must support multi-monitor setups (shielding all connected
    displays).

**Feature 4: Forensic Audit Logger**

- **Description:** A local logging system to record security violations.

- **Acceptance Criteria:**

  - Must generate an entry in a local SQLite database for every
    confirmed threat event.

  - Log schema must include: IncidentID, Timestamp, Threat_Type,
    Confidence_Score, and Duration.

**Feature 5: Settings Dashboard & System Tray**

- **Description:** A user-facing GUI to manage the application state.

- **Acceptance Criteria:**

  - The application must run quietly in the system tray.

  - The dashboard must allow the user to toggle the system ON/OFF.

  - The dashboard must allow configuration of the Confidence Threshold
    and Persistence Frame count.

**5. Out of Scope (Deferred to v2.0)**

- **Remote Webhook / API Integration:** Sending JSON alerts to external
  SOC dashboards.

- **Gaze Tracking:** Requiring the user to look away from the screen to
  trigger the block.

- **Cloud Deployment:** LensBlock v1.0 is strictly local to guarantee
  privacy.

**6. User Flow (The \"Happy Path\")**

1. User launches LensBlock.exe. The app minimizes to the system tray.

2. User opens a sensitive dashboard (e.g., customer financial data).

3. User receives a text and raises their smartphone into the camera\'s
    field of view.

4. The Persistence pipeline registers the phone across 3 consecutive
    frames.

5. LensBlock instantly maximizes a black overlay across the screen.

6. User puts the phone down.

7. The screen overlay disappears, allowing the user to resume work.

8. The incident is silently logged to the local SQLite database.

**7. Critical Architecture Rule:** The application MUST use a
multi-threaded architecture using PyQt6 QThread and pyqtSignal.

- The OpenCV video capture and ONNX inference must run on a background
  QThread.

- The background thread must emit a pyqtSignal containing the threat
  state (Safe/Threat) to the Main UI Thread.

- The Main UI Thread is the ONLY thread allowed to update the Dashboard
  or trigger the Shield overlay. Do not execute blocking time.sleep()
  calls or cv2.imshow() loops in the main thread.
