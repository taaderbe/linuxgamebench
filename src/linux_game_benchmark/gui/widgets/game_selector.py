"""Searchable game selector ComboBox with Steam cover preview."""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QPixmap

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, BG_INPUT, BG_CARD, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER,
)
from linux_game_benchmark.gui.resources import ImageCache
from linux_game_benchmark.gui.signals import AppSignals


PREVIEW_WIDTH = 184
PREVIEW_HEIGHT = 86


class GameSelector(QWidget):
    """Searchable game ComboBox with cover image preview."""

    game_changed = Signal(dict)  # emits selected game dict (or empty dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._games: list[dict] = []
        self._image_cache = ImageCache(self)
        self._image_cache.image_ready.connect(self._on_image_ready)
        self._current_app_id = 0

        self._build_ui()

        AppSignals.instance().games_loaded.connect(self._on_games_loaded)
        AppSignals.instance().game_selected.connect(self._select_game)

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Cover image preview
        self._preview = QLabel()
        self._preview.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            f"background-color: {BG_CARD}; border-radius: 6px; "
            f"color: {TEXT_MUTED}; font-size: 11px;"
        )
        self._preview.setText("No game selected")
        layout.addWidget(self._preview)

        # Right side: combo + info
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        lbl = QLabel("Game")
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        right_layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setFixedHeight(38)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.setMinimumWidth(280)
        self._combo.lineEdit().setPlaceholderText("Type to search...")
        # Configure completer for "contains" matching (not just prefix)
        completer = self._combo.completer()
        if completer:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Show dropdown popup when clicking the line edit area
        self._combo.lineEdit().installEventFilter(self)
        self._combo.currentIndexChanged.connect(self._on_index_changed)
        right_layout.addWidget(self._combo)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        right_layout.addWidget(self._info_label)
        right_layout.addStretch(1)

        layout.addWidget(right, 1)

    def eventFilter(self, obj, event):
        """Show dropdown popup when clicking on the line edit area."""
        if obj is self._combo.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            # Defer showPopup to avoid being closed by the same click cycle
            QTimer.singleShot(0, self._combo.showPopup)
            return False
        return super().eventFilter(obj, event)

    def _on_games_loaded(self, games: list):
        self._games = sorted(games, key=lambda g: g.get("name", "").lower())
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("")  # Empty first item - placeholder text shows instead
        for g in self._games:
            name = g.get("name", "Unknown")
            app_id = g.get("app_id", 0)
            self._combo.addItem(f"{name}  ({app_id})", userData=g)
        self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def _select_game(self, game: dict):
        """Select a game programmatically (e.g., from Games view click)."""
        app_id = game.get("app_id", 0)
        for i in range(1, self._combo.count()):
            g = self._combo.itemData(i)
            if g and g.get("app_id") == app_id:
                self._combo.setCurrentIndex(i)
                return

    def _on_index_changed(self, index: int):
        if index <= 0:
            self._preview.setText("No game selected")
            self._preview.setPixmap(QPixmap())
            self._preview.setStyleSheet(
                f"background-color: {BG_CARD}; border-radius: 6px; "
                f"color: {TEXT_MUTED}; font-size: 11px;"
            )
            self._info_label.setText("")
            self._current_app_id = 0
            self.game_changed.emit({})
            return

        game = self._combo.itemData(index)
        if not game:
            return

        app_id = game.get("app_id", 0)
        self._current_app_id = app_id

        # Info line
        parts = []
        if game.get("requires_proton"):
            parts.append("Proton")
        else:
            parts.append("Native")
        if game.get("has_builtin_benchmark"):
            parts.append("Has builtin benchmark")
        parts.append(f"App ID: {app_id}")
        self._info_label.setText("  |  ".join(parts))

        # Cover image
        pixmap = self._image_cache.get(app_id)
        if pixmap and not pixmap.isNull():
            self._set_preview(pixmap)
        else:
            self._preview.setText("Loading...")

        self.game_changed.emit(game)

    def _on_image_ready(self, app_id: int, pixmap: QPixmap):
        if app_id == self._current_app_id:
            self._set_preview(pixmap)

    def _set_preview(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            PREVIEW_WIDTH, PREVIEW_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > PREVIEW_WIDTH or scaled.height() > PREVIEW_HEIGHT:
            x = (scaled.width() - PREVIEW_WIDTH) // 2
            y = (scaled.height() - PREVIEW_HEIGHT) // 2
            scaled = scaled.copy(x, y, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self._preview.setPixmap(scaled)
        self._preview.setStyleSheet(f"border-radius: 6px; background: {BG_CARD};")

    def current_game(self) -> dict:
        """Return currently selected game dict, or empty dict."""
        idx = self._combo.currentIndex()
        if idx <= 0:
            return {}
        return self._combo.itemData(idx) or {}
