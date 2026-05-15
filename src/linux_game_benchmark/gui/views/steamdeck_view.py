"""Steam Deck Auto-Mode view.

Configures MangoHud for continuous background logging so every game on a
Steam Deck (or any Linux gaming setup) records FPS / TDP / temps without
the user having to launch the CLI manually. New runs that show up in the
log directory can be auto-uploaded.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linux_game_benchmark.gui.constants import (
    ACCENT,
    BG_CARD,
    BG_SURFACE,
    BORDER,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)


# ----- Filesystem helpers / config writing ------------------------------------

MANGOHUD_DIR = Path(os.path.expanduser("~/.config/MangoHud"))
MANGOHUD_CONF = MANGOHUD_DIR / "MangoHud.conf"
ENV_DIR = Path(os.path.expanduser("~/.config/environment.d"))
ENV_FILE = ENV_DIR / "linuxgamebench.conf"
LGB_LOG_DIR = Path("/tmp/mangohud-bench-lgb")

_STEAMDECK_GPU_PATTERNS = (
    "custom apu 0405",
    "custom gpu 0405",
    "van gogh",
    "custom gpu 1435",
    "sephiroth",
)
_STEAMDECK_CPU_PATTERNS = ("custom apu 0405", "custom apu 0932")

MANGOHUD_TEMPLATE = """\
# Written by Linux Game Bench GUI - lines under the LGB marker are managed.
### LGB-MANAGED-START
output_folder={out_dir}
output_format=csv
autostart_log=1
log_interval=0

# Logged sensors (CSV) - the on-screen overlay below is intentionally minimal
fps
frametime
gpu_load
gpu_temp
gpu_junction_temp
gpu_core_clock
gpu_mem_clock
gpu_mem_temp
gpu_power
gpu_power_limit
gpu_voltage
gpu_fan
cpu_load
cpu_temp
cpu_mhz
cpu_power
core_load
ram
vram
swap
battery
battery_watt
battery_time
fan
throttling_status
io_read
io_write
resolution
refresh_rate

# Minimal overlay: tiny "FPS: xx" top-right
fps_only=1
position=top-right
font_size=14
background_alpha=0
no_small_font=1
text_outline=1
text_outline_thickness=1.2
### LGB-MANAGED-END
"""


def detect_steamdeck() -> tuple[bool, str]:
    """Cheap detection - reads /sys DMI and /proc/cpuinfo. Returns
    (is_deck, label). label is "LCD", "OLED" or "" / a hint string."""
    # /sys DMI is the most reliable on SteamOS
    try:
        product = (Path("/sys/devices/virtual/dmi/id/product_name")
                   .read_text(errors="replace").strip())
        if product:
            if "Jupiter" in product:
                return True, "LCD"
            if "Galileo" in product:
                return True, "OLED"
    except OSError:
        pass

    # Fallback: cpuinfo + GPU device strings
    cpuinfo = ""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="replace").lower()
    except OSError:
        pass
    for pat in _STEAMDECK_CPU_PATTERNS:
        if pat in cpuinfo:
            return True, "Steam Deck"

    # GPU - look at /sys/class/drm/card*/device/vendor + device
    for sysfs in Path("/sys/class/drm").glob("card*"):
        try:
            dev = (sysfs / "device" / "device").read_text().strip()
            if dev in ("0x163f", "0x1435"):  # Van Gogh / Sephiroth PCI ids
                return True, ("OLED" if dev == "0x1435" else "LCD")
        except OSError:
            continue

    return False, ""


def mangohud_is_managed() -> bool:
    if not MANGOHUD_CONF.exists():
        return False
    try:
        return "### LGB-MANAGED-START" in MANGOHUD_CONF.read_text(errors="replace")
    except OSError:
        return False


def write_mangohud_config() -> tuple[bool, str]:
    """Write the LGB-managed MangoHud config and the environment.d file
    that exposes MANGOHUD=1 to every user-session process."""
    try:
        MANGOHUD_DIR.mkdir(parents=True, exist_ok=True)
        LGB_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ENV_DIR.mkdir(parents=True, exist_ok=True)

        if MANGOHUD_CONF.exists() and not mangohud_is_managed():
            backup = MANGOHUD_CONF.with_suffix(f".conf.lgb-backup-{int(time.time())}")
            shutil.copy(MANGOHUD_CONF, backup)

        MANGOHUD_CONF.write_text(MANGOHUD_TEMPLATE.format(out_dir=LGB_LOG_DIR))
        ENV_FILE.write_text(
            "# Written by Linux Game Bench GUI\n"
            "MANGOHUD=1\n"
            f"MANGOHUD_CONFIGFILE={MANGOHUD_CONF}\n"
        )
        return True, "Configured. Restart your Deck once - then every game logs automatically."
    except Exception as e:
        return False, f"Setup failed: {e}"


def remove_mangohud_config() -> tuple[bool, str]:
    """Undo write_mangohud_config(): drop env file, restore most recent
    non-LGB backup if there is one, otherwise remove the file."""
    try:
        if ENV_FILE.exists():
            ENV_FILE.unlink()
        if MANGOHUD_CONF.exists() and mangohud_is_managed():
            backups = sorted(MANGOHUD_DIR.glob("MangoHud.conf.lgb-backup-*"))
            if backups:
                shutil.copy(backups[-1], MANGOHUD_CONF)
            else:
                MANGOHUD_CONF.unlink()
        return True, "LGB MangoHud config removed. Reboot to drop MANGOHUD=1."
    except Exception as e:
        return False, f"Teardown failed: {e}"


def latest_log_file() -> Optional[Path]:
    if not LGB_LOG_DIR.exists():
        return None
    files = sorted(LGB_LOG_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# ----- View widget -----------------------------------------------------------

class _Card(QFrame):
    """Reusable card container with title."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"color: {ACCENT}; font-size: 15px; font-weight: 700; background: transparent;"
            )
            self._layout.addWidget(lbl)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
    lbl.setWordWrap(True)
    return lbl


def _value(text: str, color: str = TEXT_PRIMARY) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: 15px; font-weight: 600; background: transparent;"
    )
    return lbl


class SteamDeckView(QWidget):
    """Steam Deck Auto-Mode setup + status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: 0; }}")

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(24, 20, 24, 20)
        inner_layout.setSpacing(16)

        # Heading
        header = QLabel("Steam Deck Auto-Mode")
        header.setProperty("class", "heading")
        header.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {TEXT_PRIMARY};")
        inner_layout.addWidget(header)

        subtitle = _muted(
            "Configure MangoHud to log every game automatically. Pair with the "
            "passive upload below and your runs land on linuxgamebench.com/steamdeck "
            "without any manual step."
        )
        inner_layout.addWidget(subtitle)

        # --- Hardware detection card --------------------------------------
        self._detection_card = _Card("Hardware")
        self._detection_row = QHBoxLayout()
        self._detection_row.setSpacing(10)
        det_wrap = QWidget()
        det_wrap.setLayout(self._detection_row)
        self._detection_card.add(det_wrap)
        self._detection_label = _value("Detecting...")
        self._detection_hint = _muted("")
        self._detection_row.addWidget(self._detection_label)
        self._detection_row.addStretch(1)
        self._detection_card.add(self._detection_hint)
        inner_layout.addWidget(self._detection_card)

        # --- Setup card ----------------------------------------------------
        setup_card = _Card("MangoHud Setup")
        self._status_label = _value("Checking...")
        setup_card.add(self._status_label)
        self._setup_help = _muted(
            "Writes ~/.config/MangoHud/MangoHud.conf with continuous logging "
            "and an environment.d entry so MangoHud loads into every game "
            "(Steam, Heroic, Lutris, native) after the next reboot. Any existing "
            "config is backed up to MangoHud.conf.lgb-backup-<timestamp>."
        )
        setup_card.add(self._setup_help)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._setup_btn = QPushButton("Enable Auto-Mode")
        self._setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_btn.clicked.connect(self._on_setup_click)
        btn_row.addWidget(self._setup_btn)

        self._teardown_btn = QPushButton("Disable")
        self._teardown_btn.setProperty("class", "secondary")
        self._teardown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._teardown_btn.clicked.connect(self._on_teardown_click)
        btn_row.addWidget(self._teardown_btn)

        btn_row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(btn_row)
        setup_card.add(wrap)
        inner_layout.addWidget(setup_card)

        # --- Status card ---------------------------------------------------
        status_card = _Card("Logging Status")
        self._log_path_label = _muted("...")
        status_card.add(self._log_path_label)
        self._log_size_label = _value("--", TEXT_SECONDARY)
        status_card.add(self._log_size_label)
        self._refresh_hint = _muted(
            "If 'logging' stays empty after a reboot, double-check that the "
            "game was started via Steam and that you rebooted at least once "
            "after the setup."
        )
        status_card.add(self._refresh_hint)
        inner_layout.addWidget(status_card)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Poll for state changes every 3s; cheap reads of filesystem
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(3000)
        self._refresh()

    # --- internal -----------------------------------------------------------

    def _on_setup_click(self) -> None:
        ok, msg = write_mangohud_config()
        self._status_label.setText(msg)
        self._status_label.setStyleSheet(
            f"color: {SUCCESS if ok else ERROR}; font-size: 15px; "
            f"font-weight: 600; background: transparent;"
        )
        self._refresh()

    def _on_teardown_click(self) -> None:
        ok, msg = remove_mangohud_config()
        self._status_label.setText(msg)
        self._status_label.setStyleSheet(
            f"color: {SUCCESS if ok else ERROR}; font-size: 15px; "
            f"font-weight: 600; background: transparent;"
        )
        self._refresh()

    def _refresh(self) -> None:
        is_deck, label = detect_steamdeck()
        if is_deck:
            self._detection_label.setText(f"✓ Steam Deck {label}".strip())
            self._detection_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 16px; font-weight: 700; background: transparent;"
            )
            self._detection_hint.setText(
                "We'll log all the Deck-specific sensors (battery watts, fan, "
                "junction temp, throttling). LCD vs OLED is detected from your APU."
            )
        else:
            self._detection_label.setText("Not a Steam Deck")
            self._detection_label.setStyleSheet(
                f"color: {WARNING}; font-size: 16px; font-weight: 700; background: transparent;"
            )
            self._detection_hint.setText(
                "Auto-Mode still works on any Linux gaming setup. The sensor set "
                "is just slightly less Deck-specific."
            )

        managed = mangohud_is_managed()
        env_present = ENV_FILE.exists()
        if managed and env_present:
            self._status_label.setText("✓ Active")
            self._status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 15px; font-weight: 600; background: transparent;"
            )
            self._teardown_btn.setEnabled(True)
            self._setup_btn.setText("Re-apply config")
        else:
            self._status_label.setText("Not configured")
            self._status_label.setStyleSheet(
                f"color: {WARNING}; font-size: 15px; font-weight: 600; background: transparent;"
            )
            self._teardown_btn.setEnabled(False)
            self._setup_btn.setText("Enable Auto-Mode")

        latest = latest_log_file()
        if latest:
            size_mb = latest.stat().st_size / 1024 / 1024
            self._log_path_label.setText(f"Latest log: {latest.name}")
            self._log_size_label.setText(f"{size_mb:.2f} MB - logging")
            self._log_size_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 15px; font-weight: 600; background: transparent;"
            )
        else:
            self._log_path_label.setText(f"Log directory: {LGB_LOG_DIR}")
            self._log_size_label.setText("No logs yet - launch a game first")
            self._log_size_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 15px; font-weight: 600; background: transparent;"
            )
