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
I2C_DELAY = 0.02
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
# I2C SETUP (shared bus)
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

        value = mlx.object_temperature
        return float(value) if value is not None else 0.0

    except Exception as e:
        print("MLX ERROR:", e)
        init_mlx()
        return 0.0

# =========================================================
# ADS1115 SETUP (SCT-013)
# =========================================================
ads = ADS.ADS1115(i2c)
ads.gain = 1
ads.data_rate = 860

chan = AnalogIn(ads, 0)

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
        if value is None:
            return 0.0
        return float(value)
    except:
        return 0.0

# =========================================================
# CURRENT SENSOR (SCT-013 RMS)
# =========================================================
def read_adc(channel=0):
    raw = bus.read_word_data(0x48, 0x40 + channel)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)

    if raw > 32767:
        raw -= 65536

    time.sleep(I2C_DELAY)
    return raw


def read_current(window_ms=300):
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
# GPIO OUTPUT CONTROL
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
        lcd.write_string(center("T:{:.1f}C".format(temp)))

        lcd.cursor_pos = (2, 0)
        lcd.write_string(center("I:{:.2f}A".format(current)))

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

        # SENSOR + API LOOP
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

        # LCD LOOP
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
