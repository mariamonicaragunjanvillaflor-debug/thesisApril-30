import numpy as np
from collections import deque

# buffers (shared logic)
temp_buffer = deque(maxlen=10)
current_buffer = deque(maxlen=10)


def update_buffers(temp, current):
    temp_buffer.append(temp)
    current_buffer.append(current)


def build_basic_features(temp, current):
    update_buffers(temp, current)

    if len(temp_buffer) < 10:
        return None

    t = np.array(temp_buffer)
    c = np.array(current_buffer)

    ambient_temp = temp
    temperature = temp
    current_a = current

    current_squared = current_a ** 2
    power_loss = current_squared * 0.01
    thermal_stress = temperature * current_a

    thermal_slope = (t[-1] - t[0]) / len(t) * 5
    current_slope = (c[-1] - c[0]) / len(c) * 5

    temp_lags = list(t[::-1])[:9]
    curr_lags = list(c[::-1])[:9]

    temp_trend = t[-1] - t[-3]
    current_trend = c[-1] - c[-3]

    temp_avg_3 = np.mean(t[-3:])
    current_avg_3 = np.mean(c[-3:])

    temp_accel = (t[-1] - t[-2]) - (t[-2] - t[-3])

    thermal_memory = np.mean(t)

    features = [
        ambient_temp,
        temperature,
        temperature - 30,
        current_a,

        current_squared,
        power_loss,
        thermal_stress,

        thermal_slope,
        current_slope,
    ]

    features += temp_lags
    features += curr_lags

    features += [
        temp_trend,
        current_trend,
        temp_avg_3,
        current_avg_3,
        temp_accel,
        temp_trend,
        thermal_memory,
    ]

    return np.array(features).reshape(1, -1)