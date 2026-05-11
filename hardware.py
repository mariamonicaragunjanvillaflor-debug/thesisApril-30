import requests
import time
import math
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
from smbus2 import SMBus

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
# I2C / ADS1115 SETUP
# -----------------------
bus = SMBus(1)
ADS1115_ADDR = 0x48

# -----------------------
# SCT-013 CALIBRATION (from Arduino)
# -----------------------
SUPPLY_VOLTAGE = 5.0
ADC_COUNTS = 32767.0

CT_PRIMARY_A = 100.0
CT_SECONDARY_A = 0.05
BURDEN_RESISTOR = 33.0

CT_RATIO = CT_PRIMARY_A / CT_SECONDARY_A
AMPS_PER_COUNT = (SUPPLY_VOLTAGE / ADC_COUNTS) * (CT_RATIO / BURDEN_RESISTOR)

# -----------------------
# STATE MEMORY
# -----------------------
last_state = None


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
# RMS CURRENT (Arduino equivalent)
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
    current = rms_counts * AMPS_PER_COUNT

    if current < 0.05:
        current = 0.0

    return current


# -----------------------
# TEMP SENSOR (placeholder)
# -----------------------
def read_temperature():
    # Replace later with real DS18B20 / NTC / ADC
    return 35.0


# -----------------------
# LED CONTROL
# -----------------------
def set_led(state):
    if state == "Normal":
        GPIO.output(GREEN_LED, 1)
        GPIO.output(RED_LED, 0)

    elif state in ["Overload", "Overheating"]:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 1)

    else:
        GPIO.output(GREEN_LED, 0)
        GPIO.output(RED_LED, 0)


# -----------------------
# LCD UPDATE
# -----------------------
def lcd_update(temp, current, state, ml=None):
    global last_state

    if state != last_state:
        lcd.clear()
        last_state = state

    lcd.cursor_pos = (0, 0)
    lcd.write_string(f"T:{temp:.1f}C I:{current:.2f}A   ")

    lcd.cursor_pos = (1, 0)
    lcd.write_string(f"STATE: {state}        ")

    if ml:
        lcd.cursor_pos = (2, 0)
        lcd.write_string(
            f"H:{ml.get('hotspot_prob',0):.2f} O:{ml.get('overload_prob',0):.2f}"
        )


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

            print(f"{state} | T:{temp:.1f} | I:{current:.2f}")

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