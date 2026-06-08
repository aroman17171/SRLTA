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
        self.lap_buffer = []
        self._cached_car = ''
        self._cached_track = ''
        self._cached_config = ''
        self._last_successful_static_read = 0.0
        self._static_read_interval = 2.0  # only re-read static every 2s
        self._debug_printed = False  # one-shot debug print for position source


    def _read_static(self):
        """Fetch static info, but only every few seconds and only update
        the cache when we get real (non-empty) data. AC's static struct
        can briefly read as empty mid-update, so we never overwrite good
        cached values with blanks."""
        import time as _t
        now = _t.time()
        if now - self._last_successful_static_read < self._static_read_interval:
            return {
                'car_model': self._cached_car,
                'track':     self._cached_track,
                'track_config': self._cached_config,
            }
        try:
            sm = self.asm.read_shared_memory()
            if sm is None:
                return self._cached_payload()
            static = sm.Static
            car    = getattr(static, 'car_model', '') or ''
            track  = getattr(static, 'track', '') or ''
            config = getattr(static, 'track_configuration', '') or ''
            for name, val in (('car', car), ('track', track), ('config', config)):
                pass
            if isinstance(car, bytes):    car    = car.decode('utf-8', errors='ignore')
            if isinstance(track, bytes):  track  = track.decode('utf-8', errors='ignore')
            if isinstance(config, bytes): config = config.decode('utf-8', errors='ignore')
            car    = str(car).strip().rstrip('\x00').strip()
            track  = str(track).strip().rstrip('\x00').strip()
            config = str(config).strip().rstrip('\x00').strip()

            # Only commit to cache if we got at least one non-empty field.
            # (Don't blank out a good cache with a momentarily-empty read.)
            got_real = False
            if car and car != self._cached_car:
                self._cached_car = car
                got_real = True
            if track and track != self._cached_track:
                self._cached_track = track
                got_real = True
            if config and config != self._cached_config:
                self._cached_config = config
                got_real = True
            if got_real:
                self._last_successful_static_read = now

            return self._cached_payload()
        except Exception as e:
            # On any error just return what we have; never blank the cache.
            return self._cached_payload()

    def _cached_payload(self):
        return {
            'car_model':   self._cached_car,
            'track':       self._cached_track,
            'track_config': self._cached_config,
        }

    def read(self):
        try:
            data = self.asm.get_shared_memory_data()
            physics = data.Physics
            graphics = data.Graphics
            static = self._read_static()

            car = static['car_model'] or 'unknown_car'
            track = static['track'] or 'unknown_track'
            if static.get('track_config'):
                track = f"{track}_{static['track_config']}"

            # Get world position from graphics.car_coordinates[0] (the player's
            # car position). car_coordinates is a list of Vector3f, one per
            # car on track; the player's is always index 0. The x/z axes are
            # what we want for a top-down track map (y is vertical).
            coords = getattr(graphics, 'car_coordinates', None)
            if coords and len(coords) > 0:
                v0 = coords[0]
                # Vector3f has .x / .y / .z attributes (not subscriptable on
                # every pyaccsharedmemory version, so getattr for safety).
                pos_x = float(getattr(v0, 'x', 0.0) or 0.0)
                pos_y = float(getattr(v0, 'y', 0.0) or 0.0)
                pos_z = float(getattr(v0, 'z', 0.0) or 0.0)
            else:
                pos_x = pos_y = pos_z = 0.0
            steer = float(getattr(physics, 'steer_angle',
                                  getattr(physics, 'steer', 0.0)) or 0.0)
            # One-shot debug so we can see what fields the lib exposes
            if not self._debug_printed:
                self._debug_printed = True
                try:
                    pos = (pos_x, pos_y, pos_z)
                    spd = float(getattr(physics, 'speed_kmh', 0.0))
                    print(f"[recorder debug] pos={pos} speed={spd:.1f}kmh "
                          f"car_coordinates[0].type={type(coords[0]).__name__ if coords else 'None'}")
                except Exception:
                    pass

            
            return {
                'speed':     physics.speed_kmh,
                'gear':      physics.gear,
                'rpm':       physics.rpm,
                'throttle':  physics.gas,
                'brake':     physics.brake,
                'steering':  steer,
                'pos_x':     pos_x,
                'pos_y':     pos_y,
                'pos_z':     pos_z,
                'distance':  graphics.distance_traveled,
                'lap':       graphics.completed_lap,
                'lap_time':  graphics.current_time / 1000.0,
                'best_time': graphics.best_time / 1000.0,
                'valid_lap': graphics.is_valid_lap,
                'car':       car,
                'track':     track,
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