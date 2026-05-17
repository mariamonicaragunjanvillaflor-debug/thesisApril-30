from flask import Flask, request, jsonify, render_template
import joblib
import os
from flask_cors import CORS
from datetime import datetime
import numpy as np

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
TEMP_NORMAL_MAX = 45
TEMP_EARLY_WARNING = 55
TEMP_WARNING = 60
TEMP_CRITICAL = 70

CURRENT_WARNING = 20
CURRENT_CRITICAL = 28

# =========================================================
# ML THRESHOLDS
# =========================================================
ML_EARLY = 0.45
ML_WARNING = 0.65
ML_CRITICAL = 0.85


# =========================================================
# SMOOTHING MEMORY
# Prevents alarm flickering
# =========================================================
risk_history = []

RISK_WINDOW = 5


# =========================================================
# RISK SMOOTHING
# =========================================================
def smooth_risk(value):

    global risk_history

    risk_history.append(value)

    if len(risk_history) > RISK_WINDOW:
        risk_history.pop(0)

    return float(np.mean(risk_history))


# =========================================================
# DECISION ENGINE
# =========================================================
def decide_state(
    temp,
    current,
    hot_prob,
    ovl_prob
):

    # =====================================================
    # SMOOTHED COMPOSITE RISK
    # =====================================================
    composite_risk = max(hot_prob, ovl_prob)

    composite_risk = smooth_risk(composite_risk)

    # =====================================================
    # HOTSPOT PRIORITY
    # purely thermal abnormality
    # =====================================================
    hotspot_detected = (
        hot_prob >= ML_WARNING
        and temp >= TEMP_EARLY_WARNING
        and current < CURRENT_WARNING
    )

    # =====================================================
    # OVERLOAD PRIORITY
    # current-driven abnormality
    # =====================================================
    overload_detected = (
        ovl_prob >= ML_WARNING
        and current >= CURRENT_WARNING
    )

    # =====================================================
    # HARD SAFETY OVERRIDE
    # =====================================================
    if temp >= TEMP_CRITICAL:
        return (
            "Critical",
            "CRITICAL TEMPERATURE",
            composite_risk
        )

    if current >= CURRENT_CRITICAL:
        return (
            "Critical",
            "CRITICAL CURRENT",
            composite_risk
        )

    # =====================================================
    # CRITICAL ML PREDICTION
    # =====================================================
    if hot_prob >= ML_CRITICAL:
        return (
            "Critical",
            "PREDICTED HOTSPOT FAILURE",
            composite_risk
        )

    if ovl_prob >= ML_CRITICAL:
        return (
            "Critical",
            "PREDICTED OVERLOAD FAILURE",
            composite_risk
        )

    # =====================================================
    # HOTSPOT WARNING
    # =====================================================
    if hotspot_detected:

        if temp >= TEMP_WARNING:
            return (
                "Warning",
                "THERMAL STRESS DETECTED",
                composite_risk
            )

        return (
            "EarlyWarning",
            "EARLY HOTSPOT TREND",
            composite_risk
        )

    # =====================================================
    # OVERLOAD WARNING
    # =====================================================
    if overload_detected:

        if current >= CURRENT_WARNING:
            return (
                "Warning",
                "LOAD STRESS DETECTED",
                composite_risk
            )

        return (
            "EarlyWarning",
            "EARLY OVERLOAD TREND",
            composite_risk
        )

    # =====================================================
    # TEMPERATURE ONLY
    # =====================================================
    if temp >= TEMP_WARNING:
        return (
            "Warning",
            "HIGH TEMPERATURE",
            composite_risk
        )

    if temp >= TEMP_EARLY_WARNING:
        return (
            "EarlyWarning",
            "TEMPERATURE RISING",
            composite_risk
        )

    # =====================================================
    # CURRENT ONLY
    # =====================================================
    if current >= CURRENT_WARNING:
        return (
            "Warning",
            "HIGH CURRENT",
            composite_risk
        )

    # =====================================================
    # EARLY ML TREND
    # =====================================================
    if (
        hot_prob >= ML_EARLY
        or ovl_prob >= ML_EARLY
    ):
        return (
            "EarlyWarning",
            "PREDICTIVE TREND DETECTED",
            composite_risk
        )

    # =====================================================
    # NORMAL
    # =====================================================
    return (
        "Normal",
        "SYSTEM STABLE",
        composite_risk
    )


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

        X = X.reindex(
            columns=FEATURE_COLUMNS,
            fill_value=0
        )

        # =================================================
        # ML PREDICTIONS
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
        state, status, composite_risk = decide_state(
            temp,
            current,
            hot_prob,
            ovl_prob
        )

        # =================================================
        # STORE DATA
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
        # DEBUG TERMINAL
        # =================================================
        print(
            f"[{state}] "
            f"T={temp:.2f}C "
            f"I={current:.2f}A "
            f"HP={hot_prob:.3f} "
            f"OP={ovl_prob:.3f} "
            f"RISK={composite_risk:.3f}"
        )

        # =================================================
        # API RESPONSE
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
    print("🔥 PREDICTIVE ML PROTECTION ACTIVE")
    print("🌡 Thermal + Electrical Forecasting")
    print("===================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
