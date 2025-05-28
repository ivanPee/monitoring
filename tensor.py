from flask import Flask, Response
import cv2
import numpy as np
import threading
import time
import tflite_runtime.interpreter as tflite

app = Flask(__name__)

# Load TFLite model once
interpreter = tflite.Interpreter(model_path="detect.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
height, width = input_details[0]['shape'][1:3]
floating_model = input_details[0]['dtype'] == np.float32
PERSON_CLASS_ID = 0

# Shared frame and lock
output_frame = None
lock = threading.Lock()

# Initialize camera (smaller resolution)
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
camera.set(cv2.CAP_PROP_FPS, 10)

def detect_humans(frame):
    # Resize frame to model input size
    img = cv2.resize(frame, (width, height))
    input_data = np.expand_dims(img, axis=0)
    if floating_model:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    boxes = interpreter.get_tensor(output_details[0]['index'])[0]
    classes = interpreter.get_tensor(output_details[1]['index'])[0]
    scores = interpreter.get_tensor(output_details[2]['index'])[0]

    person_detected = False
    for i in range(len(scores)):
        if scores[i] > 0.5 and int(classes[i]) == PERSON_CLASS_ID:
            person_detected = True
            break

    # Optionally, add overlay if person detected
    if person_detected:
        cv2.putText(frame, "Person detected", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 
                    1, (0,255,0), 2)
    return frame

def camera_thread():
    global output_frame
    frame_count = 0
    while True:
        ret, frame = camera.read()
        if not ret:
            time.sleep(0.1)
            continue

        # Detect every 3rd frame to save CPU
        if frame_count % 3 == 0:
            frame = detect_humans(frame)

        with lock:
            output_frame = frame.copy()
        frame_count += 1

def generate_frames():
    global output_frame
    while True:
        with lock:
            if output_frame is None:
                continue
            ret, jpeg = cv2.imencode('.jpg', output_frame)
            if not ret:
                continue
            frame = jpeg.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.1)  # control streaming FPS (~10fps)

@app.route('/')
def index():
    return '<img src="/video_feed" width="320" height="240">'

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    t = threading.Thread(target=camera_thread)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
