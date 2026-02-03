"""My Benchmarks view - uploaded (server) and local benchmark results."""

import webbrowser
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QScrollArea, QSizePolicy, QAbstractItemView, QLineEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, BG_CARD, ACCENT, ACCENT_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
    SUCCESS, WARNING, ERROR,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import (
    FetchUserBenchmarksWorker, LocalBenchmarksWorker,
)
from linux_game_benchmark.gui.resources import ImageCache

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

TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER};
        font-size: 13px;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid {BORDER};
    }}
    QTableWidget::item:selected {{
        background-color: rgba(0, 173, 181, 0.15);
        color: {TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {BG_CARD};
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: 600;
        padding: 8px 10px;
        border: none;
        border-bottom: 2px solid {BORDER};
        border-right: 1px solid {BORDER};
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}
"""


class MyBenchmarksView(QWidget):
    """Display user's benchmarks from server and local storage."""

    THUMB_W = 80
    THUMB_H = 37
    ROW_H = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server_data = []
        self._local_data = []
        self._fetch_worker = None
        self._local_worker = None
        self._signals = AppSignals.instance()
        self._visible = False
        self._image_cache = ImageCache(self)
        self._image_cache.image_ready.connect(self._on_image_ready)
        self._image_labels: dict[int, list[QLabel]] = {}  # app_id -> [QLabel, ...]

        self._local_report_buttons = []  # (row, button) pairs for selection styling
        self._build_ui()
        self._signals.auth_changed.connect(self._on_auth_changed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(12)

        # Header row
        header_row = QWidget()
        header_row.setStyleSheet("background: transparent;")
        hr_layout = QHBoxLayout(header_row)
        hr_layout.setContentsMargins(0, 0, 0, 0)
        hr_layout.setSpacing(12)

        heading = QLabel("My Benchmarks")
        heading.setProperty("class", "heading")
        hr_layout.addWidget(heading)

        hr_layout.addStretch(1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(36)
        self._refresh_btn.setProperty("class", "secondary")
        self._refresh_btn.clicked.connect(self._refresh_all)
        hr_layout.addWidget(self._refresh_btn)

        layout.addWidget(header_row)

        # Stats summary
        self._stats_frame = QFrame()
        self._stats_frame.setProperty("class", "card")
        stats_layout = QHBoxLayout(self._stats_frame)
        stats_layout.setContentsMargins(16, 12, 16, 12)
        stats_layout.setSpacing(24)

        self._stat_labels = {}
        for key, title in [
            ("total", "Uploaded"),
            ("games", "Games"),
            ("avg_fps", "Avg FPS"),
            ("local_runs", "Local Runs"),
        ]:
            group = QWidget()
            group.setStyleSheet("background: transparent;")
            gl = QVBoxLayout(group)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.setSpacing(2)

            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; "
                "background: transparent;"
            )
            gl.addWidget(title_lbl)

            val_lbl = QLabel("--")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(
                f"color: {ACCENT}; font-size: 22px; font-weight: 700; "
                "font-family: monospace; background: transparent;"
            )
            gl.addWidget(val_lbl)
            self._stat_labels[key] = val_lbl

            stats_layout.addWidget(group, 1)

        layout.addWidget(self._stats_frame)

        # Tabs: Server | Local
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {BG_DARK};
                border: 1px solid {BORDER};
                border-top: none;
                border-radius: 0 0 8px 8px;
            }}
            QTabBar::tab {{
                background: {BG_SURFACE};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-bottom: none;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px 6px 0 0;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {BG_DARK};
                color: {ACCENT};
                border-bottom: 2px solid {ACCENT};
            }}
            QTabBar::tab:hover:!selected {{
                color: {TEXT_PRIMARY};
            }}
        """)

        # --- Server tab ---
        server_widget = QWidget()
        server_widget.setStyleSheet("background: transparent;")
        sv_layout = QVBoxLayout(server_widget)
        sv_layout.setContentsMargins(0, 8, 0, 0)
        sv_layout.setSpacing(8)

        self._server_search = QLineEdit()
        self._server_search.setPlaceholderText("Filter by game name...")
        self._server_search.setFixedHeight(32)
        self._server_search.textChanged.connect(self._filter_server_table)
        sv_layout.addWidget(self._server_search)

        self._server_status = QLabel("")
        self._server_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        sv_layout.addWidget(self._server_status)

        self._server_table = self._make_server_table()
        sv_layout.addWidget(self._server_table)

        self._tabs.addTab(server_widget, "Server Benchmarks")

        # --- Local tab ---
        local_widget = QWidget()
        local_widget.setStyleSheet("background: transparent;")
        lv_layout = QVBoxLayout(local_widget)
        lv_layout.setContentsMargins(0, 8, 0, 0)
        lv_layout.setSpacing(8)

        self._local_search = QLineEdit()
        self._local_search.setPlaceholderText("Filter by game name...")
        self._local_search.setFixedHeight(32)
        self._local_search.textChanged.connect(self._filter_local_table)
        lv_layout.addWidget(self._local_search)

        self._local_status = QLabel("")
        self._local_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        lv_layout.addWidget(self._local_status)

        self._local_table = self._make_local_table()
        lv_layout.addWidget(self._local_table)

        self._tabs.addTab(local_widget, "Local Results")

        layout.addWidget(self._tabs, 1)

        # Initial tab visibility based on auth
        self._update_server_tab_visibility()

    def _make_server_table(self) -> QTableWidget:
        headers = ["Game", "Resolution", "AVG FPS", "1% Low", "Stutter", "Consistency", "Date", ""]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(TABLE_STYLE)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)

        h = table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Game
        for col in range(1, len(headers) - 1):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(len(headers) - 1, 80)

        return table

    def _make_local_table(self) -> QTableWidget:
        headers = ["Game", "Resolution", "AVG FPS", "1% Low", "Stutter", "Date", ""]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(TABLE_STYLE)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)

        h = table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Game
        for col in range(1, len(headers) - 1):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(len(headers) - 1, 130)

        # Connect selection change for button styling
        table.itemSelectionChanged.connect(self._on_local_selection_changed)

        return table

    # --- Data loading ---

    def showEvent(self, event):
        super().showEvent(event)
        if not self._visible:
            self._visible = True
            self._refresh_all()

    def _refresh_all(self):
        self._update_server_tab_visibility()
        from linux_game_benchmark.api.auth import is_logged_in
        if is_logged_in():
            self._load_server_benchmarks()
        self._load_local_benchmarks()

    def _on_auth_changed(self, logged_in: bool, username: str):
        self._update_server_tab_visibility()
        if self._visible and logged_in:
            self._load_server_benchmarks()

    def _update_server_tab_visibility(self):
        """Show/hide the Server Benchmarks tab based on login status."""
        from linux_game_benchmark.api.auth import is_logged_in
        logged_in = is_logged_in()

        # Server tab is always index 0
        self._tabs.setTabVisible(0, logged_in)

        if not logged_in:
            # Clear server data and switch to local tab
            self._server_table.setRowCount(0)
            self._server_data = []
            self._server_status.setText("")
            self._tabs.setCurrentIndex(1)  # Switch to Local Results
            # Reset stats
            self._stat_labels["total"].setText("--")
            self._stat_labels["games"].setText("--")
            self._stat_labels["avg_fps"].setText("--")

    def _load_server_benchmarks(self):
        self._server_status.setText("Loading...")
        self._server_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        self._refresh_btn.setEnabled(False)

        self._fetch_worker = FetchUserBenchmarksWorker(parent=self)
        self._fetch_worker.finished.connect(self._on_server_data)
        self._fetch_worker.error.connect(self._on_server_error)
        self._fetch_worker.start()

    def _on_server_data(self, data: dict):
        self._refresh_btn.setEnabled(True)
        benchmarks = data.get("benchmarks", [])
        stats = data.get("stats", {})
        self._server_data = benchmarks

        count = len(benchmarks)
        self._server_status.setText(
            f"{count} benchmark{'s' if count != 1 else ''} found"
        )
        self._server_status.setStyleSheet(
            f"color: {SUCCESS}; font-size: 12px; background: transparent;"
        )

        # Update stats
        self._stat_labels["total"].setText(str(stats.get("total", count)))
        self._stat_labels["games"].setText(str(stats.get("games_count", 0)))
        avg = stats.get("avg_fps", 0)
        self._stat_labels["avg_fps"].setText(f"{avg:.1f}" if avg else "--")

        self._populate_server_table(benchmarks)

    def _on_server_error(self, error: str):
        self._refresh_btn.setEnabled(True)
        self._server_status.setText(f"Error: {error}")
        self._server_status.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; background: transparent;"
        )

    def _populate_server_table(self, benchmarks: list):
        self._server_table.setRowCount(len(benchmarks))

        for row, bm in enumerate(benchmarks):
            fps = bm.get("fps", {})

            # Game name with thumbnail
            app_id = bm.get("steam_app_id", 0)
            game_widget = self._make_game_cell(
                bm.get("game_name", "Unknown"), app_id
            )
            self._server_table.setCellWidget(row, 0, game_widget)
            self._server_table.setRowHeight(row, self.ROW_H)
            # Store data for access
            placeholder = QTableWidgetItem()
            placeholder.setData(Qt.ItemDataRole.UserRole, bm)
            self._server_table.setItem(row, 0, placeholder)

            # Resolution
            self._server_table.setItem(row, 1, QTableWidgetItem(
                bm.get("resolution", "--")
            ))

            # AVG FPS
            avg = fps.get("avg", 0)
            avg_item = QTableWidgetItem(f"{avg:.1f}" if avg else "--")
            avg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._server_table.setItem(row, 2, avg_item)

            # 1% Low
            low = fps.get("fps_1low", 0)
            low_item = QTableWidgetItem(f"{low:.1f}" if low else "--")
            low_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._server_table.setItem(row, 3, low_item)

            # Stutter rating
            stutter = bm.get("stutter_rating", "--")
            stutter_item = QTableWidgetItem(stutter)
            stutter_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = RATING_COLORS.get(stutter, TEXT_SECONDARY)
            stutter_item.setForeground(self._parse_color(color))
            self._server_table.setItem(row, 4, stutter_item)

            # Consistency rating
            consistency = bm.get("consistency_rating", "--")
            cons_item = QTableWidgetItem(consistency)
            cons_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = RATING_COLORS.get(consistency, TEXT_SECONDARY)
            cons_item.setForeground(self._parse_color(color))
            self._server_table.setItem(row, 5, cons_item)

            # Date
            created = bm.get("created_at", "")
            date_str = self._format_date(created)
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._server_table.setItem(row, 6, date_item)

            # Open button
            open_btn = QPushButton("Open")
            open_btn.setFixedHeight(28)
            open_btn.setProperty("class", "link")
            bm_id = bm.get("id", 0)
            bm_game = bm.get("game_name", "")
            open_btn.clicked.connect(lambda checked, bid=bm_id, gn=bm_game: self._open_server_benchmark(bid, gn))
            self._server_table.setCellWidget(row, 7, open_btn)

        self._server_table.resizeRowsToContents()

    def _load_local_benchmarks(self):
        self._local_status.setText("Scanning...")
        self._local_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )

        self._local_worker = LocalBenchmarksWorker(parent=self)
        self._local_worker.finished.connect(self._on_local_data)
        self._local_worker.error.connect(self._on_local_error)
        self._local_worker.start()

    def _on_local_data(self, results: list):
        self._local_data = results
        total_runs = len(results)

        self._local_status.setText(
            f"{total_runs} run{'s' if total_runs != 1 else ''}"
        )
        self._local_status.setStyleSheet(
            f"color: {SUCCESS}; font-size: 12px; background: transparent;"
        )

        self._stat_labels["local_runs"].setText(str(total_runs))
        self._populate_local_table(results)

    def _on_local_error(self, error: str):
        self._local_status.setText(f"Error: {error}")
        self._local_status.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; background: transparent;"
        )

    def _populate_local_table(self, results: list):
        self._local_table.setRowCount(len(results))
        self._local_report_buttons = []  # Track buttons for selection styling

        for row, entry in enumerate(results):
            # Game name with thumbnail
            game_id = entry.get("game_id", "")
            app_id = 0
            if game_id.startswith("steam_"):
                try:
                    app_id = int(game_id.replace("steam_", ""))
                except ValueError:
                    pass
            game_widget = self._make_game_cell(entry["display_name"], app_id)
            self._local_table.setCellWidget(row, 0, game_widget)
            self._local_table.setRowHeight(row, self.ROW_H)
            # Store data for access
            placeholder = QTableWidgetItem()
            placeholder.setData(Qt.ItemDataRole.UserRole, entry)
            self._local_table.setItem(row, 0, placeholder)

            # Resolution
            res_item = QTableWidgetItem(entry.get("resolution", "--"))
            res_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._local_table.setItem(row, 1, res_item)

            # AVG FPS
            avg = entry.get("avg_fps", 0)
            avg_item = QTableWidgetItem(f"{avg:.1f}" if avg else "--")
            avg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._local_table.setItem(row, 2, avg_item)

            # 1% Low
            low = entry.get("fps_1low", 0)
            low_item = QTableWidgetItem(f"{low:.1f}" if low else "--")
            low_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._local_table.setItem(row, 3, low_item)

            # Stutter rating
            stutter = entry.get("stutter_rating", "--")
            stutter_item = QTableWidgetItem(stutter)
            stutter_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = RATING_COLORS.get(stutter, TEXT_SECONDARY)
            stutter_item.setForeground(self._parse_color(color))
            self._local_table.setItem(row, 4, stutter_item)

            # Date
            ts = entry.get("timestamp", "")
            date_str = self._format_date(ts)
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._local_table.setItem(row, 5, date_item)

            # Open report button
            if entry.get("has_report"):
                report_btn = QPushButton("Open Report")
                report_btn.setFixedHeight(28)
                report_btn.setMinimumWidth(110)
                report_btn.setProperty("class", "link")  # Default: link style
                game_id = entry["game_id"]
                system_id = entry.get("system_id", "")
                resolution = entry.get("resolution", "")
                timestamp = entry.get("timestamp", "")
                report_btn.clicked.connect(
                    lambda checked, gid=game_id, sid=system_id, res=resolution, ts=timestamp:
                        self._open_local_report(gid, sid, res, ts)
                )
                self._local_table.setCellWidget(row, 6, report_btn)
                self._local_report_buttons.append((row, report_btn))
            else:
                self._local_table.setItem(row, 6, QTableWidgetItem(""))

        self._local_table.resizeRowsToContents()

    # --- Actions ---

    def _open_server_benchmark(self, benchmark_id: int, game_name: str = ""):
        from linux_game_benchmark.config.settings import settings
        from urllib.parse import quote
        base = settings.API_BASE_URL.replace("/api/v1", "")
        game_encoded = quote(game_name) if game_name else ""
        url = f"{base}/?game={game_encoded}&run={benchmark_id}&expand=1"
        webbrowser.open(url)

    def _open_local_report(self, game_id: str, system_id: str = "",
                           resolution: str = "", timestamp: str = ""):
        from linux_game_benchmark.benchmark.storage import BenchmarkStorage
        storage = BenchmarkStorage()
        report_path = storage.get_report_path(game_id)
        if report_path.exists():
            url = f"file://{report_path}"
            # Add hash fragment to jump to specific system+resolution+run
            if system_id and resolution:
                # Format: #run-select-{system_id}_{resolution}@{timestamp}
                url += f"#run-select-{system_id}_{resolution}"
                if timestamp:
                    # URL-encode the timestamp (replace : with -)
                    ts_safe = timestamp.replace(":", "-")
                    url += f"@{ts_safe}"
            webbrowser.open(url)

    def _on_local_selection_changed(self):
        """Update button styles based on selection."""
        selected_rows = set()
        for item in self._local_table.selectedItems():
            selected_rows.add(item.row())

        for row, btn in self._local_report_buttons:
            try:
                if row in selected_rows:
                    # Selected: red/danger style
                    btn.setProperty("class", "danger")
                else:
                    # Not selected: link style
                    btn.setProperty("class", "link")
                # Force style refresh
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except RuntimeError:
                pass  # Button may have been deleted

    # --- Game cell with thumbnail ---

    def _make_game_cell(self, name: str, app_id: int) -> QWidget:
        """Create a widget with thumbnail + game name for table cells."""
        cell = QWidget()
        cell.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(
            f"background-color: {BG_CARD}; border-radius: 4px;"
        )

        if app_id:
            pixmap = self._image_cache.get(app_id)
            if pixmap and not pixmap.isNull():
                self._set_thumb(thumb, pixmap)
            # Track label for async update
            if app_id not in self._image_labels:
                self._image_labels[app_id] = []
            self._image_labels[app_id].append(thumb)

        lay.addWidget(thumb)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600; "
            "background: transparent;"
        )
        lay.addWidget(name_lbl, 1)

        return cell

    def _set_thumb(self, label: QLabel, pixmap: QPixmap):
        scaled = pixmap.scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > self.THUMB_W or scaled.height() > self.THUMB_H:
            x = (scaled.width() - self.THUMB_W) // 2
            y = (scaled.height() - self.THUMB_H) // 2
            scaled = scaled.copy(x, y, self.THUMB_W, self.THUMB_H)
        label.setPixmap(scaled)

    def _on_image_ready(self, app_id: int, pixmap: QPixmap):
        labels = self._image_labels.get(app_id, [])
        for lbl in labels:
            try:
                self._set_thumb(lbl, pixmap)
            except RuntimeError:
                pass  # widget may have been deleted

    # --- Filtering ---

    def _filter_server_table(self, text: str):
        text = text.lower().strip()
        for row in range(self._server_table.rowCount()):
            item = self._server_table.item(row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                game_name = (data or {}).get("game_name", "").lower()
                self._server_table.setRowHidden(row, text != "" and text not in game_name)
            else:
                self._server_table.setRowHidden(row, bool(text))

    def _filter_local_table(self, text: str):
        text = text.lower().strip()
        for row in range(self._local_table.rowCount()):
            item = self._local_table.item(row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                game_name = (data or {}).get("display_name", "").lower()
                self._local_table.setRowHidden(row, text != "" and text not in game_name)
            else:
                self._local_table.setRowHidden(row, bool(text))

    # --- Helpers ---

    @staticmethod
    def _format_date(iso_str: str) -> str:
        if not iso_str:
            return "--"
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            # Try just the date part
            return iso_str[:10] if len(iso_str) >= 10 else iso_str

    @staticmethod
    def _parse_color(hex_color: str):
        from PySide6.QtGui import QColor
        return QColor(hex_color)
