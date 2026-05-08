from flask import Flask, request, jsonify, render_template
import joblib
import os
from dataclasses import dataclass
from flask_cors import CORS
from datetime import datetime

from feature_engine import build_basic_features

# ----------------------
# INIT
# ----------------------
app = Flask(__name__)
CORS(app)

latest_data_store = {}

# ----------------------
# LOAD MODELS
# ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

print("✓ Models loaded")

# ----------------------
# SENSOR STRUCT
# ----------------------
@dataclass
class SensorReading:
    ambient_temp_c: float
    temperature_c: float
    temperature_rise_c: float
    current_a: float
    thermal_slope_c_per_5s: float
    current_slope_a_per_5s: float


# ----------------------
# RECEIVE REAL HARDWARE DATA
# ----------------------
@app.route("/api/update", methods=["POST"])
def update_data():
    global latest_data_store

    try:
        data = request.json

        temp = float(data["temperature"])
        current = float(data["current"])

        # FEATURE ENGINE
        X = build_basic_features(temp, current)

        if X is None:
            risk = {
                "hotspot_prob": 0,
                "overload_prob": 0,
                "composite_risk": 0
            }

        else:
            hot_prob = hotspot_model.predict_proba(X)[0][1]
            ovl_prob = overload_model.predict_proba(X)[0][1]

            risk = {
                "hotspot_prob": float(hot_prob),
                "overload_prob": float(ovl_prob),
                "composite_risk": float((hot_prob + ovl_prob) / 2)
            }

        # SYSTEM STATE
        if temp >= 75 or risk["hotspot_prob"] > 0.7:
            state = "Overheating"

        elif current >= 21 or risk["overload_prob"] > 0.6:
            state = "Overload"

        else:
            state = "Normal"

        latest_data_store = {
            "temperature": temp,
            "current": current,
            "breakerState": state,
            "ml": risk,
            "time": datetime.now().strftime("%H:%M:%S")
        }

        return jsonify({
            "success": True,
            "state": state,
            "ml": risk
        })

    except Exception as e:
        print("ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        })


# ----------------------
# ROUTES
# ----------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/latest-data")
def latest():
    return jsonify(latest_data_store)


# ----------------------
# RUN
# ----------------------
if __name__ == "__main__":
    print("🔥 SYSTEM STARTED")
    app.run(host="0.0.0.0", port=5000, debug=True)