"""Handheld detection (the Steam Deck first): hardware model, SteamOS version, Game Mode vs Desktop Mode.

Everything reads plain files below a configurable root, so the logic can be tested
with a fake tree instead of a real Deck.

Other handhelds (ROG Ally, Legion Go, MSI Claw, ...) are recognised by the vendor and product name the firmware reports
(DMI) - the same table the server uses (lgb_steamdeck.HANDHELDS in the server repo; keep both in step). Only the Deck
is verified on real hardware; the rest is matched on the strings those devices are known to report.
"""

from __future__ import annotations

import re
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
class Handheld:
    key: str            # the device_class the server uses
    label: str
    vendor: str         # regex on the DMI vendor (lower case)
    product: str        # regex on DMI product name + version (lower case)


# Order matters: the specific model before its family ("Ally X" before "Ally"). Same table as the server's.
HANDHELDS = (
    Handheld("rog_xbox_ally", "ROG Xbox Ally", r"asus", r"xbox ally|rc73[xy]a"),
    Handheld("rog_ally_x", "ROG Ally X", r"asus", r"rog ally x|rc72la"),
    Handheld("rog_ally", "ROG Ally", r"asus", r"rog ally|rc71l"),
    Handheld("legion_go_s", "Legion Go S", r"lenovo", r"legion go s\b|\b83(?:l3|n6|q2|q3)\b"),
    Handheld("legion_go_2", "Legion Go 2", r"lenovo", r"legion go 2\b"),
    Handheld("legion_go", "Legion Go", r"lenovo", r"legion go\b|\b83e1\b"),
    Handheld("msi_claw", "MSI Claw", r"micro-star|\bmsi\b", r"\bclaw\b"),
    Handheld("ayaneo", "AYANEO", r"ayaneo|aya neo|ayadevice", r"."),
    Handheld("gpd", "GPD", r"^gpd\b", r"."),
    Handheld("onexplayer", "ONEXPLAYER", r"one-?netbook|onexplayer", r"."),
)


@dataclass(frozen=True)
class DeckInfo:
    """A supported handheld. `is_deck` is True for the Steam Deck and for every other handheld in HANDHELDS
    (the name stays from the time the Deck was the only one); `valve` tells them apart."""
    is_deck: bool
    model: str = ""              # Steam Deck: "LCD", "OLED" or "" when it is a Deck of unknown model
    steamos_version: str = ""    # e.g. "3.7.13" (empty when not SteamOS)
    game_mode: bool = False      # gamescope session running (heuristic)
    handheld: str = ""           # key of another handheld ("rog_ally"); empty for the Steam Deck
    handheld_label: str = ""     # "ROG Ally"
    vendor: str = ""             # DMI strings, sent to the server (it makes the final call)
    product: str = ""
    version: str = ""

    @property
    def valve(self) -> bool:
        return self.is_deck and not self.handheld

    @property
    def device_class(self) -> Optional[str]:
        """Value sent to the server so handheld runs can be told apart (None = not a handheld)."""
        if not self.is_deck:
            return None
        if self.handheld:
            return self.handheld
        return _DEVICE_CLASS.get(self.model, "steam_deck")

    @property
    def label(self) -> str:
        """Short human label: "LCD", "OLED", "Steam Deck" or the handheld's name (kept for the GUI)."""
        if self.handheld:
            return self.handheld_label
        return self.model or ("Steam Deck" if self.is_deck else "")

    @property
    def name(self) -> str:
        """Full name for messages: "Steam Deck LCD", "ROG Ally" or "" when this is no handheld."""
        if not self.is_deck:
            return ""
        return self.handheld_label if self.handheld else f"Steam Deck {self.model}".strip()


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


def read_dmi(root: Path) -> tuple[str, str, str]:
    """(vendor, product, version) as the firmware reports them - plain text, bounded, no serial numbers."""
    base = root / "sys/devices/virtual/dmi/id"
    return tuple(re.sub(r"\s+", " ", _read(base / name))[:80] for name in ("sys_vendor", "product_name", "product_version"))


def match_handheld(vendor: str, product: str, version: str = "") -> Optional[Handheld]:
    vendor, text = vendor.lower().strip(), f"{product} {version}".lower().strip()
    if not vendor or not text:
        return None
    for handheld in HANDHELDS:
        if re.search(handheld.vendor, vendor) and re.search(handheld.product, text):
            return handheld
    return None


def detect_steam_deck(root: Path | str = "/") -> DeckInfo:
    """Cheap detection from /sys, /proc and /etc (no subprocess, no root needed). The Steam Deck first, then the
    other handhelds by their DMI vendor and product."""
    root = Path(root)
    vendor, product, version = read_dmi(root)
    model = _model_from_dmi(root) or _model_from_cpuinfo(root) or _model_from_pci(root)
    if model:
        return DeckInfo(is_deck=True, model=model, steamos_version=_steamos_version(root),
                        game_mode=_gamescope_running(root), vendor=vendor, product=product, version=version)
    other = match_handheld(vendor, product, version)
    if other:
        return DeckInfo(is_deck=True, steamos_version=_steamos_version(root), game_mode=_gamescope_running(root),
                        handheld=other.key, handheld_label=other.label, vendor=vendor, product=product, version=version)
    return DeckInfo(is_deck=False)
