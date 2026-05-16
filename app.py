from flask import Flask, request, jsonify, render_template
import joblib
import os
from flask_cors import CORS
from datetime import datetime

from feature_engine import (
    build_basic_features,
    temp_buffer,
    current_buffer
)

# =========================================================
# INIT
# =========================================================
app = Flask(__name__)
CORS(app)

latest_data_store = {}

print("🔥 INITIALIZING SYSTEM...")


# =========================================================
# LOAD MODELS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

hotspot_model = joblib.load(
    os.path.join(BASE_DIR, "ml/hotspot_model.pkl")
)

overload_model = joblib.load(
    os.path.join(BASE_DIR, "ml/overload_model.pkl")
)

print("✓ Models loaded successfully")


# =========================================================
# FEATURE LOCK
# Ensures training/inference consistency
# =========================================================
FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

print("✓ Feature lock loaded")
print("Total features:", len(FEATURE_COLUMNS))


# =========================================================
# SYSTEM CONFIG
# =========================================================
WARMUP_SAMPLES = 10

# ML thresholds
WARNING_THRESHOLD = 0.60
CRITICAL_THRESHOLD = 0.85


# =========================================================
# API
# =========================================================
@app.route("/api/update", methods=["POST"])
def update_data():

    global latest_data_store

    try:
        # =================================================
        # RECEIVE SENSOR DATA
        # =================================================
        data = request.json

        temp = float(data["temperature"])
        current = float(data["current"])

        # =================================================
        # FEATURE ENGINE
        # IMPORTANT:
        # Uses SAME feature_engine.py from training
        # =================================================
        X = build_basic_features(temp, current)

        # =================================================
        # FORCE TRAINING COLUMN ORDER
        # Prevents feature mismatch
        # =================================================
        X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

        # =================================================
        # ML PREDICTION
        # =================================================
        hot_prob = hotspot_model.predict_proba(X)[0][1]
        ovl_prob = overload_model.predict_proba(X)[0][1]

        composite_risk = (hot_prob + ovl_prob) / 2

        # =================================================
        # ENGINEERING STATE LOGIC
        # =================================================

        # ---------------------------------------------
        # WARMUP
        # ---------------------------------------------
        if len(temp_buffer) < WARMUP_SAMPLES:

            state = "WarmingUp"
            status = "COLLECTING DATA"

        # ---------------------------------------------
        # CRITICAL
        # ---------------------------------------------
        elif hot_prob >= CRITICAL_THRESHOLD:

            state = "Critical"
            status = "HOTSPOT CRITICAL"

        elif ovl_prob >= CRITICAL_THRESHOLD:

            state = "Critical"
            status = "OVERLOAD CRITICAL"

        # ---------------------------------------------
        # WARNING
        # ---------------------------------------------
        elif hot_prob >= WARNING_THRESHOLD:

            state = "Warning"
            status = "HOTSPOT WARNING"

        elif ovl_prob >= WARNING_THRESHOLD:

            state = "Warning"
            status = "OVERLOAD WARNING"

        # ---------------------------------------------
        # NORMAL
        # ---------------------------------------------
        else:

            state = "Normal"
            status = "SYSTEM NORMAL"

        # =================================================
        # STORE LATEST DATA
        # =================================================
        latest_data_store = {

            "temperature": round(temp, 2),
            "current": round(current, 2),

            "breakerState": state,
            "status": status,

            "ml": {
                "hotspot_prob": round(float(hot_prob), 4),
                "overload_prob": round(float(ovl_prob), 4),
                "composite_risk": round(float(composite_risk), 4)
            },

            "buffer_size": len(temp_buffer),

            "time": datetime.now().strftime("%H:%M:%S")
        }

        # =================================================
        # DEBUG PRINT
        # =================================================
        print(
            f"[{state}] "
            f"T={temp:.2f}C | "
            f"I={current:.2f}A | "
            f"HP={hot_prob:.3f} | "
            f"OP={ovl_prob:.3f}"
        )

        # =================================================
        # RESPONSE
        # =================================================
        return jsonify({
            "success": True,
            "state": state,
            "status": status,

            "ml": {
                "hotspot_prob": round(float(hot_prob), 4),
                "overload_prob": round(float(ovl_prob), 4),
                "composite_risk": round(float(composite_risk), 4)
            }
        })

    except Exception as e:

        print("API ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        })


# =========================================================
# WEB ROUTES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/latest-data")
def latest():
    return jsonify(latest_data_store)


# =========================================================
# HEALTH CHECK
# =========================================================
@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "models_loaded": True,
        "buffer_size": len(temp_buffer)
    })


# =========================================================
# RUN SERVER
# =========================================================
if __name__ == "__main__":

    print("===================================")
    print("⚡ SMART PANEL MONITORING SYSTEM")
    print("🔥 Predictive ML Protection Enabled")
    print("===================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
