import requests
import time
import os
import math
from smbus2 import SMBus
from datetime import datetime

import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

import board
import busio
import adafruit_mlx90614

import numpy as np
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


# =========================================================
# CONFIG
# =========================================================
SAMPLE_INTERVAL = 1.0
LCD_REFRESH_INTERVAL = 1.0
I2C_RECOVERY_INTERVAL = 10
I2C_DELAY = 0.001
WARMUP_SAMPLES = 10

FLASK_URL = "http://127.0.0.1:5000/api/update"
TIMEOUT = 2

time.sleep(2)

last_beep_time = 0
last_green_blink = 0
green_state = False
buzzer_state = False
bus = SMBus(1)
# =========================================================
# GPIO SETUP
# =========================================================
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

# =========================================================
# SAFE MLX INIT
# =========================================================
mlx = None

def init_mlx():
    global mlx
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        mlx = adafruit_mlx90614.MLX90614(i2c)
        print("✔ MLX initialized")
    except Exception as e:
        print("MLX INIT FAILED:", e)
        mlx = None

init_mlx()


# =========================================================
# ADS1115 + SCT SETUP (NEW)
# =========================================================
i2c_ads = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c_ads)

ads.gain = 1
ads.data_rate = 860

chan = AnalogIn(ads, 0)



# =========================================================
# LCD INIT
# =========================================================
def init_lcd():
    for i in range(3):
        try:
            lcd = CharLCD(
                i2c_expander='PCF8574',
                address=0x27,
                port=1,
                cols=16,
                rows=4
            )
            lcd.clear()
            time.sleep(0.5)
            return lcd
        except Exception as e:
            print(f"LCD retry {i+1}/3 failed:", e)
            time.sleep(1)

    raise RuntimeError("LCD failed")

lcd = init_lcd()


# =========================================================
# HELPERS
# =========================================================
def get_time():
    return datetime.now().strftime("%H:%M:%S")


def center(text):
    text = str(text)
    return text[:16] if len(text) > 16 else text.center(16)


# =========================================================
# TEMP READ
# =========================================================
def read_temperature():
    global mlx

    try:
        if mlx is None:
            init_mlx()

        return float(mlx.object_temperature)

    except Exception as e:
        print("MLX ERROR:", e)
        init_mlx()
        return 0.0

def read_adc(channel=0):
    raw = bus.read_word_data(0x48, 0x40 + channel)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)

    if raw > 32767:
        raw -= 65536

    time.sleep(I2C_DELAY)
    return raw
# =========================================================
# CURRENT (SCT-013-000 RMS IMPLEMENTATION)
# =========================================================
def read_current(window_ms=100):
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

# =========================================================
# I2C RECOVERY
# =========================================================
def recover_i2c():
    try:
        os.system("i2cdetect -y 1 > /dev/null 2>&1")
        time.sleep(0.1)
    except:
        pass


# =========================================================
# OUTPUT CONTROL
# =========================================================
def set_outputs(state):
    global last_beep_time, last_green_blink, green_state, buzzer_state

    current_time = time.time()

    # =========================
    # NORMAL STATE
    # =========================
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)

    # =========================
    # WARNING STATE
    # Buzzer beeps every 3 seconds
    # =========================
    elif state == "Warning":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

        if current_time - last_beep_time >= 3:
            buzzer_state = not buzzer_state
            GPIO.output(BUZZER, buzzer_state)
            last_beep_time = current_time

    # =========================
    # CRITICAL STATE
    # Intermittent fast buzzer
    # =========================
    elif state == "Critical":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

        # fast intermittent beep (0.5 sec toggle)
        if current_time - last_beep_time >= 0.5:
            buzzer_state = not buzzer_state
            GPIO.output(BUZZER, buzzer_state)
            last_beep_time = current_time

    # =========================
    # WARMING UP STATE
    # Blinking green LED
    # =========================
    elif state == "WarmingUp":
        GPIO.output(RED_LED, 0)

        if current_time - last_green_blink >= 0.5:
            green_state = not green_state
            GPIO.output(GREEN_LED, green_state)
            last_green_blink = current_time

        GPIO.output(BUZZER, 0)

    # =========================
    # DEFAULT SAFETY
    # =========================
    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 0)

# =========================================================
# LCD UPDATE
# =========================================================
def lcd_update(state, ml, temp, current):
    try:
        now = get_time()

        hp = ml.get("hotspot_prob", 0.0) if ml else 0.0
        op = ml.get("overload_prob", 0.0) if ml else 0.0
        cr = ml.get("composite_risk", 0.0) if ml else 0.0

        lcd.cursor_pos = (0, 0)
        lcd.write_string(center(now))

        lcd.cursor_pos = (1, 0)
        lcd.write_string(center(f"T:{temp:.1f}C"))

        lcd.cursor_pos = (2, 0)
        lcd.write_string(center(f"I:{current:.2f}A"))

        lcd.cursor_pos = (3, 0)
        lcd.write_string(center(f"{state} {cr:.2f}"))

    except Exception as e:
        print("LCD ERROR:", e)
        try:
            lcd.clear()
        except:
            pass


# =========================================================
# MAIN LOOP
# =========================================================
def run():
    print("System running...")

    last_lcd = 0
    last_sensor = 0

    temp = 0
    current = 0
    state = "Normal"
    ml = {"hotspot_prob": 0, "overload_prob": 0, "composite_risk": 0}

    while True:
        now = time.time()

        # =========================
        # 🔴 SLOW LOOP (sensor + API)
        # =========================
        if now - last_sensor >= 3:   # <-- IMPORTANT FIX
            temp = read_temperature()
            current = read_current()

            try:
                response = requests.post(
                    FLASK_URL,
                    json={"temperature": temp, "current": current},
                    timeout=2
                )

                result = response.json()
                state = result.get("state", "Normal")
                ml = result.get("ml", ml)

            except Exception as e:
                print("API ERROR:", e)
                state = "Warning"

            set_outputs(state)
            last_sensor = now

        # =========================
        # 🟢 FAST LOOP (LCD every 1 sec)
        # =========================
        if now - last_lcd >= 1:
            lcd_update(state, ml, temp, current)
            last_lcd = now

        time.sleep(0.1)


# =========================================================
# START
# =========================================================
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        GPIO.cleanup()
        try:
            lcd.clear()
        except:
            pass
