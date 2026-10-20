"""Steam Deck tab: is this a Deck, is the recorder set up and running, how to record, what happened to the last runs.

The setup is the same code as `lgb deck setup` (linux_game_benchmark.deck); what the tab shows comes from
linux_game_benchmark.deck.overview, so the numbers here and in `lgb deck status` always agree.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import overview as deck_overview
from linux_game_benchmark.deck import pairing
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.gui.constants import (
    ACCENT,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)


def detect_steamdeck() -> tuple[bool, str]:
    """(is_deck, label) with label "LCD", "OLED", "Steam Deck" or "" - see deck.detect."""
    from linux_game_benchmark.deck.detect import detect_steam_deck
    info = detect_steam_deck()
    return info.is_deck, info.label


def run_setup() -> tuple[bool, str]:
    """Everything `lgb deck setup` does without questions: recorder config, environment, sounds, service."""
    try:
        deck_config.DeckConfig.load().save()
        deck_setup.write_mangohud_conf()
        deck_setup.write_env_file()
        deck_setup.ensure_sounds()
        ok, message = deck_setup.install_service()
        if not ok:
            return False, f"The recorder is configured, but the background service did not start: {message}"
        return True, "Set up. Switch to Game Mode - from now on you record with the controller chord."
    except Exception as exc:                                        # a broken home folder must not crash the app
        return False, f"Setup failed: {exc}"


def run_teardown() -> tuple[bool, str]:
    try:
        deck_setup.remove_all()
        return True, "Removed. Switch to Desktop Mode and back (or reboot) to stop MangoHud loading. Your recordings stay."
    except Exception as exc:
        return False, f"Removing failed: {exc}"


class _PairWorker(QThread):
    """Asks the server for a code, then waits until it is approved on a phone or PC (no password on the Deck)."""

    code = Signal(str, str)           # user code, link that already contains the code
    finished_ok = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        def show(info: dict) -> None:
            self.code.emit(info["user_code"], info.get("verification_url_complete") or info["verification_url"])

        def sleep(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end and not self._stop:
                time.sleep(0.2)
            if self._stop:
                raise pairing.PairingError("cancelled")

        try:
            session = pairing.pair(show, sleep=sleep)
        except pairing.PairingError as exc:
            self.finished_ok.emit(False, str(exc))
            return
        self.finished_ok.emit(True, session.get_username())


class _Card(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        label = QLabel(title)
        label.setStyleSheet(f"color: {ACCENT}; font-size: 15px; font-weight: 700; background: transparent;")
        self._layout.addWidget(label)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


def _style(label: QLabel, color: str, size: int = 13, bold: bool = False) -> None:
    label.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: {700 if bold else 400}; background: transparent;")


def _text(text: str = "", color: str = TEXT_SECONDARY, size: int = 13, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    _style(label, color, size, bold)
    return label


def _put(label: QLabel, text: str) -> None:
    """Set the text; an empty label is hidden so it does not leave a gap in its card."""
    label.setText(text)
    label.setVisible(bool(text))


def _row(*widgets: QWidget) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return box


def _button(text: str, handler, secondary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if secondary:
        button.setProperty("class", "secondary")
    button.clicked.connect(handler)
    return button


def _open(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class SteamDeckView(QWidget):
    """Steam Deck: hardware, recorder, account, how to record, latest recordings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: Optional[deck_overview.DeckOverview] = None
        self._pair_worker: Optional[_PairWorker] = None
        self._report_until = 0.0            # the answer to a button click stays visible for a while

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(24, 20, 24, 20)
        column.setSpacing(16)

        title = QLabel("Steam Deck")
        title.setProperty("class", "heading")
        title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {TEXT_PRIMARY};")
        column.addWidget(title)
        column.addWidget(_text("Record a minute of any game with a controller chord. The run uploads by itself and shows up "
                               "in its own Steam Deck category on the website - not mixed with desktop PCs."))

        # --- this device ---------------------------------------------------
        device = _Card("This device")
        self._device_line = _text(size=16, bold=True)
        self._device_hint = _text()
        self._install_line = _text(color=TEXT_PRIMARY)
        self._install_row = _row(_button("Copy install command", self._copy_install, secondary=True),
                                 _button("Open the guide", lambda: _open(self._site() + "/faq.html#steam-deck"), secondary=True))
        for widget in (self._device_line, self._device_hint, self._install_line, self._install_row):
            device.add(widget)
        column.addWidget(device)

        # --- recorder ------------------------------------------------------
        recorder = _Card("Recorder")
        self._recorder_line = _text(size=15, bold=True)
        self._recorder_facts = _text()
        self._recorder_msg = _text(color=TEXT_MUTED)
        self._recorder_msg.hide()
        self._setup_btn = _button("Set up recorder", self._on_setup)
        self._teardown_btn = _button("Disable", self._on_teardown, secondary=True)
        for widget in (self._recorder_line, self._recorder_facts, self._recorder_msg, _row(self._setup_btn, self._teardown_btn),
                       _text("Setup writes a MangoHud config (invisible overlay, logging on), an environment entry so MangoHud "
                             "loads into your games and a background service for the chord. Everything stays in your home "
                             "folder; an existing MangoHud config is backed up first. No reboot needed.", color=TEXT_MUTED, size=12)):
            recorder.add(widget)
        column.addWidget(recorder)

        # --- account -------------------------------------------------------
        account = _Card("Account")
        self._account_line = _text(size=15, bold=True)
        self._pair_code = _text(color=TEXT_PRIMARY, size=22, bold=True)
        self._pair_hint = _text()
        self._pair_code.hide()
        self._pair_hint.hide()
        self._link_btn = _button("Link account", self._on_link)
        for widget in (self._account_line, self._pair_code, self._pair_hint, _row(self._link_btn)):
            account.add(widget)
        column.addWidget(account)

        # --- how to record -------------------------------------------------
        how = _Card("How to record")
        self._how_text = _text(color=TEXT_PRIMARY)
        how.add(self._how_text)
        how.add(_text("You hear a short rising tone when the recording starts and a falling one when it is done. Change the "
                      "buttons or the length with 'lgb deck chord' and 'lgb deck setup --seconds'.", color=TEXT_MUTED, size=12))
        column.addWidget(how)

        # --- recordings ----------------------------------------------------
        runs = _Card("Latest recordings")
        self._runs_box = QVBoxLayout()
        self._runs_box.setSpacing(6)
        runs_wrap = QWidget()
        runs_wrap.setLayout(self._runs_box)
        runs.add(runs_wrap)
        runs.add(_row(_button("Steam Deck results", lambda: _open(self._site() + "/steamdeck"), secondary=True)))
        column.addWidget(runs)

        column.addStretch(1)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(4000)
        self._refresh()

    # --- helpers -------------------------------------------------------------

    def _site(self) -> str:
        return self._state.site if self._state else deck_overview.site_url()

    def _install_command(self) -> str:
        return f"curl -fsSL {self._site()}/deck | bash"

    def _copy_install(self) -> None:
        QApplication.clipboard().setText(self._install_command())

    def _pairing_active(self) -> bool:
        return self._pair_worker is not None and self._pair_worker.isRunning()

    # --- actions ---------------------------------------------------------------

    def _report(self, ok: bool, message: str) -> None:
        _put(self._recorder_msg, message)
        _style(self._recorder_msg, SUCCESS if ok else ERROR)
        self._report_until = time.monotonic() + 20
        self._refresh()

    def _on_setup(self) -> None:
        self._report(*run_setup())

    def _on_teardown(self) -> None:
        self._report(*run_teardown())

    def _on_link(self) -> None:
        if self._pairing_active():
            self._pair_worker.stop()
            return
        worker = _PairWorker(self)
        worker.code.connect(self._on_pair_code)
        worker.finished_ok.connect(self._on_pair_done)
        self._pair_worker = worker
        self._link_btn.setText("Cancel")
        _put(self._pair_hint, "Asking the server for a code...")
        _style(self._pair_hint, TEXT_SECONDARY)
        worker.start()

    def _on_pair_code(self, code: str, url: str) -> None:
        _put(self._pair_code, code)
        _put(self._pair_hint, "A browser page opens. Log in there and confirm this code - or open the link on your phone.")
        _open(url)

    def _on_pair_done(self, ok: bool, text: str) -> None:
        _put(self._pair_code, "")
        _put(self._pair_hint, f"Linked as {text}." if ok else f"Not linked: {text}")
        _style(self._pair_hint, SUCCESS if ok else WARNING)
        self._refresh()

    # --- painting ---------------------------------------------------------------

    def _refresh(self) -> None:
        state = deck_overview.collect()
        self._state = state

        if state.is_deck:
            line = f"Steam Deck {state.model}".strip() + (f"  (SteamOS {state.steamos})" if state.steamos else "")
            self._device_line.setText(line + (" - Game Mode" if state.game_mode else ""))
            _style(self._device_line, SUCCESS, 16, True)
            self._device_hint.setText("Deck runs are tagged automatically and kept apart from desktop PCs on the website.")
        else:
            self._device_line.setText("This computer is not a Steam Deck")
            _style(self._device_line, WARNING, 16, True)
            self._device_hint.setText("The recorder is made for the Deck. To set up a Deck, run this line in a terminal in its Desktop Mode:")
            self._install_line.setText(self._install_command())
        self._install_line.setVisible(not state.is_deck)
        self._install_row.setVisible(not state.is_deck)

        if state.ready:
            self._recorder_line.setText("Ready - waiting for the chord")
            _style(self._recorder_line, SUCCESS, 15, True)
        else:
            self._recorder_line.setText(f"Set up, but the background service is {state.service}" if state.configured else "Not set up")
            _style(self._recorder_line, WARNING, 15, True)
        pads = (f"controller found ({len(state.controllers)})" if state.controllers
                else ("no permission to read the controller" if state.denied else "no controller found yet"))
        self._recorder_facts.setText(f"Length {state.seconds:.0f} s  -  auto-upload {'on' if state.auto_upload else 'off'}  -  {pads}")
        if state.phase and state.recorder_age is not None and state.recorder_age < 30 and time.monotonic() > self._report_until:
            _put(self._recorder_msg, f"Recorder: {state.phase}" + (f" - {state.message}" if state.message else ""))
            _style(self._recorder_msg, TEXT_MUTED)
        self._setup_btn.setText("Repair / re-apply" if state.configured else "Set up recorder")
        self._teardown_btn.setEnabled(state.configured)

        if state.account:
            self._account_line.setText(f"Linked as {state.account}")
            _style(self._account_line, SUCCESS, 15, True)
        else:
            self._account_line.setText("Not linked - recordings upload anonymously")
            _style(self._account_line, WARNING, 15, True)
        self._link_btn.setText("Cancel" if self._pairing_active() else ("Link another account" if state.account else "Link account"))

        self._how_text.setText(
            "1. Start a game (in Game Mode).\n"
            f"2. {deck_overview.chord_words(state.chord, capital=True)}.\n"
            f"3. Play. After {state.seconds:.0f} seconds the recording ends by itself"
            f"{' and uploads' if state.auto_upload else ''} - the same chord ends it earlier (at least 30 s).")

        while self._runs_box.count():
            item = self._runs_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not state.recordings:
            self._runs_box.addWidget(_text("Nothing recorded yet.", color=TEXT_MUTED))
        for rec in state.recordings:
            words = deck_overview.STATUS_WORDS.get(rec.status, rec.status)
            color = SUCCESS if rec.status == "uploaded" else (ERROR if rec.status == "failed" else TEXT_SECONDARY)
            line = _text(f"{rec.game}  -  {rec.seconds:.0f} s  -  {words}" + (f"  ({rec.error})" if rec.error else ""), color=color)
            self._runs_box.addWidget(_row(line, _button("Open run", lambda _=False, u=rec.url: _open(u), secondary=True)) if rec.url else line)
