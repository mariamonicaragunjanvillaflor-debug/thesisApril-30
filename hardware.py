import requests
import time
import math
from datetime import datetime

import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
from smbus2 import SMBus

import board
import busio
import adafruit_mlx90614


# -----------------------
# GPIO SETUP
# -----------------------
GREEN_LED = 17
RED_LED = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)


# -----------------------
# LCD SETUP (FIXED - MATCH WORKING VERSION)
# -----------------------
lcd = CharLCD(
    i2c_expander='PCF8574',
    address=0x27,
    port=1,
    cols=20,
    rows=4
)

lcd.clear()
time.sleep(0.5)


# -----------------------
# FLASK API
# -----------------------
FLASK_URL = "http://127.0.0.1:5000/api/update"
TIMEOUT = 2


# -----------------------
# I2C SETUP
# -----------------------
bus = SMBus(1)

i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90614.MLX90614(i2c)

ADS1115_ADDR = 0x48


# -----------------------
# STATE MEMORY
# -----------------------
last_state = None


# -----------------------
# TIME (PH LOCAL)
# -----------------------
def get_ph_time():
    return datetime.now().strftime("%H:%M:%S")


# -----------------------
# ADC READ
# -----------------------
def read_adc(channel=0):
    raw = bus.read_word_data(ADS1115_ADDR, 0x40 + channel)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)

    if raw > 32767:
        raw -= 65536

    return raw


# -----------------------
# CURRENT RMS
# -----------------------
def read_current_rms(window_ms=300):
    start = time.time()

    offset = read_adc(0)
    sum_sq = 0
    samples = 0

    while (time.time() - start) < (window_ms / 1000):
        raw = read_adc(0)

        offset += (raw - offset) * 0.01
        centered = raw - offset

        sum_sq += centered * centered
        samples += 1

    if samples == 0:
        return 0.0

    rms_counts = math.sqrt(sum_sq / samples)
    current = rms_counts * 0.001

    return 0.0 if current < 0.05 else current


# -----------------------
# TEMPERATURE
# -----------------------
def read_temperature():
    try:
        return mlx.object_temperature
    except:
        return 35.0


# -----------------------
# LED CONTROL
# -----------------------
def set_led(state):
    GPIO.output(GREEN_LED, 0)
    GPIO.output(RED_LED, 0)

    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
    else:
        GPIO.output(RED_LED, 1)


# -----------------------
# LCD UPDATE (IMPROVED + SAFE PADDING)
# -----------------------
def lcd_update(temp, current, state, ml=None):
    ph_time = get_ph_time()

    line1 = f"TIME:{ph_time}"
    line2 = f"T:{temp:5.1f}C I:{current:5.2f}A"
    line3 = f"STATE:{state}"

    if ml:
        line4 = f"H:{ml.get('hotspot_prob',0):.2f} O:{ml.get('overload_prob',0):.2f}"
    else:
        line4 = "SYSTEM MONITORING"

    lines = [line1, line2, line3, line4]

    lcd.clear()

    for i in range(4):
        lcd.cursor_pos = (i, 0)
        lcd.write_string(lines[i][:20].ljust(20))  # safe trim + padding


# -----------------------
# MAIN LOOP
# -----------------------
def run():
    print("System running...")

    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string("SYSTEM STARTING".ljust(20))
    time.sleep(1)

    while True:
        try:
            temp = read_temperature()
            current = read_current_rms()

            response = requests.post(
                FLASK_URL,
                json={
                    "temperature": temp,
                    "current": current
                },
                timeout=TIMEOUT
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            result = response.json()

            state = result.get("state", "Unknown")
            ml = result.get("ml", None)

            set_led(state)
            lcd_update(temp, current, state, ml)

            print(f"{state} | T:{temp:.2f} | I:{current:.2f}")

        except Exception as e:
            print("ERROR:", e)

            set_led("Error")

            lcd.clear()
            lcd.cursor_pos = (0, 0)
            lcd.write_string("SYSTEM ERROR".ljust(20))
            lcd.cursor_pos = (1, 0)
            lcd.write_string("CHECK CONNECTION".ljust(20))

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
