import requests
import time
import math
from datetime import datetime

import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

import board
import busio
import adafruit_mlx90614

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# =========================================================
# CONFIG
# =========================================================
LCD_REFRESH_INTERVAL = 1.0
FLASK_URL = "http://127.0.0.1:5000/api/update"
TIMEOUT = 2

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
i2c = busio.I2C(board.SCL, board.SDA)

# =========================================================
# MLX90614 SETUP
# =========================================================
mlx = None

def init_mlx():
    global mlx
    try:
        mlx = adafruit_mlx90614.MLX90614(i2c)
        print("✔ MLX initialized")
    except Exception as e:
        print("MLX INIT FAILED:", e)
        mlx = None

init_mlx()

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

# =========================================================
# ADS1115 SETUP (FIXED - NO SMBUS)
# =========================================================
ads = ADS.ADS1115(i2c)
ads.gain = 1
ads.data_rate = 860

chan = AnalogIn(ads, 0)

def read_adc_voltage():
    return chan.voltage

def read_current(window_ms=300):
    start = time.time()

    values = []

    while (time.time() - start) < (window_ms / 1000):
        v = chan.voltage
        values.append(v)
        time.sleep(0.001)

    if len(values) == 0:
        return 0.0

    # Remove DC offset
    avg = sum(values) / len(values)
    centered = [x - avg for x in values]

    # RMS voltage
    sum_sq = sum(x*x for x in centered)
    rms_voltage = math.sqrt(sum_sq / len(centered))

    # SCT-013-000 calibration
    CT_RATIO = 2000
    BURDEN = 220.0

    # empirical correction
    CALIBRATION = 4.5

    current = rms_voltage * (CT_RATIO / BURDEN) * CALIBRATION

    return max(0.0, current)

# =========================================================
# LCD SETUP
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

def safe_float(value):
    try:
        return float(value) if value is not None else 0.0
    except:
        return 0.0

# =========================================================
# GPIO CONTROL
# =========================================================
def set_outputs(state):
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)

    elif state == "Warning":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)
        time.sleep(0.1)
        GPIO.output(BUZZER, 0)

    elif state == "Critical":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)

    elif state == "WarmingUp":
        GPIO.output(GREEN_LED, int(time.time() * 2) % 2)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)

    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 0)

# =========================================================
# LCD DISPLAY
# =========================================================
def lcd_update(state, ml, temp, current):
    try:
        now = get_time()

        temp = safe_float(temp)
        current = safe_float(current)
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

    temp = 0.0
    current = 0.0
    state = "Normal"
    ml = {"composite_risk": 0}

    while True:
        now = time.time()

        if now - last_sensor >= 3:
            temp = read_temperature()
            current = read_current()

            print(f"[{get_time()}] T={temp:.2f}°C | I={current:.2f}A | State={state}")

            try:
                response = requests.post(
                    FLASK_URL,
                    json={"temperature": temp, "current": current},
                    timeout=TIMEOUT
                )

                result = response.json()
                state = result.get("state", "Normal")
                ml = result.get("ml", ml)

            except Exception as e:
                print("API ERROR:", e)
                state = "Warning"

            set_outputs(state)
            last_sensor = now

        if now - last_lcd >= LCD_REFRESH_INTERVAL:
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
