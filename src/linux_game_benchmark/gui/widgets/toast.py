"""Toast notification widget with auto-dismiss and slide animation."""

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor

from linux_game_benchmark.gui.constants import (
    BG_CARD, ACCENT, TEXT_PRIMARY, TEXT_MUTED, BORDER,
    SUCCESS, WARNING, ERROR,
)

TOAST_COLORS = {
    "success": (SUCCESS, "#0d2818"),
    "error": (ERROR, "#2d1015"),
    "warning": (WARNING, "#2d2510"),
    "info": (ACCENT, "#0d1f2d"),
}

TOAST_ICONS = {
    "success": "\u2713",
    "error": "\u2717",
    "warning": "\u26A0",
    "info": "\u2139",
}


class Toast(QWidget):
    """A single toast notification."""

    def __init__(self, message: str, toast_type: str = "info",
                 duration_ms: int = 3000, parent=None):
        super().__init__(parent)
        self._duration = duration_ms
        self.setFixedHeight(40)
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)

        fg, bg = TOAST_COLORS.get(toast_type, TOAST_COLORS["info"])
        icon = TOAST_ICONS.get(toast_type, "")

        self.setStyleSheet(f"""
            Toast {{
                background-color: {bg};
                border: 1px solid {fg};
                border-radius: 8px;
                border-left: 4px solid {fg};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {fg}; font-size: 14px; background: transparent;"
        )
        icon_lbl.setFixedWidth(18)
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl, 1)

        # Opacity effect for fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

    def show_animated(self):
        """Show with slide-in, then auto-dismiss."""
        self.show()
        self.raise_()

        # Slide in from right
        start = QPoint(self.parent().width(), self.y())
        end = QPoint(self.x(), self.y())
        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(250)
        self._slide_anim.setStartValue(start)
        self._slide_anim.setEndValue(end)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.start()

        # Auto-dismiss
        QTimer.singleShot(self._duration, self._fade_out)

    def _fade_out(self):
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.finished.connect(self._on_fade_done)
        self._fade_anim.start()

    def _on_fade_done(self):
        self.hide()
        self.deleteLater()


class ToastManager(QWidget):
    """Manages toast stack in a parent widget's top-right corner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._toasts: list[Toast] = []
        self._margin = 12
        self._spacing = 6
        self.hide()

    def show_toast(self, message: str, toast_type: str = "info",
                   duration_ms: int = 3000):
        """Show a toast notification."""
        toast = Toast(message, toast_type, duration_ms, parent=self.parent())
        toast.setFixedWidth(min(350, self.parent().width() - 40))

        # Position in top-right of parent
        y_offset = self._margin
        for existing in self._toasts:
            if existing.isVisible():
                y_offset += existing.height() + self._spacing

        x = self.parent().width() - toast.width() - self._margin
        toast.move(x, y_offset)

        self._toasts.append(toast)
        toast.show_animated()

        # Clean up reference when done
        def cleanup():
            if toast in self._toasts:
                self._toasts.remove(toast)
        QTimer.singleShot(duration_ms + 500, cleanup)

    def success(self, message: str, duration_ms: int = 3000):
        self.show_toast(message, "success", duration_ms)

    def error(self, message: str, duration_ms: int = 4000):
        self.show_toast(message, "error", duration_ms)

    def warning(self, message: str, duration_ms: int = 3500):
        self.show_toast(message, "warning", duration_ms)

    def info(self, message: str, duration_ms: int = 3000):
        self.show_toast(message, "info", duration_ms)
