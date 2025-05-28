import cv2
import numpy as np
import time
import tflite_runtime.interpreter as tflite

# Load TFLite model
interpreter = tflite.Interpreter(model_path="detect.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

height, width = input_details[0]['shape'][1:3]
floating_model = input_details[0]['dtype'] == np.float32
PERSON_CLASS_ID = 0

# Initialize camera with low resolution
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 160)  # smaller resolution for speed
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)
camera.set(cv2.CAP_PROP_FPS, 5)             # low fps

def detect_humans(frame):
    img = cv2.resize(frame, (width, height))
    input_data = np.expand_dims(img, axis=0)

    if floating_model:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    boxes = interpreter.get_tensor(output_details[0]['index'])[0]
    classes = interpreter.get_tensor(output_details[1]['index'])[0]
    scores = interpreter.get_tensor(output_details[2]['index'])[0]

    for i in range(len(scores)):
        if scores[i] > 0.5 and int(classes[i]) == PERSON_CLASS_ID:
            return True
    return False

print("Starting detection loop. Press Ctrl+C to stop.")

try:
    while True:
        ret, frame = camera.read()
        if not ret:
            time.sleep(0.1)
            continue

        if detect_humans(frame):
            print("Person detected!")
        else:
            print("No person detected.")

        # Delay to reduce CPU usage (adjust as needed)
        time.sleep(1.0)

except KeyboardInterrupt:
    print("Stopping detection.")

camera.release()
