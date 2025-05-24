import cv2
import numpy as np
import time
import datetime
import requests
import atexit

# ✅ Init camera
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

# ✅ Human detector
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# ✅ State variables
detected_time = None
notified = False
buzzed = False
room_id = None

# ✅ Brightness check
def detect_brightness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray)

# ✅ Get room ID
def get_room_id_by_stream_url():
    global room_id
    try:
        res = requests.get('http://192.168.1.13/monitoring/ajax/get_room_id.php', params={
            'url': 'http://192.168.1.7:5000/video'
        })
        if res.status_code == 200:
            room_id = res.json().get('room_id')
            print("Room ID:", room_id)
    except Exception as e:
        print("Error getting room_id:", e)

# ✅ Check current schedule status
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

# ✅ Flag schedule via API
def handle_detection_action():
    try:
        res = requests.post('http://192.168.1.13/monitoring/ajax/flag_schedule.php', json={'room_id': room_id})
        print("Flagged schedule:", res.json().get('message') if res.ok else res.status_code)
    except Exception as e:
        print("Error flagging schedule:", e)

# ✅ Main loop
def monitor_loop():
    global detected_time, notified, buzzed

    get_room_id_by_stream_url()

    while True:
        success, frame = camera.read()
        if not success:
            print("Camera read failed.")
            continue

        frame = cv2.resize(frame, (320, 240))
        brightness = detect_brightness(frame)
        light_on = brightness > 100

        # Detect humans
        regions, _ = hog.detectMultiScale(frame, winStride=(4, 4), padding=(8, 8), scale=1.05)
        human_detected = len(regions) > 0

        status = check_schedule_status(room_id)
        print(f"Status: {status}, Human: {human_detected}, Light: {'ON' if light_on else 'OFF'}")

        if status == "Using":
            detected_time = None
            notified = False
            buzzed = False
        else:
            if human_detected or light_on:
                if detected_time is None:
                    detected_time = time.time()
                elapsed = time.time() - detected_time

                if elapsed >= 60 and not notified:
                    print("⚠️ Notifying admin (1 min)...")
                    notified = True

                if elapsed >= 180 and not buzzed:
                    print("🚨 Buzzing alarm and flagging schedule (3 min)...")
                    handle_detection_action()
                    buzzed = True
            else:
                detected_time = None
                notified = False
                buzzed = False

        time.sleep(1)

@atexit.register
def cleanup():
    print("Releasing camera...")
    camera.release()

if __name__ == '__main__':
    monitor_loop()
