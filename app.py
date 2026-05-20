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
    current_buffer_short
)

# =========================================================
# INIT
# =========================================================
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

latest_data_store = {}

print("🔥 INITIALIZING SYSTEM...")

# =========================================================
# EMAIL CONFIG
# =========================================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'breaker.monitor.system@gmail.com'
app.config['MAIL_PASSWORD'] = 'kzng lhzr elww gyyu'
app.config['MAIL_DEFAULT_SENDER'] = 'breaker.monitor.system@gmail.com'

try:
    mail = Mail(app)
    print("✓ Email service initialized")
except:
    mail = None

# =========================================================
# MODELS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

# =========================================================
# ALERT CONTROL
# =========================================================
last_alert_time = {}
ALERT_COOLDOWN = 300

def should_send(alert):
    now = time.time()
    if alert in last_alert_time:
        if now - last_alert_time[alert] < ALERT_COOLDOWN:
            return False
    last_alert_time[alert] = now
    return True

# =========================================================
# THRESHOLDS
# =========================================================
WARMUP = 10
WARN = 0.60
CRIT = 0.85

# =========================================================
# API
# =========================================================
@app.route("/api/update", methods=["POST"])
def update():

    data = request.json
    temp = float(data["temperature"])
    current = float(data["current"])

    X = build_basic_features(temp, current)
    X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

    hot = hotspot_model.predict_proba(X)[0][1]
    ovl = overload_model.predict_proba(X)[0][1]

    buffer_len = len(temp_buffer_short)

    # =====================================================
    # STATE LOGIC
    # =====================================================
    if buffer_len < WARMUP:
        state = "WarmingUp"

    elif hot >= CRIT or ovl >= CRIT:
        state = "Critical"

    elif hot >= WARN or ovl >= WARN:
        state = "Warning"

    else:
        state = "Normal"

    print(f"[{state}] T={temp:.2f} I={current:.2f} HP={hot:.3f} OP={ovl:.3f}")

    return jsonify({
        "state": state,
        "hotspot_prob": float(hot),
        "overload_prob": float(ovl)
    })

# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "buffer_size": len(temp_buffer_short)
    })

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    print("⚡ SYSTEM STARTED")
    app.run(host="0.0.0.0", port=5000, debug=False)
