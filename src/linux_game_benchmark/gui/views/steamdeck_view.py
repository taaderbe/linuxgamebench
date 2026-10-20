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
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import overview as deck_overview
from linux_game_benchmark.deck import pairing
from linux_game_benchmark.deck import results as deck_results
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.gui.constants import (
    ACCENT,
    BG_CARD,
    BORDER,
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


class _Job(QThread):
    """Runs one blocking call (a web request) off the UI thread; `done(result, error_text)`."""

    done = Signal(object, str)

    def __init__(self, func, *args, parent=None) -> None:
        super().__init__(parent)
        self._func, self._args = func, args

    def run(self) -> None:
        try:
            self.done.emit(self._func(*self._args), "")
        except Exception as exc:                                    # offline, server error, bad JSON: all just a message
            self.done.emit(None, str(exc) or exc.__class__.__name__)


_LEVEL_COLOR = {"good": SUCCESS, "mid": WARNING, "low": ERROR}


def _chip(text: str, checked: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setProperty("class", "secondary")
    button.setStyleSheet(
        f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; border: 1px solid {BORDER}; border-radius: 14px; "
        f"padding: 4px 14px; font-weight: 600; min-height: 22px; }}"
        f"QPushButton:checked {{ background: {ACCENT}; color: #09090f; border-color: {ACCENT}; }}"
        f"QPushButton:hover:!checked {{ border-color: {ACCENT}; color: {ACCENT}; }}")
    return button


class _GameRow(QFrame):
    """One game of the results list: a header that opens to the single runs (fetched when it is opened first)."""

    def __init__(self, row: dict, view: "SteamDeckView") -> None:
        super().__init__()
        self.setProperty("class", "card")
        self._row, self._view, self._loaded, self._job = row, view, False, None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._head = QPushButton()
        self._head.setCursor(Qt.CursorShape.PointingHandCursor)
        self._head.setStyleSheet("QPushButton { background: transparent; border: 0; text-align: left; padding: 0; }")
        self._head.setMinimumHeight(58)
        self._head.clicked.connect(self._toggle)
        line = QHBoxLayout(self._head)
        line.setContentsMargins(16, 8, 16, 8)
        line.setSpacing(14)
        name = QLabel(row["name"])
        name.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 700; background: transparent;")
        models = QLabel("  ".join(f"{deck_results.MODELS.get(k, k)} {v}" for k, v in row["models"].items()) if self._view.model == "all" else "")
        models.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; background: transparent;")
        fps = QLabel(f"{round(row['fps'])}")
        fps.setStyleSheet(f"color: {_LEVEL_COLOR[deck_results.fps_level(row['fps'])]}; font-size: 20px; font-weight: 800; background: transparent;")
        unit = QLabel("avg FPS")
        unit.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        runs = QLabel(f"{row['runs']} run{'s' if row['runs'] != 1 else ''}")
        runs.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        self._chev = QLabel(">")
        self._chev.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 16px; font-weight: 700; background: transparent;")
        for label in (name, models, fps, unit, runs, self._chev):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        line.addWidget(name, 1)
        line.addWidget(models)
        line.addWidget(fps)
        line.addWidget(unit)
        line.addWidget(runs)
        line.addWidget(self._chev)
        outer.addWidget(self._head)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(16, 0, 16, 12)
        self._body_layout.setSpacing(4)
        self._body.hide()
        outer.addWidget(self._body)

    def _toggle(self) -> None:
        opening = self._body.isHidden()
        self._body.setVisible(opening)
        self._chev.setText("v" if opening else ">")
        if opening and not self._loaded:
            self._loaded = True
            self._body_layout.addWidget(_text("Loading runs...", color=TEXT_MUTED))
            self._job = _Job(deck_results.fetch_runs, self._row["name"], parent=self)
            self._job.done.connect(self._fill)
            self._job.start()

    def _fill(self, runs, error: str) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if error:
            self._loaded = False
            self._body_layout.addWidget(_text(f"Could not load the runs ({error}). Close and open the game to retry.", color=WARNING))
            return
        lines = deck_results.runs_for(runs, self._view.model)
        if not lines:
            self._body_layout.addWidget(_text("No runs for this model yet.", color=TEXT_MUTED))
        for run in lines:
            text = (f"{run['date']}  -  {run['model']}  -  {run['resolution']}  -  {run['fps']} FPS (1% low {run['low1']})"
                    + (f"  -  {run['power']}" if run["power"] else "") + f"  -  {run['player']}")
            label = _text(text, color=TEXT_PRIMARY, size=12)
            line = QWidget()
            line_layout = QHBoxLayout(line)
            line_layout.setContentsMargins(0, 0, 0, 0)
            line_layout.setSpacing(10)
            line_layout.addWidget(label, 1)                       # the text takes the room, the button stays at the right edge
            if run["id"]:
                line_layout.addWidget(_button("Open", lambda _=False, i=run["id"]: _open(f"{self._view.site}/run/{i}"), secondary=True))
            self._body_layout.addWidget(line)


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

        self.site = deck_overview.site_url()
        self.model = "all"                          # the results filter: all / steam_deck_lcd / steam_deck_oled
        self._sort = "fps"
        self._summary: Optional[dict] = None
        self._summary_job: Optional[_Job] = None
        self._rows: list[_GameRow] = []

        head = QWidget()
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(24, 20, 24, 0)
        head_layout.setSpacing(10)
        title = QLabel("Steam Deck")
        title.setProperty("class", "heading")
        title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {TEXT_PRIMARY};")
        head_layout.addWidget(title)
        head_layout.addWidget(_text("Record a minute of any game with a controller chord. The run uploads by itself and shows up "
                                    "in its own Steam Deck category on the website - not mixed with desktop PCs."))
        self._tab_results = _chip("Results", True)
        self._tab_device = _chip("This device")
        tabs = QButtonGroup(self)
        tabs.setExclusive(True)
        for button in (self._tab_results, self._tab_device):
            tabs.addButton(button)
        self._tab_results.clicked.connect(lambda: self._show_page(0))
        self._tab_device.clicked.connect(lambda: self._show_page(1))
        head_layout.addWidget(_row(self._tab_results, self._tab_device))

        self._stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(24, 16, 24, 20)
        column.setSpacing(16)

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
        runs.add(_row(_button("Results on the website", lambda: _open(self._site() + "/steamdeck"), secondary=True)))
        column.addWidget(runs)

        column.addStretch(1)
        scroll.setWidget(inner)

        self._stack.addWidget(self._build_results_page())      # 0: what everybody recorded (same as the website)
        self._stack.addWidget(scroll)                          # 1: this device
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(head)
        outer.addWidget(self._stack, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(4000)
        self._refresh()
        first = deck_overview.collect(scan_controllers=False)
        self._show_page(1 if first.is_deck and not first.ready else 0)       # a Deck that is not set up starts at the setup
        self._load_summary()

    def _show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        (self._tab_device if index else self._tab_results).setChecked(True)

    # --- results (the website's /steamdeck) ------------------------------------

    def _build_results_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(24, 16, 24, 20)
        column.setSpacing(14)

        self._stats_box = QHBoxLayout()
        self._stats_box.setSpacing(10)
        stats_wrap = QWidget()
        stats_wrap.setLayout(self._stats_box)
        column.addWidget(stats_wrap)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._model_group = QButtonGroup(self)
        for label, key in (("All", "all"), ("LCD", "steam_deck_lcd"), ("OLED", "steam_deck_oled")):
            chip = _chip(label, key == "all")
            chip.clicked.connect(lambda _=False, k=key: self._set_model(k))
            self._model_group.addButton(chip)
            controls.addWidget(chip)
        controls.addSpacing(12)
        self._sort_group = QButtonGroup(self)
        for key in deck_results.SORTS:
            chip = _chip(deck_results.SORT_LABELS[key], key == "fps")
            chip.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self._sort_group.addButton(chip)
            controls.addWidget(chip)
        controls.addSpacing(12)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search games...")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(200)
        self._search.textChanged.connect(lambda _=None: self._render_games())
        controls.addWidget(self._search, 1)
        controls_wrap = QWidget()
        controls_wrap.setLayout(controls)
        column.addWidget(controls_wrap)

        self._results_msg = _text("Loading the Steam Deck results...", color=TEXT_MUTED)
        column.addWidget(self._results_msg)
        self._games_box = QVBoxLayout()
        self._games_box.setSpacing(8)
        games_wrap = QWidget()
        games_wrap.setLayout(self._games_box)
        column.addWidget(games_wrap)
        column.addWidget(_row(_button("Refresh", self._load_summary, secondary=True),
                              _button("Open on the website", lambda: _open(self.site + "/steamdeck"), secondary=True)))
        column.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _set_model(self, key: str) -> None:
        self.model = key
        self._render_games()

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self._render_games()

    def _load_summary(self) -> None:
        if self._summary_job is not None and self._summary_job.isRunning():
            return
        self.site = deck_overview.site_url()
        self._results_msg.setText("Loading the Steam Deck results...")
        self._results_msg.show()
        self._summary_job = _Job(deck_results.fetch_summary, parent=self)
        self._summary_job.done.connect(self._on_summary)
        self._summary_job.start()

    def _on_summary(self, data, error: str) -> None:
        if error or not isinstance(data, dict):
            self._results_msg.setText(f"The results could not be loaded ({error or 'unexpected answer'}). Check your connection and press Refresh.")
            _style(self._results_msg, WARNING)
            return
        self._summary = data
        while self._stats_box.count():
            item = self._stats_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for label, value in deck_results.stats(data):
            card = QFrame()
            card.setProperty("class", "card")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 8, 14, 8)
            box.setSpacing(0)
            number = QLabel(value)
            number.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 800; background: transparent;")
            caption = QLabel(label.upper())
            caption.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; background: transparent;")
            box.addWidget(number)
            box.addWidget(caption)
            self._stats_box.addWidget(card)
        self._stats_box.addStretch(1)
        self._render_games()

    def _render_games(self) -> None:
        while self._games_box.count():
            item = self._games_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = []
        if self._summary is None:
            return
        rows = deck_results.games(self._summary, self.model, self._search.text(), self._sort)
        if not rows:
            self._results_msg.setText("No Deck runs yet - be the first! Set up your Deck on the 'This device' tab."
                                      if not self._summary.get("runs") else "No games match this filter.")
            _style(self._results_msg, TEXT_MUTED)
            self._results_msg.show()
            return
        self._results_msg.hide()
        for row in rows:
            widget = _GameRow(row, self)
            self._rows.append(widget)
            self._games_box.addWidget(widget)

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
