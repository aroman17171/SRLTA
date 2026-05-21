# SRLTA - Sim Racing Lap Time Analyzer

A professional-grade Python telemetry analysis tool for sim racing, designed to compare lap times and provide actionable coaching feedback.

## 🎯 What's New (v2.0 Upgrade)

### Major Improvements

✅ **Real Telemetry Support**
- Multi-format loader supports SimHub exports, AC Shared Memory format, and basic CSV
- Auto-detection of telemetry format
- Standardized data format for consistent analysis

✅ **Accurate Delta Calculation**
- Time-based interpolation (not just speed/distance approximation)
- Proper cumulative time integration
- Smooth interpolation across different sampling rates
- Sector-by-sector delta analysis

✅ **Advanced Corner Detection**
- Multi-channel analysis (speed + brake + throttle + lateral G)
- Three detection methods: multi_channel, brake_points, speed_only
- Corner classification (slow/medium/fast)
- Entry, apex, and exit point identification

✅ **Professional Visualization**
- MoTeC-style telemetry plots
- Multiple channel overlays (speed, throttle, brake, etc.)
- Delta visualization with gain/loss coloring
- Corner-by-corner comparison plots
- Statistics panel with coaching insights

✅ **Coaching Feedback**
- Automated performance analysis
- Sector time comparisons
- Identification of significant time gain/loss zones
- Corner-specific feedback (better braking, apex speed, exit)

## 📁 Project Structure

```
SRLTA/
├── data/
│   ├── telemetry/              # Place your telemetry files here
│   ├── lap1.csv                # Sample lap 1 (basic format)
│   ├── lap2.csv                # Sample lap 2 (basic format)
│   ├── sample_realistic_lap1.csv  # Generated realistic sample
│   └── sample_realistic_lap2.csv  # Generated realistic sample
├── src/
│   ├── telemetry_loader.py     # Multi-format telemetry loader
│   ├── delta.py             # Accurate delta calculation
│   ├── corner_detection.py     # Advanced corner detection
│   ├── visualization.py        # Professional plotting
│   ├── analysis.py             # (Legacy - deprecated)
│   └── delta.py                # (Legacy - deprecated)
├── output/                     # Generated plots saved here
├── main.py                     # (Legacy entry point)
├── main.py                  # New analysis entry point
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/aroman17171/SRLTA.git
cd SRLTA

# Install dependencies
pip install -r requirements.txt
```

### Run Analysis

```bash
# Using realistic sample data
python main.py data/sample_realistic_lap1.csv data/sample_realistic_lap2.csv

# Using your own telemetry files
python main.py path/to/lap1.csv path/to/lap2.csv
```

## 📊 Telemetry Format Support

### Supported Formats

1. **SimHub CSV Export** (Auto-detected)
   - Exports from SimHub telemetry plugin
   - Contains columns like `SpeedKmh`, `Throttle`, `Brake`, `Gear`, etc.

2. **Assetto Corsa CSV** (Auto-detected)
   - Python shared memory exports
   - Contains velocity vectors, position data, etc.

3. **Basic CSV** (Default)
   - Minimum required columns: `distance`, `speed`
   - Optional: `throttle`, `brake`, `gear`, `rpm`, `lateral_g`, `steering`

### Required Channels

Minimum required:
- `distance` (meters)
- `speed` (km/h)

Recommended for best analysis:
- `throttle` (0-1 or 0-100%)
- `brake` (0-1 or 0-100%)
- `gear` (integer)
- `lateral_g` (g-force)

### Example CSV Format

```csv
distance,speed,throttle,brake,gear,lateral_g
0,0,0,0,1,0
50,80,0.8,0,2,0.5
100,120,1,0,3,1.2
150,110,0.6,0.2,3,2.1
```

## 🏁 Corner Detection Methods

### 1. Multi-Channel (Recommended)
Best accuracy when throttle, brake, and lateral G data available.
```python
corners = detect_corners_advanced(lap_data, method="multi_channel")
```

### 2. Brake Points
Identifies corners based on brake application points.
```python
corners = detect_corners_advanced(lap_data, method="brake_points")
```

### 3. Speed Only (Fallback)
Works with minimal data, less accurate.
```python
corners = detect_corners_advanced(lap_data, method="speed_only")
```

## 📈 Understanding the Output

### Console Output

```
SRLTA - Sim Racing Lap Time Analyzer
============================================================

📊 Loading telemetry data...
✓ Lap 1: TelemetryData(samples=855, channels=9)
✓ Lap 2: TelemetryData(samples=862, channels=9)

⏱️  Calculating time delta...
✓ Delta calculated over 1000 points

🏁 Detecting corners using 'multi_channel' method...
✓ Detected 6 corners

💬 Analysis Summary:
------------------------------------------------------------
Lap 2: 0.123s SLOWER

Sector times:
  ✓ sector_1: -0.045s
  ✗ sector_2: +0.150s
  ✓ sector_3: -0.018s

Key areas:
  Lost 0.150s at 800m-950m
  Gained 0.050s at 1200m-1350m
------------------------------------------------------------
```

### Visualization Output

1. **analysis.png** - Main telemetry comparison
   - Speed traces with corners marked
   - Delta time plot (red = slower, green = faster)
   - Throttle/brake traces (if available)
   - Statistics panel

2. **corners.png** - Corner-by-corner analysis
   - Individual corner speed traces
   - Entry/apex/exit markers
   - Performance indicators

## 🔧 Advanced Usage

### Programmatic API

```python
from src.telemetry_loader import TelemetryLoader
from src.delta import calculate_time_delta, calculate_delta_statistics
from src.corner_detection import detect_corners_advanced, analyze_corner_performance
from src.visualization import plot_comprehensive_analysis

# Load telemetry
lap1 = TelemetryLoader.load("lap1.csv")
lap2 = TelemetryLoader.load("lap2.csv")

# Calculate delta
distances, delta = calculate_time_delta(lap1, lap2)
stats = calculate_delta_statistics(delta, distances)

# Detect corners
corners = detect_corners_advanced(lap1, method="multi_channel")

# Analyze corner performance
corner_perf = analyze_corner_performance(lap1, lap2, corners)

# Visualize
fig = plot_comprehensive_analysis(lap1, lap2, distances, delta, 
                                   corners=corners, stats=stats)
```

### Custom Telemetry Loader

```python
from src.telemetry_loader import TelemetryData
import pandas as pd

# Create custom telemetry data
df = pd.DataFrame({
    'distance': [...],
    'speed': [...],
    'throttle': [...],
    'brake': [...]
})

telemetry = TelemetryData(df, metadata={'source': 'Custom'})
```

## 🎓 Technical Details

### Delta Calculation Algorithm

1. Convert speed data to time-distance relationship
2. Calculate cumulative time at each distance point: `time = ∫(1/speed) dd`
3. Interpolate both laps to identical distance points
4. Compute time difference: `delta = time_lap2 - time_lap1`

### Corner Detection Algorithm (Multi-Channel)

1. Create composite corner score from:
   - Speed reduction (40%)
   - Brake application (40%)
   - Throttle lift (20%)
   - Lateral G (30%, bonus if available)
2. Smooth score with Savitzky-Golay filter
3. Find peaks above threshold
4. Identify entry (brake start) and exit (throttle return)
5. Classify corner type based on minimum speed

## 🛣️ Roadmap

### Completed (v2.0)
- ✅ Real telemetry format support
- ✅ Accurate delta calculation
- ✅ Multi-channel corner detection
- ✅ Professional visualization
- ✅ Coaching feedback

### Planned (v3.0)
- 🔲 Live telemetry streaming (AC Shared Memory)
- 🔲 Track map visualization (2D/3D)
- 🔲 Session comparison (multiple laps)
- 🔲 MoTeC i2 format support
- 🔲 iRacing telemetry support
- 🔲 Machine learning corner classification
- 🔲 Web UI dashboard
- 🔲 Race strategy analysis

## 📚 References

### Similar Tools
- MoTeC i2 Pro - Professional motorsport telemetry analysis
- WinDarab - Racing data analysis
- Atlas - Professional racing software

### Academic References
- Casanova, D. (2000). "On Minimum Time Vehicle Manoeuvring: The Theoretical Optimal Lap"
- Brayshaw, D. & Harrison, M. (2005). "A Quasi Steady State Approach to Race Car Lap Simulation"

## 🤝 Contributing

This is a CS student project. Contributions welcome!

### Development Setup

```bash
# Install in development mode
pip install -e .

# Run tests (when implemented)
pytest tests/
```

## 📝 License

MIT License - See LICENSE file

## 👤 Author

**Alex Roman**
- GitHub: [@aroman17171](https://github.com/aroman17171)

## 🙏 Acknowledgments

- Assetto Corsa for excellent telemetry API
- SimHub for comprehensive data logging
- MoTeC for visualization inspiration