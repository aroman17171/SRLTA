import json
import sys
from pathlib import Path

DEFAULTS = {
    "voice_enabled": True,
    "mode": "full",       # full | corners | sectors | off
    "compare_mode": "best", # "best" or "previous"
    "rate": 185,
    "volume": 1.0,
    "voice_id": 0,        # pyttsx3 voice index (fallback)
    "voice_name": "en-US-AndrewNeural",  # edge-tts voice name
    "backend": "edge",    # "edge" or "pyttsx3"
}



def _settings_path() -> Path:
    """Resolve path relative to EXE when frozen, or CWD in dev."""
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(".")
    return base / "data" / "voice_settings.json"


def load() -> dict:
    path = _settings_path()
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return DEFAULTS.copy()


def save(settings: dict):
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)