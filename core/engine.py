import onnxruntime as ort
import numpy as np
import cv2

class YoloV8Engine:
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

    def detect_debug(self, frame, conf_threshold=0.25):
        """
        Runs full detection and returns an annotated frame with bounding boxes,
        class labels, and confidence scores for ALL detected objects.
        Returns (detected, best_phone_confidence, annotated_frame, detection_count).
        """
        if self.session is None or frame is None:
            return False, 0.0, frame, 0

        input_tensor = self._preprocess(frame)

        try:
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        except Exception as e:
            print(f"Inference error: {e}")
            return False, 0.0, frame, 0

        predictions = outputs[0]
        predictions = np.transpose(predictions, (0, 2, 1))[0]

        orig_h, orig_w = frame.shape[:2]
        annotated = frame.copy()

        best_phone_conf = 0.0
        phone_detected = False
        detection_count = 0

        # COCO class names (subset for display)
        coco_names = {
            0: "person", 39: "bottle", 41: "cup", 56: "chair",
            62: "tv", 63: "laptop", 66: "keyboard", 67: "cell phone",
            73: "book", 74: "clock",
        }

        for pred in predictions:
            # x_center, y_center, w, h are in model input scale
            x_c, y_c, bw, bh = pred[0], pred[1], pred[2], pred[3]
            class_scores = pred[4:]

            class_id = int(np.argmax(class_scores))
            score = float(class_scores[class_id])

            if score < conf_threshold:
                continue

            detection_count += 1

            # Check if it's our target class
            if class_id == self.target_class_id and score > best_phone_conf:
                best_phone_conf = score
                phone_detected = True

            # Scale bounding box back to original frame coordinates
            scale_x = orig_w / self.input_width
            scale_y = orig_h / self.input_height

            x1 = int((x_c - bw / 2) * scale_x)
            y1 = int((y_c - bh / 2) * scale_y)
            x2 = int((x_c + bw / 2) * scale_x)
            y2 = int((y_c + bh / 2) * scale_y)

            # Threat targets get red, everything else gets green
            is_threat = (class_id == self.target_class_id)
            color = (0, 0, 255) if is_threat else (0, 200, 0)
            thickness = 2 if is_threat else 1

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)

            label_name = coco_names.get(class_id, f"cls_{class_id}")
            label = f"{label_name} {score:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return phone_detected, best_phone_conf, annotated, detection_count
