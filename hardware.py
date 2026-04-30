import requests
import time
import joblib
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

from feature_engine import build_basic_features

# GPIO
GREEN_LED = 17
RED_LED = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)

# LCD
lcd = CharLCD('PCF8574', 0x27, cols=20, rows=4)
lcd.clear()

# API
FLASK_URL = "http://127.0.0.1:5000/api/simulate"

# MODELS
hotspot_model = joblib.load("ml/hotspot_model.pkl")
overload_model = joblib.load("ml/overload_model.pkl")


def set_led(state):
    GPIO.output(GREEN_LED, state == "Normal")
    GPIO.output(RED_LED, state != "Normal")


def lcd_update(temp, current, state):
    lcd.clear()
    lcd.write_string(f"T:{temp:.1f}C C:{current:.1f}A")
    lcd.cursor_pos = (1, 0)
    lcd.write_string(f"{state}")


def run():
    print("System running...")

    while True:
        try:
            data = requests.get(FLASK_URL).json()

            temp = float(data["temperature"])
            current = float(data["current"])

            X = build_basic_features(temp, current)

            if X is None:
                state = "Warming Up"
            else:
                hot = hotspot_model.predict_proba(X)[0][1]
                ovl = overload_model.predict(X)[0]

                state = (
                    "Overheating" if hot > 0.65
                    else "Overload" if ovl == 1
                    else "Normal"
                )

            set_led(state)
            lcd_update(temp, current, state)

            print(state, temp, current)

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