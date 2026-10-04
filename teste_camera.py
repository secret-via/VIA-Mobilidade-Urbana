import cv2
import time

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

print("CAMERA:", cap.isOpened())

inicio = time.time()
frames = 0

while time.time() - inicio < 15:
    ok, frame = cap.read()

    if not ok:
        print("ERRO AO LER FRAME")
        break

    frames += 1
    cv2.imshow("Teste da Camera", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

print("FRAMES CAPTURADOS:", frames)