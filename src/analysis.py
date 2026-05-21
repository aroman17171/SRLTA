import pandas as pd
import matplotlib.pyplot as plt
from src.delta import calculate_time_delta

def load_lap(path):
    return pd.read_csv(path)


def detect_corners(lap):
    """
    Simple corner detection:
    corners = where speed drops significantly
    """
    speed = lap["speed"].values
    distance = lap["distance"].values

    corners = []
    for i in range(1, len(speed)):
        if speed[i] < speed[i - 1] - 10:  # sharp drop threshold
            corners.append(distance[i])

    return corners


def plot_all(lap1, lap2):
    d, delta = calculate_time_delta(lap1, lap2)

    corners = detect_corners(lap1)

    fig, ax = plt.subplots(3, 1, figsize=(10, 10))

    # -------------------------
    # 1. SPEED COMPARISON
    # -------------------------
    ax[0].plot(lap1["distance"], lap1["speed"], label="Lap 1")
    ax[0].plot(lap2["distance"], lap2["speed"], label="Lap 2")
    ax[0].set_title("Speed Comparison")
    ax[0].set_ylabel("Speed")
    ax[0].legend()

    # mark corners
    for c in corners:
        ax[0].axvline(c, color="red", alpha=0.2)

    # -------------------------
    # 2. DELTA TIME
    # -------------------------
    ax[1].plot(d, delta, color="purple")
    ax[1].axhline(0, color="black", linewidth=1)
    ax[1].set_title("Delta Time (Lap2 - Lap1)")
    ax[1].set_ylabel("Time Difference")

    # -------------------------
    # 3. CORNER MAP (simple view)
    # -------------------------
    ax[2].plot(lap1["distance"], lap1["speed"])
    ax[2].set_title("Corner Detection (Speed Drops)")
    ax[2].set_xlabel("Distance")
    ax[2].set_ylabel("Speed")

    for c in corners:
        ax[2].axvline(c, color="red", alpha=0.4)

    plt.tight_layout()
    plt.show()