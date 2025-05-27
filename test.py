import cv2
import time
import threading
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
import requests
import datetime
from flask import Flask, Response
import atexit
import json
import logging

# Setup logging for easier debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# --- GPIO and LCD setup ---
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

lcd = CharLCD('PCF8574', 0x27)
lcd.clear()
lcd.write_string("Starting...")

# --- Flask App and Camera ---
app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera_lock = threading.Lock()

# --- Control Variables ---
countdown_started = False
stop_countdown_flag = False
room_id = None
room_id_lock = threading.Lock()  # To protect access to room_id

# Common headers for HTTP requests (avoid disconnections)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; MonitoringBot/1.0)'
}

# --- Get Room ID ---
def get_room_id_by_stream_url():
    global room_id
    try:
        res = requests.get(
            'https://monitoring.42web.io/ajax/get_room_id.php',
            params={'code': 'RM123MB'},
            headers=HEADERS,
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        rid = data.get('room_id')
        if rid:
            with room_id_lock:
                room_id = rid
            logging.info(f"Room ID obtained: {room_id}")
        else:
            logging.warning(f"Room ID not found in response: {data}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error getting room_id: {e}")

# --- Check Schedule ---
def check_schedule_status(rid):
    now = datetime.datetime.now()
    # Adjusting weekday to 1-7 with Monday=1 ... Sunday=7
    current_day = (now.weekday() + 1) % 7 or 7
    current_time = now.strftime("%H:%M:%S")

    try:
        res = requests.get(
            'https://monitoring.42web.io/ajax/check_schedule.php',
            params={
                'room_id': rid,
                'schedule_day': current_day,
                'current_time': current_time
            },
            headers=HEADERS,
            timeout=5
        )
        res.raise_for_status()
        data = res.json()
        if data.get('success'):
            return data.get('status')
        else:
            logging.warning(f"Schedule check failed: {data}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Schedule check error: {e}")
    return None

# --- Flag Schedule ---
def handle_detection_action():
    with room_id_lock:
        rid = room_id
    if not rid:
        logging.warning("No room_id set, cannot flag schedule.")
        return

    try:
        res = requests.post(
            'https://monitoring.42web.io/ajax/flag_schedule.php',
            json={'room_id': rid},
            headers=HEADERS,
            timeout=5
        )
        if res.ok:
            message = res.json().get('message')
            logging.info(f"Flagged schedule: {message}")
        else:
            logging.error(f"Failed to flag schedule, status code: {res.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error flagging schedule: {e}")

# --- Alert and Countdown ---
def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    lcd.clear()
    lcd.write_string("Buzzing now!")
    time.sleep(10)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    lcd.clear()
    lcd.write_string("Monitoring...")

def countdown_and_buzz():
    global countdown_started, stop_countdown_flag

    logging.info("Light detected! Starting countdown...")

    for i in range(60, 0, -1):
        if stop_countdown_flag:
            logging.info("Detection Stopped.")
            lcd.clear()
            lcd.write_string("Countdown cancelled")
            time.sleep(2)
            lcd.clear()
            lcd.write_string("Monitoring...")
            countdown_started = False
            stop_countdown_flag = False
            return

        lcd.clear()
        lcd.write_string(f"Countdown: {i}s")
        time.sleep(1)

    handle_detection_action()
    buzzer_alert()
    countdown_started = False

# --- Monitoring Thread ---
def monitoring_loop():
    global countdown_started, stop_countdown_flag

    lcd.clear()
    lcd.write_string("Monitoring...")

    # Initial fetch of room_id
    get_room_id_by_stream_url()

    while True:
        with camera_lock:
            ret, frame = camera.read()
        if not ret:
            logging.warning("Failed to read frame from camera.")
            time.sleep(1)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        logging.debug(f"Brightness: {brightness:.2f}")

        light_on = brightness > 80

        with room_id_lock:
            rid = room_id
        if rid is None:
            logging.warning("Room ID not set, retrying...")
            get_room_id_by_stream_url()
            time.sleep(5)
            continue

        status = check_schedule_status(rid)
        logging.info(f"Status: {status}, Light: {'ON' if light_on else 'OFF'}")

        if status == "Occupied":
            lcd.clear()
            lcd.write_string("Occupied")
            time.sleep(1)
            continue

        if light_on:
            if not countdown_started:
                countdown_started = True
                stop_countdown_flag = False
                threading.Thread(target=countdown_and_buzz, daemon=True).start()
        else:
            if countdown_started:
                stop_countdown_flag = True
                countdown_started = False

        time.sleep(2)

# --- Video Streaming ---
def gen_frames():
    while True:
        with camera_lock:
            success, frame = camera.read()
        if not success:
            logging.warning("Failed to read frame for streaming.")
            break
        frame = cv2.resize(frame, (320, 240))
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ret:
            logging.warning("Failed to encode frame.")
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return """
    <html>
        <body>
            <h1>Camera Stream</h1>
            <img src="/video_feed" width="640" height="480" />
        </body>
    </html>
    """

# --- Cleanup ---
@atexit.register
def cleanup():
    lcd.clear()
    camera.release()
    GPIO.cleanup()
    logging.info("Cleanup done. Exiting.")

# --- Main ---
if __name__ == '__main__':
    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()
    app.run(host='0.0.0.0', port=5000)
