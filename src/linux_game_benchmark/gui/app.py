"""QApplication setup with dark theme and crash-safety handlers."""

import atexit
import signal
import sys

from pathlib import Path

from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox
from PySide6.QtCore import Qt, QTimer, QEvent, QObject
from PySide6.QtGui import QFont, QIcon

from linux_game_benchmark.gui.constants import DARK_THEME_QSS
from linux_game_benchmark.gui.icon_gen import ensure_icons, get_arrow_qss
from linux_game_benchmark.gui.main_window import MainWindow


class _WheelFilter(QObject):
    """Block scroll-wheel events on QComboBox and QSpinBox so only the main
    scroll area scrolls."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QSpinBox)):
                event.ignore()
                return True
        return False


def _cleanup():
    """Restore MangoHud config and Steam launch options on exit."""
    try:
        from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
        mgr = MangoHudConfigManager()
        mgr.restore_backup()
    except Exception:
        pass


def run_app() -> int:
    """Create and run the Qt application. Returns exit code."""
    # Apply UI scale BEFORE creating QApplication (QT_SCALE_FACTOR must be set first)
    _apply_ui_scale()

    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Linux Game Bench")
    app.setOrganizationName("LGB")
    app.setApplicationVersion(_get_version())

    # Window icon
    icon_path = Path(__file__).parent / "icons" / "lgb.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Block scroll-wheel on combo boxes and spinboxes
    wheel_filter = _WheelFilter(app)
    app.installEventFilter(wheel_filter)

    # Dark theme + generated arrow icons
    icon_dir = ensure_icons()
    app.setStyleSheet(DARK_THEME_QSS + get_arrow_qss(str(icon_dir)))

    # Default font
    font = QFont("Noto Sans", 11)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # Crash safety
    atexit.register(_cleanup)

    # Handle SIGINT/SIGTERM gracefully
    def _signal_handler(signum, frame):
        _cleanup()
        QApplication.quit()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Allow Python signal handlers to fire while Qt event loop runs
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)

    window = MainWindow()
    window.show()

    return app.exec()


def _apply_ui_scale():
    """Apply saved UI scale factor via environment variable.

    Default is 2.0 (shown as "100%" to the user).
    """
    import os
    try:
        import json
        state_file = Path.home() / ".config" / "lgb" / "gui_state.json"
        scale = 2.0  # default: what user sees as "100%"
        if state_file.exists():
            data = json.loads(state_file.read_text())
            scale = data.get("ui_scale", 2.0)
        os.environ["QT_SCALE_FACTOR"] = str(scale)
    except Exception:
        os.environ["QT_SCALE_FACTOR"] = "2.0"


def _get_version() -> str:
    try:
        from linux_game_benchmark import __version__
        return __version__
    except Exception:
        return "0.0.0"
