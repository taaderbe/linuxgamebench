"""System info view - hardware detection display with info cards."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGridLayout, QScrollArea, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, BG_CARD, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER, SUCCESS, WARNING, ERROR,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import FullSystemInfoWorker


class InfoCard(QFrame):
    """A styled card displaying a category of system information."""

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self._rows: list[tuple[QLabel, QLabel]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)

        # Header row
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)

        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(
                f"font-size: 16px; background: transparent;"
            )
            hl.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 14px; font-weight: 700; "
            "background: transparent;"
        )
        hl.addWidget(title_lbl)

        hl.addStretch(1)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(56, 26)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setProperty("class", "link")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        hl.addWidget(copy_btn)

        layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER};")
        layout.addWidget(sep)

        # Grid for key-value pairs
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 4, 0, 0)
        self._grid.setSpacing(4)
        self._grid.setColumnStretch(0, 0)
        self._grid.setColumnStretch(1, 1)
        layout.addLayout(self._grid)

        self._title = title
        self._row_count = 0

    def add_row(self, key: str, value: str, highlight: bool = False):
        key_lbl = QLabel(key)
        key_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 600; "
            "background: transparent; padding-right: 12px;"
        )

        color = ACCENT if highlight else TEXT_PRIMARY
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {color}; font-size: 13px; background: transparent;"
        )
        val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        val_lbl.setWordWrap(True)

        self._grid.addWidget(key_lbl, self._row_count, 0, Qt.AlignmentFlag.AlignTop)
        self._grid.addWidget(val_lbl, self._row_count, 1, Qt.AlignmentFlag.AlignTop)
        self._rows.append((key_lbl, val_lbl))
        self._row_count += 1

    def add_separator(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER}; margin: 2px 0;")
        self._grid.addWidget(sep, self._row_count, 0, 1, 2)
        self._row_count += 1

    def clear_rows(self):
        for key_lbl, val_lbl in self._rows:
            key_lbl.deleteLater()
            val_lbl.deleteLater()
        self._rows.clear()
        # Remove separators too
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._row_count = 0

    def _copy_to_clipboard(self):
        lines = []
        for key_lbl, val_lbl in self._rows:
            lines.append(f"{key_lbl.text()}: {val_lbl.text()}")
        text = f"[{self._title}]\n" + "\n".join(lines)
        QApplication.clipboard().setText(text)


class SystemInfoView(QWidget):
    """Display detected system hardware information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info: dict = {}
        self._worker = None
        self._visible = False
        self._cards: dict[str, InfoCard] = {}

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DARK}; border: none; }}")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 16, 24, 24)
        self._content_layout.setSpacing(12)

        # Header row
        header_row = QWidget()
        header_row.setStyleSheet("background: transparent;")
        hr = QHBoxLayout(header_row)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(12)

        heading = QLabel("System Info")
        heading.setProperty("class", "heading")
        hr.addWidget(heading)

        hr.addStretch(1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(36)
        self._refresh_btn.setProperty("class", "secondary")
        self._refresh_btn.clicked.connect(self._detect)
        hr.addWidget(self._refresh_btn)

        copy_all_btn = QPushButton("Copy All")
        copy_all_btn.setFixedHeight(36)
        copy_all_btn.setProperty("class", "secondary")
        copy_all_btn.clicked.connect(self._copy_all)
        hr.addWidget(copy_all_btn)

        self._content_layout.addWidget(header_row)

        desc = QLabel(
            "Detected hardware and software configuration. "
            "This information is sent with each benchmark upload."
        )
        desc.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; background: transparent;"
        )
        desc.setWordWrap(True)
        self._content_layout.addWidget(desc)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        self._content_layout.addWidget(self._status)

        # Benchmark Readiness card (pre-flight checks)
        self._readiness_card = QFrame()
        self._readiness_card.setProperty("class", "card")
        rc_layout = QHBoxLayout(self._readiness_card)
        rc_layout.setContentsMargins(16, 12, 16, 12)
        rc_layout.setSpacing(16)

        rc_title = QLabel("Benchmark Readiness")
        rc_title.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 700; "
            "background: transparent;"
        )
        rc_layout.addWidget(rc_title)
        rc_layout.addSpacing(8)

        self._rc_mangohud = QLabel("")
        self._rc_mangohud.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        rc_layout.addWidget(self._rc_mangohud)

        self._rc_steam = QLabel("")
        self._rc_steam.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        rc_layout.addWidget(self._rc_steam)

        self._rc_auth = QLabel("")
        self._rc_auth.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        rc_layout.addWidget(self._rc_auth)

        rc_layout.addStretch(1)
        self._content_layout.addWidget(self._readiness_card)

        # Cards container (2-column grid)
        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: transparent;")
        self._cards_grid = QGridLayout(self._cards_widget)
        self._cards_grid.setContentsMargins(0, 0, 0, 0)
        self._cards_grid.setSpacing(12)
        self._cards_grid.setColumnStretch(0, 1)
        self._cards_grid.setColumnStretch(1, 1)

        # Create cards
        card_defs = [
            ("gpu", "GPU", "\U0001F3AE"),       # row 0, col 0
            ("cpu", "CPU", "\u2699"),            # row 0, col 1
            ("os", "Operating System", "\U0001F5A5"),  # row 1, col 0
            ("ram", "Memory", "\U0001F4BE"),     # row 1, col 1
            ("steam", "Steam", "\u2668"),        # row 2, col 0
            ("extra", "Extras", "\U0001F527"),   # row 2, col 1
        ]

        for idx, (key, title, icon) in enumerate(card_defs):
            card = InfoCard(title, icon)
            card.add_row("", "Detecting...")
            self._cards[key] = card
            row = idx // 2
            col = idx % 2
            self._cards_grid.addWidget(card, row, col)

        self._content_layout.addWidget(self._cards_widget)
        self._content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Connect auth changes to readiness update
        self._signals = AppSignals.instance()
        self._signals.auth_changed.connect(lambda *a: self._update_readiness())

    # --- Detection ---

    def showEvent(self, event):
        super().showEvent(event)
        if not self._visible:
            self._visible = True
            self._detect()
            self._update_readiness()

    def _detect(self):
        self._status.setText("Detecting hardware...")
        self._status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        self._refresh_btn.setEnabled(False)

        self._worker = FullSystemInfoWorker(parent=self)
        self._worker.finished.connect(self._on_info)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_info(self, info: dict):
        self._info = info
        self._refresh_btn.setEnabled(True)
        self._status.setText("Detection complete")
        self._status.setStyleSheet(
            f"color: {SUCCESS}; font-size: 12px; background: transparent;"
        )
        self._populate_cards(info)
        self._update_readiness()

    def _on_error(self, error: str):
        self._refresh_btn.setEnabled(True)
        self._status.setText(f"Error: {error}")
        self._status.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; background: transparent;"
        )

    # --- Readiness checks ---

    def _update_readiness(self):
        """Update the benchmark readiness indicators."""
        try:
            from linux_game_benchmark.mangohud.manager import MangoHudManager
            mango_ok = MangoHudManager.is_installed()
        except Exception:
            mango_ok = False

        try:
            import shutil
            steam_ok = shutil.which("steam") is not None
        except Exception:
            steam_ok = False

        try:
            from linux_game_benchmark.api.auth import is_logged_in
            auth_ok = is_logged_in()
        except Exception:
            auth_ok = False

        self._set_readiness_label(self._rc_mangohud, "MangoHud", mango_ok)
        self._set_readiness_label(self._rc_steam, "Steam", steam_ok)
        self._set_readiness_label(self._rc_auth, "Logged in", auth_ok)

    def _set_readiness_label(self, label: QLabel, text: str, ok: bool):
        icon = "\u2714" if ok else "\u2718"
        color = SUCCESS if ok else ERROR
        label.setText(f"{icon}  {text}")
        label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )

    # --- Populate cards ---

    def _populate_cards(self, info: dict):
        self._populate_gpu(info)
        self._populate_cpu(info)
        self._populate_os(info)
        self._populate_ram(info)
        self._populate_steam(info)
        self._populate_extras(info)

    def _populate_gpu(self, info: dict):
        card = self._cards["gpu"]
        card.clear_rows()

        gpu = info.get("gpu", {})
        all_gpus = info.get("all_gpus", [])

        card.add_row("Model", gpu.get("model", "Unknown"), highlight=True)
        card.add_row("Vendor", gpu.get("vendor", "Unknown"))

        vram = gpu.get("vram_mb", 0)
        if vram:
            vram_gb = vram / 1024
            card.add_row("VRAM", f"{vram_gb:.0f} GB ({vram} MB)")
        else:
            card.add_row("VRAM", "Unknown")

        card.add_row("Driver", gpu.get("driver", "Unknown"))
        card.add_row("Driver Version", gpu.get("driver_version", "Unknown"))
        card.add_row("Vulkan", gpu.get("vulkan_version", "Unknown"))

        if gpu.get("device_id"):
            card.add_row("Device ID", gpu["device_id"])

        # Multi-GPU
        if len(all_gpus) > 1:
            card.add_separator()
            card.add_row("GPUs Detected", str(len(all_gpus)), highlight=True)
            for i, g in enumerate(all_gpus):
                label = g.get("display_name", g.get("model", f"GPU {i}"))
                card.add_row(f"GPU {i}", label)

    def _populate_cpu(self, info: dict):
        card = self._cards["cpu"]
        card.clear_rows()

        cpu = info.get("cpu", {})
        card.add_row("Model", cpu.get("model", "Unknown"), highlight=True)
        card.add_row("Vendor", cpu.get("vendor", "Unknown"))

        cores = cpu.get("cores", 0)
        threads = cpu.get("threads", 0)
        if cores and threads:
            card.add_row("Cores / Threads", f"{cores}C / {threads}T")
        elif cores:
            card.add_row("Cores", str(cores))

        clock = cpu.get("base_clock_mhz", 0)
        if clock:
            ghz = clock / 1000
            card.add_row("Base Clock", f"{ghz:.2f} GHz ({clock} MHz)")

        governor = info.get("cpu_governor")
        if governor:
            card.add_row("Governor", governor)

    def _populate_os(self, info: dict):
        card = self._cards["os"]
        card.clear_rows()

        os_info = info.get("os", {})
        card.add_row("Distribution", os_info.get("name", "Unknown"), highlight=True)
        card.add_row("Kernel", os_info.get("kernel", "Unknown"))

        desktop = os_info.get("desktop")
        if desktop:
            card.add_row("Desktop", desktop)

        display = os_info.get("display_server")
        if display:
            card.add_row("Display Server", display.capitalize())

        scheduler = info.get("scheduler")
        if scheduler:
            card.add_row("sched-ext", scheduler, highlight=True)

    def _populate_ram(self, info: dict):
        card = self._cards["ram"]
        card.clear_rows()

        ram = info.get("ram", {})
        total_gb = ram.get("total_gb", 0)
        total_mb = ram.get("total_mb", 0)

        if total_gb:
            card.add_row("Total", f"{total_gb:.0f} GB", highlight=True)
        if total_mb:
            card.add_row("Total (MB)", f"{total_mb:,} MB")

    def _populate_steam(self, info: dict):
        card = self._cards["steam"]
        card.clear_rows()

        steam = info.get("steam_info", info.get("steam", {}))
        path = steam.get("path")

        if path:
            card.add_row("Status", "Installed", highlight=True)
            card.add_row("Path", str(path))
        else:
            card.add_row("Status", "Not found")

        proton = steam.get("proton_versions", [])
        if proton:
            card.add_row("Proton Versions", str(len(proton)))
            # Show top 5 proton versions
            for p in proton[:5]:
                card.add_row("", p)
            if len(proton) > 5:
                card.add_row("", f"... and {len(proton) - 5} more")

        # MangoHud
        mango = info.get("mangohud_installed", False)
        card.add_separator()
        card.add_row(
            "MangoHud",
            "Installed" if mango else "Not found",
            highlight=mango,
        )

    def _populate_extras(self, info: dict):
        card = self._cards["extra"]
        card.clear_rows()

        governor = info.get("cpu_governor")
        if governor:
            card.add_row("CPU Governor", governor)

        scheduler = info.get("scheduler")
        if scheduler:
            card.add_row("sched-ext Scheduler", scheduler, highlight=True)
        else:
            card.add_row("sched-ext Scheduler", "Not active")

        os_info = info.get("os", {})
        display = os_info.get("display_server")
        if display:
            card.add_row("Display Server", display.capitalize())

        desktop = os_info.get("desktop")
        if desktop:
            card.add_row("Desktop Env", desktop)

        gpu = info.get("gpu", {})
        if gpu.get("lspci_raw"):
            card.add_row("lspci", gpu["lspci_raw"])

    # --- Copy all ---

    def _copy_all(self):
        lines = []
        for key, card in self._cards.items():
            lines.append(f"[{card._title}]")
            for key_lbl, val_lbl in card._rows:
                k = key_lbl.text()
                v = val_lbl.text()
                if k:
                    lines.append(f"  {k}: {v}")
                elif v:
                    lines.append(f"  {v}")
            lines.append("")
        QApplication.clipboard().setText("\n".join(lines))
        self._status.setText("Copied to clipboard!")
        self._status.setStyleSheet(
            f"color: {SUCCESS}; font-size: 12px; background: transparent;"
        )
