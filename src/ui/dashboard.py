"""
SRLTA Dashboard - Main GUI Application
"""

import customtkinter as ctk
import threading
import time
from pathlib import Path
import sys
import os
import numpy as np
import tkinter as tk
import json
from PIL import Image, ImageTk

# Fix imports when running as exe
if getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(sys.executable))

from src.telemetry.recorder import ACTelemetryStream
from src.telemetry.loader import TelemetryLoader
from src.analysis.delta import (
    calculate_time_delta,
    calculate_delta_statistics,
    find_significant_delta_zones,
    generate_coaching_message
)
from src.voice.speaker import Speaker
from src.voice import settings as voice_settings

# Theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT       = "#E8433A"
ACCENT_GREEN = "#2ECC71"
BG_DARK      = "#0F0F0F"
BG_CARD      = "#1A1A1A"
BG_PANEL     = "#141414"
TEXT_PRIMARY = "#FFFFFF"
TEXT_MUTED   = "#888888"
TEXT_GREEN   = "#2ECC71"
TEXT_RED     = "#E8433A"
TEXT_YELLOW  = "#F1C40F"
FONT_MONO    = ("Consolas", 14)


def _data_dir() -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(".")
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_dir(track: str, car: str, date_str: str = None) -> Path:
    """Returns the directory for storing laps for a given (track, car, date).

    Layout: data/sessions/<track>/<car>/<YYYY-MM-DD>/

    Created on demand. Sanitizes track/car so they're filesystem-safe.
    """
    if not date_str:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
    def _safe(s):
        return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (s or "unknown")).strip("_") or "unknown"
    d = _data_dir() / "sessions" / _safe(track) / _safe(car) / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_stamp() -> str:
    """Returns HH-MM-SS timestamp string for filenames."""
    from datetime import datetime
    return datetime.now().strftime("%H-%M-%S")



class Card(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=10, **kwargs)


class HomeScreen(ctk.CTkFrame):
    def __init__(self, parent, on_live, on_analysis, on_settings):
        super().__init__(parent, fg_color=BG_DARK)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4), weight=1)
        self._cursor_visible = True
        self._after_id = None

        self.title_label = ctk.CTkLabel(
            self, text="SRLTA_",
            font=("Consolas", 64, "bold"),
            text_color=ACCENT
        )
        self.title_label.grid(row=0, column=0, pady=(60, 0))
        self._blink_cursor()

        ctk.CTkLabel(
            self, text="Sim Racing Lap Time Analyzer",
            font=("Consolas", 18),
            text_color=TEXT_MUTED
        ).grid(row=1, column=0, pady=(0, 40))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=20)

        self._btn_live = ctk.CTkButton(
            btn_frame, text="▶  LIVE MODE",
            font=("Consolas", 20, "bold"),
            fg_color=ACCENT, hover_color="#C0392B",
            width=280, height=70, corner_radius=8,
            command=on_live
        )
        self._btn_live.pack(pady=10)
        self._bind_hover_glow(self._btn_live)

        ctk.CTkButton(
            btn_frame, text="◈  ANALYSIS MODE",
            font=("Consolas", 20, "bold"),
            fg_color="#2C2C2C", hover_color="#3C3C3C",
            border_color=ACCENT, border_width=2,
            width=280, height=70, corner_radius=8,
            command=on_analysis
        ).pack(pady=10)

        ctk.CTkButton(
            btn_frame, text="⚙  SETTINGS",
            font=("Consolas", 16),
            fg_color="transparent", hover_color="#2C2C2C",
            border_color="#444444", border_width=1,
            width=280, height=44, corner_radius=8,
            command=on_settings
        ).pack(pady=6)

        ctk.CTkLabel(
            self, text="Make sure Assetto Corsa is running before starting Live Mode",
            font=("Consolas", 12),
            text_color=TEXT_MUTED
        ).grid(row=3, column=0, pady=(20, 0))

        ctk.CTkLabel(
            self, text="v1.0  //  SRLTA",
            font=("Consolas", 10),
            text_color="#333333"
        ).grid(row=4, column=0, pady=(0, 16))

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        text = "SRLTA_" if self._cursor_visible else "SRLTA "
        try:
            self.title_label.configure(text=text)
            self._after_id = self.after(530, self._blink_cursor)
        except Exception:
            pass

    def _bind_hover_glow(self, btn):
        def on_enter(e):
            btn.configure(border_color="#FF6B6B", border_width=2)
        def on_leave(e):
            btn.configure(border_width=0)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def destroy(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        super().destroy()


class SettingsScreen(ctk.CTkFrame):
    MODES = ["sectors", "full", "corners", "off"]
    MODE_DESC = {
        "sectors": "Lap summary with sector deltas",
        "full":    "Sectors + corner-by-corner coaching",
        "corners": "Corner coaching only",
        "off":     "No voice coaching",
    }

    def __init__(self, parent, on_back):
        super().__init__(parent, fg_color=BG_DARK)
        self.on_back = on_back
        self._s = voice_settings.load()
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=50)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            top, text="← Back",
            font=("Consolas", 13),
            fg_color="transparent", hover_color="#2C2C2C",
            width=80, command=self.on_back
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(
            top, text="SETTINGS",
            font=("Consolas", 16, "bold"),
            text_color=ACCENT
        ).grid(row=0, column=1, pady=8)

        card = Card(self)
        card.grid(row=1, column=0, padx=60, pady=40, sticky="n")
        card.grid_columnconfigure(1, weight=1)

        row = 0

        ctk.CTkLabel(card, text="VOICE COACHING",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(24, 4), sticky="w")
        self._voice_var = ctk.BooleanVar(value=self._s["voice_enabled"])
        ctk.CTkSwitch(
            card, text="",
            variable=self._voice_var,
            onvalue=True, offvalue=False,
            progress_color=ACCENT,
        ).grid(row=row, column=1, padx=30, pady=(24, 4), sticky="e")
        row += 1

        ctk.CTkLabel(card, text="COACHING MODE",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(16, 4), sticky="w")
        self._mode_var = ctk.StringVar(value=self._s["mode"])
        ctk.CTkOptionMenu(
            card, values=self.MODES, variable=self._mode_var,
            fg_color=BG_DARK, button_color=ACCENT, button_hover_color="#C0392B",
            font=("Consolas", 13), command=self._on_mode_change
        ).grid(row=row, column=1, padx=30, pady=(16, 4), sticky="e")
        row += 1

        self._mode_desc = ctk.CTkLabel(
            card, text=self.MODE_DESC[self._s["mode"]],
            font=("Consolas", 11), text_color=TEXT_MUTED, wraplength=300
        )
        self._mode_desc.grid(row=row, column=0, columnspan=2,
                             padx=30, pady=(0, 8), sticky="w")
        row += 1

        ctk.CTkLabel(card, text="VOLUME",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(16, 4), sticky="w")
        self._vol_var = ctk.DoubleVar(value=self._s["volume"])
        self._vol_lbl = ctk.CTkLabel(card,
                                     text=f"{int(self._s['volume']*100)}%",
                                     font=("Consolas", 13), text_color=TEXT_PRIMARY)
        self._vol_lbl.grid(row=row, column=1, padx=30, pady=(16, 4), sticky="e")
        row += 1
        ctk.CTkSlider(
            card, from_=0, to=1, variable=self._vol_var,
            progress_color=ACCENT, button_color=ACCENT, button_hover_color="#C0392B",
            command=lambda v: self._vol_lbl.configure(text=f"{int(float(v)*100)}%")
        ).grid(row=row, column=0, columnspan=2, padx=30, pady=(0, 8), sticky="ew")
        row += 1

        ctk.CTkLabel(card, text="SPEECH RATE",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(16, 4), sticky="w")
        self._rate_var = ctk.IntVar(value=self._s["rate"])
        self._rate_lbl = ctk.CTkLabel(card,
                                      text=f"{self._s['rate']} wpm",
                                      font=("Consolas", 13), text_color=TEXT_PRIMARY)
        self._rate_lbl.grid(row=row, column=1, padx=30, pady=(16, 4), sticky="e")
        row += 1
        ctk.CTkSlider(
            card, from_=100, to=300, variable=self._rate_var,
            progress_color=ACCENT, button_color=ACCENT, button_hover_color="#C0392B",
            command=lambda v: self._rate_lbl.configure(text=f"{int(float(v))} wpm")
        ).grid(row=row, column=0, columnspan=2, padx=30, pady=(0, 16), sticky="ew")
        row += 1

        ctk.CTkFrame(card, height=1, fg_color="#333333"
                     ).grid(row=row, column=0, columnspan=2,
                            padx=20, pady=8, sticky="ew")
        row += 1

        ctk.CTkLabel(card, text="COMPARE AGAINST",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(16, 4), sticky="w")
        self._compare_var = ctk.StringVar(value=self._s.get("compare_mode", "best"))
        ctk.CTkOptionMenu(
            card, values=["best", "previous"], variable=self._compare_var,
            fg_color=BG_DARK, button_color=ACCENT, button_hover_color="#C0392B",
            font=("Consolas", 13)
        ).grid(row=row, column=1, padx=30, pady=(16, 4), sticky="e")
        row += 1
        self._compare_desc = ctk.CTkLabel(
            card, text="Compares each new lap against the best or previous lap",
            font=("Consolas", 11), text_color=TEXT_MUTED, wraplength=300
        )
        self._compare_desc.grid(row=row, column=0, columnspan=2,
                                padx=30, pady=(0, 8), sticky="w")
        row += 1

        ctk.CTkFrame(card, height=1, fg_color="#333333"
                     ).grid(row=row, column=0, columnspan=2,
                            padx=20, pady=8, sticky="ew")
        row += 1

        # Voice picker (lists every installed TTS voice)
        from src.voice.speaker import list_voices
        self._voices = list_voices()
        ctk.CTkLabel(card, text="VOICE",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=row, column=0, padx=30, pady=(16, 4), sticky="w")
        voice_labels = [f"{v['name']} ({v['id']})" for v in self._voices] or ["Default"]
        # Try to keep the currently-saved selection visible
        cur_voice_id = self._s.get("voice_id", "pyttsx3:0")
        cur_label = next((f"{v['name']} ({v['id']})" for v in self._voices if v['id'] == cur_voice_id), voice_labels[0])
        self._voice_choice = ctk.StringVar(value=cur_label)
        ctk.CTkOptionMenu(
            card,
            values=voice_labels,
            variable=self._voice_choice,
            fg_color=BG_DARK, button_color=ACCENT, button_hover_color="#C0392B",
            font=("Consolas", 12), command=self._on_voice_change
        ).grid(row=row, column=1, padx=30, pady=(16, 4), sticky="e")
        row += 1

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=row, column=0, columnspan=2, padx=30, pady=(8, 24))

        ctk.CTkButton(
            btn_row, text="SAVE", font=("Consolas", 14, "bold"),
            fg_color=ACCENT, hover_color="#C0392B",
            width=140, height=40, corner_radius=8, command=self._save
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="TEST VOICE", font=("Consolas", 14),
            fg_color=BG_DARK, hover_color="#2C2C2C",
            border_color="#444444", border_width=1,
            width=140, height=40, corner_radius=8, command=self._test_voice
        ).pack(side="left", padx=8)

        self._status = ctk.CTkLabel(card, text="",
                                    font=("Consolas", 12), text_color=TEXT_GREEN)
        self._status.grid(row=row+1, column=0, columnspan=2, pady=(0, 8))

    def _on_mode_change(self, value):
        self._mode_desc.configure(text=self.MODE_DESC.get(value, ""))

    def _on_voice_change(self, value):
        # Live preview with the selected voice (no save yet)
        # value is like "Microsoft David Desktop (win:0)"
        selected_voice = next((v for v in self._voices if f"{v['name']} ({v['id']})" == value), None)
        if selected_voice:
            def _preview():
                eng = __import__("pyttsx3").init()
                eng.setProperty("rate", self._rate_var.get())
                eng.setProperty("volume", self._vol_var.get())
                try:
                    voices = eng.getProperty("voices") or []
                    if selected_voice["backend"] == "pyttsx3":
                        idx = selected_voice["index"]
                        if 0 <= idx < len(voices):
                            eng.setProperty("voice", voices[idx].id)
                    elif selected_voice["backend"] == "win32":
                        # Try to match by name
                        target_name = selected_voice["name"]
                        for v in voices:
                            if v.name and target_name.lower() in v.name.lower():
                                eng.setProperty("voice", v.id)
                                break
                except Exception:
                    pass
                eng.say(f"Voice {selected_voice['name']} selected.")
                eng.runAndWait()
                eng.stop()
            threading.Thread(target=_preview, daemon=True).start()

    def _save(self):
        # Find the selected voice object (format: "Name (id)" but the id
        # part is the full raw_id, e.g. "edge:en-US-AvaNeural" or "pyttsx3:0")
        selected_label = self._voice_choice.get()
        new_voice_id = "pyttsx3:0"   # pyttsx3 fallback index
        new_voice_name = "en-US-AndrewNeural"  # edge-tts voice short name
        new_backend = "edge"
        for v in self._voices:
            if f"{v['name']} ({v['id']})" == selected_label:
                # Split raw_id like "edge:en-US-AvaNeural" into backend + name
                raw = str(v.get("raw_id", ""))
                backend = v.get("backend", "edge")
                if backend == "edge":
                    new_voice_name = raw if raw else v["id"].split(":", 1)[-1]
                    new_backend = "edge"
                    new_voice_id = 0  # unused when edge is selected
                else:
                    # pyttsx3 — raw_id is the SAPI voice id, store the
                    # index so the offline fallback can find it.
                    try:
                        new_voice_id = int(v["id"].split(":", 1)[1])
                    except Exception:
                        new_voice_id = 0
                    new_backend = "pyttsx3"
                break
        voice_settings.save({
            "voice_enabled": self._voice_var.get(),
            "mode":          self._mode_var.get(),
            "compare_mode":  self._compare_var.get(),
            "volume":        round(self._vol_var.get(), 2),
            "rate":          int(self._rate_var.get()),
            "voice_id":      new_voice_id,
            "voice_name":    new_voice_name,
            "backend":       new_backend,
        })
        # Also update the running Speaker in the live screen so the change
        # takes effect immediately (not just on next app launch).
        try:
            live_sp = Speaker()
            live_sp.mode = self._mode_var.get()
            live_sp.compare_mode = self._compare_var.get()
            live_sp.voice_id = new_voice_id
            live_sp.voice_name = new_voice_name
            live_sp.backend = new_backend
            live_sp._save()
        except Exception:
            pass
        self._status.configure(text=f"✓ Saved: {new_voice_name}", text_color=TEXT_GREEN)
        self.after(2000, lambda: self._status.configure(text=""))


    def _test_voice(self):
        self._status.configure(text="Speaking…", text_color=TEXT_YELLOW)
        def _speak():
            spk = Speaker()
            spk.say("Voice coaching active. Ready to race.")
            self.after(0, lambda: self._status.configure(text=""))
        threading.Thread(target=_speak, daemon=True).start()



# Live screen with per-car/track categorization + clear-laps button
class LiveScreen(ctk.CTkFrame):
    def __init__(self, parent, on_back):
        super().__init__(parent, fg_color=BG_DARK)
        self.on_back = on_back
        self.stream = None
        self.speaker = Speaker()
        self.coach = None
        self.lap_number = 1
        self.car = "unknown_car"
        self.track = "unknown_track"
        self.session_date = ""           # YYYY-MM-DD for current session folder
        self.session_dir = None          # Path to today's folder
        self.best_lap_path = ""          # path to best.csv inside session_dir
        self.best_lap_data = None
        self.best_lap_corners = []
        self.best_lap_time = None        # float seconds, for "is this faster?" check
        self.stream_thread = None
        self._pulse_after = None
        self._pulse_state = 0
        # Cache last-rendered UI values so we only re-configure labels when
        # they actually change (cuts a ton of wasted Tk work at 20Hz).
        self._last_speed = -1
        self._last_gear  = -1
        self._last_lap_time = -1
        self._last_lap_num  = -1
        # Track previous lap for previous-lap comparison
        self._prev_lap_data = None
        self._prev_lap_time = None
        self._prev_lap_corners = []
        # Live track point collection (Bug 2)
        self._live_track_points = []
        self._live_point_counter = 0
        # Cached transform for car marker (Bug 3)
        self._map_transform = None
        self._build_ui()
    def load_track_map(self):
        """Loads the static track map and its corner data for the current track."""
        # Build the expected paths from the track name
        map_path = os.path.join("data", "track_maps", f"{self.track}.png")
        corners_path = os.path.join("data", "track_maps", "corners", f"{self.track}_corners.json")
        
        if not os.path.exists(map_path):
            # Try to find and copy it from your AC installation if it's missing.
            self.discover_track_map()
            map_path = os.path.join("data", "track_maps", f"{self.track}.png")
            if not os.path.exists(map_path):
                self.log("No track map found.")
                return

        # Load the image and corner data if both exist.
        if os.path.exists(map_path):
            pil_img = Image.open(map_path)
            self.track_image = ImageTk.PhotoImage(pil_img)
            # Display the image on the canvas.
            if hasattr(self, 'track_map_canvas'):
                self.track_map_canvas.create_image(0, 0, anchor="nw", image=self.track_image)
            
            if os.path.exists(corners_path):
                with open(corners_path, "r") as f:
                    self.track_corners = json.load(f)
                self.draw_corner_numbers()
    def detect_corners(self, telemetry_data):
        """Detect corners from a lap's telemetry data and map them to image coordinates."""
        # Get position data from the completed lap
        pos_x = telemetry_data.get_channel('pos_x')
        pos_z = telemetry_data.get_channel('pos_z')
        speed = telemetry_data.get_channel('speed')
        
        # --- 1. Algorithm to find corner apexes (points of minimum speed) ---
        corners = []
        in_corner = False
        min_speed_idx = 0
        for i in range(len(speed)):
            if not in_corner and speed[i] < 100:  # You can tune the threshold.
                in_corner = True
                min_speed_idx = i
            if in_corner and speed[i] > 100:
                # Found the apex, record its position.
                corners.append((pos_x[min_speed_idx], pos_z[min_speed_idx]))
                in_corner = False
        # --- 1. End of algorithm ---
        
        # --- 2. Map corner positions from world coordinates to image coordinates ---
        # Get the bounds of the track from the loaded lap data.
        x_min, x_max = pos_x.min(), pos_x.max()
        z_min, z_max = pos_z.min(), pos_z.max()
        
        # Get the bounds of the track map image.
        map_width, map_height = self.track_image.width(), self.track_image.height()
        
        self.track_corners = []
        for i, (corner_x, corner_z) in enumerate(corners):
            # Normalize the coordinates to the image's dimensions.
            img_x = (corner_x - x_min) / (x_max - x_min) * map_width
            img_y = (corner_z - z_min) / (z_max - z_min) * map_height
            self.track_corners.append({"x": img_x, "y": img_y, "number": i+1})
        
        # Save the corner data to a JSON file for future use.
        corners_path = os.path.join("data", "track_maps", "corners", f"{self.track}_corners.json")
        os.makedirs(os.path.dirname(corners_path), exist_ok=True)
        with open(corners_path, "w") as f:
            json.dump(self.track_corners, f)



    def _build_ui(self):
        # NOTE: row 0 = top bar (back/title/clear), row 1 = session label,
        # row 2 = main content (telemetry/logs), row 3 = bottom nav bar (srlta app-level).
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=50)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 0))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            top, text="← Back", font=("Consolas", 13),
            fg_color="transparent", hover_color="#2C2C2C",
            width=80, command=self._stop_and_back
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(
            top, text="LIVE MODE", font=("Consolas", 16, "bold"), text_color=ACCENT
        ).grid(row=0, column=1, pady=8)

        self.status_label = ctk.CTkLabel(
            top, text="● WAITING", font=("Consolas", 13), text_color=TEXT_YELLOW
        )
        self.status_label.grid(row=0, column=2, padx=20, pady=8, sticky="e")

        self._btn_clear = ctk.CTkButton(
            top, text="CLEAR TODAY", font=("Consolas", 11),
            fg_color="transparent", hover_color="#2C2C2C",
            border_color="#444444", border_width=1,
            width=110, height=28, corner_radius=6, command=self._clear_laps
        )
        self._btn_clear.grid(row=0, column=3, padx=(0, 14), pady=8, sticky="e")

        self.session_label = ctk.CTkLabel(
            self, text="Session: unknown_car @ unknown_track",
            font=("Consolas", 12), text_color=TEXT_MUTED
        )
        self.session_label.grid(row=1, column=0, columnspan=2, pady=(8, 0))

        # Left panel
        left = Card(self)
        left.grid(row=2, column=0, padx=(16, 8), pady=16, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="TELEMETRY", font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(16, 4))
        self.delta_label = ctk.CTkLabel(
            left, text="--.-s", font=("Consolas", 72, "bold"), text_color=TEXT_MUTED
        )
        self.delta_label.grid(row=1, column=0, pady=(8, 0))
        ctk.CTkLabel(left, text="DELTA VS BEST", font=("Consolas", 11), text_color=TEXT_MUTED
                     ).grid(row=2, column=0, pady=(0, 20))

        stats_frame = ctk.CTkFrame(left, fg_color="transparent")
        stats_frame.grid(row=3, column=0, pady=8, padx=20, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.speed_label = self._stat_widget(stats_frame, "SPEED", "0", "kmh", 0)
        self.gear_label  = self._stat_widget(stats_frame, "GEAR",  "1", "",     1)
        self.time_label  = self._stat_widget(stats_frame, "LAP",   "0.0", "s",  2)

        ctk.CTkLabel(left, text="LAST LAP SECTORS", font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=4, column=0, pady=(24, 4))
        self.sector_labels = []
        for i in range(3):
            lbl = ctk.CTkLabel(left, text=f"S{i+1}  --.-s", font=FONT_MONO, text_color=TEXT_MUTED)
            lbl.grid(row=5+i, column=0, pady=2)
            self.sector_labels.append(lbl)
        self.lap_count_label = ctk.CTkLabel(left, text="LAP 0", font=("Consolas", 13), text_color=TEXT_MUTED)
        self.lap_count_label.grid(row=8, column=0, pady=(20, 16))

        # Right panel
        right = Card(self)
        right.grid(row=2, column=1, padx=(8, 16), pady=16, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=0)
        ctk.CTkLabel(right, text="COACHING LOG", font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(16, 4))
        self.log_box = ctk.CTkTextbox(right, font=FONT_MONO, fg_color=BG_DARK,
                                      text_color=TEXT_PRIMARY, wrap="word", state="disabled")
        self.log_box.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        # Track map panel
        self.track_map_frame = Card(right)
        self.track_map_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        self.track_map_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.track_map_frame, text="TRACK MAP", font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(12, 4))
        # Canvas for track map
        import tkinter as tk
        self.track_map_canvas = tk.Canvas(self.track_map_frame, width=350, height=200,
                                           bg=BG_DARK, highlightthickness=0)
        self.track_map_canvas.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.track_map_drawn = False
        self.track_map_points = []
        self.track_map_corners = []

    def _stat_widget(self, parent, label, value, unit, col):
        frame = ctk.CTkFrame(parent, fg_color=BG_DARK, corner_radius=8)
        frame.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
        ctk.CTkLabel(frame, text=label, font=("Consolas", 10), text_color=TEXT_MUTED).pack(pady=(8, 0))
        val_lbl = ctk.CTkLabel(frame, text=value, font=("Consolas", 28, "bold"), text_color=TEXT_PRIMARY)
        val_lbl.pack()
        ctk.CTkLabel(frame, text=unit, font=("Consolas", 10), text_color=TEXT_MUTED).pack(pady=(0, 8))
        return val_lbl

    def _log(self, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _start_pulse(self):
        self._pulse_state = 0
        self._do_pulse()

    def _do_pulse(self):
        frames = [TEXT_GREEN, "#1A7A40", TEXT_GREEN, TEXT_GREEN, TEXT_GREEN]
        self._pulse_state = (self._pulse_state + 1) % len(frames)
        try:
            self.status_label.configure(text="● LIVE", text_color=frames[self._pulse_state])
            self._pulse_after = self.after(500, self._do_pulse)
        except Exception:
            pass

    def start(self):
        self.lap_number = 1
        self.stream = ACTelemetryStream()
        self._log("Starting live session…")
        self._log("Waiting for Assetto Corsa…")
        self.stream_thread = threading.Thread(target=self._run_stream, daemon=True)
        self.stream_thread.start()

    def _run_stream(self):
        try:
            self.stream.stream(callback=self._on_frame, on_lap_complete=self._on_lap_complete)
        except Exception as e:
            self.after(0, lambda e=e: self._log(f"Stream error: {e}"))

    def _on_frame(self, frame):
        self.after(0, lambda: self._update_ui(frame))

    def _update_ui(self, frame):
        # Only re-configure labels when the value actually changes. At 20Hz
        # this saves hundreds of Tk calls per second.
        sp = int(frame['speed'])
        if sp != self._last_speed:
            self.speed_label.configure(text=f"{sp}")
            self._last_speed = sp
        gp = frame['gear']
        if gp != self._last_gear:
            # AC telemetry: 0=R, 1=N, 2=1st, 3=2nd, etc.
            if gp == 0:
                gear_display = "R"
            elif gp == 1:
                gear_display = "N"
            else:
                gear_display = str(gp - 1)
            self.gear_label.configure(text=gear_display)
            self._last_gear = gp
        lt = frame['lap_time']
        if abs(lt - self._last_lap_time) >= 0.1:
            self.time_label.configure(text=f"{lt:.1f}")
            self._last_lap_time = lt
        ln = frame['lap']
        if ln != self._last_lap_num:
            self.lap_count_label.configure(text=f"LAP {ln}")
            self._last_lap_num = ln


        # First valid frame sets car/track, wires up coach, loads reference.
        car = frame.get('car') or ''
        track = frame.get('track') or ''
        if car and track and (car != self.car or track != self.track):
            self.car = car
            self.track = track
            # Date may have changed too (e.g. running past midnight)
            from datetime import datetime
            self.session_date = datetime.now().strftime("%Y-%m-%d")
            self.session_dir = _session_dir(self.track, self.car, self.session_date)
            self.best_lap_path = str(self.session_dir / "best.csv")
            self.best_lap_time = None
            self.session_label.configure(
                text=f"Session: {self.car}  @  {self.track}  •  {self.session_date}"
            )
            self._load_reference_lap()



        if self._pulse_after is None:
            self._start_pulse()
        
        # Collect live track points for track map (every 5th frame, Bug 2)
        px = frame.get('pos_x', 0) or 0
        pz = frame.get('pos_z', 0) or 0
        if px != 0 or pz != 0:
            self._live_point_counter += 1
            if self._live_point_counter >= 5:
                self._live_point_counter = 0
                self._live_track_points.append((float(px), float(pz)))
                # Cap at 2000 points to avoid memory growth
                if len(self._live_track_points) > 2000:
                    self._live_track_points = self._live_track_points[-2000:]

        # Update car position on track map
        self._update_car_on_track_map(frame)


    def _load_reference_lap(self):
        """Load today's best-lap reference and detect its corners."""
        from src.analysis.corner_detection import detect_corners_advanced
        self.best_lap_data = None
        if self.best_lap_data and self.best_lap_data.has_channel('pos_x'):
            px = self.best_lap_data.get_channel('pos_x')
            pz = self.best_lap_data.get_channel('pos_z')
            print(f"[DEBUG] Reference lap positions: {len(px)} points, first 5 pos_z = {pz[:5]}")
        else:
            print("[DEBUG] Reference lap has no pos_x channel")
        self.best_lap_corners = []
        self.best_lap_time = None
        if not self.best_lap_path or not Path(self.best_lap_path).exists():
            return
        try:
            self.best_lap_data = TelemetryLoader.load(self.best_lap_path)
            self.best_lap_corners = detect_corners_advanced(
                self.best_lap_data, method="multi_channel"
            )
            # Recover the lap time from the last frame
            try:
                t = self.best_lap_data.get_channel("time")
                self.best_lap_time = float(t[-1]) if len(t) else None
            except Exception:
                self.best_lap_time = None
            self._log(
                f"Reference loaded: {len(self.best_lap_corners)} corners "
                f"({self.best_lap_time:.2f}s)" if self.best_lap_time else
                f"Reference loaded: {len(self.best_lap_corners)} corners"
            )
            # Build track map from reference lap position data
            self._build_track_map()
        except Exception as e:
            self._log(f"Reference load error: {e}")
            self.best_lap_data = None
            self.best_lap_corners = []

    def _build_track_map(self):
        """Build track map from reference lap position data."""
        if not self.best_lap_data or not self.best_lap_data.has_channel('pos_x') or not self.best_lap_data.has_channel('pos_z'):
            print("[DEBUG] No position data in best lap")
            return

        try:
            pos_x = self.best_lap_data.get_channel('pos_x')
            pos_z = self.best_lap_data.get_channel('pos_z')
            
            # Filter valid positions (non-zero)
            valid = (pos_x != 0) & (pos_z != 0)
            if not np.any(valid):
                print("[DEBUG] No valid non-zero position points")
                return
            
            x = pos_x[valid]
            z = pos_z[valid]
            
            if len(x) < 10:
                print(f"[DEBUG] Only {len(x)} valid points, need at least 10")
                return
            
            x_mean = float(np.mean(x))
            z_mean = float(np.mean(z))
            x_centered = x - x_mean
            z_centered = z - z_mean
            
            canvas_w, canvas_h = 330, 180
            margin = 10
            
            x_range = x_centered.max() - x_centered.min()
            z_range = z_centered.max() - z_centered.min()
            
            print(f"[DEBUG] x_range={x_range:.2f}, z_range={z_range:.2f}")
            
            if x_range < 0.5 or z_range < 0.5:
                print("[DEBUG] Range too small to draw")
                return
            
            scale_x = (canvas_w - 2*margin) / x_range
            scale_z = (canvas_h - 2*margin) / z_range
            scale = min(scale_x, scale_z)
            
            canvas_cx = canvas_w / 2
            canvas_cy = canvas_h / 2
            
            self.track_map_points = []
            for xi, zi in zip(x_centered, z_centered):
                canvas_x = canvas_cx + xi * scale
                canvas_y = canvas_cy - zi * scale
                self.track_map_points.append((canvas_x, canvas_y))
            
            # Cache transform
            self._map_transform = (scale, canvas_cx, canvas_cy, x_mean, z_mean)
            
            # Build corners using the valid points
            self.track_map_corners = []
            if hasattr(self, 'best_lap_corners') and self.best_lap_corners:
                distance = self.best_lap_data.get_channel('distance')
                for corner in self.best_lap_corners:
                    # Find closest point in the valid data
                    corner_dist = corner.apex_distance
                    # Use original distance array to get index, then check if valid
                    dist_all = self.best_lap_data.get_channel('distance')
                    # Find index in original data where distance is closest to corner_dist
                    idx = np.argmin(np.abs(dist_all - corner_dist))
                    # Ensure that point is valid (non-zero position)
                    if idx < len(pos_x) and (pos_x[idx] != 0 or pos_z[idx] != 0):
                        canvas_x = canvas_cx + (pos_x[idx] - x_mean) * scale
                        canvas_y = canvas_cy - (pos_z[idx] - z_mean) * scale
                        self.track_map_corners.append({
                            'pos': (canvas_x, canvas_y),
                            'number': len(self.track_map_corners) + 1,
                            'type': corner.corner_type
                        })
            
            self.track_map_drawn = True
            self.after(0, self._draw_track_map)
            
        except Exception as e:
            print(f"Track map build error: {e}")
            import traceback
            traceback.print_exc()
            self.track_map_drawn = False

    def _build_track_map_from_points(self, points):
        """Build track map from a list of (x, z) tuples collected live (Bug 2)."""
        if not points or len(points) < 50:
            return
        try:
            arr = np.array(points, dtype=float)
            x = arr[:, 0]
            z = arr[:, 1]
            # Filter any zero points
            valid = (x != 0) | (z != 0)
            x = x[valid]
            z = z[valid]
            if len(x) < 50:
                return
            x_mean = float(np.mean(x))
            z_mean = float(np.mean(z))
            x_centered = x - x_mean
            z_centered = z - z_mean
            canvas_w, canvas_h = 330, 180
            margin = 10
            x_range = x_centered.max() - x_centered.min()
            z_range = z_centered.max() - z_centered.min()
            if x_range < 1 or z_range < 1:
                return
            scale_x = (canvas_w - 2*margin) / x_range
            scale_z = (canvas_h - 2*margin) / z_range
            scale = min(scale_x, scale_z)
            canvas_cx = canvas_w / 2
            canvas_cy = canvas_h / 2
            self.track_map_points = []
            for xi, zi in zip(x_centered, z_centered):
                self.track_map_points.append((canvas_cx + xi * scale, canvas_cy - zi * scale))
            # No corners known for a brand-new live track
            self.track_map_corners = []
            # Cache transform for car marker
            self._map_transform = (scale, canvas_cx, canvas_cy, x_mean, z_mean)
            self.track_map_drawn = True
            self.after(0, self._draw_track_map)
        except Exception as e:
            print(f"Live track map build error: {e}")
            self.track_map_drawn = False


    def _draw_track_map(self):
        """Draw the track map on canvas."""
        if not self.track_map_drawn or not hasattr(self, 'track_map_canvas'):
            return
        
        try:
            c = self.track_map_canvas
            c.delete("all")
            
            if len(self.track_map_points) < 2:
                return
            
            # Draw track outline (slightly wider)
            for i in range(len(self.track_map_points) - 1):
                x1, y1 = self.track_map_points[i]
                x2, y2 = self.track_map_points[i+1]
                c.create_line(x1, y1, x2, y2, fill="#333333", width=8, capstyle=tk.ROUND)
            
            # Draw track surface
            for i in range(len(self.track_map_points) - 1):
                x1, y1 = self.track_map_points[i]
                x2, y2 = self.track_map_points[i+1]
                c.create_line(x1, y1, x2, y2, fill="#2A2A2A", width=4, capstyle=tk.ROUND)
            
            # Draw racing line (thin line in accent color)
            for i in range(len(self.track_map_points) - 1):
                x1, y1 = self.track_map_points[i]
                x2, y2 = self.track_map_points[i+1]
                c.create_line(x1, y1, x2, y2, fill=ACCENT, width=1, capstyle=tk.ROUND)
            
            # Draw corners
            for corner in self.track_map_corners:
                x, y = corner['pos']
                num = corner['number']
                ctype = corner['type']
                color = TEXT_GREEN if ctype == "slow" else (TEXT_YELLOW if ctype == "medium" else TEXT_RED)
                c.create_oval(x-8, y-8, x+8, y+8, fill=color, outline="#FFFFFF", width=2)
                c.create_text(x, y, text=str(num), fill="#FFFFFF", font=("Consolas", 9, "bold"))
            
            # Draw start/finish line
            if self.track_map_points:
                x, y = self.track_map_points[0]
                c.create_line(x-15, y, x+15, y, fill="#FFFFFF", width=3)
                c.create_text(x, y-15, text="S/F", fill="#FFFFFF", font=("Consolas", 8))
            
        except Exception as e:
            print(f"Track map draw error: {e}")

    def _update_car_on_track_map(self, frame):
        """Update car position marker on track map in real-time (Bug 3 - cached transform)."""
        if not self.track_map_drawn or not hasattr(self, 'track_map_canvas'):
            return
        if self._map_transform is None:
            return
        pos_x = frame.get('pos_x', 0) or 0
        pos_z = frame.get('pos_z', 0) or 0
        if pos_x == 0 and pos_z == 0:
            return
        try:
            scale, canvas_cx, canvas_cy, x_mean, z_mean = self._map_transform
            canvas_x = canvas_cx + (pos_x - x_mean) * scale
            canvas_y = canvas_cy - (pos_z - z_mean) * scale
            c = self.track_map_canvas
            c.delete("car_marker")
            size = 6
            c.create_polygon(
                canvas_x, canvas_y - size,
                canvas_x + size, canvas_y + size,
                canvas_x - size, canvas_y + size,
                fill=ACCENT, outline="#FFFFFF", width=2, tags="car_marker"
            )
        except Exception as e:
            print(f"Car marker update error: {e}")



    def _clear_laps(self):
        """Delete ALL files in TODAY's session folder for this car+track.
        Old days are preserved; only the current YYYY-MM-DD is wiped."""
        if not self.session_dir or not self.session_dir.exists():
            self._log("No session folder to clear.")
            return
        removed = 0
        for path in self.session_dir.iterdir():
            if path.is_file() and path.suffix == ".csv":
                try:
                    path.unlink()
                    removed += 1
                except Exception as e:
                    self._log(f"Could not delete {path.name}: {e}")
        self.lap_number = 1
        self.best_lap_data = None
        self.best_lap_corners = []
        self.best_lap_time = None
        self.delta_label.configure(text="--.-s", text_color=TEXT_MUTED)
        for lbl in self.sector_labels:
            lbl.configure(text="S-  --.-s", text_color=TEXT_MUTED)
        self._log(f"Cleared {removed} file(s) in {self.session_date} for {self.car} @ {self.track}")
        self.speaker.say(f"Cleared today's laps for {self.track}.")


    def _on_lap_complete(self, frames):
        if len(frames) < 200:
            return

        # Ensure session_dir is set (it should be, but be safe)
        if not self.session_dir:
            from datetime import datetime
            self.session_date = datetime.now().strftime("%Y-%m-%d")
            self.session_dir = _session_dir(self.track, self.car, self.session_date)
            self.best_lap_path = str(self.session_dir / "best.csv")

        # Save the actual lap with a timestamped, sortable filename
        stamp = _now_stamp()
        try:
            lap_time = float(frames[-1].get("lap_time", 0))
        except Exception:
            lap_time = 0.0
        lap_filename = f"lap_{stamp}_{self.lap_number}_{lap_time:.2f}s.csv"
        lap_path = str(self.session_dir / lap_filename)
        self.stream.save_lap(frames, lap_path)
        self.after(0, lambda: self._log(
            f"\n── Lap {self.lap_number} complete • {stamp} • {lap_time:.2f}s ──"
        ))

        # Bug 2: if we don't have a reference lap (first session) and we
        # collected enough live points, build the map from them.
        if not self.track_map_drawn and len(self._live_track_points) > 50:
            self._build_track_map_from_points(self._live_track_points)
            self._live_track_points = []


        # Determine reference: best or previous lap
        from src.voice import settings as voice_settings
        v_settings = voice_settings.load()
        compare_mode = v_settings.get("compare_mode", "best")

        ref_path = None
        if compare_mode == "previous" and self._prev_lap_data is not None:
            # Compare against previous lap
            ref_data = self._prev_lap_data
            ref_corners = self._prev_lap_corners
            ref_time = self._prev_lap_time
            ref_label = "previous lap"
        else:
            # Compare against best lap
            if Path(self.best_lap_path).exists():
                ref_path = self.best_lap_path
                ref_data = self.best_lap_data
                ref_corners = self.best_lap_corners
                ref_time = self.best_lap_time
                ref_label = "best lap"
            else:
                ref_data = None

        if ref_data is not None:
            try:
                from src.analysis.corner_detection import detect_corners_advanced, analyze_corner_performance
                current = TelemetryLoader.load(lap_path)
                if not self.track_map_drawn and current.has_channel('pos_x') and current.has_channel('pos_z'):
                    px = current.get_channel('pos_x')
                    pz = current.get_channel('pos_z')
                    valid = (px != 0) & (pz != 0)
                    if np.sum(valid) > 50:
                        points = list(zip(px[valid], pz[valid]))
                        self._build_track_map_from_points(points)
                        self.track_map_drawn = True  # mark as drawn so we don't rebuild every lap
                corners = detect_corners_advanced(current, method="multi_channel")
                distances, delta = calculate_time_delta(ref_data, current)
                stats   = calculate_delta_statistics(delta, distances)
                zones   = find_significant_delta_zones(delta, distances)
                total   = stats['total_delta']
                sectors = stats['sector_deltas']

                # Corner analysis
                corner_analysis = analyze_corner_performance(ref_data, current, corners)

                # Update UI
                color = TEXT_GREEN if total < 0 else TEXT_RED
                sign  = "-" if total < 0 else "+"
                self.after(0, lambda: self.delta_label.configure(
                    text=f"{sign}{abs(total):.3f}s", text_color=color))

                for i, (k, v) in enumerate(sectors.items()):
                    s_color = TEXT_GREEN if v < 0 else TEXT_RED
                    s_sign  = "-" if v < 0 else "+"
                    txt     = f"S{i+1}  {s_sign}{abs(v):.3f}s"
                    idx     = i
                    self.after(0, lambda t=txt, c=s_color, x=idx:
                               self.sector_labels[x].configure(text=t, text_color=c))

                result = "FASTER" if total < 0 else "SLOWER"
                self.after(0, lambda: self._log(f"{result} by {abs(total):.3f}s vs {ref_label}"))
                for k, v in sectors.items():
                    s = "-" if v < 0 else "+"
                    self.after(0, lambda k=k, v=v, s=s: self._log(f"  {k}: {s}{abs(v):.3f}s"))

                # Save as new best if better
                if total < 0 and compare_mode == "best":
                    import shutil
                    shutil.copy(lap_path, self.best_lap_path)
                    self.best_lap_time = lap_time
                    self._load_reference_lap()
                    self.after(0, lambda: self._log(f"  ★ New best: {lap_time:.2f}s"))

                # Comprehensive voice summary (handles corner analysis internally)
                threading.Thread(
                    target=self.speaker.say_lap_result,
                    args=(stats, zones),
                    kwargs={
                        "corner_analysis": corner_analysis,
                        "lap_time": lap_time,
                        "ref_time": ref_time,
                        "prev_time": self._prev_lap_time,
                        "compare_mode": compare_mode,
                    },
                    daemon=True
                ).start()

            except Exception as e:
                self.after(0, lambda e=e: self._log(f"Analysis error: {e}"))

        else:
            # First lap of the day — becomes the reference
            import shutil
            shutil.copy(lap_path, self.best_lap_path)
            self.best_lap_time = lap_time
            self._load_reference_lap()
            self.after(0, lambda: self._log(
                f"  ★ First lap of the day: {lap_time:.2f}s (saved as best)"
            ))
            threading.Thread(target=self.speaker.say,
                             args=("First lap recorded. Drive another lap to compare.",),
                             daemon=True).start()

        # Store this lap as previous for next comparison
        try:
            self._prev_lap_data = TelemetryLoader.load(lap_path)
            self._prev_lap_time = lap_time
            from src.analysis.corner_detection import detect_corners_advanced
            self._prev_lap_corners = detect_corners_advanced(self._prev_lap_data, method="multi_channel")
        except Exception:
            pass

        self.lap_number += 1


    def _stop_and_back(self):
        if self._pulse_after:
            self.after_cancel(self._pulse_after)
            self._pulse_after = None
        if self.stream:
            self.stream.stop()
        self.on_back()


# Analysis screen with delta time comparison graph
class AnalysisScreen(ctk.CTkFrame):
    def __init__(self, parent, on_back):
        super().__init__(parent, fg_color=BG_DARK)
        self.on_back = on_back
        self.lap1_path = None
        self.lap2_path = None
        self._build_ui()

    def _build_ui(self):
        # Layout:
        #   row 0 = top bar
        #   row 1 = file pickers
        #   row 2 = run-analysis row
        #   row 3 = graph + results side by side
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=50)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(top, text="← Back", font=("Consolas", 13),
                      fg_color="transparent", hover_color="#2C2C2C",
                      width=80, command=self.on_back
                      ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(top, text="ANALYSIS MODE", font=("Consolas", 16, "bold"),
                     text_color=ACCENT).grid(row=0, column=1, pady=8)

        file_card = Card(self)
        file_card.grid(row=1, column=0, padx=16, pady=(16, 8), sticky="ew")
        file_card.grid_columnconfigure((0, 1), weight=1)

        for col, lbl_text, btn_text, attr in [
            (0, "REFERENCE LAP",  "Load Lap 1", "lap1_path"),
            (1, "COMPARISON LAP", "Load Lap 2", "lap2_path"),
        ]:
            f = ctk.CTkFrame(file_card, fg_color="transparent")
            f.grid(row=0, column=col, padx=20, pady=16, sticky="ew")
            ctk.CTkLabel(f, text=lbl_text, font=("Consolas", 12), text_color=TEXT_MUTED).pack(anchor="w")
            setattr(self, f"{attr}_label",
                    ctk.CTkLabel(f, text="No file selected", font=("Consolas", 12), text_color=TEXT_MUTED))
            getattr(self, f"{attr}_label").pack(anchor="w", pady=(4, 8))
            ctk.CTkButton(f, text=btn_text, font=("Consolas", 13),
                          fg_color=BG_DARK, hover_color="#2C2C2C",
                          border_color=ACCENT, border_width=1,
                          command=lambda a=attr: self._load(a)
                          ).pack(anchor="w")

        ctk.CTkButton(file_card, text="RUN ANALYSIS", font=("Consolas", 15, "bold"),
                      fg_color=ACCENT, hover_color="#C0392B",
                      height=44, corner_radius=8, command=self._run_analysis
                      ).grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="ew")

        # ---- bottom row: graph (top) + results (bottom) ----
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)  # graph row
        body.grid_rowconfigure(1, weight=1)  # results row

        # Graph card (top half)
        graph_card = Card(body)
        graph_card.grid(row=0, column=0, pady=(0, 8), sticky="nsew")
        graph_card.grid_columnconfigure(0, weight=1)
        graph_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(graph_card, text="TIME DELTA COMPARISON", font=("Consolas", 12),
                     text_color=TEXT_MUTED).grid(row=0, column=0, pady=(12, 4))
        
        # Matplotlib canvas for the graph
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
        self.graph_fig = Figure(figsize=(10, 4), dpi=100, facecolor=BG_DARK)
        self.graph_ax = self.graph_fig.add_subplot(111)
        self.graph_fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.3)
        self.graph_canvas = FigureCanvasTkAgg(self.graph_fig, graph_card)
        self.graph_canvas.get_tk_widget().configure(bg=BG_DARK)
        self.graph_canvas.get_tk_widget().grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        # Results card (bottom half)
        results_card = Card(body)
        results_card.grid(row=1, column=0, sticky="nsew")
        results_card.grid_columnconfigure(0, weight=1)
        results_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(results_card, text="ANALYSIS RESULTS", font=("Consolas", 12),
                     text_color=TEXT_MUTED).grid(row=0, column=0, pady=(12, 4))
        self.results_box = ctk.CTkTextbox(results_card, font=FONT_MONO, fg_color=BG_DARK,
                                          text_color=TEXT_PRIMARY, wrap="word", state="disabled")
        self.results_box.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")

    def _load(self, attr):
        from tkinter import filedialog
        title = "Select Reference Lap" if attr == "lap1_path" else "Select Comparison Lap"
        path = filedialog.askopenfilename(title=title, initialdir=str(_data_dir()),
                                          filetypes=[("CSV files", "*.csv")])
        if path:
            setattr(self, attr, path)
            getattr(self, f"{attr}_label").configure(text=Path(path).name, text_color=TEXT_PRIMARY)

    def _log(self, message: str):
        self.results_box.configure(state="normal")
        self.results_box.insert("end", f"{message}\n")
        self.results_box.see("end")
        self.results_box.configure(state="disabled")

    def _run_analysis(self):
        if not self.lap1_path or not self.lap2_path:
            self._log("Please load both lap files first.")
            return
        self.results_box.configure(state="normal")
        self.results_box.delete("1.0", "end")
        self.results_box.configure(state="disabled")
        self._log("Running analysis…")
        try:
            ref     = TelemetryLoader.load(self.lap1_path)
            current = TelemetryLoader.load(self.lap2_path)
            distances, delta = calculate_time_delta(ref, current)
            stats   = calculate_delta_statistics(delta, distances)
            zones   = find_significant_delta_zones(delta, distances)
            self._log(generate_coaching_message(stats, zones))
            # Draw the delta graph
            self._draw_delta_graph(distances, delta, ref, current)
        except Exception as e:
            self._log(f"Error: {e}")

    def _draw_delta_graph(self, distances, delta, ref, current):
        """Draw the delta time comparison graph showing faster/slower sections."""
        self.graph_ax.clear()
        
        # Style the graph
        self.graph_ax.set_facecolor(BG_DARK)
        self.graph_fig.set_facecolor(BG_DARK)
        
        # Plot the delta
        self.graph_ax.plot(distances, delta, color='white', linewidth=1.5, alpha=0.9)
        
        # Fill positive (slower) with red, negative (faster) with green
        positive_delta = np.where(delta >= 0, delta, 0)
        negative_delta = np.where(delta < 0, delta, 0)
        
        self.graph_ax.fill_between(distances, 0, positive_delta, 
                                   color='#E8433A', alpha=0.4, label='Slower')
        self.graph_ax.fill_between(distances, 0, negative_delta, 
                                   color='#2ECC71', alpha=0.4, label='Faster')
        
        # Reference line at zero
        self.graph_ax.axhline(y=0, color='#444444', linewidth=1, linestyle='-')
        
        # Style axes
        self.graph_ax.set_xlabel('Distance (m)', color=TEXT_MUTED, fontsize=10)
        self.graph_ax.set_ylabel('Delta Time (s)', color=TEXT_MUTED, fontsize=10)
        self.graph_ax.set_title('Time Delta: Red = Slower | Green = Faster', 
                                color=TEXT_PRIMARY, fontsize=12, fontweight='bold')
        
        # Style ticks
        self.graph_ax.tick_params(colors=TEXT_MUTED)
        self.graph_ax.spines['bottom'].set_color('#333333')
        self.graph_ax.spines['top'].set_color('#333333')
        self.graph_ax.spines['left'].set_color('#333333')
        self.graph_ax.spines['right'].set_color('#333333')
        
        # Grid
        self.graph_ax.grid(True, alpha=0.2, color='#444444')
        
        # Legend
        self.graph_ax.legend(loc='upper right', facecolor=BG_CARD, edgecolor='#444444',
                            labelcolor=TEXT_PRIMARY, fontsize=9)
        
        # Refresh the canvas
        self.graph_canvas.draw()


# Main app
class SRLTAApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SRLTA")
        self.geometry("1000x680")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DARK)
        # Two-row layout: row 0 = current screen, row 1 = persistent nav bar
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.current_screen = None
        # Cache for keeping screens alive across tab switches
        self._screens = {}
        self._build_nav_bar()
        self._show_home()

    def _build_nav_bar(self):
        """Persistent bottom bar with HOME / LIVE / ANALYSIS / SETTINGS."""
        nav_font = ("Consolas", 11, "bold")
        btn_bg = BG_PANEL
        btn_hover = "#2A2A2A"
        active_bg = "#1E1E1E"
        self._nav = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=44)
        self._nav.grid(row=1, column=0, sticky="ew")
        self._nav.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._nav_btns = {}
        for i, (text, cmd) in enumerate([
            ("\u2302  HOME", self._show_home),
            ("\u25B6  LIVE", self._show_live),
            ("\u25C8  ANALYSIS", self._show_analysis),
            ("\u2699  SETTINGS", self._show_settings),
        ]):
            btn = ctk.CTkButton(self._nav, text=text, font=nav_font,
                                fg_color=btn_bg, hover_color=btn_hover,
                                text_color=TEXT_MUTED,
                                command=cmd)
            btn.grid(row=0, column=i, sticky="ew", padx=2, pady=4)
            self._nav_btns[text.split()[-1].lower()] = btn

    def _highlight_nav(self, active):
        """Highlight the active nav button, dim the rest."""
        for name, btn in self._nav_btns.items():
            if name == active:
                btn.configure(fg_color="#2A2A2A", text_color=ACCENT)
            else:
                btn.configure(fg_color=BG_PANEL, text_color=TEXT_MUTED)

    def _switch_to(self, name):
        """Switch to a cached screen. Hides the old one, shows the new one.
        Uses grid_forget+update to prevent screen tearing."""
        # Force any pending UI updates to complete first
        self.update_idletasks()
        # Hide current screen
        if self.current_screen is not None:
            self.current_screen.grid_forget()
        # Get or create the target screen
        if name not in self._screens:
            if name == "home":
                self._screens[name] = HomeScreen(
                    self, on_live=self._show_live,
                    on_analysis=self._show_analysis,
                    on_settings=self._show_settings)
            elif name == "live":
                self._screens[name] = LiveScreen(self, on_back=self._show_home)
            elif name == "analysis":
                self._screens[name] = AnalysisScreen(self, on_back=self._show_home)
            elif name == "settings":
                self._screens[name] = SettingsScreen(self, on_back=self._show_home)
        screen = self._screens[name]
        self.current_screen = screen
        self.grid_rowconfigure(0, weight=1)
        screen.grid(row=0, column=0, sticky="nsew")
        # Force layout update before next frame to prevent tearing
        self.update_idletasks()
        # Highlight the active nav button
        self._highlight_nav(name)
        # For live screen, start the stream if not already running
        if name == "live" and hasattr(screen, 'start') and screen.stream is None:
            try:
                screen.start()
            except Exception:
                pass

    def _show_home(self):
        self._switch_to("home")

    def _show_live(self):
        self._switch_to("live")

    def _show_analysis(self):
        self._switch_to("analysis")

    def _show_settings(self):
        self._switch_to("settings")


def run():
    app = SRLTAApp()
    app.mainloop()


if __name__ == "__main__":
    run()
