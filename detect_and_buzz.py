import cv2
import time
import threading
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

# GPIO setup for buzzer
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# LCD setup (replace 0x27 if needed)
lcd = CharLCD('PCF8574', 0x27)
lcd.clear()

# Camera setup
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

# Control variables
countdown_started = False
stop_countdown_flag = False

def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    lcd.clear()
    lcd.write_string("Buzzing now!")
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    lcd.clear()
    lcd.write_string("Monitoring...")

def countdown_and_buzz():
    global countdown_started, stop_countdown_flag

    print("Light detected! Starting countdown...")

    for i in range(60, 0, -1):
        if stop_countdown_flag:
            print("Countdown cancelled due to light loss.")
            lcd.clear()
            lcd.write_string("Countdown cancelled")
            time.sleep(2)
            lcd.clear()
            lcd.write_string("Monitoring...")
            countdown_started = False
            stop_countdown_flag = False
            return

        lcd.clear()
        lcd.write_string(f"Countdown:\n{i}s remaining")
        print(f"Countdown: {i} seconds remaining")
        time.sleep(1)

    print("Countdown done. Buzzing...")
    buzzer_alert()
    countdown_started = False

try:
    lcd.write_string("Monitoring...")

    while True:
        ret, frame = camera.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        print(f"Brightness: {brightness:.2f}")

        if brightness > 100:
            if not countdown_started:
                countdown_started = True
                stop_countdown_flag = False
                threading.Thread(target=countdown_and_buzz).start()
        else:
            # If brightness low and countdown running, cancel countdown
            if countdown_started:
                stop_countdown_flag = True

        time.sleep(0.5)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    lcd.clear()
    camera.release()
    GPIO.cleanup()
