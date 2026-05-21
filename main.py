"""
SRLTA - Sim Racing Lap Time Analyzer
Main entry point for telemetry analysis
"""

import sys
from pathlib import Path

# Import upgraded modules
from src.telemetry_loader import TelemetryLoader
from src.delta import (
    calculate_time_delta,
    calculate_delta_statistics,
    find_significant_delta_zones,
    generate_coaching_message
)
from src.corner_detection import detect_corners_advanced, analyze_corner_performance
from src.visualization import (
    plot_comprehensive_analysis,
    plot_corner_analysis,
    save_plots
)
import matplotlib.pyplot as plt


def analyze_laps(lap1_path: str, lap2_path: str, detection_method: str = "multi_channel"):
    """
    Complete lap comparison analysis.
    
    Args:
        lap1_path: Path to reference lap telemetry
        lap2_path: Path to comparison lap telemetry
        detection_method: Corner detection method ("multi_channel", "brake_points", "speed_only")
    """
    print("=" * 60)
    print("SRLTA - Sim Racing Lap Time Analyzer")
    print("=" * 60)
    
    # Load telemetry
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
    
    # Calculate delta
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
    
    # Detect corners
    print(f"\n🏁 Detecting corners using '{detection_method}' method...")
    try:
        corners = detect_corners_advanced(lap1, method=detection_method)
        print(f"✓ Detected {len(corners)} corners:")
        for i, corner in enumerate(corners, 1):
            print(f"  {i}. {corner}")
    except Exception as e:
        print(f"✗ Error detecting corners: {e}")
        corners = []
    
    # Analyze corner performance
    if corners:
        print(f"\n📈 Analyzing corner performance...")
        try:
            corner_perf = analyze_corner_performance(lap1, lap2, corners)
            for perf in corner_perf:
                status = {
                    'better_apex': '✓',
                    'better_exit': '✓',
                    'better_braking': '✓',
                    'similar': '≈'
                }.get(perf['performance'], '?')
                print(f"  Corner {perf['corner_number']}: {status} {perf['performance']}")
        except Exception as e:
            print(f"✗ Error analyzing corners: {e}")
            corner_perf = []
    else:
        corner_perf = []
    
    # Generate coaching message
    print(f"\n💬 Analysis Summary:")
    print("-" * 60)
    coaching = generate_coaching_message(stats, zones)
    print(coaching)
    print("-" * 60)
    
    # Create visualizations
    print(f"\n📊 Creating visualizations...")
    try:
        # Main analysis plot
        fig1 = plot_comprehensive_analysis(
            lap1, lap2,
            distances, delta,
            corners=corners if corners else None,
            stats=stats
        )
        
        figures = {'analysis': fig1}
        
        # Corner-by-corner plot if corners detected
        if corners and corner_perf:
            fig2 = plot_corner_analysis(lap1, lap2, corners, corner_perf)
            figures['corners'] = fig2
        
        print(f"✓ Created {len(figures)} visualization(s)")
        
        # Save plots
        save_plots(figures, output_dir="output")
        
        # Show plots
        plt.show()
        
    except Exception as e:
        print(f"✗ Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✓ Analysis complete!")


def main():
    """Main entry point"""
    # Default paths
    lap1_path = "data/lap1.csv"
    lap2_path = "data/lap2.csv"
    
    # Check if custom paths provided
    if len(sys.argv) >= 3:
        lap1_path = sys.argv[1]
        lap2_path = sys.argv[2]
    
    # Check if paths exist
    if not Path(lap1_path).exists():
        print(f"Error: Lap 1 file not found: {lap1_path}")
        print("\nUsage: python main.py [lap1.csv] [lap2.csv]")
        return
    
    if not Path(lap2_path).exists():
        print(f"Error: Lap 2 file not found: {lap2_path}")
        print("\nUsage: python main.py [lap1.csv] [lap2.csv]")
        return
    
    # Run analysis
    analyze_laps(lap1_path, lap2_path)


if __name__ == "__main__":
    main()