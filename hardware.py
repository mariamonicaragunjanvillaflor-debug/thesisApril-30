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


# =========================================================
# CONFIG
# =========================================================
SAMPLE_INTERVAL = 1.0
LCD_REFRESH_INTERVAL = 1.0
I2C_DELAY = 0.02

FLASK_URL = "http://127.0.0.1:5000/api/update"
TIMEOUT = 2


# =========================================================
# SAFETY INIT DELAY
# =========================================================
time.sleep(2)


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
# I2C SETUP
# =========================================================
bus = SMBus(1)
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90614.MLX90614(i2c)


# =========================================================
# LCD INIT (SAFE RETRY)
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

    raise RuntimeError("LCD failed to initialize")


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
# SENSOR READS
# =========================================================
def read_temperature():
    try:
        time.sleep(I2C_DELAY)
        return float(mlx.object_temperature)
    except:
        return 35.0


def read_current():
    # placeholder (keep safe if ADC not ready)
    return 0.0


# =========================================================
# OUTPUT CONTROL
# =========================================================
def set_outputs(state):
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)

    elif state == "Warning":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 0)

    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)


# =========================================================
# LCD UPDATE
# =========================================================
def lcd_update(state, ml, temp, current):
    try:
        now = get_time()

        hp = ml.get("hotspot_prob", 0.0) if ml else 0.0
        op = ml.get("overload_prob", 0.0) if ml else 0.0

        lcd.cursor_pos = (0, 0)
        lcd.write_string(center(now))

        lcd.cursor_pos = (1, 0)
        lcd.write_string(center(f"T:{temp:.1f}C"))

        lcd.cursor_pos = (2, 0)
        lcd.write_string(center(f"HP:{hp:.2f} OP:{op:.2f}"))

        lcd.cursor_pos = (3, 0)
        lcd.write_string(center(state))

    except Exception as e:
        print("LCD error:", e)
        try:
            lcd.clear()
        except:
            pass


# =========================================================
# MAIN LOOP
# =========================================================
def run():
    print("System running...")

    last_lcd_update = 0

    # IMPORTANT FIX: force first LCD update
    first_run = True

    while True:
        try:
            temp = read_temperature()
            current = read_current()

            response = requests.post(
                FLASK_URL,
                json={"temperature": temp, "current": current},
                timeout=TIMEOUT
            )

            result = response.json()

            state = result.get("state", "Normal")
            ml = result.get("ml", {})

            set_outputs(state)

            # =================================================
            # FIX: ALWAYS UPDATE FIRST + PERIODIC REFRESH
            # =================================================
            now = time.time()
            if first_run or (now - last_lcd_update >= LCD_REFRESH_INTERVAL):
                lcd_update(state, ml, temp, current)
                last_lcd_update = now
                first_run = False

            print(f"{state} | T:{temp:.2f} | I:{current:.2f}")

        except Exception as e:
            print("ERROR:", e)
            set_outputs("Critical")

            try:
                lcd.clear()
                lcd.write_string("SYSTEM ERROR")
            except:
                pass

        time.sleep(SAMPLE_INTERVAL)


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
