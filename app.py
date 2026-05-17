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

print("✓ Feature lock loaded")


# =========================================================
# THRESHOLDS
# =========================================================
TEMP_CRITICAL = 70

ML_EARLY = 0.40
ML_WARNING = 0.60
ML_CRITICAL = 0.80


# =========================================================
# DECISION ENGINE (FULL PREDICTIVE)
# =========================================================
def decide_state(temp, current, hot_prob, ovl_prob):

    # -----------------------------------------------------
    # CRITICAL SAFETY OVERRIDE (ONLY HARD LIMIT)
    # -----------------------------------------------------
    if temp >= TEMP_CRITICAL:
        return "Critical", "TEMP LIMIT EXCEEDED"

    # -----------------------------------------------------
    # CRITICAL ML CONDITION
    # -----------------------------------------------------
    if hot_prob >= ML_CRITICAL or ovl_prob >= ML_CRITICAL:
        return "Critical", "HIGH RISK DETECTED"

    # -----------------------------------------------------
    # WARNING LEVEL
    # -----------------------------------------------------
    if hot_prob >= ML_WARNING or ovl_prob >= ML_WARNING:
        return "Warning", "ABNORMAL CONDITION"

    # -----------------------------------------------------
    # EARLY WARNING (IMPORTANT FOR PREDICTION)
    # -----------------------------------------------------
    if hot_prob >= ML_EARLY or ovl_prob >= ML_EARLY:
        return "EarlyWarning", "EARLY RISK DETECTED"

    # -----------------------------------------------------
    # NORMAL (ONLY IF MODEL SAYS SAFE)
    # -----------------------------------------------------
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
        # FEATURE ENGINE (STATEFUL)
        # =================================================
        X = build_basic_features(temp, current)
        X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

        # =================================================
        # ALWAYS RUN ML (NO EXCEPTIONS)
        # =================================================
        hot_prob = float(hotspot_model.predict_proba(X)[0][1])
        ovl_prob = float(overload_model.predict_proba(X)[0][1])

        # =================================================
        # DECISION
        # =================================================
        state, status = decide_state(temp, current, hot_prob, ovl_prob)

        composite_risk = (hot_prob + ovl_prob) / 2

        # =================================================
        # STORE
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

        return jsonify({
            "success": True,
            "state": state,
            "status": status,
            "ml": latest_data_store["ml"]
        })

    except Exception as e:
        print("API ERROR:", e)
        return jsonify({"success": False, "error": str(e)})


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
    print("⚡ SMART PANEL MONITORING SYSTEM")
    print("🔥 Predictive ML Enabled")
    app.run(host="0.0.0.0", port=5000, debug=False)
