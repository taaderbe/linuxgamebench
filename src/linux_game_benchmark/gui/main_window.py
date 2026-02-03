"""Main window with sidebar navigation and stacked content area."""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QStackedWidget, QLabel, QFrame, QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QShortcut, QKeySequence

from linux_game_benchmark.gui.constants import (
    MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
    BG_DARK, ACCENT, TEXT_SECONDARY, TEXT_MUTED, SUCCESS, BG_SIDEBAR,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import (
    AuthVerifyWorker, UpdateCheckWorker, SteamScanWorker,
)
from linux_game_benchmark.gui.widgets.auth_status import AuthStatusWidget
from linux_game_benchmark.gui.widgets.toast import ToastManager

STATE_FILE = Path.home() / ".config" / "lgb" / "gui_state.json"

# Sidebar navigation items: (icon_text, label, view_index)
NAV_ITEMS = [
    ("\U0001F3AE", "Games"),          # index 0
    ("\U0001F3AF", "Benchmark"),      # index 1
    ("\U0001F4CA", "My Benchmarks"),  # index 2
    ("\U0001F5A5", "System Info"),    # index 3
    ("\u2699",     "Settings"),       # index 4
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linux Game Bench")
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self._nav_buttons: list[QPushButton] = []
        self._signals = AppSignals.instance()

        self._build_ui()
        self._setup_shortcuts()
        self._setup_toasts()
        self._restore_state()
        self._check_auth()
        self._check_version()
        self._scan_games_startup()

    # --- UI Construction ---

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG_DARK};")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        # Content area
        self._stack = QStackedWidget()
        self._stack.setObjectName("content_area")
        root_layout.addWidget(self._stack, 1)

        # Add views
        from linux_game_benchmark.gui.views import (
            GamesView, BenchmarkView, MyBenchmarksView,
            SystemInfoView, SettingsView,
        )
        self._stack.addWidget(GamesView())
        self._stack.addWidget(BenchmarkView())
        self._stack.addWidget(MyBenchmarksView())
        self._stack.addWidget(SystemInfoView())
        self._stack.addWidget(SettingsView())

        # Select first tab
        self._select_nav(0)

        # Navigate to Benchmark tab when a game is selected
        self._signals.game_selected.connect(self._on_game_selected)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        # Logo / Title
        title = QLabel("LGB")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {ACCENT}; "
            "letter-spacing: 4px; padding: 12px 0 8px 0; background: transparent;"
        )
        layout.addWidget(title)

        subtitle = QLabel("Linux Game Bench")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 10px; color: {TEXT_MUTED}; padding-bottom: 12px; background: transparent;"
        )
        layout.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setProperty("class", "separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        layout.addSpacing(8)

        # Nav buttons
        for idx, (icon_text, label) in enumerate(NAV_ITEMS):
            btn = QPushButton(f"  {icon_text}  {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "false")
            btn.clicked.connect(lambda checked, i=idx: self._select_nav(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch(1)

        # Separator before auth
        sep2 = QFrame()
        sep2.setProperty("class", "separator")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Auth status widget (login/logout + username display)
        self._auth_widget = AuthStatusWidget()
        layout.addWidget(self._auth_widget)

        # Stage indicator
        self._stage_label = QLabel(self._get_stage_text())
        self._stage_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; padding: 2px 12px 4px 12px; "
            "background: transparent;"
        )
        layout.addWidget(self._stage_label)

        return sidebar

    # --- Navigation ---

    def _select_nav(self, index: int):
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._stack.setCurrentIndex(index)

    def _on_game_selected(self, game: dict):
        """Switch to Benchmark tab when a game is selected."""
        self._select_nav(1)  # Benchmark tab

    # --- Auth ---

    def _check_auth(self):
        """Verify stored token on startup."""
        self._auth_worker = AuthVerifyWorker(self)
        self._auth_worker.finished.connect(self._on_auth_verified)
        self._auth_worker.start()

    def _on_auth_verified(self, valid: bool, username: str):
        self._signals.auth_changed.emit(valid, username)

    # --- Games Scan at Startup ---

    def _scan_games_startup(self):
        """Scan Steam library at startup so game data is available on all tabs."""
        self._games_worker = SteamScanWorker(parent=self)
        self._games_worker.finished.connect(
            lambda games: self._signals.games_loaded.emit(games)
        )
        self._games_worker.start()

    # --- Version Check ---

    def _check_version(self):
        """Check for updates on startup."""
        self._version_worker = UpdateCheckWorker(parent=self)
        self._version_worker.finished.connect(self._on_version_check)
        self._version_worker.start()

    def _on_version_check(self, new_version):
        if not new_version:
            return
        try:
            from linux_game_benchmark.config.settings import settings
            current = settings.CLIENT_VERSION
        except Exception:
            current = "?"

        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"A new version v{new_version} is available.\n"
            f"Current version: v{current}\n\n"
            "Please update to get the latest features and fixes."
        )
        msg.setInformativeText(
            "Run:  pipx upgrade linux-game-benchmark\n"
            "  or: pip install --upgrade linux-game-benchmark"
        )
        update_btn = msg.addButton("Copy Update Command", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Continue", QMessageBox.ButtonRole.RejectRole)
        quit_btn = msg.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == update_btn:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText("pipx upgrade linux-game-benchmark")
            self._toast_mgr.info("Update command copied to clipboard")
        elif clicked == quit_btn:
            from PySide6.QtWidgets import QApplication
            QApplication.quit()

    # --- Stage ---

    def _get_stage_text(self) -> str:
        try:
            from linux_game_benchmark.config.settings import settings
            stage = settings.CURRENT_STAGE
            return f"Stage: {stage.upper()}"
        except Exception:
            return "Stage: PROD"

    # --- Keyboard Shortcuts ---

    def _setup_shortcuts(self):
        # Ctrl+1-5 for tab navigation
        for i in range(min(5, len(NAV_ITEMS))):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            shortcut.activated.connect(lambda idx=i: self._select_nav(idx))

        # F5 / Ctrl+R - Refresh current view
        QShortcut(QKeySequence("F5"), self).activated.connect(self._refresh_current)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._refresh_current)

        # Ctrl+L - Login
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._trigger_login)

    def _refresh_current(self):
        """Refresh the currently active view if it supports it."""
        current = self._stack.currentWidget()
        if hasattr(current, '_refresh_all'):
            current._refresh_all()
        elif hasattr(current, '_detect'):
            current._detect()
        elif hasattr(current, '_scan_games'):
            current._scan_games()

    def _trigger_login(self):
        """Open login dialog."""
        self._auth_widget._open_login_dialog()

    # --- Toasts ---

    def _setup_toasts(self):
        self._toast_mgr = ToastManager(parent=self)
        self._signals.status_message.connect(self._on_status_message)
        self._signals.auth_changed.connect(self._on_auth_toast)

    def _on_status_message(self, message: str, level: str):
        level = level.lower() if level else "info"
        if level == "error":
            self._toast_mgr.error(message)
        elif level == "success":
            self._toast_mgr.success(message)
        elif level == "warning":
            self._toast_mgr.warning(message)
        else:
            self._toast_mgr.info(message)

    def _on_auth_toast(self, logged_in: bool, username: str):
        if logged_in and username:
            self._toast_mgr.success(f"Logged in as {username}")

    def show_toast(self, message: str, toast_type: str = "info"):
        """Public API for showing toasts from any view."""
        self._toast_mgr.show_toast(message, toast_type)

    # --- Window State ---

    def _restore_state(self):
        try:
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text())
                x = data.get("x")
                y = data.get("y")
                w = data.get("width", DEFAULT_WINDOW_WIDTH)
                h = data.get("height", DEFAULT_WINDOW_HEIGHT)
                if x is not None and y is not None:
                    self.setGeometry(x, y, w, h)
                else:
                    self.resize(w, h)
                nav = data.get("nav_index", 0)
                if 0 <= nav < len(NAV_ITEMS):
                    self._select_nav(nav)
        except Exception:
            pass

    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Preserve existing keys (e.g. ui_scale) when saving window state
            data = {}
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text())
            geo = self.geometry()
            data.update({
                "x": geo.x(),
                "y": geo.y(),
                "width": geo.width(),
                "height": geo.height(),
                "nav_index": self._stack.currentIndex(),
            })
            STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_state()
        # Wait for any running worker threads to finish
        for attr in ('_auth_worker', '_version_worker'):
            worker = getattr(self, attr, None)
            if worker and worker.isRunning():
                worker.quit()
                worker.wait(2000)
        super().closeEvent(event)
