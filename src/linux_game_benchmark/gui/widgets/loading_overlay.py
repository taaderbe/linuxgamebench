"""Semi-transparent loading overlay with spinning indicator."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QConicalGradient, QPen

from linux_game_benchmark.gui.constants import ACCENT, TEXT_PRIMARY, BG_DARK


class SpinnerWidget(QWidget):
    """Animated spinning arc indicator."""

    def __init__(self, size: int = 48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._size = size
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._rotate)
        self.setStyleSheet("background: transparent;")

    def _rotate(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(ACCENT))
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        margin = 6
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.drawArc(rect, self._angle * 16, 270 * 16)

        # Dim trail
        pen2 = QPen(QColor(ACCENT))
        pen2.setWidth(3)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setOpacity(0.2)
        painter.setPen(pen2)
        painter.drawArc(rect, (self._angle + 270) * 16, 90 * 16)

        painter.end()

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with spinner and optional message."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._spinner = SpinnerWidget(56)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600; "
            "background: transparent; padding-top: 8px;"
        )
        layout.addWidget(self._label)

        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        painter.end()
        super().paintEvent(event)

    def show_loading(self, message: str = "Loading..."):
        self._label.setText(message)
        if self.parent():
            self.setGeometry(self.parent().rect())
        self._spinner.start()
        self.show()
        self.raise_()

    def hide_loading(self):
        self._spinner.stop()
        self.hide()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)
