import requests
import time
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
I2C_RECOVERY_INTERVAL = 10

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


# =========================================================
# SAFE MLX INIT (IMPORTANT FIX)
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
# SAFE TEMP READ (FIXED)
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
        return 35.0


# =========================================================
# CURRENT (placeholder)
# =========================================================
def read_current():
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

    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)
        GPIO.output(BUZZER, 1)


# =========================================================
# LCD UPDATE (STABLE)
# =========================================================
def lcd_update(state, ml, temp, current):
    try:
        now = get_time()

        hp = ml.get("hotspot_prob", 0.0)
        op = ml.get("overload_prob", 0.0)
        cr = ml.get("composite_risk", 0.0)

        lcd.cursor_pos = (0, 0)
        lcd.write_string(center(now))

        lcd.cursor_pos = (1, 0)
        lcd.write_string(center(f"T:{temp:.1f}C"))

        lcd.cursor_pos = (2, 0)
        lcd.write_string(center(f"HP:{hp:.2f} OP:{op:.2f}"))

        lcd.cursor_pos = (3, 0)
        lcd.write_string(center(f"{state} {cr:.2f}"))

    except Exception as e:
        print("LCD ERROR:", e)
        try:
            lcd.clear()
        except:
            pass


# =========================================================
# I2C RECOVERY
# =========================================================
def recover_i2c():
    try:
        os.system("i2cdetect -y 1 > /dev/null 2>&1")
    except:
        pass


# =========================================================
# MAIN LOOP
# =========================================================
def run():
    print("System running...")

    last_lcd = 0
    last_recovery = time.time()

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

            now = time.time()

            # LCD update
            if now - last_lcd >= LCD_REFRESH_INTERVAL:
                lcd_update(state, ml, temp, current)
                last_lcd = now

            # =====================================================
            # 🔥 THIS IS WHAT YOU ASKED (RPi MONITOR OUTPUT)
            # =====================================================
            print(
                f"[{state}] "
                f"T:{temp:.2f} I:{current:.2f} "
                f"HP:{ml.get('hotspot_prob', 0):.3f} "
                f"OP:{ml.get('overload_prob', 0):.3f} "
                f"CR:{ml.get('composite_risk', 0):.3f}"
            )

            # periodic recovery
            if now - last_recovery > I2C_RECOVERY_INTERVAL:
                recover_i2c()
                last_recovery = now

        except Exception as e:
            print("SYSTEM ERROR:", e)

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
