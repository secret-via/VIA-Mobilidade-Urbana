import cv2
from ultralytics import YOLO

MODEL = "runs/transito/weights/best.pt"

model = YOLO(MODEL)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

print("CAMERA:", cap.isOpened())
print("MODELO:", MODEL)

while True:
    ok, frame = cap.read()

    if not ok:
        print("ERRO AO LER CAMERA")
        break

    results = model.track(
        frame,
        persist=True,
        conf=0.25,
        verbose=False
    )

    annotated = results[0].plot()

    cv2.imshow("YOLO - Camera", annotated)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()