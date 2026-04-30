from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory
import joblib
from dataclasses import dataclass
import pandas as pd
from flask_mail import Mail, Message
from flask_cors import CORS
import json
import time
import os
from datetime import datetime
from collections import deque
import random

# ✅ FIXED: unified feature pipeline
from feature_engine import build_basic_features

latest_data_store = {}

# ----------------------
# MODELS
# ----------------------
hotspot_model = None
overload_model = None

# ----------------------
# FLASK SETUP
# ----------------------
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# ----------------------
# EMAIL CONFIG
# ----------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'breaker.monitor.system@gmail.com'
app.config['MAIL_PASSWORD'] = 'kzng lhzr elww gyyu'
app.config['MAIL_DEFAULT_SENDER'] = 'breaker.monitor.system@gmail.com'
app.config['MAIL_DEBUG'] = True

try:
    mail = Mail(app)
    print("✓ Email service initialized")
except Exception as e:
    print(f"✗ Email initialization error: {e}")
    mail = None

# ----------------------
# LOAD MODELS
# ----------------------
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    hotspot_path = os.path.join(BASE_DIR, "ml", "hotspot_model.pkl")
    overload_path = os.path.join(BASE_DIR, "ml", "overload_model.pkl")

    hotspot_model = joblib.load(hotspot_path)
    overload_model = joblib.load(overload_path)

    print("✓ Models loaded successfully")

except Exception as e:
    print(f"✗ MODEL LOAD ERROR: {e}")

# ----------------------
# STREAMING BUFFER (only for slope)
# ----------------------
temp_buffer = deque(maxlen=10)
current_buffer = deque(maxlen=10)

def compute_slope(temp, current):
    temp_buffer.append(temp)
    current_buffer.append(current)

    if len(temp_buffer) < 2:
        return 0.0, 0.0

    dt = len(temp_buffer) - 1

    thermal_slope = (temp_buffer[-1] - temp_buffer[0]) / dt * 5
    current_slope = (current_buffer[-1] - current_buffer[0]) / dt * 5

    return thermal_slope, current_slope

# ----------------------
# SENSOR DATA STRUCT
# ----------------------
@dataclass
class SensorReading:
    ambient_temp_c: float
    temperature_c: float
    temperature_rise_c: float
    current_a: float
    thermal_slope_c_per_5s: float
    current_slope_a_per_5s: float

temp_history = deque(maxlen=20)
current_history = deque(maxlen=20)

# ----------------------
# FIXED PREDICTION PIPELINE
# ----------------------
def predict_risk(reading: SensorReading):

    # 🔥 ONLY KEEP HISTORY (for feature engine consistency)
    temp_history.append(reading.temperature_c)
    current_history.append(reading.current_a)

    # ✅ BUILD FEATURES USING SHARED ENGINE (IMPORTANT FIX)
    X = build_basic_features(reading.temperature_c, reading.current_a)

    if X is None:
        return {
            "hotspot_prob": 0,
            "overload_prob": 0,
            "hotspot_flag": 0,
            "overload_flag": 0,
            "composite_risk": 0
        }

    # ----------------------
    # MODEL PREDICTION
    # ----------------------
    hotspot_prob = float(hotspot_model.predict_proba(X)[0, 1])
    overload_prob = float(overload_model.predict_proba(X)[0, 1])

    return {
        "hotspot_prob": hotspot_prob,
        "overload_prob": overload_prob,
        "hotspot_flag": int(hotspot_prob >= 0.75),
        "overload_flag": int(overload_prob >= 0.5),
        "composite_risk": 0.5 * hotspot_prob + 0.5 * overload_prob,
    }

# ----------------------
# SIMULATION + ROUTES (UNCHANGED LOGIC)
# ----------------------
sim_temp = 35
sim_current = 12

@app.route("/api/simulate")
def simulate():
    global sim_temp, sim_current, latest_data_store

    thermal_slope, current_slope = compute_slope(sim_temp, sim_current)

    reading = SensorReading(
        ambient_temp_c=25.0,
        temperature_c=sim_temp,
        temperature_rise_c=sim_temp - 25.0,
        current_a=sim_current,
        thermal_slope_c_per_5s=thermal_slope,
        current_slope_a_per_5s=current_slope
    )

    risk = predict_risk(reading)

    if sim_temp >= 75 or risk["hotspot_prob"] > 0.7:
        state = "Overheating"
    elif sim_current >= 21 or risk["overload_prob"] > 0.6:
        state = "Overload"
    else:
        state = "Normal"

    latest_data_store = {
        "temperature": sim_temp,
        "current": sim_current,
        "breakerState": state,
        "ml": risk
    }

    return jsonify(latest_data_store)

# ----------------------
# DASHBOARD ROUTES
# ----------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/full_history")
def full_history():
    return render_template("full_history.html")

@app.route("/api/latest-data")
def latest():
    return jsonify(latest_data_store)

# ----------------------
# RUN SERVER
# ----------------------
if __name__ == "__main__":
    print("\n🔥 SYSTEM STARTED")
    app.run(debug=True, host="0.0.0.0", port=5000)