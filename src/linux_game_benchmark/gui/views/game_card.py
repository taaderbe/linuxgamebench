"""Single game card widget for the grid view."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QHBoxLayout, QWidget, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QColor, QCursor, QMouseEvent

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, BG_CARD, ACCENT, ACCENT_HOVER, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER, SUCCESS, WARNING,
)

# Steam header images are 460x215
CARD_IMAGE_WIDTH = 276
CARD_IMAGE_HEIGHT = 129
CARD_WIDTH = CARD_IMAGE_WIDTH + 16  # padding
CARD_MIN_HEIGHT = 190


class GameCard(QFrame):
    """A clickable game card with cover image, name, and badges."""

    clicked = Signal(dict)        # emits game dict on left click
    right_clicked = Signal(dict)  # emits game dict on right click

    def __init__(self, game: dict, pixmap: QPixmap = None, parent=None):
        super().__init__(parent)
        self._game = game
        self.setObjectName("game_card")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedWidth(CARD_WIDTH)
        self.setMinimumHeight(CARD_MIN_HEIGHT)

        self.setStyleSheet(f"""
            #game_card {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 8px;
            }}
            #game_card:hover {{
                border-color: {ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Cover image
        self._image_label = QLabel()
        self._image_label.setFixedSize(CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(
            f"background-color: {BG_CARD}; border-radius: 6px;"
        )
        if pixmap and not pixmap.isNull():
            self._set_pixmap(pixmap)
        else:
            self._image_label.setText("Loading...")
            self._image_label.setStyleSheet(
                f"background-color: {BG_CARD}; border-radius: 6px; "
                f"color: {TEXT_MUTED}; font-size: 11px;"
            )
        layout.addWidget(self._image_label, 0, Qt.AlignmentFlag.AlignCenter)

        # Game name
        name_label = QLabel(game.get("name", "Unknown"))
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(CARD_IMAGE_WIDTH)
        name_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; padding: 0 4px;"
        )
        layout.addWidget(name_label)

        # Badges row
        badges_row = QWidget()
        badges_row.setStyleSheet("background: transparent;")
        badges_layout = QHBoxLayout(badges_row)
        badges_layout.setContentsMargins(4, 0, 4, 4)
        badges_layout.setSpacing(4)

        # Native / Proton badge
        requires_proton = game.get("requires_proton", False)
        if requires_proton:
            proton_badge = self._make_badge("Proton", WARNING)
            badges_layout.addWidget(proton_badge)
        else:
            native_badge = self._make_badge("Native", SUCCESS)
            badges_layout.addWidget(native_badge)

        # Builtin benchmark badge
        if game.get("has_builtin_benchmark", False):
            bench_badge = self._make_badge("Bench", ACCENT)
            badges_layout.addWidget(bench_badge)

        badges_layout.addStretch(1)

        # App ID
        app_id_label = QLabel(str(game.get("app_id", "")))
        app_id_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;"
        )
        badges_layout.addWidget(app_id_label)

        layout.addWidget(badges_row)

        # Glow effect on hover
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(ACCENT))
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)

    @property
    def game(self) -> dict:
        return self._game

    @property
    def app_id(self) -> int:
        return self._game.get("app_id", 0)

    def update_pixmap(self, pixmap: QPixmap):
        """Update the cover image (called when async load completes)."""
        if pixmap and not pixmap.isNull():
            self._set_pixmap(pixmap)

    def _set_pixmap(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Crop to exact size if needed
        if scaled.width() > CARD_IMAGE_WIDTH or scaled.height() > CARD_IMAGE_HEIGHT:
            x = (scaled.width() - CARD_IMAGE_WIDTH) // 2
            y = (scaled.height() - CARD_IMAGE_HEIGHT) // 2
            scaled = scaled.copy(x, y, CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT)
        self._image_label.setPixmap(scaled)
        self._image_label.setStyleSheet(f"border-radius: 6px; background: {BG_CARD};")

    def _make_badge(self, text: str, color: str) -> QLabel:
        badge = QLabel(text)
        badge.setStyleSheet(
            f"background-color: rgba({self._hex_to_rgb(color)}, 0.15); "
            f"color: {color}; font-size: 10px; font-weight: 600; "
            "border-radius: 4px; padding: 2px 6px;"
        )
        return badge

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"

    # --- Events ---

    def enterEvent(self, event):
        self._shadow.setBlurRadius(20)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setBlurRadius(0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._game)
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self._game)
        super().mousePressEvent(event)
