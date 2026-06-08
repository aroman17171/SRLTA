"""
Visualization Module
Professional telemetry visualization similar to MoTeC/RacePak style
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import numpy as np
from typing import List, Optional
from src.analysis.corner_detection import Corner

def plot_track_map(telemetry_data, corners=None):
    # Force ensure pos_x/pos_y exist by extracting from data if available
    if not telemetry_data.has_channel('pos_x') and 'pos_x' in telemetry_data.data.columns:
        # already there
        pass
    elif 'pos_x' in telemetry_data.data.columns:
        # good
        pass
    else:
        print("❌ Track map: pos_x/pos_y missing. Cannot draw.")
        return None
    
    x = telemetry_data.get_channel('pos_x')
    y = telemetry_data.get_channel('pos_y')
    
def plot_comprehensive_analysis(
    lap1_data,
    lap2_data,
    delta_distances,
    delta_times,
    corners: Optional[List[Corner]] = None,
    stats: Optional[dict] = None,
    show_channels: Optional[List[str]] = None
):
    """
    Create comprehensive telemetry comparison plot.
    
    Layout:
    - Speed comparison with corners marked
    - Delta time plot
    - Additional channels (throttle, brake, gear) if available
    - Statistics panel
    """
    # Determine which channels to show
    if show_channels is None:
        show_channels = ['speed']
        if lap1_data.has_channel('throttle'):
            show_channels.append('throttle')
        if lap1_data.has_channel('brake'):
            show_channels.append('brake')
    
    # Calculate number of subplots
    num_plots = len(show_channels) + 1  # +1 for delta
    has_stats = stats is not None
    
    # Create figure
    fig = plt.figure(figsize=(14, 3 * num_plots))
    
    if has_stats:
        # Use GridSpec to make room for stats
        gs = GridSpec(num_plots, 2, figure=fig, width_ratios=[3, 1], hspace=0.3)
        axes = [fig.add_subplot(gs[i, 0]) for i in range(num_plots)]
        stats_ax = fig.add_subplot(gs[:, 1])
    else:
        axes = fig.subplots(num_plots, 1)
        if num_plots == 1:
            axes = [axes]
    
    ax_idx = 0
    
    # Get data
    d1 = lap1_data.get_channel('distance')
    d2 = lap2_data.get_channel('distance')
    
    # --- SPEED COMPARISON ---
    ax = axes[ax_idx]
    ax_idx += 1
    
    s1 = lap1_data.get_channel('speed')
    s2 = lap2_data.get_channel('speed')
    
    ax.plot(d1, s1, label='Lap 1 (Reference)', color='#1f77b4', linewidth=2, alpha=0.8)
    ax.plot(d2, s2, label='Lap 2 (Compare)', color='#ff7f0e', linewidth=2, alpha=0.8)
    
    # Mark corners
    if corners:
        for corner in corners:
            ax.axvspan(
                corner.entry_distance,
                corner.exit_distance,
                alpha=0.1,
                color='red',
                label='Corner' if corner == corners[0] else ''
            )
            ax.axvline(corner.apex_distance, color='red', linestyle='--', alpha=0.3)
    
    ax.set_ylabel('Speed (km/h)', fontsize=11)
    ax.set_title('Speed Comparison', fontsize=12, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # --- DELTA TIME ---
    ax = axes[ax_idx]
    ax_idx += 1
    
    # Color the delta based on sign
    positive_delta = np.where(delta_times >= 0, delta_times, np.nan)
    negative_delta = np.where(delta_times < 0, delta_times, np.nan)
    
    ax.fill_between(delta_distances, 0, positive_delta, color='red', alpha=0.3, label='Lap 2 slower')
    ax.fill_between(delta_distances, 0, negative_delta, color='green', alpha=0.3, label='Lap 2 faster')
    ax.plot(delta_distances, delta_times, color='black', linewidth=1.5)
    ax.axhline(0, color='black', linewidth=1, linestyle='-')
    
    ax.set_ylabel('Delta Time (s)', fontsize=11)
    ax.set_title('Time Delta (Positive = Lap 2 Slower)', fontsize=12, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # Mark corners on delta
    if corners:
        for corner in corners:
            ax.axvline(corner.apex_distance, color='red', linestyle='--', alpha=0.2)
    
    # --- ADDITIONAL CHANNELS ---
    if 'throttle' in show_channels:
        ax = axes[ax_idx]
        ax_idx += 1
        
        t1 = lap1_data.get_channel('throttle')
        t2 = lap2_data.get_channel('throttle')
        
        ax.plot(d1, t1 * 100, label='Lap 1', color='#1f77b4', linewidth=1.5, alpha=0.7)
        ax.plot(d2, t2 * 100, label='Lap 2', color='#ff7f0e', linewidth=1.5, alpha=0.7)
        ax.set_ylabel('Throttle (%)', fontsize=11)
        ax.set_ylim(-5, 105)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    if 'brake' in show_channels:
        ax = axes[ax_idx]
        ax_idx += 1
        
        b1 = lap1_data.get_channel('brake')
        b2 = lap2_data.get_channel('brake')
        
        ax.plot(d1, b1 * 100, label='Lap 1', color='#1f77b4', linewidth=1.5, alpha=0.7)
        ax.plot(d2, b2 * 100, label='Lap 2', color='#ff7f0e', linewidth=1.5, alpha=0.7)
        ax.set_ylabel('Brake (%)', fontsize=11)
        ax.set_ylim(-5, 105)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    # Set x-label on bottom plot
    axes[-1].set_xlabel('Distance (m)', fontsize=11)
    
    # --- STATISTICS PANEL ---
    if has_stats and stats:
        stats_ax.axis('off')
        
        # Title
        stats_ax.text(0.5, 0.95, 'Analysis Summary', 
                     ha='center', va='top', fontsize=12, fontweight='bold',
                     transform=stats_ax.transAxes)
        
        # Overall delta
        total = stats['total_delta']
        color = 'green' if total < 0 else 'red'
        status = 'FASTER' if total < 0 else 'SLOWER'
        
        stats_ax.text(0.5, 0.85, f"Lap 2: {abs(total):.3f}s {status}",
                     ha='center', va='top', fontsize=11, color=color,
                     fontweight='bold', transform=stats_ax.transAxes)
        
        # Sector times
        y_pos = 0.70
        stats_ax.text(0.1, y_pos, 'Sector Deltas:', 
                     ha='left', va='top', fontsize=10, fontweight='bold',
                     transform=stats_ax.transAxes)
        y_pos -= 0.08
        
        for sector, delta in stats['sector_deltas'].items():
            color = 'green' if delta < 0 else 'red'
            marker = '▲' if delta < 0 else '▼'
            stats_ax.text(0.15, y_pos, f"{sector}: {delta:+.3f}s {marker}",
                         ha='left', va='top', fontsize=9, color=color,
                         transform=stats_ax.transAxes)
            y_pos -= 0.06
        
        # Max gain/loss
        y_pos -= 0.04
        stats_ax.text(0.1, y_pos, 'Biggest Changes:',
                     ha='left', va='top', fontsize=10, fontweight='bold',
                     transform=stats_ax.transAxes)
        y_pos -= 0.08
        
        stats_ax.text(0.15, y_pos, f"Max gain: {abs(stats['max_gain']):.3f}s",
                     ha='left', va='top', fontsize=9, color='green',
                     transform=stats_ax.transAxes)
        y_pos -= 0.06
        
        stats_ax.text(0.15, y_pos, f"  @ {stats['max_gain_distance']:.0f}m",
                     ha='left', va='top', fontsize=8, style='italic',
                     transform=stats_ax.transAxes)
        y_pos -= 0.08
        
        stats_ax.text(0.15, y_pos, f"Max loss: {abs(stats['max_loss']):.3f}s",
                     ha='left', va='top', fontsize=9, color='red',
                     transform=stats_ax.transAxes)
        y_pos -= 0.06
        
        stats_ax.text(0.15, y_pos, f"  @ {stats['max_loss_distance']:.0f}m",
                     ha='left', va='top', fontsize=8, style='italic',
                     transform=stats_ax.transAxes)
        
        # Add subtle border
        rect = mpatches.Rectangle((0, 0), 1, 1, 
                                 linewidth=1, edgecolor='gray', 
                                 facecolor='none', transform=stats_ax.transAxes)
        stats_ax.add_patch(rect)
    
    plt.tight_layout()
    return fig


def plot_corner_analysis(lap1_data, lap2_data, corners: List[Corner], corner_analysis: List[dict]):
    """
    Create focused corner-by-corner analysis plot.
    Shows speed traces for each corner with performance metrics.
    """
    n_corners = len(corners)
    if n_corners == 0:
        print("No corners to analyze")
        return
    
    # Create subplot grid
    cols = min(3, n_corners)
    rows = (n_corners + cols - 1) // cols
    
    fig, axes = plt.subplots(rows, cols, figsize=(5*cols, 4*rows))
    if n_corners == 1:
        axes = np.array([axes])
    axes = axes.flatten()
    
    d1 = lap1_data.get_channel('distance')
    s1 = lap1_data.get_channel('speed')
    d2 = lap2_data.get_channel('distance')
    s2 = lap2_data.get_channel('speed')
    
    for i, (corner, analysis) in enumerate(zip(corners, corner_analysis)):
        ax = axes[i]
        
        # Get corner window
        margin = 50  # meters before/after corner
        window_start = max(0, corner.entry_distance - margin)
        window_end = corner.exit_distance + margin
        
        # Filter data to window
        mask1 = (d1 >= window_start) & (d1 <= window_end)
        mask2 = (d2 >= window_start) & (d2 <= window_end)
        
        ax.plot(d1[mask1], s1[mask1], label='Lap 1', color='#1f77b4', linewidth=2)
        ax.plot(d2[mask2], s2[mask2], label='Lap 2', color='#ff7f0e', linewidth=2)
        
        # Mark corner phases
        ax.axvline(corner.entry_distance, color='red', linestyle='--', alpha=0.5, label='Entry')
        ax.axvline(corner.apex_distance, color='darkred', linestyle='-', alpha=0.5, label='Apex')
        ax.axvline(corner.exit_distance, color='red', linestyle='--', alpha=0.5, label='Exit')
        
        # Performance indicator
        perf = analysis['performance']
        perf_text = {
            'better_apex': '✓ Better apex speed',
            'better_exit': '✓ Better exit speed',
            'better_braking': '✓ Better braking',
            'similar': '≈ Similar'
        }
        
        color = 'green' if perf != 'similar' else 'gray'
        ax.text(0.5, 0.95, perf_text.get(perf, perf),
               transform=ax.transAxes, ha='center', va='top',
               fontsize=9, color=color, fontweight='bold',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        ax.set_title(f"Corner {i+1} ({corner.corner_type})", fontweight='bold')
        ax.set_xlabel('Distance (m)')
        ax.set_ylabel('Speed (km/h)')
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(True, alpha=0.3)
    
    # Hide unused subplots
    for i in range(n_corners, len(axes)):
        axes[i].set_visible(False)
    
    plt.tight_layout()
    return fig


def plot_track_map(telemetry_data, corners: Optional[List[Corner]] = None):
    """
    Plot 2D track map if position data available.
    Requires x, y position channels.
    """
    if not (telemetry_data.has_channel('pos_x') and telemetry_data.has_channel('pos_y')):
        print("Position data not available for track map")
        return None
    
    x = telemetry_data.get_channel('pos_x')
    y = telemetry_data.get_channel('pos_y')
    speed = telemetry_data.get_channel('speed')
    
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Color-code by speed
    scatter = ax.scatter(x, y, c=speed, cmap='RdYlGn', s=5, alpha=0.6)
    plt.colorbar(scatter, ax=ax, label='Speed (km/h)')
    
    # Mark corners
    if corners:
        d = telemetry_data.get_channel('distance')
        for corner in corners:
            idx = np.argmin(np.abs(d - corner.apex_distance))
            ax.plot(x[idx], y[idx], 'r*', markersize=15, markeredgecolor='black')
    
    ax.set_xlabel('X Position (m)')
    ax.set_ylabel('Y Position (m)')
    ax.set_title('Track Map (Color = Speed)', fontweight='bold')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    return fig


def save_plots(figures: dict, output_dir: str = "output"):
    """
    Save multiple figures to files.
    
    Args:
        figures: Dict of {filename: figure}
        output_dir: Output directory
    """
    from pathlib import Path
    
    Path(output_dir).mkdir(exist_ok=True)
    
    for filename, fig in figures.items():
        filepath = Path(output_dir) / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f"Saved: {filepath}")


if __name__ == "__main__":
    print("Visualization module ready")
    print("Use plot_comprehensive_analysis() to create telemetry plots")