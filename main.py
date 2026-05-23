"""
SRLTA - Sim Racing Lap Time Analyzer
"""

import sys
from pathlib import Path
from src.telemetry.recorder import ACTelemetryStream
from src.telemetry.loader import TelemetryLoader
from src.analysis.delta import (
    calculate_time_delta,
    calculate_delta_statistics,
    find_significant_delta_zones,
    generate_coaching_message
)
from src.analysis.corner_detection import detect_corners_advanced, analyze_corner_performance
from src.ui.plots import plot_comprehensive_analysis, plot_corner_analysis, save_plots
import matplotlib.pyplot as plt


def live_mode():
    print("=" * 60)
    print("SRLTA - Live Mode")
    print("=" * 60)
    print("Drive normally. Each completed lap will be saved and analyzed.")
    print("Ctrl+C to stop.\n")

    from src.voice.speaker import Speaker
    speaker = Speaker()
    speaker.test()  # confirms voice is working when you start

    stream = ACTelemetryStream()
    best_lap_path = "data/best_lap.csv"
    lap_number = 1

    def on_frame(frame):
        print(f"\r  Speed: {frame['speed']:6.1f} km/h  "
              f"Dist: {frame['distance']:6.0f}m  "
              f"Lap: {frame['lap']}  "
              f"Time: {frame['lap_time']:.1f}s", end="")

    def on_lap_complete(frames):
        nonlocal lap_number, best_lap_path
        print(f"\n\n✓ Lap {lap_number} complete — {len(frames)} frames recorded")
        
        lap_path = f"data/lap_{lap_number}.csv"
        stream.save_lap(frames, lap_path)

        if Path(best_lap_path).exists():
            print("  Comparing to best lap...")
            try:
                ref = TelemetryLoader.load(best_lap_path)
                current = TelemetryLoader.load(lap_path)
                distances, delta = calculate_time_delta(ref, current)
                stats = calculate_delta_statistics(delta, distances)
                zones = find_significant_delta_zones(delta, distances)

                # Print to terminal
                coaching = generate_coaching_message(stats, zones)
                print(coaching)

                # Speak it
                speaker.say_lap_result(stats, zones)

                # Update best lap if this one is faster
                if stats['total_delta'] < 0:
                    import shutil
                    shutil.copy(lap_path, best_lap_path)
                    print("  New best lap saved!")
                    #speaker.say("New best lap!", interrupt=False)

            except Exception as e:
                print(f"  Could not compare: {e}")
        else:
            import shutil
            shutil.copy(lap_path, best_lap_path)
            print("  First lap saved as reference. Drive another lap to compare!")
            speaker.say("First lap recorded. Drive another lap to compare.")

        lap_number += 1

    try:
        stream.stream(callback=on_frame, on_lap_complete=on_lap_complete)
    except KeyboardInterrupt:
        stream.stop()
        print("\n\nStopped.")


def analyze_laps(lap1_path: str, lap2_path: str, detection_method: str = "multi_channel"):
    print("=" * 60)
    print("SRLTA - Sim Racing Lap Time Analyzer")
    print("=" * 60)

    print(f"\n📊 Loading telemetry data...")
    try:
        lap1 = TelemetryLoader.load(lap1_path)
        lap2 = TelemetryLoader.load(lap2_path)
        print(f"✓ Lap 1: {lap1}")
        print(f"  Source: {lap1.metadata.get('source', 'Unknown')}")
        print(f"  Channels: {', '.join(lap1.channels)}")
        print(f"✓ Lap 2: {lap2}")
        print(f"  Source: {lap2.metadata.get('source', 'Unknown')}")
        print(f"  Channels: {', '.join(lap2.channels)}")
    except Exception as e:
        print(f"✗ Error loading telemetry: {e}")
        return

    print(f"\n⏱️  Calculating time delta...")
    try:
        distances, delta = calculate_time_delta(lap1, lap2)
        stats = calculate_delta_statistics(delta, distances)
        zones = find_significant_delta_zones(delta, distances)
        print(f"✓ Delta calculated over {len(distances)} points")
    except Exception as e:
        print(f"✗ Error calculating delta: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n🏁 Detecting corners using '{detection_method}' method...")
    try:
        corners = detect_corners_advanced(lap1, method=detection_method)
        print(f"✓ Detected {len(corners)} corners")
    except Exception as e:
        print(f"✗ Error detecting corners: {e}")
        corners = []

    if corners:
        print(f"\n📈 Analyzing corner performance...")
        try:
            corner_perf = analyze_corner_performance(lap1, lap2, corners)
        except Exception as e:
            print(f"✗ Error analyzing corners: {e}")
            corner_perf = []
    else:
        corner_perf = []

    print(f"\n💬 Analysis Summary:")
    print("-" * 60)
    print(generate_coaching_message(stats, zones))
    print("-" * 60)

    print(f"\n📊 Creating visualizations...")
    try:
        fig1 = plot_comprehensive_analysis(
            lap1, lap2, distances, delta,
            corners=corners if corners else None,
            stats=stats
        )
        figures = {'analysis': fig1}
        if corners and corner_perf:
            figures['corners'] = plot_corner_analysis(lap1, lap2, corners, corner_perf)
        save_plots(figures, output_dir="output")
        plt.show()
    except Exception as e:
        print(f"✗ Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()

    print("\n✓ Analysis complete!")


def main():
    if "--live" in sys.argv:
        live_mode()
        return
    if "--analyze" in sys.argv:
        # existing analysis mode
        lap1_path = sys.argv[2] if len(sys.argv) > 2 else "data/lap1.csv"
        lap2_path = sys.argv[3] if len(sys.argv) > 3 else "data/lap2.csv"
        analyze_laps(lap1_path, lap2_path)
        return

    # Default — launch GUI
    from src.ui.dashboard import run
    run()


if __name__ == "__main__":
    main()