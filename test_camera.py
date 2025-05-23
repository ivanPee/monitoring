from flask import Flask, Response
import cv2

app = Flask(__name__)

# Open camera (use 0 or the right device index)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            # Yield frame in HTTP multipart format for MJPEG streaming
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    # Video streaming route
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    # Simple page with video stream embedded
    return '''
    <html><body>
    <h1>Camera Stream</h1>
    <img src="/video_feed" width="640" height="480" />
    </body></html>
    '''

if __name__ == '__main__':
    # Run server on your local network IP, port 5000, accessible by other devices
    app.run(host='0.0.0.0', port=5000, debug=True)
