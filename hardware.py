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
TIMEOUT = 2

# -----------------------
# STATE MEMORY (prevents LCD flicker)
# -----------------------
last_state = None


# -----------------------
# LED CONTROL (IMPROVED)
# -----------------------
def set_led(state, risk=None):
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)

    elif state == "Overload":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

    elif state == "Overheating":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 0)


# -----------------------
# LCD UPDATE (NO CLEAR EVERY LOOP)
# -----------------------
def lcd_update(temp, current, state, ml=None):
    global last_state

    if state != last_state:
        lcd.clear()
        last_state = state

    lcd.cursor_pos = (0, 0)
    lcd.write_string(f"T:{temp:.1f}C I:{current:.1f}A   ")

    lcd.cursor_pos = (1, 0)
    lcd.write_string(f"STATE: {state}        ")

    if ml:
        lcd.cursor_pos = (2, 0)
        lcd.write_string(f"H:{ml['hotspot_prob']:.2f} O:{ml['overload_prob']:.2f}")


# -----------------------
# SENSOR SIMULATION
# -----------------------
def read_sensors():
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
            temp, current = read_sensors()

            response = requests.post(
                FLASK_URL,
                json={
                    "temperature": temp,
                    "current": current
                },
                timeout=TIMEOUT
            )

            # -----------------------
            # SAFE RESPONSE CHECK
            # -----------------------
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            result = response.json()

            state = result.get("state", "Unknown")
            ml = result.get("ml", None)

            # -----------------------
            # OUTPUTS
            # -----------------------
            set_led(state, ml)
            lcd_update(temp, current, state, ml)

            print(f"{state} | T:{temp:.1f} | I:{current:.1f}")

        except Exception as e:
            print("ERROR:", e)

            GPIO.output(RED_LED, 1)
            GPIO.output(GREEN_LED, 0)

        time.sleep(1)


# -----------------------
# SAFE EXIT
# -----------------------
if __name__ == "__main__":
    try:
        run()

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        GPIO.cleanup()
        lcd.clear()