import cv2
import time
import threading
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

# Setup buzzer
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Setup LCD
lcd = CharLCD('PCF8574', 0x27)
lcd.clear()

# Camera
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

# Shared state
countdown_started = False

def buzzer_alert():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    lcd.clear()
    lcd.write_string("Buzzing now!")
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    lcd.clear()
    lcd.write_string("Monitoring...")

def countdown_and_buzz():
    global countdown_started
    lcd.clear()
    lcd.write_string("Light detected!")
    print("Light detected! Starting countdown...")
    time.sleep(60)  # 1 minute countdown
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

        if brightness > 100 and not countdown_started:
            countdown_started = True
            threading.Thread(target=countdown_and_buzz).start()

        time.sleep(0.5)

except KeyboardInterrupt:
    prin
