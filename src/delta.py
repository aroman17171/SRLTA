"""
Delta Analysis Module
Calculates accurate time deltas between laps using proper interpolation
"""

import numpy as np
from scipy import interpolate
from typing import Tuple, Optional
import warnings


def calculate_time_delta(
    lap1_data,
    lap2_data,
    reference_channel: str = "distance",
    interpolation_points: int = 1000
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate accurate time delta between two laps.
    
    The delta shows how much faster/slower lap2 is compared to lap1
    at each point on track.
    
    Method:
    1. Integrate speed over time to get cumulative time vs distance
    2. Interpolate both laps to same distance points
    3. Calculate time difference
    
    Args:
        lap1_data: TelemetryData for reference lap
        lap2_data: TelemetryData for comparison lap
        reference_channel: Channel to align on (usually 'distance')
        interpolation_points: Number of points for smooth comparison
    
    Returns:
        (distances, delta_times) where:
        - distances: array of distance points
        - delta_times: time difference (positive = lap2 slower)
    """
    
    # Get distance and speed channels
    d1 = lap1_data.get_channel('distance')
    s1 = lap1_data.get_channel('speed')
    
    d2 = lap2_data.get_channel('distance')
    s2 = lap2_data.get_channel('speed')
    
    # Calculate cumulative time for each lap
    time1 = _calculate_cumulative_time(d1, s1)
    time2 = _calculate_cumulative_time(d2, s2)
    
    # Find common distance range
    d_min = max(d1.min(), d2.min())
    d_max = min(d1.max(), d2.max())
    
    # Create uniform distance points for interpolation
    distances = np.linspace(d_min, d_max, interpolation_points)
    
    # Interpolate time at each distance point
    time1_interp = _safe_interpolate(d1, time1, distances)
    time2_interp = _safe_interpolate(d2, time2, distances)
    
    # Calculate delta (positive means lap2 is slower)
    delta = time2_interp - time1_interp
    
    return distances, delta


def _calculate_cumulative_time(distance: np.ndarray, speed: np.ndarray) -> np.ndarray:
    """
    Calculate cumulative time from distance and speed data.
    
    Time = integral of (1/speed) * distance
    
    Args:
        distance: Distance array (meters)
        speed: Speed array (km/h)
    
    Returns:
        Cumulative time array (seconds)
    """
    # Convert speed to m/s
    speed_ms = speed / 3.6
    
    # Prevent division by zero
    speed_ms = np.where(speed_ms < 0.1, 0.1, speed_ms)
    
    # Calculate distance increments
    dd = np.diff(distance, prepend=distance[0])
    dd = np.abs(dd)  # Handle any negative increments
    
    # Calculate time for each segment: dt = distance / speed
    dt = dd / speed_ms
    
    # Cumulative time
    time = np.cumsum(dt)
    
    return time


def _safe_interpolate(x: np.ndarray, y: np.ndarray, x_new: np.ndarray) -> np.ndarray:
    """
    Safely interpolate y values at new x points.
    Handles edge cases and ensures monotonic x values.
    
    Args:
        x: Original x values
        y: Original y values
        x_new: New x values to interpolate to
    
    Returns:
        Interpolated y values
    """
    # Remove any duplicate x values (keep first occurrence)
    unique_mask = np.concatenate(([True], np.diff(x) != 0))
    x = x[unique_mask]
    y = y[unique_mask]
    
    # Ensure x is monotonically increasing
    if not np.all(np.diff(x) >= 0):
        warnings.warn("Distance values are not monotonic. Sorting data.")
        sort_idx = np.argsort(x)
        x = x[sort_idx]
        y = y[sort_idx]
    
    # Use linear interpolation (could upgrade to spline if needed)
    f = interpolate.interp1d(
        x, y,
        kind='linear',
        bounds_error=False,
        fill_value='extrapolate'
    )
    
    return f(x_new)


def calculate_delta_statistics(delta: np.ndarray, distances: np.ndarray) -> dict:
    """
    Calculate statistics about the delta between laps.
    
    Args:
        delta: Delta time array (seconds)
        distances: Corresponding distance array
    
    Returns:
        Dictionary with delta statistics
    """
    stats = {
        'total_delta': delta[-1],  # Final time difference
        'max_gain': np.min(delta),  # Most time gained (negative delta)
        'max_loss': np.max(delta),  # Most time lost (positive delta)
        'avg_delta': np.mean(delta),
        'std_delta': np.std(delta),
    }
    
    # Find where max gain/loss occurred
    stats['max_gain_distance'] = distances[np.argmin(delta)]
    stats['max_loss_distance'] = distances[np.argmax(delta)]
    
    # Calculate sectors (divide track into 3)
    sector_size = len(distances) // 3
    stats['sector_deltas'] = {
        'sector_1': delta[sector_size] - delta[0],
        'sector_2': delta[2*sector_size] - delta[sector_size],
        'sector_3': delta[-1] - delta[2*sector_size],
    }
    
    return stats


def find_significant_delta_zones(
    delta: np.ndarray,
    distances: np.ndarray,
    threshold: float = 0.1,
    min_zone_length: float = 50
) -> list:
    """
    Find zones where significant time is gained or lost.
    
    Args:
        delta: Delta time array
        distances: Distance array
        threshold: Minimum delta rate (seconds per meter)
        min_zone_length: Minimum zone length to report (meters)
    
    Returns:
        List of dicts describing each significant zone
    """
    # Calculate rate of delta change
    delta_rate = np.gradient(delta, distances)
    
    # Find zones where rate exceeds threshold
    significant = np.abs(delta_rate) > threshold
    
    zones = []
    in_zone = False
    zone_start = 0
    
    for i, is_sig in enumerate(significant):
        if is_sig and not in_zone:
            # Start of new zone
            zone_start = i
            in_zone = True
        elif not is_sig and in_zone:
            # End of zone
            zone_end = i
            zone_length = distances[zone_end] - distances[zone_start]
            
            if zone_length >= min_zone_length:
                zone_delta = delta[zone_end] - delta[zone_start]
                zones.append({
                    'start_distance': distances[zone_start],
                    'end_distance': distances[zone_end],
                    'length': zone_length,
                    'delta_change': zone_delta,
                    'type': 'gain' if zone_delta < 0 else 'loss'
                })
            
            in_zone = False
    
    return zones


def compare_speed_traces(
    lap1_data,
    lap2_data,
    interpolation_points: int = 1000
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compare speed traces at identical distance points.
    
    Returns:
        (distances, speed1, speed2) - all interpolated to same distance points
    """
    d1 = lap1_data.get_channel('distance')
    s1 = lap1_data.get_channel('speed')
    
    d2 = lap2_data.get_channel('distance')
    s2 = lap2_data.get_channel('speed')
    
    # Common distance range
    d_min = max(d1.min(), d2.min())
    d_max = min(d1.max(), d2.max())
    
    distances = np.linspace(d_min, d_max, interpolation_points)
    
    speed1 = _safe_interpolate(d1, s1, distances)
    speed2 = _safe_interpolate(d2, s2, distances)
    
    return distances, speed1, speed2


def generate_coaching_message(stats: dict, zones: list) -> str:
    """
    Generate human-readable coaching message from delta analysis.
    
    Args:
        stats: Statistics from calculate_delta_statistics
        zones: Significant zones from find_significant_delta_zones
    
    Returns:
        Coaching message string
    """
    messages = []
    
    # Overall result
    total = stats['total_delta']
    if abs(total) < 0.05:
        messages.append(f"Lap times nearly identical (Δ{total:+.3f}s)")
    elif total < 0:
        messages.append(f"✓ Lap 2 faster by {abs(total):.3f}s")
    else:
        messages.append(f"✗ Lap 2 slower by {total:.3f}s")
    
    # Sector analysis
    messages.append("\nSector times:")
    for sector, delta in stats['sector_deltas'].items():
        status = "✓" if delta <= 0 else "✗"
        messages.append(f"  {status} {sector}: {delta:+.3f}s")
    
    # Significant zones
    if zones:
        messages.append("\nKey areas:")
        for zone in zones[:3]:  # Top 3 zones
            zone_type = "gained" if zone['type'] == 'gain' else "lost"
            messages.append(
                f"  {zone_type.title()} {abs(zone['delta_change']):.3f}s "
                f"at {zone['start_distance']:.0f}m-{zone['end_distance']:.0f}m"
            )
    
    return "\n".join(messages)


if __name__ == "__main__":
    # Test with synthetic data
    print("Testing delta calculation...")
    
    # Create test data
    distance = np.linspace(0, 1000, 100)
    speed1 = 100 + 20 * np.sin(distance / 100)
    speed2 = 102 + 20 * np.sin(distance / 100 + 0.1)  # Slightly faster
    
    # Mock TelemetryData
    class MockTelem:
        def __init__(self, d, s):
            self.d = d
            self.s = s
        def get_channel(self, ch):
            if ch == 'distance':
                return self.d
            return self.s
    
    lap1 = MockTelem(distance, speed1)
    lap2 = MockTelem(distance, speed2)
    
    d, delta = calculate_time_delta(lap1, lap2)
    stats = calculate_delta_statistics(delta, d)
    
    print(f"Total delta: {stats['total_delta']:.3f}s")
    print(f"Max gain at: {stats['max_gain_distance']:.0f}m")
    print(f"Max loss at: {stats['max_loss_distance']:.0f}m")