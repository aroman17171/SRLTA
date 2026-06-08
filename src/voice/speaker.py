"""SRLTA Voice Coaching - Edge-TTS primary, pyttsx3 fallback."""

import threading
import queue
import socket
import time as _time
import asyncio
import tempfile
import os
import pyttsx3
from src.voice.settings import load as load_settings, save as save_settings


# ─────────────────────────────────────────────────────────────────────────────
# Audio playback - try playsound (the old classic), then playsound3, then
# pygame.mixer, then winsound as a last-resort fallback. Whichever imports
# first wins, and we cache it.
# ─────────────────────────────────────────────────────────────────────────────
def _get_playsound():
    """Return a `playsound(path, block=True)` callable, or None if nothing works."""
    if hasattr(_get_playsound, "_cached"):
        return _get_playsound._cached
    for mod_name, attr in (("playsound", "playsound"),
                           ("playsound3", "playsound")):
        try:
            mod = __import__(mod_name)
            fn = getattr(mod, attr, None)
            if callable(fn):
                _get_playsound._cached = fn
                return fn
        except Exception:
            continue
    # Last resort: pygame.mixer (always installed with customtkinter projects)
    try:
        import pygame  # type: ignore
        try:
            pygame.mixer.init()
        except Exception:
            pass
        def _pygame_play(path, block=True):
            try:
                snd = pygame.mixer.Sound(path)
                ch = snd.play()
                if block and ch is not None:
                    while ch.get_busy():
                        _time.sleep(0.05)
            except Exception as e:
                print(f"pygame play error: {e}")
        _get_playsound._cached = _pygame_play
        return _pygame_play
    except Exception:
        pass
    # Final fallback: winsound (sync PlaySound on Windows)
    try:
        import winsound  # type: ignore
        def _winsound_play(path, block=True):
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            except Exception as e:
                print(f"winsound play error: {e}")
        _get_playsound._cached = _winsound_play
        return _winsound_play
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Online check (cached)
# ─────────────────────────────────────────────────────────────────────────────
_online_cache = {"value": False, "ts": 0.0}
_online_lock = threading.Lock()
ONLINE_HOST = ("speech.platform.bing.com", 443)
ONLINE_TIMEOUT = 1.5
ONLINE_CACHE_TTL = 30.0  # seconds


def _is_online() -> bool:
    """Quick socket connect to Bing speech endpoint with caching."""
    now = _time.time()
    with _online_lock:
        if now - _online_cache["ts"] < ONLINE_CACHE_TTL:
            return _online_cache["value"]
    result = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(ONLINE_TIMEOUT)
        sock.connect(ONLINE_HOST)
        sock.close()
        result = True
    except Exception:
        result = False
    with _online_lock:
        _online_cache["value"] = result
        _online_cache["ts"] = now
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Edge-TTS voice enumeration (curated list of voices known to be available)
# ─────────────────────────────────────────────────────────────────────────────
EDGE_VOICES = [
    # ---- Male Voices ----
    ("Brian",                    "en-US-BrianNeural",       "Male",   "en-US"),
    ("Guy",                      "en-US-GuyNeural",         "Male",   "en-US"),
    ("Jarvis",                   "en-GB-RyanNeural",        "Male",   "en-GB"),
    ("Eric",                     "en-US-EricNeural",        "Male",   "en-US"),
    ("William AU",               "en-AU-WilliamNeural",     "Male",   "en-AU"),

    # ---- Female Voices ----
    ("Ava",                      "en-US-AvaNeural",         "Female", "en-US"),
    ("Emma",                     "en-US-EmmaNeural",        "Female", "en-US"),
    ("Jenny",                    "en-US-JennyNeural",       "Female", "en-US"),
    ("Aria",                     "en-US-AriaNeural",        "Female", "en-US"),
    ("Michelle",                 "en-US-MichelleNeural",    "Female", "en-US"),
    ("Sonia UK",                 "en-GB-SoniaNeural",       "Female", "en-GB"),
]




def _list_voices_pyttsx3():
    """Get voices from pyttsx3 (offline fallback)."""
    out = []
    try:
        eng = pyttsx3.init()
        voices = eng.getProperty("voices") or []
        for i, v in enumerate(voices):
            try:
                name = v.name or f"Voice {i}"
            except Exception:
                name = f"Voice {i}"
            try:
                lang = (v.languages[0] if v.languages else "") or ""
            except Exception:
                lang = ""
            out.append({
                "id": f"pyttsx3:{i}",
                "name": name,
                "lang": lang,
                "backend": "pyttsx3",
                "raw_id": v.id or "",
                "index": i,
            })
        try:
            eng.stop()
        except Exception:
            pass
    except Exception as e:
        print(f"pyttsx3 voice list error: {e}")
    return out


def _list_voices_edge():
    """Get edge-tts voices (online)."""
    out = []
    for i, (display, short, gender, locale) in enumerate(EDGE_VOICES):
        out.append({
            "id": f"edge:{short}",
            "name": f"{display}",
            "lang": locale,
            "backend": "edge",
            "raw_id": short,
            "index": i,
        })
    return out


def list_voices(force_refresh=False):
    """Returns voices - edge-tts voices when online, pyttsx3 when offline."""
    if _is_online():
        return _list_voices_edge()
    return _list_voices_pyttsx3()


# ─────────────────────────────────────────────────────────────────────────────
# Speaker
# ─────────────────────────────────────────────────────────────────────────────

class Speaker:
    MODES = ["sectors", "full", "corners", "off"]
    MODE_DESC = {
        "sectors": "Lap summary with sector deltas",
        "full":    "Sectors + corner-by-corner coaching",
        "corners": "Corner coaching only",
        "off":     "No voice coaching",
    }

    def __init__(self):
        s = load_settings()
        self.voice_enabled = s["voice_enabled"]
        self.mode          = s.get("mode", "sectors")
        self.compare_mode  = s.get("compare_mode", "best")
        self.rate          = s["rate"]
        self.volume        = s["volume"]
        # pyttsx3 fallback voice
        self.voice_id      = s.get("voice_id", 0)
        # edge-tts voice name (e.g. "en-US-AndrewNeural")
        self.voice_name    = s.get("voice_name", "en-US-AndrewNeural")
        # preferred backend
        self.backend       = s.get("backend", "edge")

    # ------------------------------------------------------------------ #
    #  Core                                                                #
    # ------------------------------------------------------------------ #
    def say(self, message: str):
        """Speak a message. Non-blocking - queues speech to a single worker thread."""
        if not self.voice_enabled or self.mode == "off" or not message:
            return
        print(f"🎙️  {message}")
        self._enqueue(message)

    # ── Speech queue ─────────────────────────────────────────────────── #
    _speech_queue = queue.Queue()
    _worker_started = False

    @classmethod
    def _ensure_worker(cls):
        if cls._worker_started:
            return
        cls._worker_started = True
        t = threading.Thread(target=cls._worker_loop, daemon=True)
        t.start()

    @classmethod
    def _worker_loop(cls):
        while True:
            try:
                msg, self_ref = cls._speech_queue.get()
                if msg is None:
                    break
                self_ref._speak_blocking(msg)
            except Exception as e:
                print(f"Speech worker error: {e}")

    def _enqueue(self, message: str):
        self._ensure_worker()
        self._speech_queue.put((message, self))

    def _speak_blocking(self, message):
        """Try edge-tts first if online, otherwise fall back to pyttsx3."""
        if self.backend == "edge" and _is_online():
            try:
                self._speak_edge(message)
                return
            except Exception as e:
                print(f"edge-tts failed, falling back to pyttsx3: {e}")
        # Fallback to pyttsx3
        try:
            self._speak_pyttsx3(message)
        except Exception as e:
            print(f"pyttsx3 speak error: {e}")

    def _speak_edge(self, message):
        """Use edge-tts to generate MP3, then playsound it (any backend)."""
        import edge_tts

        playsound_fn = _get_playsound()
        if playsound_fn is None:
            raise RuntimeError("No audio playback backend available "
                               "(install playsound, playsound3, or pygame)")

        # Create temp file in system temp dir (works with PyInstaller)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="srlta_tts_")
        os.close(tmp_fd)
        tmp_path = os.path.join(tempfile.gettempdir(), os.path.basename(tmp_path))

        try:
            async def _gen():
                comm = edge_tts.Communicate(message, voice=self.voice_name)
                await comm.save(tmp_path)

            asyncio.run(_gen())

            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                playsound_fn(tmp_path, block=True)
        finally:
            # Clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    def _speak_pyttsx3(self, message):
        """Use pyttsx3 to speak (offline fallback)."""
        try:
            eng = pyttsx3.init()
            if eng is None:
                return
            try:
                eng.setProperty("rate", self.rate)
                eng.setProperty("volume", self.volume)
            except Exception:
                pass
            self._apply_voice_to_engine(eng)
            eng.say(message)
            eng.runAndWait()
            try:
                eng.stop()
            except Exception:
                pass
        except Exception as e:
            print(f"pyttsx3 speak error: {e}")

    def _apply_voice_to_engine(self, eng):
        """Select a pyttsx3 voice matching self.voice_id."""
        try:
            voices = eng.getProperty("voices") or []
            if isinstance(self.voice_id, int):
                idx = self.voice_id
            else:
                # Try to parse "pyttsx3:N" format
                try:
                    _, idx_str = str(self.voice_id).split(":", 1)
                    idx = int(idx_str)
                except Exception:
                    idx = 0
            if 0 <= idx < len(voices):
                eng.setProperty("voice", voices[idx].id)
        except Exception as e:
            print(f"_apply_voice_to_engine error: {e}")

    @staticmethod
    def _parse_voice_id(voice_id):
        try:
            if isinstance(voice_id, int):
                return "pyttsx3", voice_id
            backend, idx = str(voice_id).split(":", 1)
            return backend, int(idx)
        except Exception:
            return "pyttsx3", 0

    # ------------------------------------------------------------------ #
    #  Lap Result Summary (Called after each lap)                         #
    # ------------------------------------------------------------------ #

    def say_lap_result(self, stats: dict, zones: list, corner_analysis: list = None,
                       lap_time: float = None, ref_time: float = None,
                       prev_time: float = None, compare_mode: str = "best"):
        """
        Post-lap voice summary.
        """
        mode = load_settings().get("mode", self.mode)
        total = stats["total_delta"]
        sectors = stats["sector_deltas"]

        if compare_mode == "previous" and prev_time is not None:
            ref_label = "your last lap"
        else:
            ref_label = "your best lap"

        messages = []

        if mode in ("sectors", "full"):
            if abs(total) < 0.05:
                messages.append(f"Pretty much the same as {ref_label}.")
            elif total < 0:
                messages.append(f"Nice, you were {abs(total):.1f} seconds quicker than {ref_label}.")
            else:
                messages.append(f"You were {abs(total):.1f} seconds slower than {ref_label}.")

        if mode in ("sectors", "full"):
            sector_items = list(sectors.items())
            if sector_items:
                best_sector = min(sector_items, key=lambda x: x[1])
                worst_sector = max(sector_items, key=lambda x: x[1])
                sector_names = {"sector_1": "1", "sector_2": "2", "sector_3": "3"}

                parts = []
                if best_sector[1] < -0.1:
                    parts.append(f"you gained {abs(best_sector[1]):.1f} in sector {sector_names[best_sector[0]]}")
                if worst_sector[1] > 0.1:
                    parts.append(f"lost {abs(worst_sector[1]):.1f} in sector {sector_names[worst_sector[0]]}")
                if parts:
                    messages.append("and ".join(parts) + ".")

        if mode != "off" and corner_analysis:
            major_corners = [c for c in corner_analysis
                            if 0.05 < c.get("time_lost", 0) <= 0.8
                            and abs(c.get("entry_speed_diff", 0)) < 20
                            and abs(c.get("exit_speed_diff", 0)) < 20]
            major_corners = sorted(major_corners, key=lambda c: c["time_lost"], reverse=True)

            if len(major_corners) >= 2:
                messages.append("Here's where you can improve.")
                for c in major_corners[:2]:
                    n = c["corner_number"]
                    tl = c["time_lost"]
                    brake_diff = c.get("brake_diff_m", 0)
                    exit_diff = c.get("exit_speed_diff", 0)
                    entry_diff = c.get("entry_speed_diff", 0)

                    if brake_diff >= 8:
                        messages.append(f"In turn {n}, you're braking about {brake_diff:.0f} meters too early, costing you {tl:.1f} seconds. You can brake a bit later there.")
                    elif brake_diff <= -8:
                        messages.append(f"In turn {n}, you're braking {abs(brake_diff):.0f} meters too late. Try getting on the brakes just a touch earlier to carry more speed through.")
                    elif exit_diff > 3:
                        messages.append(f"In turn {n}, you're {exit_diff:.0f} km/h slower on exit than you should be. Getting on the throttle earlier would save {tl:.1f} seconds.")
                    elif 3 < entry_diff < 15:
                        messages.append(f"In turn {n}, carry about {entry_diff:.0f} more km/h through the entry and you'll pick up {tl:.1f} seconds.")
                    else:
                        messages.append(f"In turn {n}, you're losing {tl:.1f} seconds. Focus on hitting the apex cleaner and getting back on the power sooner.")

                    line_dev = c.get("line_deviation_avg", 0)
                    line_dev_apex = c.get("line_deviation_apex", 0)
                    if line_dev > 1.0:
                        if line_dev_apex > 1.5:
                            messages.append(f"In turn {n}, you're running about {line_dev_apex:.0f} meters wide at the apex. Tighten your line there.")
                        elif line_dev > 1.0:
                            messages.append(f"In turn {n}, you're off the racing line by about {line_dev:.0f} meters. Try hitting the apex tighter.")

        full_message = " ".join(messages)
        self.say(full_message)

    # ------------------------------------------------------------------ #
    #  Settings                                                            #
    # ------------------------------------------------------------------ #

    def cycle_mode(self):
        idx = self.MODES.index(self.mode)
        self.mode = self.MODES[(idx + 1) % len(self.MODES)]
        self._save()
        print(f"  📢  Coaching mode → {self.mode.upper()}")

    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        self._save()
        state = "ON" if self.voice_enabled else "OFF"
        print(f"  🔊  Voice → {state}")

    def set_volume(self, value: float):
        self.volume = max(0.0, min(1.0, value))
        self._save()
        print(f"  🔉  Volume → {self.volume:.0%}")

    def set_rate(self, value: int):
        self.rate = max(100, min(300, value))
        self._save()
        print(f"  ⏩  Rate → {self.rate} wpm")

    def set_voice_id(self, voice_id):
        self.voice_id = voice_id
        self._save()
        print(f"  🗣  Voice → {voice_id}")

    def set_voice_name(self, voice_name: str):
        self.voice_name = voice_name
        self._save()
        print(f"  🗣  Voice name → {voice_name}")

    def set_backend(self, backend: str):
        if backend in ("edge", "pyttsx3"):
            self.backend = backend
            self._save()
            print(f"  🔊  Backend → {backend}")

    def set_compare_mode(self, mode: str):
        if mode in ("best", "previous"):
            self.compare_mode = mode
            self._save()
            print(f"  📊  Compare mode → {mode}")

    def print_status(self):
        print(f"\n  ── Voice Settings ──────────────────")
        print(f"  Voice:     {'ON' if self.voice_enabled else 'OFF'}")
        print(f"  Mode:      {self.mode.upper()}")
        print(f"  Compare:   {self.compare_mode}")
        print(f"  Backend:   {self.backend}")
        print(f"  Online:    {_is_online()}")
        print(f"  Volume:    {self.volume:.0%}")
        print(f"  Rate:      {self.rate} wpm")
        print(f"  Voice ID:  {self.voice_id}")
        print(f"  Voice:     {self.voice_name}")
        print(f"  ────────────────────────────────────\n")

    def _save(self):
        save_settings({
            "voice_enabled": self.voice_enabled,
            "mode":          self.mode,
            "compare_mode":  self.compare_mode,
            "rate":          self.rate,
            "volume":        self.volume,
            "voice_id":      self.voice_id,
            "voice_name":    self.voice_name,
            "backend":       self.backend,
        })

    def test(self):
        self.say("Sim Racing Lap Time Analyzer voice coaching active. Ready to race.")


