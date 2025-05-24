from flask import Flask, Response
import cv2
import imutils
import numpy as np
import datetime
import time
import requests
import atexit

app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

# ✅ Human Detector
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# ✅ Detection Timing
detected_time = None
notified = False
buzzed = False
room_id = None

# ✅ Brightness Check
def detect_brightness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray)

# ✅ Get room_id from PHP backend
def get_room_id_by_stream_url():
    global room_id
    try:
        res = requests.get('http://192.168.1.13/monitoring/ajax/get_room_id.php', params={
            'url': 'http://192.168.1.7:5000/video'
        })
        if res.status_code == 200:
            data = res.json()
            room_id = data.get('room_id')
        else:
            print("Failed to get room_id:", res.status_code)
    except Exception as e:
        print("Error fetching room_id:", e)

# ✅ Flag to server
def handle_detection_action():
    try:
        response = requests.post('http://192.168.1.13/monitoring/ajax/flag_schedule.php', json={'room_id': room_id})
        if response.status_code == 200:
            print("Flagged schedule:", response.json().get('message'))
        else:
            print("Failed to flag schedule:", response.status_code)
    except Exception as e:
        print("Flag request error:", e)

# ✅ Check if room is scheduled to be used
def check_schedule_status(room_id):
    now = datetime.datetime.now()
    current_day = (now.weekday() + 1) % 7 or 7
    current_time = now.strftime("%H:%M:%S")
    try:
        res = requests.get('http://192.168.1.13/monitoring/ajax/check_schedule.php', params={
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

# ✅ Main detection loop
def gen_frames():
    global detected_time, notified, buzzed, room_id
    get_room_id_by_stream_url()

    while True:
        success, frame = camera.read()
        if not success:
            break

        frame = cv2.resize(frame, (320, 240))
        orig = frame.copy()

        # Detect humans
        regions, _ = hog.detectMultiScale(frame, winStride=(4, 4), padding=(8, 8), scale=1.05)
        human_detected = len(regions) > 0

        for (x, y, w, h) in regions:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        # Detect light
        brightness = detect_brightness(orig)
        light_on = brightness > 100

        # Overlay info
        if human_detected:
            cv2.putText(frame, "Human Detected", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        cv2.putText(frame, f"Light: {'ON' if light_on else 'OFF'}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255) if light_on else (0,0,255), 1)

        # Check room usage
        status = check_schedule_status(room_id)
        if status == "Using":
            detected_time = None
            notified = False
            buzzed = False
            cv2.putText(frame, "Status: Using", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1)
        else:
            if human_detected or light_on:
                if detected_time is None:
                    detected_time = time.time()
                elapsed = time.time() - detected_time

                if elapsed >= 60 and not notified:
                    print("⚠️ Notifying admin (1 min)...")
                    # Here you can trigger actual notification
                    notified = True

                if elapsed >= 180 and not buzzed:
                    print("🚨 Buzzing alarm (3 min)...")
                    # Activate buzzer here
                    handle_detection_action()
                    buzzed = True

                if elapsed >= 180:
                    cv2.putText(frame, "⚠️ Buzzer Triggered", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
            else:
                detected_time = None
                notified = False
                buzzed = False

        # Encode and yield
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.1)

@app.route('/')
def index():
    return '''
        <h1>Room Monitoring</h1>
        <img src="/video" width="640"><br>
        <p>Live Feed</p>
    '''

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@atexit.register
def cleanup():
    camera.release()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
