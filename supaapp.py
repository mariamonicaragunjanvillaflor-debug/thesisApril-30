from hardware import read_temperature, read_current
from supabase import create_client
from datetime import datetime
import time
import joblib

# =========================================================
# SUPABASE CONFIG
# =========================================================
SUPABASE_URL = "https://qkniqwgcwvxkgjciccad.supabase.co"
SUPABASE_KEY = "sb_publishable_pzHW1LlymSCVL876qchBKw_pPY0xN-2"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================
# LOAD ML MODELS
# (Make sure these .pkl files exist in your folder)
# =========================================================
hotspot_model = joblib.load("hotspot_model.pkl")
overload_model = joblib.load("overload_model.pkl")


# =========================================================
# MAIN LOOP
# =========================================================
while True:

    try:
        # 1. READ REAL SENSORS
        temp = read_temperature()
        current = read_current()   # FIXED (removed read_current_rms)

        if temp is None or current is None:
            print("Sensor read failed, skipping...")
            continue

        # 2. ML INPUT
        X = [[temp, current]]

        # 3. ML PREDICTIONS
        hot_prob = hotspot_model.predict_proba(X)[0][1]
        ovl_prob = overload_model.predict_proba(X)[0][1]

        # 4. RISK COMPUTATION
        composite = (hot_prob + ovl_prob) / 2

        # 5. BREAKER STATE LOGIC
        if composite > 0.9:
            state = "TRIPPED"
        elif composite > 0.7:
            state = "WARNING"
        else:
            state = "NORMAL"

        # 6. DATA PACKAGE
        data = {
            "created_at": datetime.now().isoformat(),
            "temperature_c": float(temp),
            "current_a": float(current),
            "breaker_state": state,
            "hotspot_probability": float(hot_prob),
            "overload_probability": float(ovl_prob),
            "composite_risk": float(composite)
        }

        # 7. SEND TO SUPABASE
        response = supabase.table("breaker_readings").insert(data).execute()

        print("Uploaded:", response.data)

    except Exception as e:
        print("Error:", e)

    # 8. DELAY (avoid flooding sensors + Supabase)
    time.sleep(5)
