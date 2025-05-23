from flask import Flask, Response
import cv2
import imutils
import datetime
import mysql.connector

app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

# Database config (kept in case needed later)
db_config = {
    'host': '192.168.1.13',
    'user': 'root',
    'password': '',
    'database': 'monitoring'
}

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            frame = imutils.resize(frame, width=640)
            
            # Just stream the frame as-is without any detection or annotations
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return '''
        <h1>Room Monitoring</h1>
        <img src="/video" width="640"><br><br>
        <p>Live monitoring stream.</p>
    '''

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
