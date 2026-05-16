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
# SYSTEM STABILITY CONFIG
# =========================================================
SAMPLE_INTERVAL = 1.0
I2C_DELAY = 0.02
WARMUP_SAMPLES = 10

FLASK_URL = "http://127.0.0.1:5000/api/update"
TIMEOUT = 2


# =========================================================
# INITIAL DELAY (hardware stabilization)
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
# LCD SAFE INIT
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
            print(f"LCD init retry {i+1}/3 failed:", e)
            time.sleep(1)

    raise RuntimeError("LCD failed to initialize")


lcd = init_lcd()


# =========================================================
# TIME HELPERS
# =========================================================
def get_ph_time():
    return datetime.now().strftime("%H:%M:%S")


def center_text(text, width=16):
    text = str(text)
    return text[:width] if len(text) >= width else text.center(width)


# =========================================================
# SENSOR READS
# =========================================================
def read_temperature():
    try:
        time.sleep(I2C_DELAY)
        return mlx.object_temperature
    except:
        return 35.0


def read_adc(channel=0):
    raw = bus.read_word_data(0x48, 0x40 + channel)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)

    if raw > 32767:
        raw -= 65536

    time.sleep(I2C_DELAY)
    return raw


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
last_beep_time = 0
buzzer_state = False


def set_outputs(state):
    global last_beep_time, buzzer_state

    now = time.time()

    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)
        buzzer_state = False

    elif state == "Warning":
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

        if now - last_beep_time >= 2:
            buzzer_state = not buzzer_state
            GPIO.output(BUZZER, buzzer_state)
            last_beep_time = now

    elif state == "WarmingUp":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)
        GPIO.output(BUZZER, 0)

    else:  # Critical or Error fallback
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)
        buzzer_state = True


# =========================================================
# LCD WRITE SAFE
# =========================================================
def lcd_write(row, text):
    try:
        text = str(text).ljust(16)[:16]
        lcd.cursor_pos = (row, 0)
        lcd.write_string(text)
        time.sleep(I2C_DELAY)
    except Exception as e:
        print("LCD ERROR:", e)
        recover_i2c()


def lcd_update(state, ml=None):
    now = get_ph_time()

    hotspot = ml.get("hotspot_prob", 0.0) if ml else 0.0
    overload = ml.get("overload_prob", 0.0) if ml else 0.0

    status_map = {
        "Normal": "SYSTEM OK",
        "Warning": "CHECK LOAD",
        "Critical": "DANGER!",
        "WarmingUp": "INITIALIZING"
    }

    status = status_map.get(state, "UNKNOWN")

    lcd_write(0, center_text(now))
    lcd_write(1, center_text(f"HP:{hotspot:.2f}"))
    lcd_write(2, center_text(f"OP:{overload:.2f}"))
    lcd_write(3, center_text(f"{state}|{status}"))


# =========================================================
# MAIN LOOP
# =========================================================
last_state = None


def run():
    global last_state

    print("System running...")

    lcd.clear()
    lcd_write(0, "SYSTEM STARTING")
    time.sleep(1)

    while True:
        loop_start = time.time()

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

            state = result.get("state", "Critical")  # safe fallback
            ml = result.get("ml", None)

            set_outputs(state)

            if state != last_state:
                lcd_update(state, ml)
                last_state = state

            print(f"{state} | T:{temp:.2f} | I:{current:.2f}")

        except Exception as e:
            print("ERROR:", e)

            set_outputs("Critical")

            lcd_write(0, "SYSTEM ERROR")
            lcd_write(1, "RECOVERING...")
            lcd_write(2, "")
            lcd_write(3, "")

            recover_i2c()

        elapsed = time.time() - loop_start
        time.sleep(max(0, SAMPLE_INTERVAL - elapsed))


# =========================================================
# CLEAN EXIT
# =========================================================
if __name__ == "__main__":
    try:
        run()

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        GPIO.cleanup()
        try:
            lcd.clear()
        except:
            pass
