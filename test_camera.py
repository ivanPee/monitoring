import cv2
from flask import Flask, Response
import time
import atexit

app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        frame = cv2.resize(frame, (320, 240))  # Resize to reduce load
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])  # Lower quality
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    # Simple page to display video stream
    return """
    <html>
        <body>
            <h1>Camera Stream</h1>
            <img src="/video_feed" width="640" height="480" />
        </body>
    </html>
    """

@atexit.register
def cleanup():
    camera.release()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
