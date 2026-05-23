"""
SRLTA Dashboard - Main GUI Application
"""

import customtkinter as ctk
import threading
import time
from pathlib import Path
import sys
import os

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

# ── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT       = "#E8433A"   # red accent
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


# ── Reusable card frame ───────────────────────────────────────────────────────
class Card(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=10, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# HOME SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class HomeScreen(ctk.CTkFrame):
    def __init__(self, parent, on_live, on_analysis):
        super().__init__(parent, fg_color=BG_DARK)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4), weight=1)

        # Logo / title
        ctk.CTkLabel(
            self, text="SRLTA",
            font=("Consolas", 64, "bold"),
            text_color=ACCENT
        ).grid(row=0, column=0, pady=(60, 0))

        ctk.CTkLabel(
            self, text="Sim Racing Lap Time Analyzer",
            font=("Consolas", 18),
            text_color=TEXT_MUTED
        ).grid(row=1, column=0, pady=(0, 60))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=20)

        ctk.CTkButton(
            btn_frame, text="⬤  LIVE MODE",
            font=("Consolas", 20, "bold"),
            fg_color=ACCENT, hover_color="#C0392B",
            width=280, height=70, corner_radius=8,
            command=on_live
        ).pack(pady=12)

        ctk.CTkButton(
            btn_frame, text="⬤  ANALYSIS MODE",
            font=("Consolas", 20, "bold"),
            fg_color="#2C2C2C", hover_color="#3C3C3C",
            border_color=ACCENT, border_width=2,
            width=280, height=70, corner_radius=8,
            command=on_analysis
        ).pack(pady=12)

        ctk.CTkLabel(
            self, text="Make sure Assetto Corsa is running before starting Live Mode",
            font=("Consolas", 12),
            text_color=TEXT_MUTED
        ).grid(row=3, column=0, pady=(40, 0))


# ══════════════════════════════════════════════════════════════════════════════
# LIVE SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class LiveScreen(ctk.CTkFrame):
    def __init__(self, parent, on_back):
        super().__init__(parent, fg_color=BG_DARK)
        self.on_back = on_back
        self.stream = None
        self.speaker = Speaker()
        self.lap_number = 1
        self.best_lap_path = "data/best_lap.csv"
        self.stream_thread = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top bar ──────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=50)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            top, text="← Back",
            font=("Consolas", 13),
            fg_color="transparent", hover_color="#2C2C2C",
            width=80, command=self._stop_and_back
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(
            top, text="LIVE MODE",
            font=("Consolas", 16, "bold"),
            text_color=ACCENT
        ).grid(row=0, column=1, pady=8)

        self.status_label = ctk.CTkLabel(
            top, text="● WAITING FOR AC",
            font=("Consolas", 13),
            text_color=TEXT_YELLOW
        )
        self.status_label.grid(row=0, column=2, padx=20, pady=8, sticky="e")

        # ── Left panel: live telemetry ────────────────────────────────────────
        left = Card(self)
        left.grid(row=1, column=0, padx=(16, 8), pady=16, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="TELEMETRY",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(16, 4))

        # Delta — big display
        self.delta_label = ctk.CTkLabel(
            left, text="--.-s",
            font=("Consolas", 72, "bold"),
            text_color=TEXT_MUTED
        )
        self.delta_label.grid(row=1, column=0, pady=(8, 0))

        ctk.CTkLabel(left, text="DELTA VS BEST",
                     font=("Consolas", 11), text_color=TEXT_MUTED
                     ).grid(row=2, column=0, pady=(0, 20))

        # Speed / Gear / Lap time
        stats_frame = ctk.CTkFrame(left, fg_color="transparent")
        stats_frame.grid(row=3, column=0, pady=8, padx=20, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.speed_label = self._stat_widget(stats_frame, "SPEED", "0", "km/h", 0)
        self.gear_label  = self._stat_widget(stats_frame, "GEAR",  "1", "",     1)
        self.time_label  = self._stat_widget(stats_frame, "LAP",   "0.0", "s",  2)

        # Sector splits
        ctk.CTkLabel(left, text="LAST LAP SECTORS",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=4, column=0, pady=(24, 4))

        self.sector_labels = []
        for i in range(3):
            lbl = ctk.CTkLabel(left,
                               text=f"S{i+1}  --.-s",
                               font=FONT_MONO,
                               text_color=TEXT_MUTED)
            lbl.grid(row=5+i, column=0, pady=2)
            self.sector_labels.append(lbl)

        # Lap counter
        self.lap_count_label = ctk.CTkLabel(
            left, text="LAP 0",
            font=("Consolas", 13),
            text_color=TEXT_MUTED
        )
        self.lap_count_label.grid(row=8, column=0, pady=(20, 16))

        # ── Right panel: coaching log ─────────────────────────────────────────
        right = Card(self)
        right.grid(row=1, column=1, padx=(8, 16), pady=16, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right, text="COACHING LOG",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(16, 4))

        self.log_box = ctk.CTkTextbox(
            right,
            font=FONT_MONO,
            fg_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            wrap="word",
            state="disabled"
        )
        self.log_box.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

    def _stat_widget(self, parent, label, value, unit, col):
        frame = ctk.CTkFrame(parent, fg_color=BG_DARK, corner_radius=8)
        frame.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
        ctk.CTkLabel(frame, text=label,
                     font=("Consolas", 10), text_color=TEXT_MUTED
                     ).pack(pady=(8, 0))
        val_lbl = ctk.CTkLabel(frame, text=value,
                               font=("Consolas", 28, "bold"),
                               text_color=TEXT_PRIMARY)
        val_lbl.pack()
        ctk.CTkLabel(frame, text=unit,
                     font=("Consolas", 10), text_color=TEXT_MUTED
                     ).pack(pady=(0, 8))
        return val_lbl

    def _log(self, message: str):
        """Append a message to the coaching log."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start(self):
        """Start the live telemetry stream in a background thread."""
        self.lap_number = 1
        self.stream = ACTelemetryStream()
        self._log("Starting live session...")
        self._log("Waiting for Assetto Corsa...")
        self.stream_thread = threading.Thread(
            target=self._run_stream, daemon=True)
        self.stream_thread.start()

    def _run_stream(self):
        try:
            self.stream.stream(
                callback=self._on_frame,
                on_lap_complete=self._on_lap_complete
            )
        except Exception as e:
            self.after(0, lambda: self._log(f"Stream error: {e}"))

    def _on_frame(self, frame):
        """Called every frame from the stream thread — update UI safely."""
        self.after(0, lambda: self._update_ui(frame))

    def _update_ui(self, frame):
        self.speed_label.configure(text=f"{frame['speed']:.0f}")
        self.gear_label.configure(text=str(frame['gear']))
        self.time_label.configure(text=f"{frame['lap_time']:.1f}")
        self.lap_count_label.configure(text=f"LAP {frame['lap']}")
        self.status_label.configure(text="● LIVE", text_color=TEXT_GREEN)

    def _on_lap_complete(self, frames):
        """Called when a lap is completed."""
        if len(frames) < 200:
            return

        lap_path = f"data/lap_{self.lap_number}.csv"
        self.stream.save_lap(frames, lap_path)

        self.after(0, lambda: self._log(
            f"\n── Lap {self.lap_number} complete ──"))

        if Path(self.best_lap_path).exists():
            try:
                ref     = TelemetryLoader.load(self.best_lap_path)
                current = TelemetryLoader.load(lap_path)
                distances, delta = calculate_time_delta(ref, current)
                stats   = calculate_delta_statistics(delta, distances)
                zones   = find_significant_delta_zones(delta, distances)

                total   = stats['total_delta']
                sectors = stats['sector_deltas']

                # Update delta display
                color = TEXT_GREEN if total < 0 else TEXT_RED
                sign  = "-" if total < 0 else "+"
                self.after(0, lambda: self.delta_label.configure(
                    text=f"{sign}{abs(total):.3f}s",
                    text_color=color
                ))

                # Update sector labels
                for i, (k, v) in enumerate(sectors.items()):
                    s_color = TEXT_GREEN if v < 0 else TEXT_RED
                    s_sign  = "-" if v < 0 else "+"
                    txt     = f"S{i+1}  {s_sign}{abs(v):.3f}s"
                    idx     = i
                    self.after(0, lambda t=txt, c=s_color, x=idx:
                               self.sector_labels[x].configure(
                                   text=t, text_color=c))

                # Log result
                result = ("FASTER" if total < 0 else "SLOWER")
                self.after(0, lambda: self._log(
                    f"{result} by {abs(total):.3f}s"))
                for k, v in sectors.items():
                    sign = "-" if v < 0 else "+"
                    self.after(0, lambda k=k, v=v, s=sign:
                               self._log(f"  {k}: {s}{abs(v):.3f}s"))

                # Best lap update
                if total < 0:
                    import shutil
                    shutil.copy(lap_path, self.best_lap_path)
                    self.after(0, lambda: self._log("  ★ New best lap!"))

                # Voice coaching (in background so UI doesn't freeze)
                threading.Thread(
                    target=self.speaker.say_lap_result,
                    args=(stats, zones),
                    daemon=True
                ).start()

            except Exception as e:
                self.after(0, lambda: self._log(f"Analysis error: {e}"))
        else:
            import shutil
            shutil.copy(lap_path, self.best_lap_path)
            self.after(0, lambda: self._log(
                "Reference lap saved. Drive another lap to compare!"))
            threading.Thread(
                target=self.speaker.say,
                args=("First lap recorded. Drive another lap to compare.",),
                daemon=True
            ).start()

        self.lap_number += 1

    def _stop_and_back(self):
        if self.stream:
            self.stream.stop()
        self.on_back()


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class AnalysisScreen(ctk.CTkFrame):
    def __init__(self, parent, on_back):
        super().__init__(parent, fg_color=BG_DARK)
        self.on_back = on_back
        self.lap1_path = None
        self.lap2_path = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Top bar
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
            top, text="ANALYSIS MODE",
            font=("Consolas", 16, "bold"),
            text_color=ACCENT
        ).grid(row=0, column=1, pady=8)

        # File selector
        file_card = Card(self)
        file_card.grid(row=1, column=0, padx=16, pady=(16, 8), sticky="ew")
        file_card.grid_columnconfigure((0, 1), weight=1)

        # Lap 1
        lap1_frame = ctk.CTkFrame(file_card, fg_color="transparent")
        lap1_frame.grid(row=0, column=0, padx=20, pady=16, sticky="ew")
        ctk.CTkLabel(lap1_frame, text="REFERENCE LAP",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).pack(anchor="w")
        self.lap1_label = ctk.CTkLabel(
            lap1_frame, text="No file selected",
            font=("Consolas", 12), text_color=TEXT_MUTED)
        self.lap1_label.pack(anchor="w", pady=(4, 8))
        ctk.CTkButton(
            lap1_frame, text="Load Lap 1",
            font=("Consolas", 13),
            fg_color=BG_DARK, hover_color="#2C2C2C",
            border_color=ACCENT, border_width=1,
            command=self._load_lap1
        ).pack(anchor="w")

        # Lap 2
        lap2_frame = ctk.CTkFrame(file_card, fg_color="transparent")
        lap2_frame.grid(row=0, column=1, padx=20, pady=16, sticky="ew")
        ctk.CTkLabel(lap2_frame, text="COMPARISON LAP",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).pack(anchor="w")
        self.lap2_label = ctk.CTkLabel(
            lap2_frame, text="No file selected",
            font=("Consolas", 12), text_color=TEXT_MUTED)
        self.lap2_label.pack(anchor="w", pady=(4, 8))
        ctk.CTkButton(
            lap2_frame, text="Load Lap 2",
            font=("Consolas", 13),
            fg_color=BG_DARK, hover_color="#2C2C2C",
            border_color=ACCENT, border_width=1,
            command=self._load_lap2
        ).pack(anchor="w")

        # Run button
        ctk.CTkButton(
            file_card, text="RUN ANALYSIS",
            font=("Consolas", 15, "bold"),
            fg_color=ACCENT, hover_color="#C0392B",
            height=44, corner_radius=8,
            command=self._run_analysis
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="ew")

        # Results
        results_card = Card(self)
        results_card.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        results_card.grid_columnconfigure(0, weight=1)
        results_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(results_card, text="RESULTS",
                     font=("Consolas", 12), text_color=TEXT_MUTED
                     ).grid(row=0, column=0, pady=(16, 4))

        self.results_box = ctk.CTkTextbox(
            results_card,
            font=FONT_MONO,
            fg_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            wrap="word",
            state="disabled"
        )
        self.results_box.grid(row=1, column=0, padx=16,
                              pady=(0, 16), sticky="nsew")

    def _load_lap1(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Reference Lap",
            initialdir="data",
            filetypes=[("CSV files", "*.csv")]
        )
        if path:
            self.lap1_path = path
            self.lap1_label.configure(
                text=Path(path).name, text_color=TEXT_PRIMARY)

    def _load_lap2(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Comparison Lap",
            initialdir="data",
            filetypes=[("CSV files", "*.csv")]
        )
        if path:
            self.lap2_path = path
            self.lap2_label.configure(
                text=Path(path).name, text_color=TEXT_PRIMARY)

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
        self._log("Running analysis...")

        try:
            ref     = TelemetryLoader.load(self.lap1_path)
            current = TelemetryLoader.load(self.lap2_path)
            distances, delta = calculate_time_delta(ref, current)
            stats   = calculate_delta_statistics(delta, distances)
            zones   = find_significant_delta_zones(delta, distances)
            coaching = generate_coaching_message(stats, zones)

            self._log(coaching)
        except Exception as e:
            self._log(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
class SRLTAApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SRLTA")
        self.geometry("1000x680")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DARK)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.current_screen = None
        self._show_home()

    def _clear(self):
        if self.current_screen:
            self.current_screen.grid_forget()

    def _show_home(self):
        self._clear()
        self.current_screen = HomeScreen(
            self,
            on_live=self._show_live,
            on_analysis=self._show_analysis
        )
        self.current_screen.grid(row=0, column=0, sticky="nsew")

    def _show_live(self):
        self._clear()
        screen = LiveScreen(self, on_back=self._show_home)
        screen.grid(row=0, column=0, sticky="nsew")
        self.current_screen = screen
        screen.start()

    def _show_analysis(self):
        self._clear()
        self.current_screen = AnalysisScreen(self, on_back=self._show_home)
        self.current_screen.grid(row=0, column=0, sticky="nsew")


def run():
    app = SRLTAApp()
    app.mainloop()


if __name__ == "__main__":
    run()