from ultralytics import YOLO

# Loading YOLOv8n
model = YOLO("yolo26n.pt")

model.export(format="onnx", opset=17)