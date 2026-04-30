import numpy as np
import pandas as pd
from collections import deque

# =========================
# STREAMING BUFFERS
# =========================
temp_buffer = deque(maxlen=10)
current_buffer = deque(maxlen=10)

def update_buffers(temp, current):
    temp_buffer.append(temp)
    current_buffer.append(current)


# =========================
# FEATURE ENGINE (MATCH TRAINING)
# =========================
def build_basic_features(temp, current):

    update_buffers(temp, current)

    # -------------------------
    # SAFETY: warm-up phase
    # -------------------------
    if len(temp_buffer) < 10:
        return pd.DataFrame([{
            "ambient_temp_c": temp,
            "temperature_c": temp,
            "temperature_rise_c": 0,
            "current_a": current,

            "current_squared": current ** 2,
            "power_loss": (current ** 2) * 0.01,
            "thermal_stress": temp * current,

            "thermal_slope_c_per_5s": 0,
            "current_slope_a_per_5s": 0,

            "temp_trend": 0,
            "current_trend": 0,

            "temp_avg_3": temp,
            "current_avg_3": current,

            "temp_acceleration": 0,
            "temp_trend_long": 0,
            "thermal_memory": temp,

            **{f"temp_lag_{i}": temp for i in range(1, 10)},
            **{f"current_lag_{i}": current for i in range(1, 10)},
        }])

    # =========================
    # DATA ARRAYS
    # =========================
    t = np.array(temp_buffer)
    c = np.array(current_buffer)

    # =========================
    # CORE FEATURES
    # =========================
    ambient_temp = temp
    temperature = temp
    current_a = current

    current_squared = current_a ** 2
    power_loss = current_squared * 0.01
    thermal_stress = temperature * current_a

    thermal_slope = (t[-1] - t[0]) / len(t) * 5
    current_slope = (c[-1] - c[0]) / len(c) * 5

    # =========================
    # LAGS (STRICT 9)
    # =========================
    temp_lags = list(t[::-1])[:9]
    curr_lags = list(c[::-1])[:9]

    # pad safety
    temp_lags += [t[-1]] * (9 - len(temp_lags))
    curr_lags += [c[-1]] * (9 - len(curr_lags))

    # =========================
    # DERIVED FEATURES
    # =========================
    temp_trend = t[-1] - t[-3]
    current_trend = c[-1] - c[-3]

    temp_avg_3 = np.mean(t[-3:])
    current_avg_3 = np.mean(c[-3:])

    temp_acceleration = (t[-1] - t[-2]) - (t[-2] - t[-3])

    thermal_memory = np.mean(t)

    temp_trend_long = t[-1] - t[-7]

    # =========================
    # BUILD FEATURE DICT (MATCH TRAINING ORDER)
    # =========================
    features = {
        "ambient_temp_c": ambient_temp,
        "temperature_c": temperature,
        "temperature_rise_c": temperature - 30,
        "current_a": current_a,

        "current_squared": current_squared,
        "power_loss": power_loss,
        "thermal_stress": thermal_stress,

        "thermal_slope_c_per_5s": thermal_slope,
        "current_slope_a_per_5s": current_slope,

        "temp_trend": temp_trend,
        "current_trend": current_trend,

        "temp_avg_3": temp_avg_3,
        "current_avg_3": current_avg_3,

        "temp_acceleration": temp_acceleration,
        "temp_trend_long": temp_trend_long,
        "thermal_memory": thermal_memory,
    }

    # lags
    for i in range(9):
        features[f"temp_lag_{i+1}"] = temp_lags[i]
        features[f"current_lag_{i+1}"] = curr_lags[i]

    return pd.DataFrame([features])