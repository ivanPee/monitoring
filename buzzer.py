import cv2
from flask import Flask, Response
import time
import atexit
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
import threading

# -------------------- GPIO + LCD SETUP --------------------
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

lcd = CharLCD('PCF8574', 0x27)

# Buzzer alert function (in background thread)
def buzz_and_display():
    for i in range(5):
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        lcd.clear()
        lcd.write_string(f'Buzzing {i+1}')
        time.sleep(3)

        GPIO.output(BUZZER_PIN, GPIO.LOW)
        lcd.clear()
        lcd.write_string('Waiting...')
        time.sleep(3)
    lcd.clear()

# -------------------- CAMERA + FLASK SETUP --------------------
app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        frame = cv2.resize(frame, (320, 240))
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
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
    return """
    <html>
        <body>
            <h1>Camera Stream</h1>
            <img src="/video_feed" width="640" height="480" /><br/>
            <a href="/buzz">Trigger Buzzer</a>
        </body>
    </html>
    """

@app.route('/buzz')
def buzz():
    threading.Thread(target=buzz_and_display).start()
    return "🔔 Buzzer triggered!"

# -------------------- CLEANUP --------------------
@atexit.register
def cleanup():
    print("Cleaning up...")
    lcd.clear()
    GPIO.cleanup()
    camera.release()

# -------------------- RUN APP --------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
