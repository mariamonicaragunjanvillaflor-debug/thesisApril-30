from flask import Flask, request, jsonify, render_template
import joblib
import os
from flask_cors import CORS
from datetime import datetime

from feature_engine import build_basic_features

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
# =========================================================
FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

print("✓ Feature lock loaded")


# =========================================================
# ENGINEERING THRESHOLDS
# =========================================================

# PHYSICAL SAFETY LIMITS
TEMP_NORMAL_MAX = 45
TEMP_WARNING_MIN = 55
TEMP_CRITICAL = 70

# ML PROBABILITY THRESHOLDS
ML_EARLY = 0.45
ML_WARNING = 0.65
ML_CRITICAL = 0.85


# =========================================================
# DECISION ENGINE
# =========================================================
def decide_state(temp, current, hot_prob, ovl_prob):

    # =====================================================
    # HARD SAFETY OVERRIDE
    # =====================================================
    if temp >= TEMP_CRITICAL:
        return "Critical", "TEMP LIMIT EXCEEDED"

    # =====================================================
    # VERY LOW TEMP REGION
    # Prevent false positives in cool temperatures
    # =====================================================
    if temp < TEMP_NORMAL_MAX:

        # Only allow EARLY warning in low temps
        if hot_prob >= ML_WARNING and current > 5:
            return "EarlyWarning", "UNUSUAL THERMAL TREND"

        if ovl_prob >= ML_WARNING and current > 10:
            return "EarlyWarning", "CURRENT TREND DETECTED"

        return "Normal", "SYSTEM STABLE"

    # =====================================================
    # MID TEMP REGION (45C - 55C)
    # ML starts becoming important
    # =====================================================
    if TEMP_NORMAL_MAX <= temp < TEMP_WARNING_MIN:

        if hot_prob >= ML_CRITICAL:
            return "Critical", "HOTSPOT RISK"

        if ovl_prob >= ML_CRITICAL:
            return "Critical", "OVERLOAD RISK"

        if hot_prob >= ML_WARNING:
            return "Warning", "THERMAL WARNING"

        if ovl_prob >= ML_WARNING:
            return "Warning", "OVERLOAD WARNING"

        if hot_prob >= ML_EARLY:
            return "EarlyWarning", "THERMAL TREND"

        if ovl_prob >= ML_EARLY:
            return "EarlyWarning", "CURRENT TREND"

        return "Normal", "SYSTEM STABLE"

    # =====================================================
    # HIGH TEMP REGION (55C+)
    # Aggressive protection zone
    # =====================================================
    if hot_prob >= ML_CRITICAL or ovl_prob >= ML_CRITICAL:
        return "Critical", "HIGH RISK DETECTED"

    if hot_prob >= ML_WARNING or ovl_prob >= ML_WARNING:
        return "Warning", "ABNORMAL CONDITION"

    return "EarlyWarning", "ELEVATED TEMPERATURE"


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
        # =================================================
        X = build_basic_features(temp, current)

        # force same training order
        X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

        # =================================================
        # ML PREDICTION
        # =================================================
        hot_prob = float(
            hotspot_model.predict_proba(X)[0][1]
        )

        ovl_prob = float(
            overload_model.predict_proba(X)[0][1]
        )

        # =================================================
        # DECISION ENGINE
        # =================================================
        state, status = decide_state(
            temp,
            current,
            hot_prob,
            ovl_prob
        )

        composite_risk = (hot_prob + ovl_prob) / 2

        # =================================================
        # STORE RESULT
        # =================================================
        latest_data_store = {

            "temperature": round(temp, 2),
            "current": round(current, 2),

            "breakerState": state,
            "status": status,

            "ml": {
                "hotspot_prob": round(hot_prob, 4),
                "overload_prob": round(ovl_prob, 4),
                "composite_risk": round(composite_risk, 4)
            },

            "time": datetime.now().strftime("%H:%M:%S")
        }

        # =================================================
        # DEBUG LOG
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

    print("===================================")
    print("⚡ SMART PANEL MONITORING SYSTEM")
    print("🔥 Predictive ML Protection Enabled")
    print("===================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
