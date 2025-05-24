import RPi.GPIO as GPIO
import time
from RPLCD.i2c import CharLCD

BUZZER_PIN = 18

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Initialize the LCD (replace 0x27 with your screen's I2C address)
lcd = CharLCD('PCF8574', 0x27)

try:
    for i in range(5):
        # Turn buzzer ON
        GPIO.output(BUZZER_PIN, GPIO.HIGH)

        # Print message on LCD
        lcd.clear()
        lcd.write_string(f'Buzzing {i+1}')
        
        time.sleep(3)

        # Turn buzzer OFF
        GPIO.output(BUZZER_PIN, GPIO.LOW)

        # Clear LCD or print something else during buzzer off time
        lcd.clear()
        lcd.write_string('Waiting...')
        
        time.sleep(3)

finally:
    lcd.clear()
    GPIO.cleanup()
