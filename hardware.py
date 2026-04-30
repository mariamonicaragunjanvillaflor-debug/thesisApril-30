import requests
import time
import joblib
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

from feature_engine import build_basic_features

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
# API
# -----------------------
FLASK_URL = "http://127.0.0.1:5000/api/simulate"

# -----------------------
# MODELS
# -----------------------
hotspot_model = joblib.load("ml/hotspot_model.pkl")
overload_model = joblib.load("ml/overload_model.pkl")


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
    lcd.write_string(f"T:{temp:.1f}C C:{current:.1f}A")
    lcd.cursor_pos = (1, 0)
    lcd.write_string(f"{state}")


# -----------------------
# MAIN LOOP
# -----------------------
def run():
    print("System running...")

    while True:
        try:
            data = requests.get(FLASK_URL).json()

            temp = float(data["temperature"])
            current = float(data["current"])

            # FEATURE ENGINE (MATCHS APP.PY)
            X = build_basic_features(temp, current)

            if X is None:
                state = "Warming Up"

            else:
                # FIXED: use predict_proba (NOT predict)
                hot_prob = hotspot_model.predict_proba(X)[0][1]
                ovl_prob = overload_model.predict_proba(X)[0][1]

                # SAME LOGIC AS APP.PY
                if temp >= 75 or hot_prob > 0.7:
                    state = "Overheating"
                elif current >= 21 or ovl_prob > 0.6:
                    state = "Overload"
                else:
                    state = "Normal"

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