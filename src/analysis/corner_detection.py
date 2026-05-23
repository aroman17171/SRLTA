"""
Corner Detection Module
Advanced corner detection using multiple telemetry channels
"""

import numpy as np
from scipy import signal
from typing import List, Dict, Tuple, Optional
import warnings


class Corner:
    """Represents a detected corner with its characteristics"""
    
    def __init__(
        self,
        entry_distance: float,
        apex_distance: float,
        exit_distance: float,
        min_speed: float,
        corner_type: str = "unknown"
    ):
        self.entry_distance = entry_distance
        self.apex_distance = apex_distance
        self.exit_distance = exit_distance
        self.min_speed = min_speed
        self.corner_type = corner_type  # slow, medium, fast
        self.length = exit_distance - entry_distance
    
    def __repr__(self):
        return (f"Corner(apex={self.apex_distance:.0f}m, "
                f"speed={self.min_speed:.0f}km/h, type={self.corner_type})")


def detect_corners_advanced(
    telemetry_data,
    method: str = "multi_channel",
    min_corner_separation: float = 100.0
) -> List[Corner]:
    """
    Detect corners using advanced multi-channel analysis.
    
    Args:
        telemetry_data: TelemetryData object
        method: Detection method ("multi_channel", "speed_only", "brake_points")
        min_corner_separation: Minimum distance between corners (meters)
    
    Returns:
        List of Corner objects
    """
    if method == "multi_channel" and telemetry_data.has_channel('brake'):
        return _detect_corners_multi_channel(telemetry_data, min_corner_separation)
    elif method == "brake_points" and telemetry_data.has_channel('brake'):
        return _detect_corners_brake_points(telemetry_data, min_corner_separation)
    else:
        return _detect_corners_speed_only(telemetry_data, min_corner_separation)


def _detect_corners_multi_channel(
    telemetry_data,
    min_separation: float
) -> List[Corner]:
    """
    Detect corners using speed, brake, and throttle channels.
    Most accurate method when all channels available.
    """
    distance = telemetry_data.get_channel('distance')
    speed = telemetry_data.get_channel('speed')
    
    # Get brake and throttle if available
    brake = telemetry_data.get_channel('brake') if telemetry_data.has_channel('brake') else np.zeros_like(speed)
    throttle = telemetry_data.get_channel('throttle') if telemetry_data.has_channel('throttle') else np.ones_like(speed)
    
    # Create composite corner score
    # High score = likely a corner
    corner_score = np.zeros_like(speed)
    
    # 1. Speed reduction component (normalized)
    speed_normalized = (speed - speed.min()) / (speed.max() - speed.min() + 1e-6)
    speed_reduction = 1 - speed_normalized
    corner_score += speed_reduction * 0.4
    
    # 2. Braking component
    corner_score += brake * 0.4
    
    # 3. Throttle lift component (1 - throttle)
    corner_score += (1 - throttle) * 0.2
    
    # 4. Lateral G if available
    if telemetry_data.has_channel('lateral_g'):
        lateral_g = np.abs(telemetry_data.get_channel('lateral_g'))
        lateral_normalized = lateral_g / (lateral_g.max() + 1e-6)
        corner_score += lateral_normalized * 0.3
    
    # Smooth the score
    window_size = max(3, int(len(corner_score) / 100))
    if window_size % 2 == 0:
        window_size += 1
    corner_score_smooth = signal.savgol_filter(corner_score, window_size, 2)
    
    # Find peaks in corner score
    peak_threshold = np.mean(corner_score_smooth) + 0.5 * np.std(corner_score_smooth)
    peaks, properties = signal.find_peaks(
        corner_score_smooth,
        height=peak_threshold,
        distance=int(min_separation / (distance[1] - distance[0] + 1e-6))
    )
    
    # Create Corner objects
    corners = []
    for peak_idx in peaks:
        # Find corner entry (where braking starts or throttle lifts)
        entry_idx = _find_corner_entry(peak_idx, brake, throttle, window=20)
        
        # Find corner exit (where full throttle resumes)
        exit_idx = _find_corner_exit(peak_idx, brake, throttle, window=20)
        
        # Apex is the minimum speed point in corner
        apex_idx = entry_idx + np.argmin(speed[entry_idx:exit_idx+1])
        
        corner = Corner(
            entry_distance=distance[entry_idx],
            apex_distance=distance[apex_idx],
            exit_distance=distance[exit_idx],
            min_speed=speed[apex_idx],
            corner_type=_classify_corner(speed[apex_idx])
        )
        
        corners.append(corner)
    
    return corners


def _detect_corners_brake_points(
    telemetry_data,
    min_separation: float
) -> List[Corner]:
    """
    Detect corners based on brake application points.
    Good for identifying braking zones.
    """
    distance = telemetry_data.get_channel('distance')
    speed = telemetry_data.get_channel('speed')
    brake = telemetry_data.get_channel('brake')
    
    # Find significant brake applications
    brake_threshold = 0.3
    braking = brake > brake_threshold
    
    # Find brake zones (continuous braking)
    brake_zones = []
    in_zone = False
    zone_start = 0
    
    for i, is_braking in enumerate(braking):
        if is_braking and not in_zone:
            zone_start = i
            in_zone = True
        elif not is_braking and in_zone:
            if i - zone_start > 3:  # Minimum zone length
                brake_zones.append((zone_start, i))
            in_zone = False
    
    # Convert brake zones to corners
    corners = []
    for entry_idx, exit_idx in brake_zones:
        # Apex is minimum speed in brake zone
        apex_idx = entry_idx + np.argmin(speed[entry_idx:exit_idx+1])
        
        # Extend exit to where speed increases again
        exit_search = min(exit_idx + 20, len(speed) - 1)
        for i in range(exit_idx, exit_search):
            if speed[i] > speed[apex_idx] * 1.1:  # 10% speed increase
                exit_idx = i
                break
        
        corner = Corner(
            entry_distance=distance[entry_idx],
            apex_distance=distance[apex_idx],
            exit_distance=distance[exit_idx],
            min_speed=speed[apex_idx],
            corner_type=_classify_corner(speed[apex_idx])
        )
        
        corners.append(corner)
    
    # Filter by minimum separation
    corners = _filter_close_corners(corners, min_separation)
    
    return corners


def _detect_corners_speed_only(
    telemetry_data,
    min_separation: float
) -> List[Corner]:
    """
    Detect corners using only speed data (fallback method).
    Less accurate but works when other channels unavailable.
    """
    distance = telemetry_data.get_channel('distance')
    speed = telemetry_data.get_channel('speed')
    
    # Smooth speed to reduce noise
    window_size = max(5, int(len(speed) / 100))
    if window_size % 2 == 0:
        window_size += 1
    speed_smooth = signal.savgol_filter(speed, window_size, 2)
    
    # Find local minima in speed (potential corners)
    # Invert speed to find peaks (minima become peaks)
    inverted_speed = -speed_smooth
    
    peak_threshold = -np.mean(speed_smooth) + 0.5 * np.std(speed_smooth)
    peaks, properties = signal.find_peaks(
        inverted_speed,
        height=peak_threshold,
        prominence=15,  # Minimum speed drop
        distance=int(min_separation / (distance[1] - distance[0] + 1e-6))
    )
    
    corners = []
    for apex_idx in peaks:
        # Find entry: where speed starts decreasing significantly
        entry_idx = apex_idx
        for i in range(apex_idx - 1, max(0, apex_idx - 30), -1):
            if speed[i] > speed[apex_idx] + 20:  # 20 km/h above apex
                entry_idx = i
                break
        
        # Find exit: where speed recovers
        exit_idx = apex_idx
        for i in range(apex_idx + 1, min(len(speed), apex_idx + 30)):
            if speed[i] > speed[apex_idx] + 20:
                exit_idx = i
                break
        
        corner = Corner(
            entry_distance=distance[entry_idx],
            apex_distance=distance[apex_idx],
            exit_distance=distance[exit_idx],
            min_speed=speed[apex_idx],
            corner_type=_classify_corner(speed[apex_idx])
        )
        
        corners.append(corner)
    
    return corners


def _find_corner_entry(peak_idx: int, brake: np.ndarray, throttle: np.ndarray, window: int = 20) -> int:
    """Find where corner entry begins (brake application or throttle lift)"""
    start = max(0, peak_idx - window)
    
    # Look backwards for brake application or significant throttle lift
    for i in range(peak_idx, start, -1):
        if brake[i] < 0.1 and throttle[i] > 0.8:
            return i
    
    return start


def _find_corner_exit(peak_idx: int, brake: np.ndarray, throttle: np.ndarray, window: int = 20) -> int:
    """Find where corner exit ends (full throttle return)"""
    end = min(len(brake) - 1, peak_idx + window)
    
    # Look forwards for full throttle return
    for i in range(peak_idx, end):
        if brake[i] < 0.1 and throttle[i] > 0.9:
            return i
    
    return end


def _classify_corner(min_speed: float) -> str:
    """Classify corner type based on minimum speed"""
    if min_speed < 80:
        return "slow"
    elif min_speed < 140:
        return "medium"
    else:
        return "fast"


def _filter_close_corners(corners: List[Corner], min_separation: float) -> List[Corner]:
    """Remove corners that are too close together (keep the sharper one)"""
    if len(corners) <= 1:
        return corners
    
    filtered = [corners[0]]
    
    for corner in corners[1:]:
        last_corner = filtered[-1]
        separation = corner.apex_distance - last_corner.apex_distance
        
        if separation >= min_separation:
            filtered.append(corner)
        else:
            # Keep the corner with lower minimum speed (sharper corner)
            if corner.min_speed < last_corner.min_speed:
                filtered[-1] = corner
    
    return filtered


def analyze_corner_performance(
    lap1_data,
    lap2_data,
    corners: List[Corner]
) -> List[Dict]:
    """
    Compare corner performance between two laps.
    
    Args:
        lap1_data: Reference lap telemetry
        lap2_data: Comparison lap telemetry
        corners: List of corners detected
    
    Returns:
        List of dicts with corner performance analysis
    """
    analysis = []
    
    d1 = lap1_data.get_channel('distance')
    s1 = lap1_data.get_channel('speed')
    
    d2 = lap2_data.get_channel('distance')
    s2 = lap2_data.get_channel('speed')
    
    for i, corner in enumerate(corners):
        # Find indices for this corner in both laps
        entry1 = np.argmin(np.abs(d1 - corner.entry_distance))
        apex1 = np.argmin(np.abs(d1 - corner.apex_distance))
        exit1 = np.argmin(np.abs(d1 - corner.exit_distance))
        
        entry2 = np.argmin(np.abs(d2 - corner.entry_distance))
        apex2 = np.argmin(np.abs(d2 - corner.apex_distance))
        exit2 = np.argmin(np.abs(d2 - corner.exit_distance))
        
        # Compare speeds
        entry_speed_diff = s2[entry2] - s1[entry1]
        apex_speed_diff = s2[apex2] - s1[apex1]
        exit_speed_diff = s2[exit2] - s1[exit1]
        
        # Determine performance
        if apex_speed_diff > 2:
            performance = "better_apex"
        elif exit_speed_diff > 2:
            performance = "better_exit"
        elif entry_speed_diff < -2:
            performance = "better_braking"
        else:
            performance = "similar"
        
        analysis.append({
            'corner_number': i + 1,
            'apex_distance': corner.apex_distance,
            'corner_type': corner.corner_type,
            'entry_speed_diff': entry_speed_diff,
            'apex_speed_diff': apex_speed_diff,
            'exit_speed_diff': exit_speed_diff,
            'performance': performance
        })
    
    return analysis


if __name__ == "__main__":
    print("Corner detection module ready")
    print("Use detect_corners_advanced() with TelemetryData objects")