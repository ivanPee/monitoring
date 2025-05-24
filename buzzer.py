import RPi.GPIO as GPIO
import time

BUZZER_PIN = 18  # GPIO pin used

GPIO.setmode(GPIO.BCM)       # Use Broadcom pin-numbering
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Beep 5 times
for _ in range(5):
    GPIO.output(BUZZER_PIN, GPIO.HIGH)  # Turn buzzer on
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)   # Turn buzzer off
    time.sleep(3)

GPIO.cleanup()
