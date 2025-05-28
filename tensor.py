from flask import Flask, Response
import cv2
import numpy as np
import tflite_runtime.interpreter as tflite

app = Flask(__name__)

# Load TFLite model
interpreter = tflite.Interpreter(model_path="detect.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]
floating_model = input_details[0]['dtype'] == np.float32
PERSON_CLASS_ID = 0

# Initialize camera
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

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

    # Just check for presence, no drawing
    for i in range(len(scores)):
        if scores[i] > 0.5 and int(classes[i]) == PERSON_CLASS_ID:
            print("Person detected!")
            break

    return frame

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        frame = detect_humans(frame)
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return '<img src="/video_feed" width="640" height="480">'

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
