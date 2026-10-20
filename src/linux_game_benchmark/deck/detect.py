"""Steam Deck detection: hardware model, SteamOS version, Game Mode vs Desktop Mode.

Everything reads plain files below a configurable root, so the logic can be tested
with a fake tree instead of a real Deck.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# DMI product / board names: Valve sets them to the codename of the model
_DMI_MODELS = {"jupiter": "LCD", "galileo": "OLED"}
# "model name" in /proc/cpuinfo
_CPU_MODELS = {"custom apu 0405": "LCD", "custom apu 0932": "OLED"}
# PCI device ids of the GPU (Van Gogh = LCD, Sephiroth = OLED)
_PCI_MODELS = {"0x163f": "LCD", "0x1435": "OLED"}

_DEVICE_CLASS = {"LCD": "steam_deck_lcd", "OLED": "steam_deck_oled"}


@dataclass(frozen=True)
class DeckInfo:
    is_deck: bool
    model: str = ""              # "LCD", "OLED" or "" when it is a Deck of unknown model
    steamos_version: str = ""    # e.g. "3.7.13" (empty when not SteamOS)
    game_mode: bool = False      # gamescope session running (heuristic)

    @property
    def device_class(self) -> Optional[str]:
        """Value sent to the server so Deck runs can be told apart (None = not a Deck)."""
        if not self.is_deck:
            return None
        return _DEVICE_CLASS.get(self.model, "steam_deck")

    @property
    def label(self) -> str:
        """Human label: "LCD", "OLED" or "Steam Deck" (kept for the GUI)."""
        return self.model or ("Steam Deck" if self.is_deck else "")


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _model_from_dmi(root: Path) -> str:
    for name in ("product_name", "board_name"):
        value = _read(root / "sys/devices/virtual/dmi/id" / name).lower()
        if value in _DMI_MODELS:
            return _DMI_MODELS[value]
    return ""


def _model_from_cpuinfo(root: Path) -> str:
    text = _read(root / "proc/cpuinfo").lower()
    for pattern, model in _CPU_MODELS.items():
        if pattern in text:
            return model
    return ""


def _model_from_pci(root: Path) -> str:
    drm = root / "sys/class/drm"
    try:
        cards = sorted(drm.glob("card*"))
    except OSError:
        return ""
    for card in cards:
        model = _PCI_MODELS.get(_read(card / "device" / "device").lower())
        if model:
            return model
    return ""


def _steamos_version(root: Path) -> str:
    fields = {}
    for line in _read(root / "etc/os-release").splitlines():
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip().strip('"')
    if fields.get("ID") != "steamos":
        return ""
    return fields.get("VERSION_ID") or fields.get("BUILD_ID") or ""


def _gamescope_running(root: Path) -> bool:
    try:
        entries = list((root / "proc").iterdir())
    except OSError:
        return False
    for entry in entries:
        if entry.name.isdigit() and _read(entry / "comm").startswith("gamescope"):
            return True
    return False


def detect_steam_deck(root: Path | str = "/") -> DeckInfo:
    """Cheap detection from /sys, /proc and /etc (no subprocess, no root needed)."""
    root = Path(root)
    model = _model_from_dmi(root) or _model_from_cpuinfo(root) or _model_from_pci(root)
    if not model:
        return DeckInfo(is_deck=False)
    return DeckInfo(
        is_deck=True,
        model=model,
        steamos_version=_steamos_version(root),
        game_mode=_gamescope_running(root),
    )
