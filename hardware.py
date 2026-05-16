import requests
import time
import math
import os
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
BUZZER = 22

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)
GPIO.setup(BUZZER, GPIO.OUT)

GPIO.output(GREEN_LED, 0)
GPIO.output(RED_LED, 0)
GPIO.output(BUZZER, 0)


# -----------------------
# LCD SETUP
# -----------------------
lcd = CharLCD(
    i2c_expander='PCF8574',
    address=0x27,
    port=1,
    cols=16,
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
# TIME
# -----------------------
def get_ph_time():
    return datetime.now().strftime("%H:%M:%S")


# -----------------------
# CENTER TEXT
# -----------------------
def center_text(text, width=16):
    text = str(text)
    return text[:width] if len(text) >= width else text.center(width)


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
        time.sleep(0.001)

        raw = read_adc(0)
        offset += (raw - offset) * 0.01
        centered = raw - offset

        sum_sq += centered * centered
        samples += 1

    if samples == 0:
        return 0.0

    rms = math.sqrt(sum_sq / samples)
    current = rms * 0.001

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
# RECOVERY
# -----------------------
def recover_i2c():
    try:
        os.system("i2cdetect -y 1 > /dev/null 2>&1")
        time.sleep(0.1)
    except:
        pass


# -----------------------
# LED + BUZZER CONTROL
# -----------------------
last_beep_time = 0
buzzer_state = False

def set_outputs(state):
    global last_beep_time, buzzer_state

    current_time = time.time()

    # NORMAL
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)
        buzzer_state = False

    # WARNING (beep every 2 seconds)
    elif state == "Warning":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

        if current_time - last_beep_time >= 2:
            buzzer_state = not buzzer_state
            GPIO.output(BUZZER, buzzer_state)
            last_beep_time = current_time

    # ALERT / ERROR (continuous)
    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)
        buzzer_state = True


# -----------------------
# LCD WRITE SAFE
# -----------------------
def lcd_write(row, text):
    try:
        text = (str(text) + " " * 16)[:16]
        lcd.cursor_pos = (row, 0)
        lcd.write_string(text)
    except Exception as e:
        print("LCD ERROR:", e)
        recover_i2c()


# -----------------------
# LCD UPDATE
# -----------------------
def lcd_update(state, ml=None):
    ph_time = get_ph_time()

    hotspot = ml.get("hotspot_prob", 0.0) if ml else 0.0
    overload = ml.get("overload_prob", 0.0) if ml else 0.0

    line1 = center_text(ph_time)
    line2 = center_text(f"HP:{hotspot:.2f}")
    line3 = center_text(f"OP:{overload:.2f}")

    status = {
        "Normal": "SYSTEM OK",
        "Warning": "CHECK LOAD"
    }.get(state, "ALERT")

    line4 = center_text(f"{state}|{status}")

    lcd_write(0, line1)
    lcd_write(1, line2)
    lcd_write(2, line3)
    lcd_write(3, line4)


# -----------------------
# MAIN LOOP
# -----------------------
def run():
    print("System running...")

    lcd.clear()
    lcd_write(0, "SYSTEM STARTING")
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

            set_outputs(state)
            lcd_update(state, ml)

            print(f"{state} | T:{temp:.2f} | I:{current:.2f}")

        except Exception as e:
            print("ERROR:", e)

            set_outputs("Error")

            lcd_write(0, "SYSTEM ERROR")
            lcd_write(1, "RESTARTING...")
            lcd_write(2, "")
            lcd_write(3, "")

            recover_i2c()

        time.sleep(1)


# -----------------------
# CLEAN EXIT
# -----------------------
if __name__ == "__main__":
    try:
        run()

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        GPIO.cleanup()
        lcd.clear()
