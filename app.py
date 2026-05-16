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

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

print("✓ Models loaded successfully")


# =========================================================
# FEATURE LOCK
# =========================================================
FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()


# =========================================================
# ENGINEERING THRESHOLDS
# =========================================================
TEMP_CRITICAL = 70

ML_WARNING = 0.55
ML_CRITICAL = 0.75


# =========================================================
# DECISION ENGINE (CENTRAL LOGIC)
# =========================================================
def decide_state(temp, hot_prob, ovl_prob):

    # HARD SAFETY OVERRIDE
    if temp >= TEMP_CRITICAL:
        return "Critical", "TEMPERATURE LIMIT EXCEEDED"

    # ML CRITICAL
    if hot_prob >= ML_CRITICAL or ovl_prob >= ML_CRITICAL:
        return "Critical", "HIGH RISK DETECTED"

    # WARNING ZONE
    if hot_prob >= ML_WARNING or ovl_prob >= ML_WARNING:
        return "Warning", "EARLY RISK DETECTED"

    # EARLY SIGNAL (important for predictive behavior)
    if hot_prob >= 0.30 or ovl_prob >= 0.30:
        return "EarlyWarning", "TREND DETECTED"

    return "Normal", "SYSTEM STABLE"


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
        # 🔥 ALWAYS RUN FEATURE ENGINE
        # =================================================
        X = build_basic_features(temp, current)
        X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

        # =================================================
        # 🔥 ALWAYS RUN ML (IMPORTANT FIX)
        # =================================================
        hot_prob = float(hotspot_model.predict_proba(X)[0][1])
        ovl_prob = float(overload_model.predict_proba(X)[0][1])

        # =================================================
        # DECISION LAYER
        # =================================================
        state, status = decide_state(temp, hot_prob, ovl_prob)

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
