import cv2
import time
import threading
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
import requests
import datetime
from flask import Flask, Response
import atexit
import numpy as np

# GPIO and LCD
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

lcd = CharLCD('PCF8574', 0x27)
lcd.clear()
lcd.write_string("Starting...")

# Flask
app = Flask(__name__)
camera = cv2.VideoCapture(0)
camera.set(3, 320)  # width
camera.set(4, 240)  # height
camera_lock = threading.Lock()

# Lightweight Face Detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# Globals
countdown_started = False
stop_countdown_flag = False
room_id = None

# Helper: Get Room ID
def get_room_id():
    global room_id
    try:
        r = requests.get('http://192.168.1.4/monitoring/ajax/get_room_id.php', params={'code': 'RM123MB'})
        if r.ok:
            room_id = r.json().get('room_id')
    except: pass

# Helper: Check Schedule
def check_schedule_status(room_id):
    try:
        now = datetime.datetime.now()
        res = requests.get('http://192.168.1.4/monitoring/ajax/check_schedule.php', params={
            'room_id': room_id,
            'schedule_day': (now.weekday() + 1) % 7 or 7,
            'current_time': now.strftime("%H:%M:%S")
        })
        if res.ok:
            return res.json().get('status')
    except: pass
    return None

# Post Flag
def handle_detection_action():
    try:
        requests.post('http://192.168.1.4/monitoring/ajax/flag_schedule.php', json={'room_id': room_id})
    except: pass

# Buzzer Alert
def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    lcd.clear()
    lcd.write_string("Buzzing!")
    time.sleep(5)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

# Countdown Logic
def countdown_and_buzz():
    global countdown_started, stop_countdown_flag
    for i in range(30, 0, -1):
        if stop_countdown_flag:
            lcd.clear()
            lcd.write_string("Cancelled")
            time.sleep(1)
            lcd.clear()
            lcd.write_string("Monitoring")
            countdown_started = False
            stop_countdown_flag = False
            return
        lcd.clear()
        lcd.write_string(f"Countdown: {i}")
        time.sleep(1)

    handle_detection_action()
    buzzer_alert()
    countdown_started = False

# Detection Logic
def detect_face_and_light(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = gray.mean()
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    return len(faces) > 0, brightness > 80

# Main Monitoring Loop
def monitoring_loop():
    global countdown_started, stop_countdown_flag
    get_room_id()
    lcd.clear()
    lcd.write_string("Monitoring...")

    while True:
        with camera_lock:
            ret, frame = camera.read()
        if not ret:
            continue

        person, light_on = detect_face_and_light(frame)
        status = check_schedule_status(room_id)

        print(f"Person: {person}, Light: {'ON' if light_on else 'OFF'}, Status: {status}")

        if status == "Occupied":
            lcd.clear()
            lcd.write_string("Occupied")
            time.sleep(1)
            continue

        if person and light_on and not countdown_started:
            countdown_started = True
            stop_countdown_flag = False
            threading.Thread(target=countdown_and_buzz).start()
        elif not (person and light_on) and countdown_started:
            stop_countdown_flag = True

        time.sleep(1)

# Video Feed for Web
def gen_frames():
    while True:
        with camera_lock:
            success, frame = camera.read()
        if not success:
            continue
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.15)

@app.route('/')
def index():
    return "<h1>Raspberry Pi Monitoring</h1><img src='/video_feed'>"

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@atexit.register
def cleanup():
    camera.release()
    GPIO.cleanup()
    lcd.clear()

if __name__ == "__main__":
    threading.Thread(target=monitoring_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
