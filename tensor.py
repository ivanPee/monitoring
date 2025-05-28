from flask import Flask, Response
import cv2
import numpy as np
import tflite_runtime.interpreter as tflite
import platform

app = Flask(__name__)

# Load TFLite model
interpreter = tflite.Interpreter(model_path="detect.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]

floating_model = input_details[0]['dtype'] == np.float32

# Human class index in COCO is 0 or 1 depending on model
PERSON_CLASS_ID = 0

# Initialize webcam
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

def detect_humans(frame):
    img = cv2.resize(frame, (width, height))
    input_data = np.expand_dims(img, axis=0)

    if floating_model:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    boxes = interpreter.get_tensor(output_details[0]['index'])[0]  # Bounding box coordinates
    classes = interpreter.get_tensor(output_details[1]['index'])[0]  # Class index
    scores = interpreter.get_tensor(output_details[2]['index'])[0]  # Confidence scores

    for i in range(len(scores)):
        if scores[i] > 0.5 and int(classes[i]) == PERSON_CLASS_ID:
            ymin, xmin, ymax, xmax = boxes[i]
            (imH, imW) = frame.shape[:2]
            (startX, startY, endX, endY) = (int(xmin * imW), int(ymin * imH),
                                            int(xmax * imW), int(ymax * imH))
            cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)
            cv2.putText(frame, f'Person: {int(scores[i]*100)}%',
                        (startX, startY - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 2)
    return frame

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        frame = detect_humans(frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return '''
    <html>
        <head><title>Human Detection Stream</title></head>
        <body>
            <h1>Raspberry Pi Human Detection</h1>
            <img src="/video_feed" width="640" height="480">
        </body>
    </html>
    '''

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
