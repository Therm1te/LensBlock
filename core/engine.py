import onnxruntime as ort
import numpy as np
import cv2


class YoloV8Engine:
    # Cooldown: number of frames to keep blurring after a threat disappears
    THREAT_COOLDOWN_FRAMES = 10
    # Safety margin: expand bounding boxes by this percentage in all directions
    ROI_PADDING_PERCENT = 0.20
    # Heavy blur kernel - large enough to resist AI sharpening reversal
    BLUR_KERNEL = (99, 99)

    def __init__(self, model_path="models/yolov8n.onnx"):
        # We attempt to use DirectML for GPU acceleration on Windows, falling back to CPU if unavailable.
        providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
        
        try:
            self.session = ort.InferenceSession(model_path, providers=providers)
            print(f"ONNX Runtime initialized with providers: {self.session.get_providers()}")
        except Exception as e:
            print(f"Failed to load ONNX model at {model_path}. Error: {e}")
            self.session = None
            return

        # YOLOv8 input names and shapes dynamically obtained from the ONNX session
        model_inputs = self.session.get_inputs()
        self.input_name = model_inputs[0].name
        self.input_shape = model_inputs[0].shape # e.g., [1, 3, 640, 640]
        self.input_width = self.input_shape[3] if isinstance(self.input_shape[3], int) else 640
        self.input_height = self.input_shape[2] if isinstance(self.input_shape[2], int) else 640

        self.output_names = [output.name for output in self.session.get_outputs()]

        # COCO class ID for cell phone is 67
        self.target_class_id = 67

        # Threat memory: dict of threat_id -> { "box": (x1, y1, x2, y2), "cooldown": int }
        self.active_threats = {}
        self._next_threat_id = 0

    def _preprocess(self, image):
        """
        Prepares the OpenCV BGR image for YOLOv8 inference.
        Resize -> Convert BGR to RGB -> Normalize -> Transpose -> Add batch dimension
        """
        # 1. Resize image to model input shape
        img = cv2.resize(image, (self.input_width, self.input_height))
        
        # 2. Convert from BGR (OpenCV default) to RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 3. Normalize intensity values (0-255 -> 0.0-1.0)
        img = img.astype(np.float32) / 255.0
        
        # 4. HWC (Height, Width, Channels) to CHW (Channels, Height, Width)
        img = np.transpose(img, (2, 0, 1))
        
        # 5. Add batch dimension (BCHW)
        img = np.expand_dims(img, axis=0)
        
        return img

    def _postprocess(self, outputs, orig_img_shape):
        """
        Processes YOLOv8 model outputs to find our target class (cell phone).
        YOLOv8 output shape is typically [batch_size, num_classes + 4, num_anchors]
        E.g., for COCO (80 classes) it is [1, 84, 8400]
        """
        predictions = outputs[0]  # Take the first batch
        
        # Transpose to [num_anchors, 84] for easier iteration
        predictions = np.transpose(predictions, (0, 2, 1))[0] 
        
        best_confidence = 0.0
        detected = False
        
        for pred in predictions:
            # Classes start at index 4 (0: x, 1: y, 2: w, 3: h)
            class_scores = pred[4:]
            
            # For performance, we can just check our target class directly
            if len(class_scores) > self.target_class_id:
                phone_score = class_scores[self.target_class_id]
                if phone_score > best_confidence:
                    best_confidence = phone_score
                    detected = True

        return detected, float(best_confidence)

    def detect(self, frame):
        """
        Runs full detection pipeline (Preprocess -> Inference -> Postprocess)
        """
        if self.session is None or frame is None:
            return False, 0.0

        # Create input tensor
        input_tensor = self._preprocess(frame)
        
        # Run inference
        try:
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
            
            # Postprocess outputs specifically looking for class 67 (cell phone)
            detected, confidence = self._postprocess(outputs, frame.shape)
            return detected, confidence
        except Exception as e:
            print(f"Inference error: {e}")
            return False, 0.0

    def _pad_box(self, x1, y1, x2, y2, img_w, img_h):
        """Expands a bounding box by ROI_PADDING_PERCENT in all directions."""
        bw = x2 - x1
        bh = y2 - y1
        pad_x = int(bw * self.ROI_PADDING_PERCENT)
        pad_y = int(bh * self.ROI_PADDING_PERCENT)
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(img_w, x2 + pad_x),
            min(img_h, y2 + pad_y),
        )

    def _iou(self, boxA, boxB):
        """Computes Intersection-over-Union between two (x1, y1, x2, y2) boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        union = areaA + areaB - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _apply_heavy_blur(frame, x1, y1, x2, y2, kernel):
        """Applies a stacked heavy Gaussian blur to a region of the frame."""
        roi = frame[y1:y2, x1:x2]
        if roi.size > 0:
            # Double-stack for irreversibility
            blurred = cv2.GaussianBlur(roi, kernel, 0)
            blurred = cv2.GaussianBlur(blurred, kernel, 0)
            frame[y1:y2, x1:x2] = blurred

    def detect_and_censor(self, frame, conf_threshold=0.25):
        """
        Runs inference and returns two frames with temporal hysteresis:
          - clean_censored: Only threat regions blurred (heavy, padded) — for virtual camera.
          - annotated_preview: Blurs + indicator boxes / borders — for dashboard preview.
        Returns (detected, best_phone_conf, clean_censored, annotated_preview, detection_count).
        
        Threat Memory ensures that if YOLO misses a frame, the blur persists
        for THREAT_COOLDOWN_FRAMES before being removed.
        """
        if self.session is None or frame is None:
            return False, 0.0, frame, frame, 0

        input_tensor = self._preprocess(frame)
        try:
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        except Exception as e:
            print(f"Inference error: {e}")
            return False, 0.0, frame, frame, 0

        predictions = outputs[0]
        predictions = np.transpose(predictions, (0, 2, 1))[0]

        orig_h, orig_w = frame.shape[:2]
        scale_x = orig_w / self.input_width
        scale_y = orig_h / self.input_height

        # --- 1. Gather current-frame detections ---
        current_detections = []  # list of (x1, y1, x2, y2) for threats
        best_phone_conf = 0.0
        phone_detected = False
        detection_count = 0

        for pred in predictions:
            x_c, y_c, bw, bh = pred[0], pred[1], pred[2], pred[3]
            class_scores = pred[4:]
            class_id = int(np.argmax(class_scores))
            score = float(class_scores[class_id])

            if score < conf_threshold:
                continue

            detection_count += 1
            is_threat = (class_id == self.target_class_id)

            if is_threat:
                if score > best_phone_conf:
                    best_phone_conf = score
                    phone_detected = True

                x1 = max(0, int((x_c - bw / 2) * scale_x))
                y1 = max(0, int((y_c - bh / 2) * scale_y))
                x2 = min(orig_w, int((x_c + bw / 2) * scale_x))
                y2 = min(orig_h, int((y_c + bh / 2) * scale_y))
                current_detections.append((x1, y1, x2, y2))

        # --- 2. Update Threat Memory (hysteresis buffer) ---
        matched_ids = set()
        for det_box in current_detections:
            best_match_id = None
            best_iou = 0.3  # Minimum IoU to consider it the same object
            for tid, threat in self.active_threats.items():
                iou = self._iou(det_box, threat["box"])
                if iou > best_iou:
                    best_iou = iou
                    best_match_id = tid

            if best_match_id is not None:
                # Update existing threat with new position
                self.active_threats[best_match_id]["box"] = det_box
                self.active_threats[best_match_id]["cooldown"] = 0
                matched_ids.add(best_match_id)
            else:
                # New threat
                self.active_threats[self._next_threat_id] = {
                    "box": det_box,
                    "cooldown": 0,
                }
                matched_ids.add(self._next_threat_id)
                self._next_threat_id += 1

        # Age out unmatched threats
        expired = []
        for tid, threat in self.active_threats.items():
            if tid not in matched_ids:
                threat["cooldown"] += 1
                if threat["cooldown"] > self.THREAT_COOLDOWN_FRAMES:
                    expired.append(tid)
        for tid in expired:
            del self.active_threats[tid]

        # --- 3. Apply blurs from ALL active threats (current + remembered) ---
        clean = frame.copy()
        annotated = frame.copy()

        for tid, threat in self.active_threats.items():
            box = threat["box"]
            # Expand with safety margin
            px1, py1, px2, py2 = self._pad_box(*box, orig_w, orig_h)

            # Heavy stacked blur on both frames
            self._apply_heavy_blur(clean, px1, py1, px2, py2, self.BLUR_KERNEL)
            self._apply_heavy_blur(annotated, px1, py1, px2, py2, self.BLUR_KERNEL)

            # Glow border on annotated ONLY
            is_cooling = threat["cooldown"] > 0
            border_color = (0, 140, 255) if is_cooling else (0, 0, 200)  # Orange if fading
            cv2.rectangle(annotated, (px1, py1), (px2, py2), border_color, 2)
            cv2.rectangle(annotated, (px1-1, py1-1), (px2+1, py2+1), (0, 0, 120), 1)

        return phone_detected, best_phone_conf, clean, annotated, detection_count

    def clear_threat_memory(self):
        """Resets the hysteresis buffer (e.g. when switching modes)."""
        self.active_threats.clear()
        self._next_threat_id = 0
