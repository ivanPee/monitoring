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

# --- Flask App and Camera ---
app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera_lock = threading.Lock()

# --- HOG Human Detector Setup ---
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# --- Control Variables ---
room_id = None
prev_gray = None
motion_timer_start = None
motion_flagged = False
last_lcd_status = ""
motion_timer_start = None
motion_flagged = False
light_timer_start = None
light_flagged = False

# --- LCD display update ---
def set_lcd_status(text):
    global last_lcd_status
    if text != last_lcd_status:
        lcd.clear()
        lcd.write_string(text)
        print("[LCD] " + text)
        last_lcd_status = text

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

# --- Check Schedule Status ---
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
def flag_schedule(detection):
    try:
        res = requests.post('http://192.168.1.4/monitoring/ajax/flag_schedule.php', json={'room_id': room_id, detection:detection})
        print("Flagged schedule:", res.json().get('message') if res.ok else res.status_code)
    except Exception as e:
        print("Error flagging schedule:", e)

# --- Buzzer Alert ---
def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    set_lcd_status("Buzzing!")
    time.sleep(5)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

# --- Monitoring Thread ---
def monitoring_loop():
    global prev_gray, motion_timer_start, motion_flagged
    global light_timer_start, light_flagged

    get_room_id_by_stream_url()
    set_lcd_status("Monitoring...")

    while True:
        with camera_lock:
            ret, frame = camera.read()
        if not ret:
            continue

        frame_resized = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (11, 11), 0)
        
        # Find brightest point
        (minVal, maxVal, minLoc, maxLoc) = cv2.minMaxLoc(blurred)
        
        # Get brightness of a 20x20 patch around brightest point
        x, y = maxLoc
        patch = gray[max(0, y-10):y+10, max(0, x-10):x+10]
        brightness = patch.mean() if patch.size > 0 else 0
        
        status = check_schedule_status(room_id)
        light_on = brightness > 110
        motion_detected = False
        human_detected = False

        # Motion Detection
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            motion_area = cv2.countNonZero(thresh)
            motion_detected = motion_area > 500
        prev_gray = gray

        # Human Detection
        rects, weights = hog.detectMultiScale(frame_resized, winStride=(4,4), padding=(8,8), scale=1.02)
        human_detected = len(rects) > 0
        
        # rects, weights = hog.detectMultiScale(
        #     frame,
        #     winStride=(8, 8),
        #     padding=(16, 16),
        #     scale=1.05
        # )

        # filtered_rects = []
        # for i, (x, y, w, h) in enumerate(rects):
        #     if weights[i] > 0.6:  # Adjust threshold based on test (0.5–0.7 usually works well)
        #         filtered_rects.append((x, y, w, h))
        # human_detected = len(filtered_rects) > 0

        # --- Print & LCD status logic ---
        if human_detected:
            set_lcd_status("Human detected")
        elif motion_detected:
            set_lcd_status("Motion detected")
        elif light_on:
            set_lcd_status("Light detected")
        else:
            set_lcd_status("Monitoring...")

        print(f"[INFO] Human: {human_detected}, Motion: {motion_detected}, Light: {light_on}, Status: {status}")

        # If occupied, skip flagging
        if status == "Occupied":
            set_lcd_status("Occupied...")
            time.sleep(1)
            continue

        # If human detected, flag immediately
        if human_detected:
            flag_schedule("Human")
            buzzer_alert()
            time.sleep(5)
            continue

        # Motion consistency logic
        if motion_detected:
            if not motion_timer_start:
                motion_timer_start = time.time()
            elif time.time() - motion_timer_start >= 60 and not motion_flagged:
                motion_flagged = True
                print("[ALERT] Motion > 60s. Flagging schedule...")
                flag_schedule("Motion")
                buzzer_alert()
        else:
            motion_timer_start = None
            motion_flagged = False

        # Light consistency logic
        if light_on:
            if not light_timer_start:
                light_timer_start = time.time()
            elif time.time() - light_timer_start >= 60 and not light_flagged:
                light_flagged = True
                print("[ALERT] Light > 60s. Flagging schedule...")
                flag_schedule("Light")
                buzzer_alert()
        else:
            light_timer_start = None
            light_flagged = False

        time.sleep(1)

# --- Video Feed with Human Boxes ---
def gen_frames():
    while True:
        with camera_lock:
            success, frame = camera.read()
        if not success:
            break

        frame = cv2.resize(frame, (320, 240))

        # Human detection boxes
        rects, _ = hog.detectMultiScale(frame, winStride=(8,8), padding=(8,8), scale=1.05)
        for (x, y, w, h) in rects:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0,255,0), 2)

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return """
    <html>
        <body>
            <h1>Live Camera</h1>
            <img src="/video_feed" />
        </body>
    </html>
    """

# --- Cleanup ---
@atexit.register
def cleanup():
    lcd.clear()
    camera.release()
    GPIO.cleanup()

# --- Run ---
if __name__ == '__main__':
    threading.Thread(target=monitoring_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
