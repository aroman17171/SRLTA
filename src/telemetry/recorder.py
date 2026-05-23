import pyaccsharedmemory
import time
import csv
from pathlib import Path
import pyaccsharedmemory

class ACTelemetryStream:
    def __init__(self):
        self.asm = pyaccsharedmemory.accSharedMemory()
        self.running = False
        self.current_lap = 0
        self.lap_buffer = []  # stores frames for current lap in progress

    def read(self):
        try:
            data = self.asm.get_shared_memory_data()
            physics = data.Physics
            graphics = data.Graphics

            return {
                'speed':     physics.speed_kmh,  # already km/h, correct
                'gear':      physics.gear,
                'rpm':       physics.rpm,
                'throttle':  physics.gas,
                'brake':     physics.brake,
                'distance':  graphics.distance_traveled,
                'lap':       graphics.completed_lap,
                'lap_time':  graphics.current_time / 1000.0,
                'best_time': graphics.best_time / 1000.0,
                'valid_lap': graphics.is_valid_lap,
            }
        except pyaccsharedmemory.SharedMemoryTimeout:
            return None
        except Exception as e:
            print(f"Read error: {e}")
            return None

    def stream(self, callback, on_lap_complete=None, hz=20):
        self.running = True
        interval = 1.0 / hz
        self.lap_start_distance = None  # None until first real movement
        print(f"Streaming at {hz}hz. Ctrl+C to stop.")

        while self.running:
            frame = self.read()
            if frame:
                # Skip frames where car isn't moving yet
                if frame['speed'] < 1.0:
                    time.sleep(interval)
                    continue

                # Set start distance on first real movement
                if self.lap_start_distance is None:
                    self.lap_start_distance = frame['distance']
                    self.current_lap = frame['lap']

                # Detect lap change
                if frame['lap'] != self.current_lap:
                    if on_lap_complete and len(self.lap_buffer) > 50:
                        on_lap_complete(self.lap_buffer)
                    self.lap_buffer = []
                    self.current_lap = frame['lap']
                    self.lap_start_distance = frame['distance']

                # Normalize distance to start of current lap
                frame['distance'] = frame['distance'] - self.lap_start_distance
                self.lap_buffer.append(frame)
                callback(frame)

            time.sleep(interval)

    def save_lap(self, frames, path: str):
        """Save a completed lap buffer to CSV."""
        if not frames:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=frames[0].keys())
            writer.writeheader()
            writer.writerows(frames)
        print(f"Saved lap to {path}")

    def stop(self):
        self.running = False