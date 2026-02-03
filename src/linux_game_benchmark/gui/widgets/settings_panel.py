"""Game settings form with resolution, GPU, and all game-specific dropdowns."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame,
    QPushButton, QGridLayout, QSizePolicy, QSpinBox, QLineEdit,
)
from PySide6.QtCore import Qt, Signal

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
)


def _title_case(s: str) -> str:
    """Capitalize for display: 'ultra-quality' -> 'Ultra-Quality'."""
    return s.replace("-", " ").replace("_", " ").title() if s else ""


class SettingsPanel(QWidget):
    """Game settings panel with resolution, GPU, and all VALID_OPTIONS dropdowns."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combos: dict[str, QComboBox] = {}
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- Resolution & Duration row ---
        res_frame = self._make_section("Resolution, Duration & GPU")
        res_layout = QGridLayout()
        res_layout.setSpacing(8)

        from linux_game_benchmark.config.preferences import Preferences
        res_names = Preferences.RESOLUTION_NAMES

        res_label = QLabel("Resolution")
        res_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        res_layout.addWidget(res_label, 0, 0)
        self._res_combo = QComboBox()
        self._res_combo.setFixedHeight(34)
        for key, display in res_names.items():
            self._res_combo.addItem(display, userData=key)
        self._res_combo.setCurrentIndex(1)  # FHD default
        self._res_combo.currentIndexChanged.connect(lambda: self.settings_changed.emit())
        res_layout.addWidget(self._res_combo, 0, 1)

        # Duration setting
        dur_label = QLabel("Min. Duration")
        dur_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        res_layout.addWidget(dur_label, 0, 2)
        self._dur_spin = QSpinBox()
        self._dur_spin.setFixedHeight(34)
        self._dur_spin.setMinimum(30)
        self._dur_spin.setMaximum(300)
        self._dur_spin.setValue(60)
        self._dur_spin.setSuffix(" s")
        self._dur_spin.setToolTip("Minimum benchmark duration (30-300 seconds)")
        self._dur_spin.valueChanged.connect(lambda: self.settings_changed.emit())
        res_layout.addWidget(self._dur_spin, 0, 3)

        # GPU selector (only visible for multi-GPU)
        gpu_label = QLabel("GPU")
        gpu_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        self._gpu_label = gpu_label
        res_layout.addWidget(gpu_label, 1, 0)
        self._gpu_combo = QComboBox()
        self._gpu_combo.setFixedHeight(34)
        self._gpu_combo.currentIndexChanged.connect(lambda: self.settings_changed.emit())
        res_layout.addWidget(self._gpu_combo, 1, 1)

        # Hide GPU row by default, shown when multi-GPU detected
        self._gpu_label.setVisible(False)
        self._gpu_combo.setVisible(False)

        res_frame.layout().addLayout(res_layout)
        layout.addWidget(res_frame)

        # --- Game Settings ---
        self._settings_frame = self._make_section("Game Settings")
        settings_grid = QGridLayout()
        settings_grid.setSpacing(8)
        settings_grid.setColumnStretch(1, 1)
        settings_grid.setColumnStretch(3, 1)

        valid_options = Preferences.VALID_OPTIONS
        # Game settings (without OC - those go in separate section)
        game_fields = [
            ("preset", "Preset"),
            ("raytracing", "Ray Tracing"),
            ("upscaling", "Upscaling"),
            ("upscaling_quality", "Upscaling Quality"),
            ("framegen", "Frame Gen"),
            ("aa", "Anti-Aliasing"),
            ("hdr", "HDR"),
            ("vsync", "VSync"),
            ("framelimit", "Frame Limit"),
        ]

        # Fields with natural on/off defaults
        TOGGLE_DEFAULTS = {
            "hdr": "off",
            "vsync": "off",
        }

        row = 0
        col = 0
        for key, display_name in game_fields:
            options = valid_options.get(key, [])

            lbl = QLabel(display_name)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
            settings_grid.addWidget(lbl, row, col * 2)

            combo = QComboBox()
            combo.setFixedHeight(34)

            if key in TOGGLE_DEFAULTS:
                default_val = TOGGLE_DEFAULTS[key]
                combo.addItem(_title_case(default_val), userData=default_val)
                for opt in options:
                    if opt != default_val:
                        combo.addItem(_title_case(opt), userData=opt)
            elif "none" in options:
                combo.addItem("None", userData="none")
                for opt in options:
                    if opt != "none":
                        combo.addItem(_title_case(opt), userData=opt)
            else:
                combo.addItem("None", userData="none")
                for opt in options:
                    combo.addItem(_title_case(opt), userData=opt)

            combo.currentIndexChanged.connect(lambda: self.settings_changed.emit())
            settings_grid.addWidget(combo, row, col * 2 + 1)
            self._combos[key] = combo

            col += 1
            if col >= 2:
                col = 0
                row += 1

        self._settings_frame.layout().addLayout(settings_grid)
        layout.addWidget(self._settings_frame)

        # --- Hardware Overclock Section ---
        self._oc_frame = self._make_section("Hardware Overclock")
        oc_grid = QGridLayout()
        oc_grid.setSpacing(8)
        oc_grid.setColumnStretch(1, 1)
        oc_grid.setColumnStretch(3, 1)

        # Row 0: CPU OC dropdown (left) | GPU OC dropdown (right)
        cpu_oc_lbl = QLabel("CPU OC")
        cpu_oc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        oc_grid.addWidget(cpu_oc_lbl, 0, 0)
        cpu_oc_combo = QComboBox()
        cpu_oc_combo.setFixedHeight(34)
        cpu_oc_combo.addItem("No", userData="no")
        cpu_oc_combo.addItem("Yes", userData="yes")
        cpu_oc_combo.currentIndexChanged.connect(lambda: self.settings_changed.emit())
        cpu_oc_combo.currentIndexChanged.connect(self._on_cpu_oc_changed)
        oc_grid.addWidget(cpu_oc_combo, 0, 1)
        self._combos["cpu_oc"] = cpu_oc_combo

        gpu_oc_lbl = QLabel("GPU OC")
        gpu_oc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        oc_grid.addWidget(gpu_oc_lbl, 0, 2)
        gpu_oc_combo = QComboBox()
        gpu_oc_combo.setFixedHeight(34)
        gpu_oc_combo.addItem("No", userData="no")
        gpu_oc_combo.addItem("Yes", userData="yes")
        gpu_oc_combo.currentIndexChanged.connect(lambda: self.settings_changed.emit())
        gpu_oc_combo.currentIndexChanged.connect(self._on_gpu_oc_changed)
        oc_grid.addWidget(gpu_oc_combo, 0, 3)
        self._combos["gpu_oc"] = gpu_oc_combo

        # Row 1: CPU Info (left) | GPU Info (right) - shown when OC = Yes
        self._cpu_oc_info_lbl = QLabel("CPU Info")
        self._cpu_oc_info_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._cpu_oc_info_lbl.setVisible(False)
        oc_grid.addWidget(self._cpu_oc_info_lbl, 1, 0)
        self._cpu_oc_detail = QLineEdit()
        self._cpu_oc_detail.setPlaceholderText("5.2 GHz all-core, 1.35V")
        self._cpu_oc_detail.setFixedHeight(34)
        self._cpu_oc_detail.setVisible(False)
        oc_grid.addWidget(self._cpu_oc_detail, 1, 1)

        self._gpu_oc_info_lbl = QLabel("GPU Info")
        self._gpu_oc_info_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._gpu_oc_info_lbl.setVisible(False)
        oc_grid.addWidget(self._gpu_oc_info_lbl, 1, 2)
        self._gpu_oc_detail = QLineEdit()
        self._gpu_oc_detail.setPlaceholderText("+150 core, +500 mem")
        self._gpu_oc_detail.setFixedHeight(34)
        self._gpu_oc_detail.setVisible(False)
        oc_grid.addWidget(self._gpu_oc_detail, 1, 3)

        self._oc_frame.layout().addLayout(oc_grid)
        layout.addWidget(self._oc_frame)

    def _on_cpu_oc_changed(self):
        """Show/hide CPU OC info field based on dropdown value."""
        combo = self._combos.get("cpu_oc")
        if combo:
            show = combo.currentData() == "yes"
            self._cpu_oc_info_lbl.setVisible(show)
            self._cpu_oc_detail.setVisible(show)
            if not show:
                self._cpu_oc_detail.clear()

    def _on_gpu_oc_changed(self):
        """Show/hide GPU OC info field based on dropdown value."""
        combo = self._combos.get("gpu_oc")
        if combo:
            show = combo.currentData() == "yes"
            self._gpu_oc_info_lbl.setVisible(show)
            self._gpu_oc_detail.setVisible(show)
            if not show:
                self._gpu_oc_detail.clear()

    def _make_section(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "card")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(8)

        heading = QLabel(title)
        heading.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent;"
        )
        frame_layout.addWidget(heading)
        return frame

    # --- GPU ---

    def set_gpus(self, gpus: list[dict]):
        """Populate GPU combo from detected GPUs. Hide if single GPU."""
        self._gpu_combo.blockSignals(True)
        self._gpu_combo.clear()
        for gpu in gpus:
            name = gpu.get("name", gpu.get("model", "Unknown GPU"))
            pci = gpu.get("pci_address", "")
            gpu_type = gpu.get("type", "")
            display = f"{name} ({gpu_type})" if gpu_type else name
            self._gpu_combo.addItem(display, userData=pci)
        self._gpu_combo.blockSignals(False)

        multi = len(gpus) > 1
        self._gpu_label.setVisible(multi)
        self._gpu_combo.setVisible(multi)

    # --- Get/Set Values ---

    def get_resolution_key(self) -> str:
        """Return resolution key like '2' for FHD."""
        return self._res_combo.currentData() or "2"

    def get_min_duration(self) -> int:
        """Return minimum benchmark duration in seconds."""
        return self._dur_spin.value()

    def get_gpu_pci(self) -> str:
        """Return selected GPU PCI address, or empty string."""
        return self._gpu_combo.currentData() or ""

    def get_game_settings(self) -> dict:
        """Return dict of non-None game settings, including OC details."""
        result = {}
        for key, combo in self._combos.items():
            val = combo.currentData()
            if val is not None:
                result[key] = val
        # Add OC info if OC is enabled (matches CLI field names)
        if result.get("cpu_oc") == "yes":
            info = self._cpu_oc_detail.text().strip()
            if info:
                result["cpu_oc_info"] = info
        if result.get("gpu_oc") == "yes":
            info = self._gpu_oc_detail.text().strip()
            if info:
                result["gpu_oc_info"] = info
        return result

    def set_game_settings(self, settings: dict):
        """Apply settings dict to dropdowns and OC info fields."""
        for key, combo in self._combos.items():
            val = settings.get(key)
            if val is None:
                combo.setCurrentIndex(0)
            else:
                for i in range(combo.count()):
                    if combo.itemData(i) == val:
                        combo.setCurrentIndex(i)
                        break
        # Set OC info fields
        self._cpu_oc_detail.setText(settings.get("cpu_oc_info", ""))
        self._gpu_oc_detail.setText(settings.get("gpu_oc_info", ""))
        # Update visibility
        self._on_cpu_oc_changed()
        self._on_gpu_oc_changed()

    def set_resolution_key(self, key: str):
        """Set resolution by key like '3' for WQHD."""
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == key:
                self._res_combo.setCurrentIndex(i)
                return

    def reset_game_settings(self):
        """Reset all game settings to 'Not set'."""
        for combo in self._combos.values():
            combo.setCurrentIndex(0)
        # Clear and hide OC detail fields
        self._cpu_oc_detail.clear()
        self._gpu_oc_detail.clear()
        self._on_cpu_oc_changed()
        self._on_gpu_oc_changed()

    def load_defaults_from_preferences(self):
        """Load default settings from preferences."""
        try:
            from linux_game_benchmark.config.preferences import preferences
            self.set_resolution_key(preferences.resolution)
            self._dur_spin.setValue(preferences.duration)
            defaults = {}
            for key in self._combos:
                val = getattr(preferences, f"default_{key}", None)
                if val:
                    defaults[key] = val
            self.set_game_settings(defaults)
        except Exception:
            pass
