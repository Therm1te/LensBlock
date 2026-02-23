import cv2

backends = [
    ("Media Foundation", cv2.CAP_MSMF),
    ("Default API", cv2.CAP_ANY),
    ("DirectShow", cv2.CAP_DSHOW)
]

for name, backend in backends:
    print(f"\n--- Testing Backend: {name} ---")
    cap = cv2.VideoCapture(0, backend)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"SUCCESS! Camera works perfectly with {name}.")
            cv2.imshow('Camera Test', frame)
            cv2.waitKey(3000)
            cap.release()
            cv2.destroyAllWindows()
            break
        else:
            print(f"Opened with {name}, but the frame is blank/empty.")
            cap.release()
    else:
        print(f"Failed to connect using {name}.")