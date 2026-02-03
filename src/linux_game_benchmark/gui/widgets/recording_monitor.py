"""Live recording status widget with timer, pulsing indicator, and cancel button."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER, ERROR, SUCCESS, WARNING,
)

MIN_VALID_SECONDS = 30  # Server minimum for a valid benchmark
DEFAULT_MAX_DURATION = 300  # Safety maximum when no duration set


class RecordingMonitor(QWidget):
    """Live benchmark recording status with timer and validation indicator."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elapsed = 0
        self._total_duration = DEFAULT_MAX_DURATION
        self._state = "idle"  # idle, waiting, recording, analyzing

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(600)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_on = True

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Status row
        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        sr_layout = QHBoxLayout(status_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        sr_layout.setSpacing(10)

        self._indicator = QLabel("\u25CF")
        self._indicator.setFixedWidth(20)
        self._indicator.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 16px; background: transparent;"
        )
        sr_layout.addWidget(self._indicator)

        self._status_text = QLabel("Ready")
        self._status_text.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700; "
            "background: transparent;"
        )
        sr_layout.addWidget(self._status_text, 1)

        layout.addWidget(status_row)

        # Timer display
        self._timer_label = QLabel("00:00")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 48px; font-weight: 800; "
            "font-family: monospace; background: transparent; padding: 8px 0;"
        )
        layout.addWidget(self._timer_label)

        # Validation hint
        self._hint_label = QLabel("")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;"
        )
        layout.addWidget(self._hint_label)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {ERROR};
                border-color: {ERROR};
            }}
        """)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self._cancel_btn)

    # --- State transitions ---

    def set_launching(self):
        self._state = "launching"
        self._elapsed = 0
        self._indicator.setStyleSheet(
            f"color: {WARNING}; font-size: 16px; background: transparent;"
        )
        self._status_text.setText("Launching game...")
        self._hint_label.setText("Waiting for the game to start")
        self._timer_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 48px; font-weight: 800; "
            "font-family: monospace; background: transparent; padding: 8px 0;"
        )
        self._timer_label.setText("--:--")
        self._blink_timer.start()

    def set_waiting(self):
        self._state = "waiting"
        self._elapsed = 0
        self._indicator.setStyleSheet(
            f"color: {WARNING}; font-size: 16px; background: transparent;"
        )
        self._status_text.setText("Waiting for recording...")
        self._hint_label.setText("Press Shift+F2 in-game to start recording")
        self._timer_label.setText("--:--")
        self._blink_timer.start()

    def set_recording(self):
        self._state = "recording"
        self._elapsed = 0
        self._timer.start()
        self._blink_timer.start()
        self._update_recording_display()

    def set_analyzing(self):
        self._state = "analyzing"
        self._timer.stop()
        self._blink_timer.stop()
        self._indicator.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; background: transparent;"
        )
        self._status_text.setText("Analyzing results...")
        self._hint_label.setText("Processing frametime data")

    def set_idle(self):
        self._state = "idle"
        self._elapsed = 0
        self._timer.stop()
        self._blink_timer.stop()
        self._indicator.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 16px; background: transparent;"
        )
        self._status_text.setText("Ready")
        self._timer_label.setText("00:00")
        self._timer_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 48px; font-weight: 800; "
            "font-family: monospace; background: transparent; padding: 8px 0;"
        )
        self._hint_label.setText("")

    # --- Timer ---

    def _tick(self):
        self._elapsed += 1
        self._update_recording_display()

    def _update_recording_display(self):
        mins = self._elapsed // 60
        secs = self._elapsed % 60
        self._timer_label.setText(f"{mins:02d}:{secs:02d}")

        remaining = max(0, self._total_duration - self._elapsed)
        r_mins = remaining // 60
        r_secs = remaining % 60
        remaining_text = f"  ({r_mins:02d}:{r_secs:02d} remaining)"

        if self._elapsed < MIN_VALID_SECONDS:
            self._timer_label.setStyleSheet(
                f"color: {WARNING}; font-size: 48px; font-weight: 800; "
                "font-family: monospace; background: transparent; padding: 8px 0;"
            )
            valid_remaining = MIN_VALID_SECONDS - self._elapsed
            self._hint_label.setText(
                f"Minimum {valid_remaining}s more for valid benchmark"
                + remaining_text
            )
            self._hint_label.setStyleSheet(
                f"color: {WARNING}; font-size: 13px; background: transparent;"
            )
        else:
            self._timer_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 48px; font-weight: 800; "
                "font-family: monospace; background: transparent; padding: 8px 0;"
            )
            self._hint_label.setText(
                "Benchmark valid" + remaining_text
            )
            self._hint_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 13px; background: transparent;"
            )

        self._status_text.setText("RECORDING")

    def _blink(self):
        self._blink_on = not self._blink_on
        if self._state == "recording":
            color = ERROR if self._blink_on else TEXT_MUTED
        elif self._state in ("waiting", "launching"):
            color = WARNING if self._blink_on else TEXT_MUTED
        else:
            return
        self._indicator.setStyleSheet(
            f"color: {color}; font-size: 16px; background: transparent;"
        )

    def set_total_duration(self, seconds: int):
        """Set total recording duration for remaining-time display."""
        self._total_duration = seconds if seconds > 0 else DEFAULT_MAX_DURATION

    @property
    def elapsed(self) -> int:
        return self._elapsed
