from flask import Flask, request, jsonify, render_template
import joblib
import os
import time
from flask_cors import CORS
from flask_mail import Mail, Message
from datetime import datetime

from feature_engine import (
    build_basic_features,
    temp_buffer_short,
    temp_buffer_long,
    current_buffer_short,
    current_buffer_long
)

# =========================================================
# INIT
# =========================================================
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

latest_data_store = {}

print("🔥 INITIALIZING SYSTEM...")

# =========================================================
# EMAIL CONFIG
# =========================================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'breaker.monitor.system@gmail.com'
app.config['MAIL_PASSWORD'] = 'kzng lhzr elww gyyu'
app.config['MAIL_DEFAULT_SENDER'] = 'breaker.monitor.system@gmail.com'

mail = Mail(app)

# =========================================================
# LOAD MODELS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

print("✓ Models loaded")

# =========================================================
# FEATURE COLUMNS (CRITICAL)
# =========================================================
FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

# =========================================================
# ALERT CONTROL
# =========================================================
last_alert_time = {}
ALERT_COOLDOWN = 300

def should_send_alert(key):
    now = time.time()
    if key in last_alert_time:
        if now - last_alert_time[key] < ALERT_COOLDOWN:
            return False
    last_alert_time[key] = now
    return True

# =========================================================
# ALERT FUNCTION
# =========================================================
def send_alert(temp, current, hp, op, alert_type):

    recipients = [
        'gwenlykapergis@gmail.com',
        'mariamonicaragunjanvillaflor@gmail.com',
        'mercymicadespabiladeras@gmail.com'
    ]

    subject = "Breaker Alert"

    body = f"""
Temperature: {temp}
Current: {current}
Hotspot: {hp:.3f}
Overload: {op:.3f}
Time: {datetime.now()}
"""

    msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=recipients)
    msg.body = body

    mail.send(msg)

# =========================================================
# API
# =========================================================
@app.route("/api/update", methods=["POST"])
def update():

    try:
        data = request.json
        temp = float(data["temperature"])
        current = float(data["current"])

        # =================================================
        # FEATURE ENGINE (ONLY SOURCE OF FEATURES)
        # =================================================
        X = build_basic_features(temp, current)

        # ALIGN FEATURES (CRITICAL)
        X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

        # =================================================
        # PREDICTIONS
        # =================================================
        hot_prob = float(hotspot_model.predict_proba(X)[0][1])
        ovl_prob = float(overload_model.predict_proba(X)[0][1])

        composite = (hot_prob + ovl_prob) / 2

        # =================================================
        # STATE LOGIC (SIMPLE + STABLE)
        # =================================================
        if hot_prob > 0.85 or ovl_prob > 0.85:
            state = "Critical"
        elif hot_prob > 0.60 or ovl_prob > 0.60:
            state = "Warning"
        else:
            state = "Normal"

        # =================================================
        # ALERTS
        # =================================================
        if state == "Critical" and should_send_alert("critical"):
            send_alert(temp, current, hot_prob, ovl_prob, "critical")

        elif state == "Warning" and should_send_alert("warning"):
            send_alert(temp, current, hot_prob, ovl_prob, "warning")

        # =================================================
        # STORE
        # =================================================
        global latest_data_store
        latest_data_store = {
            "temperature": temp,
            "current": current,
            "state": state,
            "ml": {
                "hotspot": hot_prob,
                "overload": ovl_prob,
                "composite": composite
            },
            "time": datetime.now().strftime("%H:%M:%S")
        }

        print(f"[{state}] T={temp} I={current} HP={hot_prob:.3f} OP={ovl_prob:.3f}")

        return jsonify({
            "success": True,
            "state": state,
            "ml": latest_data_store["ml"]
        })

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"success": False, "error": str(e)})

# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/latest")
def latest():
    return jsonify(latest_data_store)

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    print("⚡ SYSTEM ONLINE")
    app.run(host="0.0.0.0", port=5000, debug=False)
