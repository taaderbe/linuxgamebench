"""FPS metrics card with large AVG display, percentile lows, and rating badges."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
)
from PySide6.QtCore import Qt

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, BG_CARD, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER, SUCCESS, WARNING, ERROR,
)

RATING_COLORS = {
    "Excellent": SUCCESS,
    "excellent": SUCCESS,
    "Good": "#4ecca3",
    "good": "#4ecca3",
    "Moderate": WARNING,
    "moderate": WARNING,
    "Acceptable": WARNING,
    "Poor": ERROR,
    "poor": ERROR,
}


class FpsDisplay(QWidget):
    """FPS metrics display with large AVG, percentile lows, and rating badges."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- AVG FPS (large) ---
        avg_frame = QFrame()
        avg_frame.setProperty("class", "card")
        avg_layout = QVBoxLayout(avg_frame)
        avg_layout.setContentsMargins(16, 12, 16, 12)
        avg_layout.setSpacing(2)

        avg_title = QLabel("Average FPS")
        avg_title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        avg_layout.addWidget(avg_title)

        self._avg_value = QLabel("--")
        self._avg_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avg_value.setStyleSheet(
            f"color: {ACCENT}; font-size: 52px; font-weight: 800; "
            "font-family: monospace; background: transparent; padding: 4px 0;"
        )
        avg_layout.addWidget(self._avg_value)

        layout.addWidget(avg_frame)

        # --- Secondary metrics grid ---
        metrics_frame = QFrame()
        metrics_frame.setProperty("class", "card")
        grid = QGridLayout(metrics_frame)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(8)

        self._metric_labels = {}
        metrics = [
            ("1% Low", "1_percent_low"),
            ("0.1% Low", "0.1_percent_low"),
            ("Min", "minimum"),
            ("Max", "maximum"),
        ]

        for col, (display, key) in enumerate(metrics):
            title = QLabel(display)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            grid.addWidget(title, 0, col)

            value = QLabel("--")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700; "
                "font-family: monospace; background: transparent;"
            )
            grid.addWidget(value, 1, col)
            self._metric_labels[key] = value

        layout.addWidget(metrics_frame)

        # --- Rating badges row ---
        badges_frame = QFrame()
        badges_frame.setProperty("class", "card")
        badges_layout = QHBoxLayout(badges_frame)
        badges_layout.setContentsMargins(12, 10, 12, 10)
        badges_layout.setSpacing(12)

        self._stutter_badge = self._make_badge_group("Stutter")
        badges_layout.addWidget(self._stutter_badge["widget"], 1)

        self._consistency_badge = self._make_badge_group("Consistency")
        badges_layout.addWidget(self._consistency_badge["widget"], 1)

        self._overall_badge = self._make_badge_group("Overall")
        badges_layout.addWidget(self._overall_badge["widget"], 1)

        layout.addWidget(badges_frame)

    def _make_badge_group(self, title: str) -> dict:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(title_lbl)

        value_lbl = QLabel("--")
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(value_lbl)

        return {"widget": widget, "value": value_lbl}

    # --- Set data ---

    def set_metrics(self, metrics: dict):
        """Populate display from FrametimeAnalyzer.analyze() result."""
        fps = metrics.get("fps", {})
        stutter = metrics.get("stutter", {})
        pacing = metrics.get("frame_pacing", {})
        summary = metrics.get("summary", {})

        # AVG
        avg = fps.get("average", 0)
        self._avg_value.setText(f"{avg:.1f}" if avg else "--")

        # Secondary metrics
        for key, label in self._metric_labels.items():
            val = fps.get(key, 0)
            label.setText(f"{val:.1f}" if val else "--")

        # Badges
        stutter_rating = stutter.get("stutter_rating", "--")
        self._set_badge(self._stutter_badge, stutter_rating)

        consistency_rating = pacing.get("consistency_rating", "--")
        self._set_badge(self._consistency_badge, consistency_rating)

        overall_rating = summary.get("overall_rating", "--")
        self._set_badge(self._overall_badge, overall_rating)

    def _set_badge(self, badge: dict, rating: str):
        color = RATING_COLORS.get(rating, TEXT_SECONDARY)
        badge["value"].setText(rating)
        badge["value"].setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: 700; background: transparent;"
        )

    def clear(self):
        """Reset all values to placeholder."""
        self._avg_value.setText("--")
        for label in self._metric_labels.values():
            label.setText("--")
        for badge in (self._stutter_badge, self._consistency_badge, self._overall_badge):
            badge["value"].setText("--")
            badge["value"].setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 700; background: transparent;"
            )
