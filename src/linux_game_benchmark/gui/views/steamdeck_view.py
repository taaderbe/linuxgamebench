"""Steam Deck view: one-click setup of the recorder (same code as `lgb deck setup`) and a status overview.

The recorder logs every game from the start (MangoHud flight recorder); a controller chord marks the
part to keep and uploads it. See linux_game_benchmark.deck.
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


# ----- Setup (shared with the CLI) ------------------------------------------------

from linux_game_benchmark.deck import config as deck_config  # noqa: E402
from linux_game_benchmark.deck import setup as deck_setup  # noqa: E402

LGB_LOG_DIR = deck_config.log_dir()


def detect_steamdeck() -> tuple[bool, str]:
    """(is_deck, label) with label "LCD", "OLED", "Steam Deck" or "" - see deck.detect."""
    from linux_game_benchmark.deck.detect import detect_steam_deck
    info = detect_steam_deck()
    return info.is_deck, info.label


def mangohud_is_managed() -> bool:
    return deck_setup.is_managed(deck_setup.mangohud_conf_path())


def write_mangohud_config() -> tuple[bool, str]:
    """Everything `lgb deck setup` does without questions: recorder config, environment, sounds, service."""
    try:
        deck_config.DeckConfig.load().save()
        deck_setup.write_mangohud_conf()
        deck_setup.write_env_file()
        deck_setup.ensure_sounds()
        ok, message = deck_setup.install_service()
        if not ok:
            return False, f"Recorder configured, but the background service failed: {message}"
        return True, "Done. Switch back to Game Mode - then every game is recorded and you start/stop with the controller chord."
    except Exception as e:
        return False, f"Setup failed: {e}"


def remove_mangohud_config() -> tuple[bool, str]:
    try:
        deck_setup.remove_all()
        return True, "Removed. Switch to Desktop Mode and back (or reboot) to stop MangoHud loading."
    except Exception as e:
        return False, f"Teardown failed: {e}"


def latest_log_file() -> Optional[Path]:
    from linux_game_benchmark.deck.game import newest_log
    log = newest_log(deck_config.log_dir(), max_age=24 * 3600)
    return log


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
    """Steam Deck recorder setup + status."""

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
        header = QLabel("Steam Deck")
        header.setProperty("class", "heading")
        header.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {TEXT_PRIMARY};")
        inner_layout.addWidget(header)

        subtitle = _muted(
            "Set up the recorder once: every game is logged in the background and you "
            "start/stop a recording with a controller chord (default: hold LB + RB, press VIEW). "
            "The recording is uploaded automatically unless you cancel it."
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
        setup_card = _Card("Recorder")
        self._status_label = _value("Checking...")
        setup_card.add(self._status_label)
        self._setup_help = _muted(
            "Writes ~/.config/MangoHud/MangoHud.conf (invisible overlay, logging on), "
            "an environment.d entry so MangoHud loads into your games, and a background "
            "service for the chord. Everything stays in your home folder. An existing "
            "MangoHud config is backed up to MangoHud.conf.lgb-backup-<timestamp>. "
            "Switch to Game Mode afterwards (no reboot needed)."
        )
        setup_card.add(self._setup_help)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._setup_btn = QPushButton("Set up recorder")
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
            "If 'logging' stays empty, start a game from Game Mode once after the setup. "
            "More details: run 'lgb deck status' in a terminal."
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
                "Deck runs are tagged as Steam Deck and shown in their own category "
                "on the website (not mixed with desktop PCs)."
            )
        else:
            self._detection_label.setText("Not a Steam Deck")
            self._detection_label.setStyleSheet(
                f"color: {WARNING}; font-size: 16px; font-weight: 700; background: transparent;"
            )
            self._detection_hint.setText(
                "The recorder also works on a normal Linux PC, but only a real Steam Deck "
                "is tagged as Steam Deck."
            )

        managed = mangohud_is_managed()
        env_present = deck_setup.env_file_path().exists()
        if managed and env_present:
            state = deck_setup.service_state()
            self._status_label.setText("✓ Active" if state == "active" else f"Configured - service is {state}")
            self._status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 15px; font-weight: 600; background: transparent;"
            )
            self._teardown_btn.setEnabled(True)
            self._setup_btn.setText("Repair / re-apply")
        else:
            self._status_label.setText("Not configured")
            self._status_label.setStyleSheet(
                f"color: {WARNING}; font-size: 15px; font-weight: 600; background: transparent;"
            )
            self._teardown_btn.setEnabled(False)
            self._setup_btn.setText("Set up recorder")

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
