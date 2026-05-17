from hardware import read_temperature, read_current
from supabase import create_client
from datetime import datetime
import time

# =========================================================
# SUPABASE (FILLED IN)
# =========================================================
SUPABASE_URL = "https://qkniqwgcwvxkgjciccad.supabase.co"
SUPABASE_KEY = "sb_publishable_pzHW1LlymSCVL876qchBKw_pPY0xN-2"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================================================
# MAIN LOOP
# =========================================================
while True:

    # 1. READ REAL SENSORS
    temp = read_temperature()
    current = read_current_rms()

    if temp is None or current is None:
        continue

    # 2. ML INPUT
    X = [[temp, current]]

    # 3. ML PREDICTIONS
    hot_prob = hotspot_model.predict_proba(X)[0][1]
    ovl_prob = overload_model.predict_proba(X)[0][1]

    # 4. RISK COMPUTATION
    composite = (hot_prob + ovl_prob) / 2

    # 5. BREAKER STATE
    if composite > 0.9:
        state = "TRIPPED"
    elif composite > 0.7:
        state = "WARNING"
    else:
        state = "NORMAL"

    # 6. DATA PACKAGE
    data = {
        "created_at": datetime.now().isoformat(),
        "temperature_c": temp,
        "current_a": current,
        "breaker_state": state,
        "hotspot_probability": hot_prob,
        "overload_probability": ovl_prob,
        "composite_risk": composite
    }

    # 7. SEND TO SUPABASE
    response = (
        supabase
        .table("breaker_readings")
        .insert(data)
        .execute()
    )

    print("Uploaded:", response.data)

    time.sleep(5)
