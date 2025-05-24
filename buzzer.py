import cv2
from flask import Flask, Response
import time
import atexit
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
import threading
import spidev

# -------------------- GPIO + LCD SETUP --------------------
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

lcd = CharLCD('PCF8574', 0x27)

# -------------------- SPI + LIGHT SENSOR SETUP --------------------
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

# Light Detection Threshold
LIGHT_THRESHOLD = 300
countdown_seconds = 60
countdown_active = False
countdown_lock = threading.Lock()

def read_light_channel(channel=0):
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    value = ((adc[1] & 3) << 8) + adc[2]
    return value

def trigger_buzzer():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    lcd.clear()
    lcd.write_string("🔔 Buzzing!")
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    lcd.clear()

def light_monitor():
    global countdown_active

    while True:
        light_level = read_light_channel()
        if light_level > LIGHT_THRESHOLD:
            with countdown_lock:
                if not countdown_active:
                    countdown_active = True
                    threading.Thread(target=countdown_and_buzz, daemon=True).start()
        time.sleep(2)

def countdown_and_buzz():
    global countdown_active

    lcd.clear()
    lcd.write_string("Light Detected!")
    for i in range(countdown_seconds, 0, -1):
        light_level = read_light_channel()
        if light_level < LIGHT_THRESHOLD:
            lcd.clear()
            lcd.write_string("Light Gone!")
            countdown_active = False
            time.sleep(2)
            lcd.clear()
            return
        lcd.clear()
        lcd.write_string(f"Countdown: {i}s")
        time.sleep(1)

    trigger_buzzer()
    countdown_active = False

# -------------------- CAMERA + FLASK --------------------
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
        </body>
    </html>
    """

# -------------------- CLEANUP --------------------
@atexit.register
def cleanup():
    print("Cleaning up...")
    lcd.clear()
    GPIO.cleanup()
    camera.release()
    spi.close()

# -------------------- START --------------------
if __name__ == '__main__':
    threading.Thread(target=light_monitor, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
