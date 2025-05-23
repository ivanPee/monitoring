from flask import Flask, render_template, Response
import cv2
import imutils
import numpy as np
import datetime
import mysql.connector
import time

app = Flask(__name__)
camera = cv2.VideoCapture(0)

# ✅ Database config
db_config = {
    'host': '192.168.1.13',
    'user': 'root',
    'password': '',
    'database': 'monitoring'
}

# ✅ Load human detector
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# ✅ Track detection time
last_detected = None
room_id = None  # Will be fetched based on stream_url

def get_day_number():
    return (datetime.datetime.today().weekday() + 1) % 7 or 7

def detect_brightness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray)

def get_room_id_by_stream_url():
    global room_id
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    # Modify this query based on your actual table/column names
    cursor.execute("SELECT room_id FROM tbl_room WHERE stream_url = %s", ("http://192.168.1.7:5000/video",))
    row = cursor.fetchone()
    room_id = row[0] if row else None
    cursor.close()
    conn.close()

def handle_detection_action():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    current_day = str(get_day_number())
    current_time = now.time()

    # Check for existing schedule
    cursor.execute("""
        SELECT schedule_id FROM tbl_schedule
        WHERE room_id = %s AND schedule_day = %s
        AND schedule_time <= %s AND end_time >= %s
    """, (room_id, current_day, current_time, current_time))
    result = cursor.fetchone()

    if result:
        schedule_id = result[0]
        cursor.execute("""
            UPDATE tbl_schedule SET status = 'Flagged'
            WHERE schedule_id = %s
        """, (schedule_id,))
        print(f"Updated existing schedule ID {schedule_id} to Flagged.")
    else:
        cursor.execute("""
            INSERT INTO tbl_schedule (schedule_day, schedule_time, duration, room_id, used_by, date_added, status, is_permanent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            current_day, current_time, 30,
            room_id, 0, now, 'Flagged', 'Temporary'
        ))
        print(f"Inserted new temporary schedule for Room {room_id}.")

    conn.commit()
    cursor.close()
    conn.close()

def gen_frames():
    global last_detected, room_id
    get_room_id_by_stream_url()  # get room_id from stream_url

    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            frame = imutils.resize(frame, width=640)
            orig = frame.copy()

            # Detect humans
            (regions, _) = hog.detectMultiScale(frame, winStride=(4, 4), padding=(8, 8), scale=1.05)

            # Draw rectangles for humans
            for (x, y, w, h) in regions:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            human_detected = len(regions) > 0

            if human_detected:
                cv2.putText(frame, "Human Detected", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # Detect light
            brightness = detect_brightness(orig)
            light_status = "ON" if brightness > 100 else "OFF"
            light_on = light_status == "ON"
            color = (0, 255, 255) if light_on else (0, 0, 255)
            cv2.putText(frame, f"Light: {light_status}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            # Check schedule
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            current_day = str(get_day_number())
            now = datetime.datetime.now()
            current_time = now.time()

            cursor.execute("""
                SELECT status FROM tbl_schedule
                WHERE room_id = %s AND schedule_day = %s
                AND schedule_time <= %s AND end_time >= %s
            """, (room_id, current_day, current_time, current_time))
            row = cursor.fetchone()
            conn.close()

            if row and row[0] == 'Using':
                cv2.putText(frame, "Status: Using", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 255), 2)
                last_detected = None  # reset
            else:
                if human_detected or light_on:
                    if last_detected is None:
                        last_detected = time.time()
                    elif time.time() - last_detected >= 300:  # 5 minutes
                        handle_detection_action()
                        last_detected = None  # reset after action
                        cv2.putText(frame, "⚠️ Flagged!", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                else:
                    last_detected = None

            # Encode and stream frame
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return '''
        <h1>Room Monitoring</h1>
        <img src="/video" width="640"><br><br>
        <p>Live monitoring stream.</p>
    '''

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
