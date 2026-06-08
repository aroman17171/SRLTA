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
    
    # Build racing line from reference lap if position data available
    racing_line = None
    if lap1_data.has_channel('pos_x') and lap1_data.has_channel('pos_z'):
        racing_line = _build_racing_line(lap1_data, corners)
    
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
            
        exit_speed_loss = max(0, s1[exit1] - s2[exit2])  # lap2 slower on exit

        # Physically correct time loss estimate
        exit_zone = 50.0  # meters after apex
        avg_speed_ms = max(s1[apex1] / 3.6, 1.0)
        ref_exit_speed = max(s1[exit1], 1.0)
        time_lost = round((exit_zone / avg_speed_ms) * (exit_speed_loss / ref_exit_speed), 2)
        time_lost = min(time_lost, 0.8)  # Cap at 0.8s per corner
        
        brake_diff_m = 0.0
        if lap1_data.has_channel('brake') and lap2_data.has_channel('brake'):
            b1 = lap1_data.get_channel('brake')
            b2 = lap2_data.get_channel('brake')
            # Search backwards from apex for first hard brake (>0.3) in a 200m window
            search_start1 = max(0, entry1 - 40)
            search_start2 = max(0, entry2 - 40)

            brake_idx1 = entry1
            for j in range(entry1, search_start1, -1):
                if b1[j] > 0.3:
                    brake_idx1 = j
                    break

            brake_idx2 = entry2
            for j in range(entry2, search_start2, -1):
                if b2[j] > 0.3:
                    brake_idx2 = j
                    break

            brake_diff_m = round(d1[brake_idx1] - d2[brake_idx2], 1)
        
        # Calculate racing line deviation if position data available
        line_deviation_entry = 0.0
        line_deviation_apex = 0.0
        line_deviation_exit = 0.0
        avg_deviation = 0.0
        
        if racing_line is not None and lap2_data.has_channel('pos_x') and lap2_data.has_channel('pos_z'):
            line_dev = _calculate_line_deviation(lap2_data, racing_line, corner)
            line_deviation_entry = line_dev.get('entry', 0.0)
            line_deviation_apex = line_dev.get('apex', 0.0)
            line_deviation_exit = line_dev.get('exit', 0.0)
            avg_deviation = line_dev.get('avg', 0.0)

        analysis.append({
            'corner_number': i + 1,
            'apex_distance': corner.apex_distance,
            'corner_type': corner.corner_type,
            'entry_speed_diff': round(float(entry_speed_diff), 1),
            'apex_speed_diff':  round(float(apex_speed_diff), 1),
            'exit_speed_diff':  round(float(exit_speed_diff), 1),
            'performance': performance,
            'time_lost': time_lost,
            'brake_diff_m': brake_diff_m,
            'line_deviation_entry': round(line_deviation_entry, 1),
            'line_deviation_apex': round(line_deviation_apex, 1),
            'line_deviation_exit': round(line_deviation_exit, 1),
            'line_deviation_avg': round(avg_deviation, 1),
        })
    
    return analysis


def _build_racing_line(telemetry_data, corners: List[Corner]) -> Dict:
    """
    Build a racing line model from reference lap position data.
    Creates a parametric curve through X/Z positions at each distance.
    """
    distance = telemetry_data.get_channel('distance')
    pos_x = telemetry_data.get_channel('pos_x')
    pos_z = telemetry_data.get_channel('pos_z')
    
    # Create interpolation functions for the racing line
    from scipy import interpolate
    
    # Only use valid (non-zero) positions
    valid_mask = (pos_x != 0) | (pos_z != 0)
    if not np.any(valid_mask):
        return None
    
    valid_dist = distance[valid_mask]
    valid_x = pos_x[valid_mask]
    valid_z = pos_z[valid_mask]
    
    if len(valid_dist) < 10:
        return None
    
    # Sort by distance
    sort_idx = np.argsort(valid_dist)
    valid_dist = valid_dist[sort_idx]
    valid_x = valid_x[sort_idx]
    valid_z = valid_z[sort_idx]
    
    # Create spline interpolation for the racing line
    try:
        # Use cubic spline for smooth racing line
        x_spline = interpolate.UnivariateSpline(valid_dist, valid_x, k=min(3, len(valid_dist)-1), s=len(valid_dist))
        z_spline = interpolate.UnivariateSpline(valid_dist, valid_z, k=min(3, len(valid_dist)-1), s=len(valid_dist))
        
        return {
            'distance': valid_dist,
            'x': valid_x,
            'z': valid_z,
            'x_spline': x_spline,
            'z_spline': z_spline,
        }
    except Exception:
        return None


def _calculate_line_deviation(lap2_data, racing_line: Dict, corner: Corner) -> Dict:
    """
    Calculate lateral deviation from the racing line for a specific corner.
    Returns deviation at entry, apex, exit, and average.
    """
    d2 = lap2_data.get_channel('distance')
    pos_x = lap2_data.get_channel('pos_x')
    pos_z = lap2_data.get_channel('pos_z')
    
    # Sample points across the corner zone
    corner_start = corner.entry_distance
    corner_end = corner.exit_distance
    
    # Find indices in the lap data for this corner
    mask = (d2 >= corner_start) & (d2 <= corner_end)
    if not np.any(mask):
        return {'entry': 0.0, 'apex': 0.0, 'exit': 0.0, 'avg': 0.0}
    
    corner_dist = d2[mask]
    corner_x = pos_x[mask]
    corner_z = pos_z[mask]
    
    # Filter out invalid positions
    valid = (corner_x != 0) | (corner_z != 0)
    if not np.any(valid):
        return {'entry': 0.0, 'apex': 0.0, 'exit': 0.0, 'avg': 0.0}
    
    corner_dist = corner_dist[valid]
    corner_x = corner_x[valid]
    corner_z = corner_z[valid]
    
    x_spline = racing_line['x_spline']
    z_spline = racing_line['z_spline']
    
    deviations = []
    entry_dev = apex_dev = exit_dev = 0.0
    
    for dist, x, z in zip(corner_dist, corner_x, corner_z):
        try:
            # Get ideal racing line position at this distance
            ideal_x = float(x_spline(dist))
            ideal_z = float(z_spline(dist))
            
            # Calculate lateral deviation (perpendicular distance to racing line)
            # We approximate lateral direction using tangent to racing line
            eps = 0.1  # Small distance to estimate tangent
            if dist + eps <= racing_line['distance'][-1]:
                tangent_x = float(x_spline(dist + eps)) - ideal_x
                tangent_z = float(z_spline(dist + eps)) - ideal_z
            else:
                tangent_x = ideal_x - float(x_spline(dist - eps))
                tangent_z = ideal_z - float(z_spline(dist - eps))
            
            tangent_len = np.sqrt(tangent_x**2 + tangent_z**2)
            if tangent_len > 1e-6:
                # Normal vector (pointing to the right of track direction)
                normal_x = -tangent_z / tangent_len
                normal_z = tangent_x / tangent_len
                
                # Vector from ideal position to actual position
                dx = x - ideal_x
                dz = z - ideal_z
                
                # Project onto normal to get lateral deviation
                deviation = dx * normal_x + dz * normal_z
                deviations.append(abs(deviation))
                
                # Record deviations at key points
                if abs(dist - corner.entry_distance) < 5:
                    entry_dev = abs(deviation)
                if abs(dist - corner.apex_distance) < 5:
                    apex_dev = abs(deviation)
                if abs(dist - corner.exit_distance) < 5:
                    exit_dev = abs(deviation)
        except Exception:
            continue
    
    avg_dev = np.mean(deviations) if deviations else 0.0
    
    return {
        'entry': entry_dev,
        'apex': apex_dev,
        'exit': exit_dev,
        'avg': avg_dev,
    }


if __name__ == "__main__":
    print("Corner detection module ready")
    print("Use detect_corners_advanced() with TelemetryData objects")