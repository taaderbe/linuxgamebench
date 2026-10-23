"""Everything the Steam Deck tab of the desktop app (and anyone else) wants to show, read in one go.

Plain data in, no Qt: the tab only paints this, and the unit tests can check it against a fake home folder.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from linux_game_benchmark.config.settings import settings
from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.chord import VIEW_HINT, GamepadReader, button_label
from linux_game_benchmark.deck.detect import detect_steam_deck
from linux_game_benchmark.deck.queue import Queue

STATUS_WORDS = {"pending": "waiting to upload", "uploaded": "uploaded", "failed": "failed", "uploading": "uploading"}


def site_url() -> str:
    """The website that belongs to the stage the app talks to (API address without /api/v1)."""
    base = settings.API_BASE_URL.rstrip("/")
    return base[:-len("/api/v1")] if base.endswith("/api/v1") else base


@dataclass
class Recording:
    id: str
    game: str
    seconds: float
    status: str          # pending / uploaded / failed
    url: str = ""
    error: str = ""


@dataclass
class DeckOverview:
    is_deck: bool = False
    model: str = ""                  # "LCD", "OLED" or ""
    device_name: str = ""            # "Steam Deck LCD", "ROG Ally" ... (empty when this is no handheld)
    steamos: str = ""
    game_mode: bool = False
    configured: bool = False         # MangoHud config + environment written
    service: str = "unknown"         # systemd state: active / inactive / failed / unknown
    chord: str = deck_config.DEFAULT_CHORD
    seconds: float = 60.0
    auto_upload: bool = True
    account: Optional[str] = None
    controllers: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    phase: str = ""                  # what the running recorder says: idle / logging / recording / ...
    message: str = ""
    recorder_age: Optional[float] = None
    recordings: list[Recording] = field(default_factory=list)   # newest first
    site: str = ""

    @property
    def ready(self) -> bool:
        """Configured and the service runs: only the chord is left to do."""
        return self.configured and self.service == "active"


def _recorder_status() -> tuple[str, str, Optional[float]]:
    try:
        info = json.loads((deck_config.data_dir() / "status.json").read_text())
    except (OSError, ValueError):
        return "", "", None
    age = max(0.0, time.time() - float(info.get("time", 0))) if info.get("time") else None
    return str(info.get("phase") or ""), str(info.get("message") or ""), age


def collect(scan_controllers: bool = True) -> DeckOverview:
    deck = detect_steam_deck()
    cfg = deck_config.DeckConfig.load()
    out = DeckOverview(
        is_deck=deck.is_deck, model=deck.model, device_name=deck.name, steamos=deck.steamos_version, game_mode=deck.game_mode,
        configured=deck_setup.is_managed(deck_setup.mangohud_conf_path()) and deck_setup.env_file_path().exists(),
        service=deck_setup.service_state(), chord=cfg.chord, seconds=cfg.record_seconds, auto_upload=cfg.auto_upload,
        site=site_url(),
    )
    try:
        from linux_game_benchmark.api.auth import get_current_session
        session = get_current_session()
        out.account = session.get_username() if session else None
    except Exception:
        out.account = None
    if scan_controllers:
        reader = GamepadReader()
        out.controllers = [path for path in reader.rescan()]
        out.denied = list(reader.denied)
        reader.close()
    out.phase, out.message, out.recorder_age = _recorder_status()
    try:
        items = Queue(deck_config.queue_dir()).items()
    except OSError:
        items = []
    for item in reversed(items[-5:]):
        meta = item.meta
        out.recordings.append(Recording(
            id=item.id, game=str(meta.get("game_name") or "Unknown game"), seconds=float(meta.get("seconds") or 0),
            status=item.status, url=str(meta.get("url") or ""), error=str(meta.get("error") or "")))
    return out


def chord_words(chord: str, capital: bool = False, hint: bool = False) -> str:
    """'LB+RB>VIEW' -> 'hold L1 + R1, then press VIEW' (the names the Deck prints on its buttons). With `hint` the VIEW button is
    described, because it is the one people do not find: 'VIEW (the small button left of the screen with two overlapping squares)'."""
    held, _, pressed = chord.partition(">")
    pressed_word = button_label(pressed)
    if hint and pressed_word.upper() == "VIEW":
        pressed_word = f"{pressed_word} ({VIEW_HINT})"
    return f"{'Hold' if capital else 'hold'} {' + '.join(button_label(p) for p in held.split('+') if p)}, then press {pressed_word}"
