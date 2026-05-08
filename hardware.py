import requests
import time
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

# -----------------------
# GPIO SETUP
# -----------------------
GREEN_LED = 17
RED_LED = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)

# -----------------------
# LCD SETUP
# -----------------------
lcd = CharLCD('PCF8574', 0x27, cols=20, rows=4)
lcd.clear()

# -----------------------
# FLASK API
# -----------------------
FLASK_URL = "http://127.0.0.1:5000/api/update"

# -----------------------
# LED CONTROL
# -----------------------
def set_led(state):
    GPIO.output(GREEN_LED, state == "Normal")
    GPIO.output(RED_LED, state != "Normal")


# -----------------------
# LCD DISPLAY
# -----------------------
def lcd_update(temp, current, state):
    lcd.clear()

    lcd.write_string(f"T:{temp:.1f}C I:{current:.1f}A")

    lcd.cursor_pos = (1, 0)
    lcd.write_string(state)


# -----------------------
# REPLACE THIS WITH REAL SENSOR
# -----------------------
def read_sensors():

    # EXAMPLE VALUES
    temp = 35.0
    current = 12.0

    return temp, current


# -----------------------
# MAIN LOOP
# -----------------------
def run():

    print("System running...")

    while True:

        try:
            # READ REAL SENSOR
            temp, current = read_sensors()

            # SEND TO FLASK
            response = requests.post(
                FLASK_URL,
                json={
                    "temperature": temp,
                    "current": current
                }
            )

            result = response.json()

            state = result["state"]

            # UPDATE OUTPUTS
            set_led(state)
            lcd_update(temp, current, state)

            print(f"{state} | T:{temp:.1f} | I:{current:.1f}")

        except Exception as e:

            print("ERROR:", e)

            GPIO.output(RED_LED, 1)
            GPIO.output(GREEN_LED, 0)

        time.sleep(1)


if __name__ == "__main__":

    try:
        run()

    except KeyboardInterrupt:
        GPIO.cleanup()
        lcd.clear()