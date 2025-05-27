import cv2
import time
import threading
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
import requests
import datetime
from flask import Flask, Response
import atexit

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

# --- Background Subtractor for motion detection ---
back_sub = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=50, detectShadows=False)

# --- Control Variables ---
countdown_started = False
stop_countdown_flag = False
room_id = None

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
    lcd.clear()
    lcd.write_string("Buzzing now!")
    time.sleep(10)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    lcd.clear()
    lcd.write_string("Monitoring...")

def countdown_and_buzz():
    global countdown_started, stop_countdown_flag

    print("Light detected! Starting countdown...")

    for i in range(60, 0, -1):
        if stop_countdown_flag:
            print("Detection Stopped.")
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
    get_room_id_by_stream_url()

    while True:
        with camera_lock:
            ret, frame = camera.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        print(f"Brightness: {brightness:.2f}")

        light_on = brightness > 80
        status = check_schedule_status(room_id)
        print(f"Status: {status}, Light: {'ON' if light_on else 'OFF'}")

        if status == "Occupied":
            lcd.clear()
            lcd.write_string("Occupied")
            time.sleep(1)  # Slight delay to reduce LCD flicker
            continue  # Skip the rest of the loop (no countdown, no checks)

        # Room is NOT occupied, proceed with logic
        if light_on:
            if not countdown_started:
                countdown_started = True
                stop_countdown_flag = False
                threading.Thread(target=countdown_and_buzz).start()
        else:
            if countdown_started:
                stop_countdown_flag = True
                countdown_started = False

        time.sleep(2)

# --- Video Streaming with green object framing ---
def gen_frames():
    while True:
        with camera_lock:
            success, frame = camera.read()
        if not success:
            break

        frame = cv2.resize(frame, (320, 240))
        fg_mask = back_sub.apply(frame)

        # Find contours on foreground mask
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            if cv2.contourArea(cnt) > 500:  # filter out small noise
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)  # green box

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
