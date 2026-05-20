import numpy as np
import pandas as pd
from collections import deque

# =========================================================
# STREAMING BUFFERS
# =========================================================
temp_buffer_short = deque(maxlen=10)
temp_buffer_long = deque(maxlen=10)

current_buffer_short = deque(maxlen=10)
current_buffer_long = deque(maxlen=10)

# =========================================================
# RESET BUFFERS
# =========================================================
def reset_buffers():
    temp_buffer_short.clear()
    temp_buffer_long.clear()
    current_buffer_short.clear()
    current_buffer_long.clear()

# =========================================================
# UPDATE BUFFERS
# =========================================================
def _update_buffers(temp, current):
    temp_buffer_short.append(float(temp))
    temp_buffer_long.append(float(temp))

    current_buffer_short.append(float(current))
    current_buffer_long.append(float(current))

# =========================================================
# FEATURE ENGINE
# =========================================================
def build_basic_features(temp, current):

    temp = float(temp)
    current = float(current)

    _update_buffers(temp, current)

    # =====================================================
    # WARMUP MODE
    # =====================================================
    if len(temp_buffer_short) < 10 or len(temp_buffer_long) < 10:

        features = {
            "ambient_temp_c": temp,
            "temperature_c": temp,
            "current_a": current,
            "current_squared": current ** 2,
            "power_loss": 0.01 * (current ** 2),
            "thermal_stress": temp * current,
            "temp_slope_short": 0.0,
            "temp_slope_long": 0.0,
            "current_slope_short": 0.0,
            "current_slope_long": 0.0,
            "temp_acceleration": 0.0,
            "trend_strength": 0.0,
            "temp_ema": temp,
            "current_ema": current,
            "thermal_memory": temp,
            "thermal_energy": temp * current
        }

        # safe lag init (no distortion, no random noise)
        for i in range(10):
            features[f"temp_lag_{i+1}"] = temp
            features[f"current_lag_{i+1}"] = current

        return pd.DataFrame([features])

    # =====================================================
    # CONVERT BUFFERS
    # =====================================================
    t_s = np.array(temp_buffer_short, dtype=np.float32)
    c_s = np.array(current_buffer_short, dtype=np.float32)

    t_l = np.array(temp_buffer_long, dtype=np.float32)
    c_l = np.array(current_buffer_long, dtype=np.float32)

    # =====================================================
    # SAFE SLOPES
    # =====================================================
    temp_slope_short = (t_s[-1] - t_s[0]) / (len(t_s) - 1)
    temp_slope_long = (t_l[-1] - t_l[0]) / (len(t_l) - 1)

    current_slope_short = (c_s[-1] - c_s[0]) / (len(c_s) - 1)
    current_slope_long = (c_l[-1] - c_l[0]) / (len(c_l) - 1)

    # =====================================================
    # ACCELERATION
    # =====================================================
    temp_acceleration = t_s[-1] - 2*t_s[-2] + t_s[-3]

    # =====================================================
    # TREND STRENGTH
    # =====================================================
    trend_strength = np.mean(np.diff(t_s) > 0)

    # =====================================================
    # STABLE EMA (FIXED)
    # =====================================================
    alpha = 0.3
    temp_ema = t_s[0]
    current_ema = c_s[0]

    for v in t_s[1:]:
        temp_ema = alpha * v + (1 - alpha) * temp_ema

    for v in c_s[1:]:
        current_ema = alpha * v + (1 - alpha) * current_ema

    # =====================================================
    # THERMAL MEMORY
    # =====================================================
    thermal_memory = np.mean(t_l)

    # =====================================================
    # LAGS
    # =====================================================
    temp_lags = list(t_s[::-1])[:10]
    curr_lags = list(c_s[::-1])[:10]

    # =====================================================
    # FINAL FEATURE SET
    # =====================================================
    features = {
        "ambient_temp_c": temp,
        "temperature_c": temp,
        "current_a": current,
        "current_squared": current ** 2,
        "power_loss": 0.01 * (current ** 2),
        "thermal_stress": temp * current,

        "temp_slope_short": temp_slope_short,
        "temp_slope_long": temp_slope_long,
        "current_slope_short": current_slope_short,
        "current_slope_long": current_slope_long,

        "temp_acceleration": temp_acceleration,
        "trend_strength": trend_strength,

        "temp_ema": temp_ema,
        "current_ema": current_ema,

        "thermal_memory": thermal_memory,

        "thermal_energy": thermal_memory * current
    }

    for i in range(10):
        features[f"temp_lag_{i+1}"] = temp_lags[i]
        features[f"current_lag_{i+1}"] = curr_lags[i]

    return pd.DataFrame([features])
