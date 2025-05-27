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

# --- HOG Human Detector Setup ---
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# --- Control Variables ---
countdown_started = False
stop_countdown_flag = False
room_id = None

# --- For motion detection ---
prev_gray = None

# --- Shared status for LCD display ---
lcd_status_lock = threading.Lock()
lcd_status_text = "Starting..."

def set_lcd_status(text):
    global lcd_status_text
    with lcd_status_lock:
        lcd_status_text = text

def update_lcd():
    while True:
        with lcd_status_lock:
            text = lcd_status_text
        lcd.clear()
        lcd.write_string(text)
        time.sleep(1)  # update every 1 sec

# --- Room ID ---
def get_room_id_by_stream_url():
    global room_id
    try:
        res = requests.get('http://192.168.1.4/monitoring/ajax/get_room_id.php', params={
            'code': 'RM123MB'
        })
        if res.status_code == 200:
            room_id = res.json().get('room_id')
            print("Room ID:", room_id)
    except Exception as e:
        print("Error getting room_id:", e)

# --- Check Schedule ---
def check_schedule_status(room_id):
    now = datetime.datetime.now()
    
    current_day = (now.weekday() + 1) % 7 or 7
    current_time = now.strftime("%H:%M:%S")

    try:
        res = requests.get('http://192.168.1.4/monitoring/ajax/check_schedule.php', params={
            'room_id': room_id,
            'schedule_day': current_day,
            'current_time': current_time
        })
        data = res.json()
        if data['success']:
            return data['status']
    except Exception as e:
        print("Schedule check error:", e)
    return None

# --- Flag Schedule ---
def handle_detection_action():
    try:
        res = requests.post('http://192.168.1.4/monitoring/ajax/flag_schedule.php', json={'room_id': room_id})
        print("Flagged schedule:", res.json().get('message') if res.ok else res.status_code)
    except Exception as e:
        print("Error flagging schedule:", e)

# --- Alert and Countdown ---
def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    set_lcd_status("Buzzing now!")
    time.sleep(10)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    set_lcd_status("Monitoring...")

def countdown_and_buzz():
    global countdown_started, stop_countdown_flag

    print("Light detected! Starting countdown...")

    for i in range(60, 0, -1):
        if stop_countdown_flag:
            print("Detection Stopped.")
            set_lcd_status("Countdown cancelled")
            time.sleep(2)
            set_lcd_status("Monitoring...")
            countdown_started = False
            stop_countdown_flag = False
            return

        set_lcd_status(f"Countdown: {i}s")
        time.sleep(1)

    handle_detection_action()
    buzzer_alert()
    countdown_started = False

# --- Monitoring Thread ---
def monitoring_loop():
    global countdown_started, stop_countdown_flag, prev_gray
    set_lcd_status("Monitoring...")
    get_room_id_by_stream_url()

    while True:
        with camera_lock:
            ret, frame = camera.read()
        if not ret:
            continue

        resized_frame = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        # print(f"Brightness: {brightness:.2f}")

        light_on = brightness > 80
        status = check_schedule_status(room_id)
        # print(f"Status: {status}, Light: {'ON' if light_on else 'OFF'}")

        # Simple motion detection by frame difference
        motion_detected = False
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            motion_area = cv2.countNonZero(thresh)
            motion_detected = motion_area > 500  # Tune threshold if needed
        prev_gray = gray

        # Human detection on resized frame
        rects, weights = hog.detectMultiScale(resized_frame, winStride=(8,8), padding=(8,8), scale=1.05)
        human_detected = len(rects) > 0

        # Update LCD status by priority: Human > Motion > Light > Normal
        if human_detected:
            set_lcd_status("Human detected")
        elif motion_detected:
            set_lcd_status("Motion detected")
        elif light_on:
            set_lcd_status("Light detected")
        else:
            set_lcd_status("Monitoring...")

        if status == "Occupied":
            set_lcd_status("Occupied")
            time.sleep(1)
            continue

        # Countdown logic on light
        if light_on and not countdown_started:
            countdown_started = True
            stop_countdown_flag = False
            threading.Thread(target=countdown_and_buzz).start()
        elif not light_on and countdown_started:
            stop_countdown_flag = True
            countdown_started = False

        time.sleep(1)

# --- Video Streaming with human detection and green boxes ---
def gen_frames():
    while True:
        with camera_lock:
            success, frame = camera.read()
        if not success:
            break

        frame = cv2.resize(frame, (320, 240))

        # Detect humans and draw green boxes
        rects, weights = hog.detectMultiScale(frame, winStride=(8,8), padding=(8,8), scale=1.05)
        for i, (x, y, w, h) in enumerate(rects):
            # You can filter by weights[i] if needed (e.g., >0.5)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
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

# --- Start LCD updater thread ---
lcd_thread = threading.Thread(target=update_lcd, daemon=True)
lcd_thread.start()

# --- Cleanup ---
@atexit.register
def cleanup():
    lcd.clear()
    camera.release()
    GPIO.cleanup()

# --- Main ---
if __name__ == '__main__':
    threading.Thread(target=monitoring_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
