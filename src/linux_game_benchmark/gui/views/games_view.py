"""Games library view - Steam game grid/list with search and filtering."""

import webbrowser
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QScrollArea, QFrame, QMenu, QApplication, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QPixmap, QAction, QCursor

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, BG_INPUT, ACCENT, ACCENT_HOVER, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, BORDER, SUCCESS, WARNING, ERROR,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import SteamScanWorker
from linux_game_benchmark.gui.resources import ImageCache
from linux_game_benchmark.gui.views.game_card import GameCard, CARD_WIDTH


class FlowLayout(QVBoxLayout):
    """Simple flow-like layout that wraps game cards into rows.

    We use nested HBoxLayouts inside a VBoxLayout to simulate a
    CSS-like flex-wrap, since Qt doesn't have a built-in flow layout
    that works well inside a QScrollArea.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(12)
        self._widgets: list[QWidget] = []
        self._row_containers: list[QWidget] = []
        self._generation = 0  # bumped on clear to invalidate deferred reflows

    def add_widget(self, widget: QWidget):
        self._widgets.append(widget)

    def reflow(self, container_width: int, generation: int = -1):
        """Recompute row layout based on available width.

        Args:
            container_width: Available pixel width for cards.
            generation: If provided, skip reflow when stale (generation mismatch).
        """
        if container_width <= 0:
            return
        if generation >= 0 and generation != self._generation:
            return

        card_spacing = 12
        cards_per_row = max(1, (container_width + card_spacing) // (CARD_WIDTH + card_spacing))

        # Remove old row containers (cards are reparented, not deleted)
        for rc in self._row_containers:
            rc.setParent(None)
            rc.deleteLater()
        self._row_containers.clear()

        # Remove spacer items
        for i in reversed(range(self.count())):
            item = self.itemAt(i)
            if item and not item.widget():
                self.removeItem(item)

        # Re-add widgets in rows
        row_widget = None
        row_layout = None
        for i, w in enumerate(self._widgets):
            if i % cards_per_row == 0:
                row_widget = QWidget()
                row_widget.setStyleSheet("background: transparent;")
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(card_spacing)
                self.addWidget(row_widget)
                self._row_containers.append(row_widget)
            w.setParent(row_widget)
            row_layout.addWidget(w)

        # Fill last row with stretch
        if row_layout:
            row_layout.addStretch(1)

        self.addStretch(1)

    def clear_all(self):
        """Remove all card widgets and row containers."""
        self._generation += 1

        # Delete cards
        for w in self._widgets:
            w.setParent(None)
            w.deleteLater()
        self._widgets.clear()

        # Delete row containers
        for rc in self._row_containers:
            rc.setParent(None)
            rc.deleteLater()
        self._row_containers.clear()

        # Remove any remaining spacer items
        for i in reversed(range(self.count())):
            item = self.itemAt(i)
            if item:
                if item.widget():
                    item.widget().setParent(None)
                    item.widget().deleteLater()
                self.removeItem(item)


class GamesView(QWidget):
    """Steam games library with grid/list display modes."""

    FILTER_ALL = "All Games"
    FILTER_NATIVE = "Native"
    FILTER_PROTON = "Proton"
    FILTER_BENCHMARK = "Has Benchmark"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._games: list[dict] = []
        self._filtered_games: list[dict] = []
        self._cards: dict[int, GameCard] = {}  # app_id -> card
        self._grid_mode = True
        self._scan_worker: Optional[SteamScanWorker] = None
        self._signals = AppSignals.instance()
        self._image_cache = ImageCache(self)
        self._image_cache.image_ready.connect(self._on_image_ready)
        self._auto_scanned = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background: transparent;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(10)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search games...")
        self._search.setFixedHeight(36)
        self._search.setMinimumWidth(200)
        self._search.setMaximumWidth(350)
        self._search.textChanged.connect(self._apply_filters)
        tb_layout.addWidget(self._search)

        # Filter dropdown
        self._filter_combo = QComboBox()
        self._filter_combo.addItems([
            self.FILTER_ALL, self.FILTER_NATIVE,
            self.FILTER_PROTON, self.FILTER_BENCHMARK,
        ])
        self._filter_combo.setFixedHeight(36)
        self._filter_combo.setFixedWidth(150)
        self._filter_combo.currentTextChanged.connect(self._apply_filters)
        tb_layout.addWidget(self._filter_combo)

        tb_layout.addStretch(1)

        # Game count
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        tb_layout.addWidget(self._count_label)

        # Grid / List toggle
        self._toggle_btn = QPushButton("List")
        self._toggle_btn.setFixedSize(70, 36)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SURFACE};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {ACCENT};
                color: {TEXT_PRIMARY};
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_view_mode)
        tb_layout.addWidget(self._toggle_btn)

        # Scan button
        self._scan_btn = QPushButton("Scan Steam")
        self._scan_btn.setFixedHeight(36)
        self._scan_btn.clicked.connect(self._start_scan)
        tb_layout.addWidget(self._scan_btn)

        layout.addWidget(toolbar)

        # --- Content area (scroll) ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG_DARK}; border: none; }}"
        )

        # Grid container
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._flow = FlowLayout(self._grid_container)
        self._flow.setContentsMargins(0, 0, 0, 0)

        # List container (table)
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "App ID", "Type", "Benchmark"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 90)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(3, 100)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_DARK};
                color: {TEXT_PRIMARY};
                border: none;
                gridline-color: {BORDER};
                font-size: 13px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: rgba(0, 173, 181, 0.15);
                color: {TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {BG_SURFACE};
                color: {TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {BORDER};
                padding: 8px;
                font-weight: 600;
                font-size: 12px;
            }}
        """)
        self._table.cellDoubleClicked.connect(self._on_table_double_click)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.setVisible(False)

        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._table, 1)
        self._table.setVisible(False)

        # --- Empty state ---
        self._empty_label = QLabel(
            "No games found. Click \"Scan Steam\" to scan your library."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 15px; padding: 60px;"
        )
        layout.addWidget(self._empty_label)
        self._empty_label.setVisible(True)

        # Connect signals
        self._signals.games_loaded.connect(self._on_games_loaded)

    # --- Auto-scan on first show ---

    def showEvent(self, event):
        super().showEvent(event)
        if not self._auto_scanned:
            self._auto_scanned = True
            if not self._games:  # Skip if already loaded from startup scan
                self._scan_games()

    def _scan_games(self):
        """Public method for external refresh calls."""
        self._start_scan()

    # --- Scanning ---

    def _start_scan(self):
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._scan_btn.setText("Scanning...")
        self._scan_btn.setEnabled(False)
        self._scan_worker = SteamScanWorker(self)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, games: list):
        self._scan_btn.setText("Scan Steam")
        self._scan_btn.setEnabled(True)
        self._games = sorted(games, key=lambda g: g.get("name", "").lower())
        self._signals.games_loaded.emit(self._games)
        self._apply_filters()

    def _on_scan_error(self, error: str):
        self._scan_btn.setText("Scan Steam")
        self._scan_btn.setEnabled(True)
        self._signals.status_message.emit(f"Scan failed: {error}", "error")

    def _on_games_loaded(self, games: list):
        """Handle games loaded from external source (e.g. cached)."""
        if not self._games:
            self._games = sorted(games, key=lambda g: g.get("name", "").lower())
            self._apply_filters()

    # --- Filtering ---

    def _apply_filters(self):
        search = self._search.text().lower().strip()
        filter_type = self._filter_combo.currentText()

        filtered = self._games
        if search:
            filtered = [
                g for g in filtered
                if search in g.get("name", "").lower()
                or search in str(g.get("app_id", ""))
            ]

        if filter_type == self.FILTER_NATIVE:
            filtered = [g for g in filtered if not g.get("requires_proton", False)]
        elif filter_type == self.FILTER_PROTON:
            filtered = [g for g in filtered if g.get("requires_proton", False)]
        elif filter_type == self.FILTER_BENCHMARK:
            filtered = [g for g in filtered if g.get("has_builtin_benchmark", False)]

        self._filtered_games = filtered
        self._count_label.setText(f"{len(filtered)} games")

        has_games = len(filtered) > 0
        self._empty_label.setVisible(not has_games)

        if self._grid_mode:
            self._scroll.setVisible(has_games)
            self._table.setVisible(False)
            self._populate_grid()
        else:
            self._scroll.setVisible(False)
            self._table.setVisible(has_games)
            self._populate_table()

    # --- Grid Mode ---

    def _populate_grid(self):
        self._flow.clear_all()
        self._cards.clear()

        for game in self._filtered_games:
            app_id = game.get("app_id", 0)
            pixmap = self._image_cache.get(app_id)
            card = GameCard(game, pixmap, parent=None)
            card.clicked.connect(self._on_game_clicked)
            card.right_clicked.connect(self._on_game_right_clicked)
            self._cards[app_id] = card
            self._flow.add_widget(card)

        # Defer reflow to after layout is computed, using generation to prevent stale calls
        gen = self._flow._generation
        QTimer.singleShot(0, lambda: self._do_reflow(gen))

    def _do_reflow(self, generation: int = -1):
        width = self._scroll.viewport().width() - 8
        self._flow.reflow(width, generation)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._grid_mode and self._cards:
            gen = self._flow._generation
            QTimer.singleShot(0, lambda: self._do_reflow(gen))

    # --- List Mode ---

    def _populate_table(self):
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._filtered_games))

        for row, game in enumerate(self._filtered_games):
            name_item = QTableWidgetItem(game.get("name", "Unknown"))
            name_item.setData(Qt.ItemDataRole.UserRole, game)
            self._table.setItem(row, 0, name_item)

            app_id_item = QTableWidgetItem(str(game.get("app_id", "")))
            app_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, app_id_item)

            proton = game.get("requires_proton", False)
            type_item = QTableWidgetItem("Proton" if proton else "Native")
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, type_item)

            bench = game.get("has_builtin_benchmark", False)
            bench_item = QTableWidgetItem("Yes" if bench else "")
            bench_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, bench_item)

    # --- View Mode Toggle ---

    def _toggle_view_mode(self):
        self._grid_mode = not self._grid_mode
        self._toggle_btn.setText("List" if self._grid_mode else "Grid")
        self._apply_filters()

    # --- Image Cache ---

    def _on_image_ready(self, app_id: int, pixmap: QPixmap):
        card = self._cards.get(app_id)
        if card:
            card.update_pixmap(pixmap)

    # --- Game Selection ---

    def _on_game_clicked(self, game: dict):
        self._signals.game_selected.emit(game)

    def _on_table_double_click(self, row: int, col: int):
        item = self._table.item(row, 0)
        if item:
            game = item.data(Qt.ItemDataRole.UserRole)
            if game:
                self._signals.game_selected.emit(game)

    # --- Context Menu ---

    def _on_game_right_clicked(self, game: dict):
        self._show_context_menu(game, QCursor.pos())

    def _on_table_context_menu(self, pos):
        item = self._table.itemAt(pos)
        if not item:
            return
        row = item.row()
        name_item = self._table.item(row, 0)
        if not name_item:
            return
        game = name_item.data(Qt.ItemDataRole.UserRole)
        if game:
            self._show_context_menu(game, self._table.viewport().mapToGlobal(pos))

    def _show_context_menu(self, game: dict, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_SURFACE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: rgba(0, 173, 181, 0.2);
            }}
        """)

        app_id = game.get("app_id", 0)
        name = game.get("name", "Unknown")

        run_action = menu.addAction("Run Benchmark")
        run_action.triggered.connect(lambda: self._signals.game_selected.emit(game))

        menu.addSeparator()

        steam_action = menu.addAction("View on Steam")
        steam_action.triggered.connect(
            lambda: webbrowser.open(f"https://store.steampowered.com/app/{app_id}")
        )

        protondb_action = menu.addAction("View on ProtonDB")
        protondb_action.triggered.connect(
            lambda: webbrowser.open(f"https://www.protondb.com/app/{app_id}")
        )

        menu.addSeparator()

        copy_id_action = menu.addAction(f"Copy App ID ({app_id})")
        copy_id_action.triggered.connect(
            lambda: QApplication.clipboard().setText(str(app_id))
        )

        copy_name_action = menu.addAction("Copy Game Name")
        copy_name_action.triggered.connect(
            lambda: QApplication.clipboard().setText(name)
        )

        menu.exec(global_pos)
