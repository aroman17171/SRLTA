"""
Quick test to verify RealTimeCoach fires correctly.
Uses the first two laps from data/ as the comparison.

Run: python test_coach.py
"""

import sys
from pathlib import Path

sys.path.insert(0, '.')

from src.telemetry.loader import TelemetryLoader
from src.analysis.corner_detection import detect_corners_advanced
from src.analysis.coach import RealTimeCoach


class FakeSpeaker:
    """Captures what the coach says without actually playing TTS."""
    def __init__(self):
        self.messages = []

    def say(self, msg):
        self.messages.append(msg)
        print(f"  [SPEAKER] {msg}")


def main():
    data_dir = Path("data")
    csvs = sorted(data_dir.glob("lap_*.csv"))
    if len(csvs) < 2:
        print("Need at least 2 lap files in data/ to test. Drive two laps first.")
        return

    ref_path    = csvs[0]   # "lap_1.csv" as the reference
    current_path = csvs[1]  # "lap_2.csv" as the current

    print(f"Reference lap: {ref_path.name}")
    print(f"Current lap:   {current_path.name}")

    ref     = TelemetryLoader.load(str(ref_path))
    current = TelemetryLoader.load(str(current_path))

    corners = detect_corners_advanced(ref, method="multi_channel")
    print(f"\nDetected {len(corners)} corners in reference lap:")
    for i, c in enumerate(corners):
        print(f"  Corner {i+1}: entry={c.entry_distance:.0f}m, apex={c.apex_distance:.0f}m, "
              f"exit={c.exit_distance:.0f}m, type={c.corner_type}")

    # Build a fake live stream from the current lap
    d = current.get_channel("distance")
    s = current.get_channel("speed")
    b = current.get_channel("brake") if current.has_channel("brake") else [0.0] * len(d)

    # Slow down the current lap speeds a bit so the coach has something to say
    s_slow = [v * 0.85 for v in s]   # 15% slower → "carry more speed in" etc.
    b_high = [min(1.0, v * 1.5) for v in b]

    print(f"\nSimulating {len(d)} frames with a slower / heavier-brake lap...")
    print("(Original ref, then slowed+overbraked current, so coach should fire)\n")

    speaker = FakeSpeaker()
    coach = RealTimeCoach(speaker)
    # Override the cooldown so we hear every message
    coach.cooldown = 0.0

    for i in range(len(d)):
        frame = {
            "distance": float(d[i]),
            "speed":    float(s_slow[i]),
            "brake":    float(b_high[i]),
        }
        coach.update(frame, ref, corners)

    print(f"\nCoach fired {len(speaker.messages)} messages:")
    for m in speaker.messages:
        print(f"  - {m}")


if __name__ == "__main__":
    main()
