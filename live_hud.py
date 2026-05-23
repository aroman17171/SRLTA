"""
SRLTA Real-Time HUD Overlay
Displays live delta and coaching while you drive in AC

REQUIREMENTS:
- pip install pyacsm pygame

USAGE:
1. Record a reference lap first (using ac_live_recorder.py)
2. Load it: python live_hud.py data/recorded_laps/lap_1_reference.csv
3. Drive in AC - HUD shows live delta!
"""

import pygame
import sys
import time
import numpy as np
from pathlib import Path

try:
    import pyacsm
    AC_AVAILABLE = True
except ImportError:
    AC_AVAILABLE = False
    print("ERROR: pyacsm not installed")
    print("Install: pip install pyacsm")

from src.telemetry_loader import TelemetryLoader
from src.corner_detection import detect_corners_advanced
from src.live_telemetry import LiveDeltaCalculator, LiveCoachingSystem


class LiveHUD:
    """Real-time HUD overlay for AC"""
    
    def __init__(self, reference_lap_path: str, width: int = 400, height: int = 300):
        """
        Initialize HUD.
        
        Args:
            reference_lap_path: Path to reference lap CSV
            width: HUD window width
            height: HUD window height
        """
        # Load reference lap
        print(f"📊 Loading reference lap: {reference_lap_path}")
        self.ref_lap = TelemetryLoader.load(reference_lap_path)
        print(f"✓ Loaded: {self.ref_lap}")
        
        # Detect corners in reference lap
        print("🏁 Detecting corners...")
        self.corners = detect_corners_advanced(self.ref_lap)
        print(f"✓ Found {len(self.corners)} corners")
        
        # Initialize coaching system
        self.coaching = LiveCoachingSystem(self.ref_lap, self.corners)
        
        # Initialize pygame
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SRLTA Live Delta")
        
        # Fonts
        self.font_large = pygame.font.Font(None, 72)
        self.font_medium = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 32)
        self.font_tiny = pygame.font.Font(None, 24)
        
        # Colors
        self.COLOR_BG = (20, 20, 30)
        self.COLOR_FASTER = (50, 255, 50)
        self.COLOR_SLOWER = (255, 50, 50)
        self.COLOR_NEUTRAL = (200, 200, 200)
        self.COLOR_TEXT = (255, 255, 255)
        self.COLOR_CORNER = (255, 200, 0)
        
        # State
        self.current_delta = 0
        self.current_distance = 0
        self.current_speed = 0
        self.current_gear = 1
        self.lap_time = 0
        self.coaching_message = ""
        self.message_time = 0
        
        # FPS
        self.clock = pygame.time.Clock()
        self.target_fps = 60
        
        # Track connection
        self.connected = False
        self.last_read_time = 0
        
    def connect_to_ac(self) -> bool:
        """Test AC connection"""
        if not AC_AVAILABLE:
            return False
        
        try:
            physics = pyacsm.read_physics()
            graphics = pyacsm.read_graphics()
            self.connected = True
            return True
        except:
            self.connected = False
            return False
    
    def read_ac_telemetry(self) -> dict:
        """Read current telemetry from AC"""
        try:
            physics = pyacsm.read_physics()
            graphics = pyacsm.read_graphics()
            static = pyacsm.read_static()
            
            distance = graphics.normalized_car_position * static.track_length
            
            return {
                'distance': distance,
                'speed': physics.speed_kmh,
                'throttle': physics.gas,
                'brake': physics.brake,
                'gear': physics.gear,
                'time': graphics.i_current_time / 1000.0,
                'lap_count': graphics.completed_laps,
            }
        except Exception as e:
            print(f"Error reading AC: {e}")
            self.connected = False
            return None
    
    def update_telemetry(self):
        """Update telemetry and delta"""
        data = self.read_ac_telemetry()
        
        if data is None:
            return
        
        self.current_distance = data['distance']
        self.current_speed = data['speed']
        self.current_gear = data['gear']
        self.lap_time = data['time']
        
        # Update coaching system
        message = self.coaching.update(
            data['distance'],
            data['speed'],
            data['time'],
            data.get('brake', 0)
        )
        
        if message:
            self.coaching_message = message
            self.message_time = time.time()
        
        # Get delta
        self.current_delta = self.coaching.delta_calc.update(
            data['distance'],
            data['speed'],
            data['time']
        )
    
    def draw_delta_display(self):
        """Draw main delta display"""
        y_pos = 20
        
        # Delta value
        if self.current_delta is not None:
            delta_abs = abs(self.current_delta)
            
            # Choose color
            if delta_abs < 0.05:
                color = self.COLOR_NEUTRAL
                status = ""
            elif self.current_delta < 0:
                color = self.COLOR_FASTER
                status = "↑"
            else:
                color = self.COLOR_SLOWER
                status = "↓"
            
            # Draw delta
            delta_text = f"{status} {delta_abs:.2f}s"
            text_surface = self.font_large.render(delta_text, True, color)
            text_rect = text_surface.get_rect(center=(self.width // 2, y_pos + 40))
            self.screen.blit(text_surface, text_rect)
            
            # Draw "DELTA" label
            label = self.font_small.render("DELTA", True, self.COLOR_TEXT)
            label_rect = label.get_rect(center=(self.width // 2, y_pos))
            self.screen.blit(label, label_rect)
        else:
            # Not enough data yet
            text = self.font_medium.render("Waiting...", True, self.COLOR_NEUTRAL)
            text_rect = text.get_rect(center=(self.width // 2, y_pos + 40))
            self.screen.blit(text, text_rect)
    
    def draw_info_bar(self):
        """Draw info bar with speed, gear, distance"""
        y_pos = self.height - 80
        
        # Speed
        speed_text = f"{self.current_speed:.0f} km/h"
        speed_surf = self.font_medium.render(speed_text, True, self.COLOR_TEXT)
        self.screen.blit(speed_surf, (20, y_pos))
        
        # Gear
        gear_text = f"G{self.current_gear}"
        gear_surf = self.font_medium.render(gear_text, True, self.COLOR_TEXT)
        self.screen.blit(gear_surf, (self.width - 100, y_pos))
        
        # Distance
        dist_text = f"{self.current_distance:.0f}m"
        dist_surf = self.font_small.render(dist_text, True, self.COLOR_NEUTRAL)
        dist_rect = dist_surf.get_rect(center=(self.width // 2, y_pos + 40))
        self.screen.blit(dist_surf, dist_rect)
    
    def draw_coaching_message(self):
        """Draw coaching message"""
        # Only show message for 5 seconds
        if time.time() - self.message_time > 5:
            return
        
        if not self.coaching_message:
            return
        
        y_pos = 140
        
        # Background box
        padding = 10
        msg_surf = self.font_small.render(self.coaching_message, True, self.COLOR_TEXT)
        box_width = msg_surf.get_width() + padding * 2
        box_height = msg_surf.get_height() + padding * 2
        
        box_rect = pygame.Rect(
            (self.width - box_width) // 2,
            y_pos,
            box_width,
            box_height
        )
        
        pygame.draw.rect(self.screen, (40, 40, 50), box_rect)
        pygame.draw.rect(self.screen, self.COLOR_CORNER, box_rect, 2)
        
        # Message text
        text_rect = msg_surf.get_rect(center=(self.width // 2, y_pos + box_height // 2))
        self.screen.blit(msg_surf, text_rect)
    
    def draw_connection_status(self):
        """Draw AC connection status"""
        if self.connected:
            color = self.COLOR_FASTER
            text = "LIVE"
        else:
            color = self.COLOR_SLOWER
            text = "DISCONNECTED"
        
        status_surf = self.font_tiny.render(text, True, color)
        self.screen.blit(status_surf, (10, 10))
    
    def draw(self):
        """Draw complete HUD"""
        # Clear screen
        self.screen.fill(self.COLOR_BG)
        
        # Draw components
        self.draw_connection_status()
        self.draw_delta_display()
        self.draw_coaching_message()
        self.draw_info_bar()
        
        # Update display
        pygame.display.flip()
    
    def run(self):
        """Main loop"""
        print("\n🎮 Starting Live HUD...")
        print("=" * 60)
        
        # Try to connect
        if not self.connect_to_ac():
            print("⚠️  AC not detected. Start AC and drive on track!")
            print("HUD will connect automatically when AC is running.")
        else:
            print("✓ Connected to AC!")
        
        print("\nHUD Controls:")
        print("  - ESC or Q: Quit")
        print("  - R: Reset delta")
        print("=" * 60)
        
        running = True
        last_update = time.time()
        update_interval = 0.1  # Update telemetry 10x per second
        
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_r:
                        # Reset delta
                        self.coaching.reset()
                        print("Delta reset")
            
            # Update telemetry at fixed rate
            current_time = time.time()
            if current_time - last_update >= update_interval:
                # Try to connect if not connected
                if not self.connected:
                    self.connect_to_ac()
                
                # Update telemetry
                if self.connected:
                    self.update_telemetry()
                
                last_update = current_time
            
            # Draw HUD
            self.draw()
            
            # Maintain FPS
            self.clock.tick(self.target_fps)
        
        pygame.quit()
        print("\n✓ HUD closed")


def main():
    """Entry point"""
    print("=" * 60)
    print("SRLTA LIVE HUD - Real-Time Delta Display")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\nUsage: python live_hud.py <reference_lap.csv>")
        print("\nExample:")
        print("  python live_hud.py data/recorded_laps/lap_1_monza.csv")
        print("\nFirst record a reference lap with:")
        print("  python ac_live_recorder.py")
        sys.exit(1)
    
    reference_lap = sys.argv[1]
    
    if not Path(reference_lap).exists():
        print(f"\n❌ Error: File not found: {reference_lap}")
        sys.exit(1)
    
    # Create and run HUD
    hud = LiveHUD(reference_lap)
    hud.run()


if __name__ == "__main__":
    main()