"""
Telemetry Loader Module
Handles loading telemetry data from various sim racing sources:
- Assetto Corsa Shared Memory format
- SimHub CSV exports
- MoTeC i2 format (future)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional


class TelemetryData:
    """
    Standardized telemetry data container.
    All loaders convert to this format for consistent analysis.
    """
    
    def __init__(self, data: pd.DataFrame, metadata: Optional[Dict] = None):
        self.data = data
        self.metadata = metadata or {}
        self._validate()
    
    def _validate(self):
        """Ensure required channels exist"""
        required = ['distance', 'speed']
        missing = [ch for ch in required if ch not in self.data.columns]
        if missing:
            raise ValueError(f"Missing required channels: {missing}")
    
    @property
    def channels(self):
        """Return list of available data channels"""
        return list(self.data.columns)
    
    def has_channel(self, channel: str) -> bool:
        """Check if a channel exists"""
        return channel in self.data.columns
    
    def get_channel(self, channel: str) -> np.ndarray:
        """Get channel data as numpy array"""
        if not self.has_channel(channel):
            raise ValueError(f"Channel '{channel}' not found. Available: {self.channels}")
        return self.data[channel].values
    
    def __repr__(self):
        return f"TelemetryData(samples={len(self.data)}, channels={len(self.channels)})"


class TelemetryLoader:
    """Factory class for loading telemetry from different sources"""
    
    @staticmethod
    def load(file_path: str, format: str = "auto") -> TelemetryData:
        """
        Load telemetry data from file.
        
        Args:
            file_path: Path to telemetry file
            format: Format type ("auto", "simhub", "ac_csv", "motec")
        
        Returns:
            TelemetryData object
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {file_path}")
        
        if format == "auto":
            format = TelemetryLoader._detect_format(path)
        
        loaders = {
            "simhub": TelemetryLoader._load_simhub,
            "ac_csv": TelemetryLoader._load_ac_csv,
            "basic_csv": TelemetryLoader._load_basic_csv,
        }
        
        if format not in loaders:
            raise ValueError(f"Unknown format: {format}. Supported: {list(loaders.keys())}")
        
        return loaders[format](path)
    
    @staticmethod
    def _detect_format(path: Path) -> str:
        """Auto-detect telemetry format from file structure"""
        try:
            df = pd.read_csv(path, nrows=5)
            columns = set(df.columns)
            
            # SimHub exports typically have these columns
            simhub_indicators = {'CarCoordinates_X', 'CarCoordinates_Y', 'CarCoordinates_Z', 'SpeedKmh'}
            if simhub_indicators.issubset(columns):
                return "simhub"
            
            # AC CSV format (from Python Shared Memory exports)
            ac_indicators = {'lapTime', 'worldPosition', 'velocity'}
            if any(ind in columns for ind in ac_indicators):
                return "ac_csv"
            
            # Basic format (what we currently have)
            basic_indicators = {'distance', 'speed'}
            if basic_indicators.issubset(columns):
                return "basic_csv"
            
            return "basic_csv"  # default fallback
            
        except Exception as e:
            raise ValueError(f"Could not detect format: {e}")
    
    @staticmethod
    def _load_simhub(path: Path) -> TelemetryData:
        """Load SimHub CSV export"""
        df = pd.read_csv(path)
        
        # Map SimHub columns to standard format
        column_map = {
            'SpeedKmh': 'speed',
            'Throttle': 'throttle',
            'Brake': 'brake',
            'Gear': 'gear',
            'Rpms': 'rpm',
            'Steer': 'steering',
            'AccelerationSway': 'lateral_g',
            'AccelerationHeave': 'vertical_g',
            'AccelerationSurge': 'longitudinal_g',
        }
        
        # Rename columns that exist
        rename_dict = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Calculate distance if not present
        if 'distance' not in df.columns:
            if 'speed' in df.columns and 'DataCorePlugin.GameRawData.Telemetry.LapTimeSeconds' in df.columns:
                # Integrate speed over time to get distance
                time = df['DataCorePlugin.GameRawData.Telemetry.LapTimeSeconds'].values
                speed_ms = df['speed'].values / 3.6  # km/h to m/s
                
                dt = np.diff(time, prepend=0)
                distance = np.cumsum(speed_ms * dt)
                df['distance'] = distance
            else:
                # Fallback: assume constant sample rate
                df['distance'] = np.arange(len(df)) * 10  # 10m increments
        
        metadata = {
            'source': 'SimHub',
            'file': str(path),
            'original_columns': list(df.columns)
        }
        
        return TelemetryData(df, metadata)
    
    @staticmethod
    def _load_ac_csv(path: Path) -> TelemetryData:
        """Load Assetto Corsa Python Shared Memory export"""
        df = pd.read_csv(path)
        
        # AC shared memory typically provides velocity vectors
        # Calculate speed if needed
        if 'speed' not in df.columns and all(col in df.columns for col in ['velocity_x', 'velocity_y', 'velocity_z']):
            df['speed'] = np.sqrt(
                df['velocity_x']**2 + 
                df['velocity_y']**2 + 
                df['velocity_z']**2
            ) * 3.6  # m/s to km/h
        
        # Calculate distance from position or time
        if 'distance' not in df.columns:
            if all(col in df.columns for col in ['pos_x', 'pos_y', 'pos_z']):
                # Calculate cumulative distance from position changes
                pos_diff = np.sqrt(
                    np.diff(df['pos_x'], prepend=df['pos_x'].iloc[0])**2 +
                    np.diff(df['pos_y'], prepend=df['pos_y'].iloc[0])**2 +
                    np.diff(df['pos_z'], prepend=df['pos_z'].iloc[0])**2
                )
                df['distance'] = np.cumsum(pos_diff)
            else:
                # Fallback
                df['distance'] = np.arange(len(df)) * 10
        
        metadata = {
            'source': 'Assetto Corsa',
            'file': str(path),
        }
        
        return TelemetryData(df, metadata)
    
    @staticmethod
    def _load_basic_csv(path: Path) -> TelemetryData:
        """Load basic CSV format (current format)"""
        df = pd.read_csv(path)
        
        metadata = {
            'source': 'Basic CSV',
            'file': str(path),
        }
        
        return TelemetryData(df, metadata)


def create_sample_ac_telemetry(output_path: str, lap_time: float = 90.0, track_length: float = 3000.0):
    """
    Create a realistic sample telemetry file in AC format.
    Useful for testing without actual sim racing data.
    
    Args:
        output_path: Where to save the CSV
        lap_time: Total lap time in seconds
        track_length: Track length in meters
    """
    import numpy as np
    
    # Generate time series (10Hz sampling)
    sample_rate = 10  # Hz
    num_samples = int(lap_time * sample_rate)
    time = np.linspace(0, lap_time, num_samples)
    
    # Generate realistic lap profile
    # Track has 3 major corners
    corners = [0.25, 0.5, 0.75]  # fractional positions
    
    distance = np.linspace(0, track_length, num_samples)
    
    # Speed profile with corners
    speed = np.ones(num_samples) * 200  # km/h baseline
    
    for corner_pos in corners:
        corner_dist = corner_pos * track_length
        # Gaussian speed reduction at corners
        corner_effect = 80 * np.exp(-((distance - corner_dist)**2) / (100**2))
        speed -= corner_effect
    
    # Add some noise
    speed += np.random.normal(0, 3, num_samples)
    speed = np.clip(speed, 50, 250)  # Realistic limits
    
    # Generate throttle and brake from speed changes
    speed_change = np.gradient(speed)
    throttle = np.clip((speed_change + 2) / 3, 0, 1)
    brake = np.clip((-speed_change) / 5, 0, 1)
    
    # Generate gear from speed
    gear = np.floor(speed / 35).astype(int)
    gear = np.clip(gear, 1, 6)
    
    # Calculate lateral G (approximation from speed at corners)
    lateral_g = np.zeros(num_samples)
    for corner_pos in corners:
        corner_dist = corner_pos * track_length
        corner_effect = 2.5 * np.exp(-((distance - corner_dist)**2) / (80**2))
        lateral_g += corner_effect
    
    # Create DataFrame
    df = pd.DataFrame({
        'time': time,
        'distance': distance,
        'speed': speed,
        'throttle': throttle,
        'brake': brake,
        'gear': gear,
        'lateral_g': lateral_g,
        'rpm': speed * 50 + np.random.normal(0, 100, num_samples),
        'steering': np.sin(distance / 200) * 0.3  # Approximate steering
    })
    
    df.to_csv(output_path, index=False)
    print(f"Created sample telemetry: {output_path}")
    print(f"  Lap time: {lap_time:.2f}s")
    print(f"  Track length: {track_length:.0f}m")
    print(f"  Samples: {num_samples}")


if __name__ == "__main__":
    # Test the loader
    print("Testing telemetry loader...")
    
    # Test loading basic CSV
    try:
        telem = TelemetryLoader.load("data/lap1.csv")
        print(f"✓ Loaded: {telem}")
        print(f"  Channels: {telem.channels}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Create realistic sample
    create_sample_ac_telemetry("data/sample_realistic_lap1.csv", lap_time=85.5, track_length=2800)
    create_sample_ac_telemetry("data/sample_realistic_lap2.csv", lap_time=86.2, track_length=2800)