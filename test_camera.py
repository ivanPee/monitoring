import cv2
import time

camera = cv2.VideoCapture(0)
time.sleep(2)  # Wait for camera warm-up

while True:
    ret, frame = camera.read()
    if not ret:
        print("Failed to grab frame")
        break
    cv2.imshow("Camera Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

camera.release()
cv2.destroyAllWindows()
