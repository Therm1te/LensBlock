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

    def _letterbox(self, img, new_shape=(640, 640), color=(114, 114, 114)):
        """Resizes and pads image to preserve aspect ratio"""
        shape = img.shape[:2]  # current shape [height, width]
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
        dw /= 2  # divide padding into 2 sides
        dh /= 2
        
        if shape[::-1] != new_unpad:  # resize
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
            
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
        return img, r, (dw, dh)

    def _preprocess(self, image):
        """
        Prepares the OpenCV BGR image for YOLOv8 inference.
        Letterbox Resize -> Convert BGR to RGB -> Normalize -> Transpose -> Add batch dimension
        """
        # 1. Letterbox resize image to model input shape preserving aspect ratio
        img, ratio, pad = self._letterbox(image, new_shape=(self.input_width, self.input_height))
        
        # 2. Convert from BGR (OpenCV default) to RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 3. Normalize intensity values (0-255 -> 0.0-1.0)
        img = img.astype(np.float32) / 255.0
        
        # 4. HWC (Height, Width, Channels) to CHW (Channels, Height, Width)
        img = np.transpose(img, (2, 0, 1))
        
        # 5. Add batch dimension (BCHW)
        img = np.expand_dims(img, axis=0)
        
        return img, ratio, pad

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
        input_tensor, _, _ = self._preprocess(frame)
        
        # Run inference
        try:
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
            
            # Postprocess outputs specifically looking for class 67 (cell phone)
            detected, confidence = self._postprocess(outputs, frame.shape)
            return detected, confidence
        except Exception as e:
            print(f"Inference error: {e}")
            return False, 0.0

    def detect_with_boxes(self, frame, conf_threshold=None):
        """
        Runs detection and returns bounding boxes for all threat-class objects.
        Returns (detected, best_confidence, threat_boxes)
        where threat_boxes is a list of (x1, y1, x2, y2) in original frame coords.
        """
        if self.session is None or frame is None:
            return False, 0.0, []

        if conf_threshold is None:
            conf_threshold = 0.25

        input_tensor, ratio, pad = self._preprocess(frame)

        try:
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        except Exception as e:
            print(f"Inference error: {e}")
            return False, 0.0, []

        predictions = np.transpose(outputs[0], (0, 2, 1))[0]
        orig_h, orig_w = frame.shape[:2]
        pad_w, pad_h = pad

        best_conf = 0.0
        detected = False
        threat_boxes = []

        for pred in predictions:
            x_c, y_c, bw, bh = pred[0], pred[1], pred[2], pred[3]
            class_scores = pred[4:]

            if len(class_scores) <= self.target_class_id:
                continue

            score = float(class_scores[self.target_class_id])
            if score < conf_threshold:
                continue

            detected = True
            if score > best_conf:
                best_conf = score

            x1 = max(0, int((x_c - bw / 2 - pad_w) / ratio))
            y1 = max(0, int((y_c - bh / 2 - pad_h) / ratio))
            x2 = min(orig_w, int((x_c + bw / 2 - pad_w) / ratio))
            y2 = min(orig_h, int((y_c + bh / 2 - pad_h) / ratio))
            threat_boxes.append((x1, y1, x2, y2))

        return detected, best_conf, threat_boxes
