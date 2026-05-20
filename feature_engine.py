

def _update_buffers(temp, current):
    temp_buffer.append(temp)
    current_buffer.append(current)
    temp_buffer.append(float(temp))
    current_buffer.append(float(current))


# =========================
# FEATURE ENGINE (UNIFIED)
# FEATURE ENGINE (FIXED + CONSISTENT)
# =========================
def build_basic_features(temp, current):
"""
    SINGLE SOURCE OF TRUTH FEATURE ENGINE
    - used in training
    - used in Flask API
    - used in Raspberry Pi inference
    FIXED VERSION:
    - consistent training/inference behavior
    - stable early predictions
    - reduced probability inflation
   """

_update_buffers(temp, current)

    t = np.array(temp_buffer, dtype=float)
    c = np.array(current_buffer, dtype=float)

# =========================
    # WARM-UP (not enough history)
    # WARM-UP MODE (IMPORTANT FIX)
# =========================
    if len(temp_buffer) < 10:
        t = temp
        c = current
    if len(t) < 5:
        base_temp = float(temp)
        base_current = float(current)

features = {
            "ambient_temp_c": t,
            "temperature_c": t,
            "ambient_temp_c": base_temp,
            "temperature_c": base_temp,
"temperature_rise_c": 0.0,
            "current_a": c,
            "current_a": base_current,

            "current_squared": c ** 2,
            "power_loss": (c ** 2) * 0.01,
            "current_squared": base_current ** 2,
            "power_loss": (base_current ** 2) * 0.01,
"thermal_stress": 0.0,

"thermal_slope_c_per_5s": 0.0,
"current_slope_a_per_5s": 0.0,

"temp_trend": 0.0,
"current_trend": 0.0,
            "temp_avg_3": t,
            "current_avg_3": c,

            "temp_avg_3": base_temp,
            "current_avg_3": base_current,

"temp_acceleration": 0.0,
"temp_trend_long": 0.0,
            "thermal_memory": t,

            # FIX: stable baseline instead of inflated value
            "thermal_memory": base_temp,
}

for i in range(1, 10):
            features[f"temp_lag_{i}"] = t
            features[f"current_lag_{i}"] = c
            features[f"temp_lag_{i}"] = base_temp
            features[f"current_lag_{i}"] = base_current

return pd.DataFrame([features])

# =========================
    # FULL BUFFER MODE
    # NORMAL MODE (STABLE)
# =========================
    t = np.array(temp_buffer)
    c = np.array(current_buffer)
    ambient_temp = float(temp)
    current_a = float(current)

    ambient_temp = temp
    current_a = current
    # Safe arrays (avoid crash if partial buffer)
    t_safe = np.pad(t, (10 - len(t), 0), mode="edge")
    c_safe = np.pad(c, (10 - len(c), 0), mode="edge")

current_squared = current_a ** 2
power_loss = current_squared * 0.01
    thermal_stress = np.mean(t) * current_a  # consistent physical memory

    # FIX: consistent thermal stress definition
    thermal_stress = np.mean(t_safe) * current_a

# =========================
    # SMOOTH SLOPES (5-sec approx)
    # SMOOTH SLOPES
# =========================
    thermal_slope = (t[-1] - t[0]) / len(t) * 5
    current_slope = (c[-1] - c[0]) / len(c) * 5
    thermal_slope = (t_safe[-1] - t_safe[0]) / 10 * 5
    current_slope = (c_safe[-1] - c_safe[0]) / 10 * 5

# =========================
# LAGS
# =========================
    temp_lags = list(t[::-1])[:9]
    curr_lags = list(c[::-1])[:9]

    temp_lags += [t[-1]] * (9 - len(temp_lags))
    curr_lags += [c[-1]] * (9 - len(curr_lags))
    temp_lags = list(t_safe[::-1])[:9]
    curr_lags = list(c_safe[::-1])[:9]

# =========================
    # DERIVED FEATURES
    # DERIVED FEATURES (FIXED SAFETY)
# =========================
    temp_trend = t[-1] - t[-2]
    current_trend = c[-1] - c[-2]
    temp_trend = t_safe[-1] - t_safe[-2]
    current_trend = c_safe[-1] - c_safe[-2]

    temp_avg_3 = np.mean(t[-3:])
    current_avg_3 = np.mean(c[-3:])
    temp_avg_3 = np.mean(t_safe[-3:])
    current_avg_3 = np.mean(c_safe[-3:])

    temp_acceleration = t[-1] - 2*t[-2] + t[-3]
    temp_acceleration = t_safe[-1] - 2 * t_safe[-2] + t_safe[-3]

    temp_trend_long = t[-1] - t[-7] if len(t) >= 7 else 0.0
    temp_trend_long = t_safe[-1] - t_safe[-7]

    thermal_memory = np.mean(t)
    thermal_memory = np.mean(t_safe)

# =========================
    # FINAL FEATURE SET
    # FINAL FEATURES
# =========================
features = {
"ambient_temp_c": ambient_temp,
        "temperature_c": temp,
        "temperature_rise_c": np.mean(t) - 25,
        "temperature_c": ambient_temp,
        "temperature_rise_c": np.mean(t_safe) - 30,  # FIXED baseline (important)

"current_a": current_a,

"current_squared": current_squared,
@@ -132,7 +140,6 @@ def build_basic_features(temp, current):
"thermal_memory": thermal_memory,
}

    # add lags
for i in range(9):
features[f"temp_lag_{i+1}"] = temp_lags[i]
features[f"current_lag_{i+1}"] = curr_lags[i]
