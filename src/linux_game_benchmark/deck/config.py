"""Deck settings (deck.json) and the folders the Deck service uses. Everything lives under $HOME."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from linux_game_benchmark.config.settings import settings
from linux_game_benchmark.deck.chord import DEFAULT_CHORD, parse_chord


def data_dir() -> Path:
    """~/.local/share/lgb/deck (LGB_DATA_DIR overrides, used by tests)."""
    base = os.environ.get("LGB_DATA_DIR") or os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "lgb")
    return Path(base) / "deck"


def log_dir() -> Path:
    return data_dir() / "logs"


def mangoapp_log_dir() -> Path:
    """Logs written by Steam's performance overlay (Game Mode): every game, also the OpenGL ones. Kept apart from `logs`."""
    return data_dir() / "mangoapp-logs"


def mangoapp_intake_dir() -> Path:
    """Where Steam's overlay program writes a log when nothing tells it otherwise: the home folder. The service moves the finished
    logs into `mangoapp_log_dir()` (and touches nothing else in the home folder)."""
    return Path(os.path.expanduser("~"))


def queue_dir() -> Path:
    return data_dir() / "queue"


def config_path() -> Path:
    return Path(settings.CONFIG_DIR) / "deck.json"


@dataclass
class DeckConfig:
    chord: str = DEFAULT_CHORD        # hold two buttons, press a third
    auto_upload: bool = True          # upload as soon as a recording is done
    record_seconds: float = 60.0      # one chord press records this long, then it finishes by itself
    min_seconds: float = 30.0         # shorter recordings are not accepted (server minimum)
    max_seconds: float = 300.0        # longest recording the server accepts
    cancel_window: float = 0.0        # >0: seconds after the end in which the chord still cancels the upload
    sound: bool = True                # beeps for start / stop / cancel / done / error

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "DeckConfig":
        path = path or config_path()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        known = {f.name for f in fields(cls)}
        config = cls(**{k: v for k, v in data.items() if k in known})
        try:
            parse_chord(config.chord)
        except ValueError:
            config.chord = DEFAULT_CHORD         # a hand-edited broken chord must not stop the service
        try:
            config.record_seconds = min(max(float(config.record_seconds), config.min_seconds), config.max_seconds)
        except (TypeError, ValueError):
            config.record_seconds = 60.0
        return config

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n")
        os.replace(tmp, path)
        return path
