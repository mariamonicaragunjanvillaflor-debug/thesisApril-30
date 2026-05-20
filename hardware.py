
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
from smbus2 import SMBus

import board
import busio
import adafruit_mlx90614

import numpy as np
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


# =========================================================
# CONFIG
@@ -55,10 +58,27 @@ def init_mlx():
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

BURDEN_RESISTOR = 220.0
CT_RATIO = 2000
CALIBRATION = 0.0505
SAMPLES = 800
NOISE_THRESHOLD = 0.05


# =========================================================
# LCD INIT
# =========================================================
@@ -81,7 +101,6 @@ def init_lcd():

raise RuntimeError("LCD failed")


lcd = init_lcd()


@@ -98,7 +117,7 @@ def center(text):


# =========================================================
# SAFE TEMP READ (STABLE FIX)
# TEMP READ
# =========================================================
def read_temperature():
global mlx
@@ -116,10 +135,31 @@ def read_temperature():


# =========================================================
# CURRENT (placeholder)
# CURRENT (SCT-013-000 RMS IMPLEMENTATION)
# =========================================================
def read_current():
    return 0.0

    samples = []

    for _ in range(SAMPLES):
        samples.append(chan.voltage)

    samples = np.array(samples)

    # remove DC bias
    samples = samples - np.mean(samples)

    vrms = np.sqrt(np.mean(samples ** 2))

    secondary_current = vrms / BURDEN_RESISTOR
    primary_current = secondary_current * CT_RATIO

    primary_current *= CALIBRATION

    if primary_current < NOISE_THRESHOLD:
        primary_current = 0

    return primary_current


# =========================================================
@@ -160,7 +200,7 @@ def lcd_update(state, ml, temp, current):
lcd.write_string(center(f"T:{temp:.1f}C"))

lcd.cursor_pos = (2, 0)
        lcd.write_string(center(f"HP:{hp:.2f} OP:{op:.2f}"))
        lcd.write_string(center(f"I:{current:.2f}A"))

lcd.cursor_pos = (3, 0)
lcd.write_string(center(f"{state} {cr:.2f}"))
@@ -189,9 +229,6 @@ def run():
temp = read_temperature()
current = read_current()

            # =================================================
            # SAFE API CALL (IMPORTANT FIX)
            # =================================================
try:
response = requests.post(
FLASK_URL,
@@ -203,7 +240,7 @@ def run():
state = result.get("state", "Normal")
ml = result.get("ml", last_valid_ml)

                last_valid_ml = ml  # store last good reading
                last_valid_ml = ml

except Exception as api_error:
print("API ERROR:", api_error)
@@ -214,14 +251,10 @@ def run():

now = time.time()

            # LCD refresh
if now - last_lcd >= LCD_REFRESH_INTERVAL:
lcd_update(state, ml, temp, current)
last_lcd = now

            # =================================================
            # RPi MONITOR OUTPUT (CLEAN + STABLE)
            # =================================================
print(
f"[{state}] "
f"T:{temp:.2f} I:{current:.2f} "
@@ -230,7 +263,6 @@ def run():
f"CR:{ml.get('composite_risk', 0):.3f}"
)

            # periodic recovery
if now - last_recovery > I2C_RECOVERY_INTERVAL:
os.system("i2cdetect -y 1 > /dev/null 2>&1")
last_recovery = now
