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
# ADS1115 READ
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
# LCD UPDATE (IMPROVED UI)
# -----------------------
def lcd_update(temp, current, state, ml=None):
    global last_state

    ph_time = get_ph_time()

    def write(row, text):
        lcd.cursor_pos = (row, 0)
        lcd.write_string(text.ljust(20))  # FORCE overwrite full row

    # Clear ONLY when state changes OR first run
    if state != last_state:
        lcd.clear()
        last_state = state

    # LINE 1
    write(0, f"TIME:{ph_time}")

    # LINE 2
    write(1, f"T:{temp:5.1f}C I:{current:5.2f}A")

    # LINE 3
    write(2, f"STATE:{state}")

    # LINE 4
    if ml:
        write(
            3,
            f"H:{ml.get('hotspot_prob',0):.2f} "
            f"O:{ml.get('overload_prob',0):.2f}"
        )
    else:
        write(3, "SYSTEM MONITORING")


# -----------------------
# MAIN LOOP
# -----------------------
def run():
    print("System running...")

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
            lcd_update(0, 0, "Error", None)

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
