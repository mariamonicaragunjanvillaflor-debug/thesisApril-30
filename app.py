from flask import Flask, request, jsonify, render_template
import joblib
import os
from flask_cors import CORS
from datetime import datetime

from feature_engine import build_basic_features, temp_buffer

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

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

print("✓ Models loaded successfully")


# =========================================================
# FEATURE LOCK
# =========================================================
FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

print("✓ Feature lock loaded")


# =========================================================
# THRESHOLDS (ENGINEERING BASED)
# =========================================================
TEMP_NORMAL_MAX = 45
TEMP_WARNING_MIN = 55
TEMP_WARNING_MAX = 60
TEMP_CRITICAL = 70

ML_WARNING = 0.60
ML_CRITICAL = 0.85


# =========================================================
# API
# =========================================================
@app.route("/api/update", methods=["POST"])
def update_data():

    global latest_data_store

    try:
        data = request.json

        temp = float(data["temperature"])
        current = float(data["current"])

        # =================================================
        # 🔥 HARD PHYSICS SAFETY LAYER (MOST IMPORTANT FIX)
        # =================================================
        if temp < TEMP_NORMAL_MAX:
            state = "Normal"
            status = "SAFE TEMPERATURE"

            hot_prob = 0.0
            ovl_prob = 0.0

        elif temp >= TEMP_CRITICAL:
            state = "Critical"
            status = "OVERHEATING (TEMP LIMIT)"

            hot_prob = 1.0
            ovl_prob = 0.0

        else:
            # =================================================
            # ML ONLY IN MID-RANGE (55–70°C)
            # =================================================
            X = build_basic_features(temp, current)
            X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

            hot_prob = hotspot_model.predict_proba(X)[0][1]
            ovl_prob = overload_model.predict_proba(X)[0][1]

            # =================================================
            # STATE DECISION (ML-GUIDED)
            # =================================================
            if hot_prob >= ML_CRITICAL or ovl_prob >= ML_CRITICAL:
                state = "Critical"
                status = "ML CRITICAL RISK"

            elif hot_prob >= ML_WARNING:
                state = "Warning"
                status = "EARLY HOTSPOT WARNING"

            elif ovl_prob >= ML_WARNING:
                state = "Warning"
                status = "EARLY OVERLOAD WARNING"

            else:
                state = "Normal"
                status = "STABLE MID-RANGE"

        # =================================================
        # STORE DATA
        # =================================================
        latest_data_store = {
            "temperature": round(temp, 2),
            "current": round(current, 2),

            "breakerState": state,
            "status": status,

            "ml": {
                "hotspot_prob": float(round(hot_prob, 4)),
                "overload_prob": float(round(ovl_prob, 4)),
                "composite_risk": float(round((hot_prob + ovl_prob) / 2, 4))
            },

            "time": datetime.now().strftime("%H:%M:%S")
        }

        # =================================================
        # DEBUG LOG
        # =================================================
        print(
            f"[{state}] "
            f"T={temp:.2f}C | I={current:.2f}A | "
            f"HP={hot_prob:.3f} | OP={ovl_prob:.3f}"
        )

        return jsonify({
            "success": True,
            "state": state,
            "status": status,
            "ml": latest_data_store["ml"]
        })

    except Exception as e:
        print("API ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        })


# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/latest-data")
def latest():
    return jsonify(latest_data_store)


@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "models_loaded": True
    })


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    print("⚡ SMART PANEL SYSTEM STARTED")
    app.run(host="0.0.0.0", port=5000, debug=False)
