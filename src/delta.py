# src/delta.py
import numpy as np

def calculate_time_delta(lap1, lap2):
    """
    Converts speed + distance into an approximate time model,
    then computes delta between laps.
    """

    d = np.array(lap1["distance"])

    s1 = np.array(lap1["speed"])
    s2 = np.array(lap2["speed"])

    # prevent divide-by-zero
    s1 = np.where(s1 <= 1, 1, s1)
    s2 = np.where(s2 <= 1, 1, s2)

    # approximate segment time = distance / speed
    t1 = d / s1
    t2 = d / s2

    return d, (t2 - t1)