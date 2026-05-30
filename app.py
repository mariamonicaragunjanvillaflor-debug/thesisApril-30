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
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

latest_data_store = {}

print("🔥 INITIALIZING SYSTEM...")

# =========================================================
# EMAIL CONFIG (SAFE)
# =========================================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'breaker.monitor.system@gmail.com'
app.config['MAIL_PASSWORD'] = 'kzng lhzr elww gyyu'
app.config['MAIL_DEFAULT_SENDER'] = 'breaker.monitor.system@gmail.com'

mail = None
email_enabled = False

try:
    mail = Mail(app)
    email_enabled = True
    print("✓ Email service initialized")
except Exception as e:
    print(f"✗ Email initialization error: {e}")
    print("⚠ Email alerts disabled — system continues normally")

# =========================================================
# LOAD MODELS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

hotspot_model = joblib.load(os.path.join(BASE_DIR, "ml/hotspot_model.pkl"))
overload_model = joblib.load(os.path.join(BASE_DIR, "ml/overload_model.pkl"))

FEATURE_COLUMNS = hotspot_model.feature_names_in_.tolist()

# =========================================================
# THRESHOLDS
# =========================================================
WARMUP_SAMPLES = 10
WARNING_THRESHOLD = 0.70
CRITICAL_THRESHOLD = 0.85

# =========================================================
# ALERT TRACKING
# =========================================================
last_alert_time = {}
ALERT_COOLDOWN_SECONDS = 300


def should_send_alert(alert_type):
    now = time.time()
    if alert_type in last_alert_time:
        if now - last_alert_time[alert_type] < ALERT_COOLDOWN_SECONDS:
            return False
    last_alert_time[alert_type] = now
    return True


# =========================================================
# FALLBACK LOGGER
# =========================================================
def log_fallback_alert(subject, body):
    try:
        with open("alert_fallback_log.txt", "a") as f:
            f.write("\n============================\n")
            f.write(f"TIME: {datetime.now()}\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(body + "\n")
        print("✓ Alert saved locally (fallback log)")
    except Exception as e:
        print("⚠ Fallback logging failed:", e)


# =========================================================
# EMAIL ALERT SYSTEM
# =========================================================
def send_breaker_alert(reading, risk, alert_type, message_action):

    if not email_enabled or mail is None:
        print("⚠ Email skipped (disabled)")
        return False, "Email disabled"

    recipients = [
        'gwenlykapergis@gmail.com',
        'mariamonicaragunjanvillaflor@gmail.com',
        'mercymicadespabiladeras@gmail.com'
    ]

    subject = "Breaker System Alert"

    if alert_type == "Critical":
        subject = "🔴 CRITICAL POWER SYSTEM ALERT"
    elif alert_type == "Warning":
        subject = "⚠️ WARNING: Electrical Risk Detected"

    body = f"""
BREAKER MONITORING SYSTEM ALERT

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Temperature: {reading.temperature_c:.1f}°C
Current: {reading.current_a:.2f}A

Hotspot Risk: {risk['hotspot_prob']*100:.1f}%
Overload Risk: {risk['overload_prob']*100:.1f}%

--- PROACTIVE ACTION RECOMMENDED ---
{message_action}
"""

    try:
        msg = Message(subject=subject,
                      sender=app.config['MAIL_USERNAME'],
                      recipients=recipients)

        msg.body = body
        mail.send(msg)

        print("✓ Email sent:", subject)
        return True, "Sent"

    except Exception as e:
        print("✗ Email failed:", e)
        log_fallback_alert(subject, body)
        return False, str(e)


# =========================================================
# STATE LOGIC
# =========================================================
def determine_state(hot_prob, ovl_prob):

    if len(temp_buffer_short) < 10 or len(temp_buffer_long) < 10:
        return "WarmingUp", "System initializing..."

    if hot_prob >= CRITICAL_THRESHOLD:
        return "Critical", "Severe overheating detected"

    if ovl_prob >= CRITICAL_THRESHOLD:
        return "Critical", "Severe overload detected"

    if hot_prob >= WARNING_THRESHOLD:
        return "Warning", "Elevated temperature detected"

    if ovl_prob >= WARNING_THRESHOLD:
        return "Warning", "High load detected"

    return "Normal", "System stable"


# =========================================================
# ACTION ENGINE
# =========================================================
def get_action(state, hotspot, overload):

    if state == "Warning":

        if hotspot and overload:
            return "Reduce load immediately → hotspot + overload detected. Check wiring."

        if hotspot:
            return "Reduce load and inspect connections."

        if overload:
            return "Turn off heavy appliances."

        return "Monitor system."

    if state == "Critical":

        if hotspot and overload:
            return "SHUT DOWN SYSTEM immediately."

        if hotspot:
            return "SHUT DOWN → overheating detected."

        if overload:
            return "DISCONNECT LOAD immediately."

        return "Emergency inspection required."

    return "System normal."


# =========================================================
# API ENDPOINT
# =========================================================
@app.route("/api/update", methods=["POST"])
def update_data():

    data = request.json
    temp = float(data["temperature"])
    current = float(data["current"])

    X = build_basic_features(temp, current)
    X = X.reindex(columns=FEATURE_COLUMNS, fill_value=0)

    hot_prob = float(hotspot_model.predict_proba(X)[0][1])
    ovl_prob = float(overload_model.predict_proba(X)[0][1])

    state, status = determine_state(hot_prob, ovl_prob)

    # =====================================================
    # FORECAST (FIXED INDENTATION)
    # =====================================================
    feat = X

    future_temp = temp
    future_current = current

    try:
        future_temp = temp + feat["temp_slope_short"].values[0] * 10
        future_current = current + feat["current_slope_short"].values[0] * 10
    except:
        pass

    action = get_action(
        state,
        hot_prob >= WARNING_THRESHOLD,
        ovl_prob >= WARNING_THRESHOLD
    )

    # ALERTS
    if state in ["Warning", "Critical"]:
        if should_send_alert(state):

            send_breaker_alert(
                reading=type("obj", (), {
                    "temperature_c": temp,
                    "current_a": current
                }),
                risk={
                    "hotspot_prob": hot_prob,
                    "overload_prob": ovl_prob
                },
                alert_type=state,
                message_action=action
            )

    # ✅ FIXED INDENTATION HERE (THIS WAS YOUR BUG)
    latest_data_store.update({
        "temperature": float(temp),
        "current": float(current),
        "state": state,
        "status": status,
        "action": action,
        "ml": {
            "hotspot_prob": float(hot_prob),
            "overload_prob": float(ovl_prob),
            "composite_risk": float((hot_prob + ovl_prob) / 2)
        },
        "forecast": {
            "future_temp": float(round(future_temp, 2)),
            "future_current": float(round(future_current, 2))
        },
        "buffer_size": int(len(temp_buffer_short)),
        "time": datetime.now().strftime("%H:%M:%S")
    })

    print(f"[{state}] T={temp:.2f} I={current:.2f} HP={hot_prob:.2f} OP={ovl_prob:.2f}")

    return jsonify(latest_data_store)


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
    return jsonify({"status": "online"})


# =========================================================
# RUN SERVER
# =========================================================
if __name__ == "__main__":
    print("⚡ SMART PANEL SYSTEM ONLINE")
    app.run(host="0.0.0.0", port=5000, debug=False)
