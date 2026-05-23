# SRLTA - Sim Racing Lap Time Analyzer

A Python-based sim racing telemetry tool for Assetto Corsa that records live driving data, compares laps, and provides real-time + post-lap coaching (including voice feedback).

This project is currently in **early development**, with a working live telemetry recorder, basic GUI, and voice coaching system.

---

## Features (Current State)

### Live Telemetry (Working)
- Reads real-time Assetto Corsa data via shared memory
- Displays:
  - Speed (km/h)
  - Gear
  - Lap time
  - Lap counter
- Records full laps automatically
- Saves laps to CSV for later analysis

### Lap Comparison (Working)
- Compares current lap vs best lap
- Calculates:
  - Total delta time
  - Sector deltas (basic split by distance thirds)
- Detects improvement or slowdown per lap

### Voice Coaching (Working)
- Offline text-to-speech using `pyttsx3`
- Speaks after each lap:
  - Faster/slower result
  - Sector performance summary
  - Biggest time loss areas

### GUI (Working - Early Version)
Built with `customtkinter`:
- Home screen:
  - Live Mode
  - Analysis Mode
- Live screen:
  - Real-time telemetry
  - Delta vs best lap
  - Sector display
  - Coaching log
- Analysis screen:
  - Load two CSV laps
  - Run comparison analysis

---

## Project Structure


SRLTA/
├── src/
│ ├── ui/
│ │ └── dashboard.py # Main GUI app
│ ├── voice/
│ │ └── speaker.py # Voice coaching (pyttsx3)
│ ├── telemetry/
│ │ ├── recorder.py # Live shared memory stream
│ │ └── loader.py # CSV loader
│ ├── analysis/
│ │ └── delta.py # Lap delta + stats
│
├── data/
│ ├── lap_*.csv # Recorded laps
│ └── best_lap.csv # Reference lap
│
├── analysis.py # Simple CSV analysis (legacy test script)
├── main.py # ENTRY POINT
└── requirements.txt


---

## Installation

```bash
git clone https://github.com/aroman17171/SRLTA.git
cd SRLTA

pip install -r requirements.txt
Required packages
pyaccsharedmemory
pyttsx3
customtkinter
pandas
numpy

---

## How to Run

### Launch Full App (Recommended)

```bash
py main.py

This opens the GUI.

Live Telemetry Mode (Terminal)
py main.py --live
Starts shared memory streaming
Records laps automatically
Prints telemetry + lap results
Plays voice coaching after each lap
Analysis Mode (Legacy)
py main.py --analyze data/lap_1.csv data/lap_2.csv
Compares two saved laps
Outputs delta + sector breakdown
Telemetry Source

This project uses:

pyaccsharedmemory
Assetto Corsa Shared Memory API

It reads:

Speed
Gear
RPM (limited depending on build)
Gas / Brake inputs (if available)
Lap timing + distance
Known Limitations (Current Stage)
Sector splits are simplified (distance-based thirds, not real track sectors)
Some telemetry fields depend on game/session state
Lap validity is not filtered (all laps are treated as valid)
Shared memory can occasionally timeout between laps
GUI is functional but not production polished
Roadmap
Next Improvements
Proper track sector detection (not distance split)
Better invalid lap filtering
Fix telemetry gaps / timeout handling
Save best lap automatically with metadata
Improve GUI styling + responsiveness
Future Goals
Pack into standalone .exe
Add real track maps
Add replay overlay system
Add data-driven driving tips (braking, throttle, etc.)
Running Notes

If you get shared memory errors:

Make sure Assetto Corsa is running
Be in a driving session (not just menus)
Restart game if data stops streaming
Author

Adam Roman
GitHub: https://github.com/aroman17171