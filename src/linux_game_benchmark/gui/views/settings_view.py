"""Settings view - benchmark defaults, connection, GPU, game settings, info."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QGridLayout, QScrollArea, QSizePolicy, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, BG_CARD, ACCENT, ACCENT_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
    SUCCESS, WARNING, ERROR,
)
from linux_game_benchmark.gui.workers import UpdateCheckWorker


def _title_case(s: str) -> str:
    return s.replace("-", " ").replace("_", " ").title() if s else ""


class SettingsView(QWidget):
    """Application settings and preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._game_combos: dict[str, QComboBox] = {}
        self._update_worker = None
        self._visible = False

        self._build_ui()
        self._load_current_values()

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
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 16, 24, 24)
        cl.setSpacing(16)

        # Header
        header_row = QWidget()
        header_row.setStyleSheet("background: transparent;")
        hr = QHBoxLayout(header_row)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(12)

        heading = QLabel("Settings")
        heading.setProperty("class", "heading")
        hr.addWidget(heading)

        hr.addStretch(1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(36)
        self._save_btn.setFixedWidth(90)
        self._save_btn.setProperty("class", "secondary")
        self._save_btn.clicked.connect(self._save_all)
        hr.addWidget(self._save_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedHeight(36)
        reset_btn.setProperty("class", "danger")
        reset_btn.clicked.connect(self._reset_all)
        hr.addWidget(reset_btn)

        cl.addWidget(header_row)

        # === Section 1: Benchmark Defaults ===
        bench_frame = self._make_section("Benchmark Defaults")
        bg = QGridLayout()
        bg.setSpacing(8)
        bg.setColumnStretch(1, 1)

        # Resolution
        bg.addWidget(self._make_label("Default Resolution"), 0, 0)
        self._res_combo = QComboBox()
        self._res_combo.setFixedHeight(32)
        from linux_game_benchmark.config.preferences import Preferences
        for key, display in Preferences.RESOLUTION_NAMES.items():
            self._res_combo.addItem(display, userData=key)
        bg.addWidget(self._res_combo, 0, 1)

        # Upload
        bg.addWidget(self._make_label("Upload"), 1, 0)
        self._upload_combo = QComboBox()
        self._upload_combo.setFixedHeight(32)
        self._upload_combo.addItem("Yes", userData="y")
        self._upload_combo.addItem("No", userData="n")
        bg.addWidget(self._upload_combo, 1, 1)

        # Duration
        bg.addWidget(self._make_label("Duration"), 2, 0)
        self._duration_spin = QSpinBox()
        self._duration_spin.setFixedHeight(32)
        self._duration_spin.setMinimum(30)
        self._duration_spin.setMaximum(300)
        self._duration_spin.setValue(30)
        self._duration_spin.setSuffix(" s")
        bg.addWidget(self._duration_spin, 2, 1)

        bench_frame.layout().addLayout(bg)
        cl.addWidget(bench_frame)

        # === Section 1b: UI Scale ===
        scale_frame = self._make_section("UI Scale")
        sg = QGridLayout()
        sg.setSpacing(8)
        sg.setColumnStretch(1, 1)

        sg.addWidget(self._make_label("Scale Factor"), 0, 0)
        self._scale_combo = QComboBox()
        self._scale_combo.setFixedHeight(34)
        for label, value in [
            ("50%", 1.0),
            ("75%", 1.5),
            ("100% (Default)", 2.0),
            ("125%", 2.5),
            ("150%", 3.0),
            ("175%", 3.5),
            ("200%", 4.0),
        ]:
            self._scale_combo.addItem(label, userData=value)
        sg.addWidget(self._scale_combo, 0, 1)

        self._scale_note = QLabel("")
        self._scale_note.setStyleSheet(
            f"color: {WARNING}; font-size: 12px; background: transparent; font-style: italic;"
        )
        self._scale_note.setVisible(False)
        self._scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        sg.addWidget(self._scale_note, 1, 0, 1, 2)

        scale_frame.layout().addLayout(sg)
        cl.addWidget(scale_frame)

        # === Section 2: GPU Default ===
        gpu_frame = self._make_section("GPU Default")
        gl = QGridLayout()
        gl.setSpacing(8)
        gl.setColumnStretch(1, 1)

        gl.addWidget(self._make_label("Default GPU"), 0, 0)
        self._gpu_combo = QComboBox()
        self._gpu_combo.setFixedHeight(32)
        self._gpu_combo.addItem("Auto-detect (first dGPU)", userData="")
        gl.addWidget(self._gpu_combo, 0, 1)

        self._gpu_status = QLabel("")
        self._gpu_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        gl.addWidget(self._gpu_status, 1, 0, 1, 2)

        gpu_frame.layout().addLayout(gl)
        cl.addWidget(gpu_frame)

        # Populate GPUs async
        self._detect_gpus()

        # === Section 3: Game Settings Defaults ===
        game_frame = self._make_section("Game Settings Defaults")
        gg = QGridLayout()
        gg.setSpacing(8)
        gg.setColumnStretch(1, 1)
        gg.setColumnStretch(3, 1)

        fields = [
            ("preset", "Preset"),
            ("raytracing", "Ray Tracing"),
            ("upscaling", "Upscaling"),
            ("upscaling_quality", "Upscaling Quality"),
            ("framegen", "Frame Gen"),
            ("aa", "Anti-Aliasing"),
            ("hdr", "HDR"),
            ("vsync", "VSync"),
            ("framelimit", "Frame Limit"),
            ("cpu_oc", "CPU OC"),
            ("gpu_oc", "GPU OC"),
        ]

        valid_options = Preferences.VALID_OPTIONS
        # Fields with natural on/off or yes/no defaults
        TOGGLE_DEFAULTS = {
            "hdr": "off",
            "vsync": "off",
            "cpu_oc": "no",
            "gpu_oc": "no",
        }

        row = 0
        col = 0
        for key, display_name in fields:
            options = valid_options.get(key, [])

            lbl = self._make_label(display_name)
            gg.addWidget(lbl, row, col * 2)

            combo = QComboBox()
            combo.setFixedHeight(30)

            if key in TOGGLE_DEFAULTS:
                # Toggle fields: natural default first
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

            gg.addWidget(combo, row, col * 2 + 1)
            self._game_combos[key] = combo

            col += 1
            if col >= 2:
                col = 0
                row += 1

        game_frame.layout().addLayout(gg)
        cl.addWidget(game_frame)

        # === Section 4: Info ===
        info_frame = self._make_section("About")
        ig = QGridLayout()
        ig.setSpacing(8)
        ig.setColumnStretch(1, 1)

        from linux_game_benchmark.config.settings import settings
        ig.addWidget(self._make_label("Client Version"), 0, 0)
        ver_lbl = QLabel(settings.CLIENT_VERSION)
        ver_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 700; "
            "font-family: monospace; background: transparent;"
        )
        ig.addWidget(ver_lbl, 0, 1)

        update_btn = QPushButton("Check for Updates")
        update_btn.setFixedHeight(34)
        update_btn.setProperty("class", "secondary")
        update_btn.clicked.connect(self._check_updates)
        self._update_btn = update_btn
        ig.addWidget(update_btn, 1, 0)

        self._update_status = QLabel("")
        self._update_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        ig.addWidget(self._update_status, 1, 1)

        ig.addWidget(self._make_label("Website"), 2, 0)
        site_lbl = QLabel("linuxgamebench.com")
        site_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; background: transparent; "
            "text-decoration: underline;"
        )
        site_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        site_lbl.mousePressEvent = lambda e: self._open_url("https://linuxgamebench.com")
        ig.addWidget(site_lbl, 2, 1)

        ig.addWidget(self._make_label("GitHub"), 3, 0)
        gh_lbl = QLabel("github.com/taaderbe/linuxgamebench")
        gh_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; background: transparent; "
            "text-decoration: underline;"
        )
        gh_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        gh_lbl.mousePressEvent = lambda e: self._open_url(
            "https://github.com/taaderbe/linuxgamebench"
        )
        ig.addWidget(gh_lbl, 3, 1)

        info_frame.layout().addLayout(ig)
        cl.addWidget(info_frame)

        cl.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

    # --- Helpers ---

    def _make_section(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(16, 12, 16, 14)
        fl.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet(
            f"color: {ACCENT}; font-size: 14px; font-weight: 700; "
            "background: transparent;"
        )
        fl.addWidget(heading)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER};")
        fl.addWidget(sep)

        return frame

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        return lbl

    # --- Load / Save ---

    def _load_current_values(self):
        from linux_game_benchmark.config.settings import settings
        from linux_game_benchmark.config.preferences import preferences

        # Resolution
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == preferences.resolution:
                self._res_combo.setCurrentIndex(i)
                break

        # Upload
        upload = preferences.upload
        self._upload_combo.setCurrentIndex(0 if upload == "y" else 1)

        # Duration
        duration = getattr(preferences, "duration", 30)
        self._duration_spin.setValue(duration)

        # Game settings defaults
        for key, combo in self._game_combos.items():
            val = getattr(preferences, f"default_{key}", None)
            if val:
                for i in range(combo.count()):
                    if combo.itemData(i) == val:
                        combo.setCurrentIndex(i)
                        break
            else:
                combo.setCurrentIndex(0)

        # UI Scale
        self._load_ui_scale()

    def _save_all(self):
        from linux_game_benchmark.config.settings import settings
        from linux_game_benchmark.config.preferences import preferences

        # Resolution
        preferences.resolution = self._res_combo.currentData() or "2"

        # Upload
        preferences.upload = self._upload_combo.currentData() or "y"

        # Duration
        preferences.duration = self._duration_spin.value()

        # GPU
        gpu_pci = self._gpu_combo.currentData() or ""
        if gpu_pci:
            preferences.gpu_preference = gpu_pci
            idx = self._gpu_combo.currentIndex()
            preferences.gpu_display_name = self._gpu_combo.itemText(idx)
            settings.set_default_gpu(gpu_pci)
        else:
            preferences.clear_gpu_preference()
            settings.clear_default_gpu()

        # Game settings defaults
        for key, combo in self._game_combos.items():
            val = combo.currentData()
            setattr(preferences, f"default_{key}", val)

        # UI Scale
        scale_changed = self._save_ui_scale()

        # Emit settings_saved signal so other views can reload
        from linux_game_benchmark.gui.signals import AppSignals
        AppSignals.instance().settings_saved.emit()

        # Show "Saved!" feedback on button
        self._save_btn.setText("Saved!")
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(78, 204, 163, 0.15);
                color: {SUCCESS};
                border: 1px solid {SUCCESS};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)
        QTimer.singleShot(1500, self._reset_save_btn)

    def _reset_save_btn(self):
        """Reset save button to normal state."""
        self._save_btn.setText("Save")
        self._save_btn.setStyleSheet("")  # Revert to class-based QSS

    def _reset_all(self):
        from linux_game_benchmark.config.preferences import preferences
        preferences.reset()
        self._load_current_values()
        # Reset game combos to not-set
        for combo in self._game_combos.values():
            combo.setCurrentIndex(0)

    # --- GPU detection ---

    def _detect_gpus(self):
        try:
            from linux_game_benchmark.system.hardware_info import detect_all_gpus
            from linux_game_benchmark.config.settings import settings

            gpus = detect_all_gpus()
            default_pci = settings.get_default_gpu() or ""

            if len(gpus) > 1:
                self._gpu_combo.clear()
                self._gpu_combo.addItem("Auto-detect (first dGPU)", userData="")
                for g in gpus:
                    name = g.get("display_name", g.get("model", "Unknown"))
                    pci = g.get("pci_address", "")
                    self._gpu_combo.addItem(name, userData=pci)
                    if default_pci and pci == default_pci:
                        self._gpu_combo.setCurrentIndex(self._gpu_combo.count() - 1)
                self._gpu_status.setText(f"{len(gpus)} GPUs detected")
            else:
                self._gpu_status.setText(
                    "Single GPU detected - no selection needed"
                )
        except Exception:
            self._gpu_status.setText("GPU detection unavailable")

    # --- Update check ---

    def _check_updates(self):
        self._update_btn.setEnabled(False)
        self._update_status.setText("Checking...")
        self._update_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )

        self._update_worker = UpdateCheckWorker(parent=self)
        self._update_worker.finished.connect(self._on_update_result)
        self._update_worker.start()

    def _on_update_result(self, new_version):
        self._update_btn.setEnabled(True)
        if new_version:
            self._update_status.setText(f"Update available: v{new_version}")
            self._update_status.setStyleSheet(
                f"color: {WARNING}; font-size: 12px; font-weight: 600; "
                "background: transparent;"
            )
        else:
            self._update_status.setText("Up to date")
            self._update_status.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px; background: transparent;"
            )

    # --- UI Scale ---

    def _on_scale_changed(self):
        """Show restart hint when scale is changed."""
        current = self._scale_combo.currentData() or 2.0
        if hasattr(self, "_initial_scale") and abs(current - self._initial_scale) > 0.01:
            self._scale_note.setText("Restart required for changes to take effect.")
            self._scale_note.setVisible(True)
        else:
            self._scale_note.setVisible(False)

    def _load_ui_scale(self):
        import json
        from pathlib import Path
        try:
            state_file = Path.home() / ".config" / "lgb" / "gui_state.json"
            scale = 2.0
            if state_file.exists():
                data = json.loads(state_file.read_text())
                scale = data.get("ui_scale", 2.0)
            self._initial_scale = scale  # Store initial scale for comparison
            for i in range(self._scale_combo.count()):
                if abs(self._scale_combo.itemData(i) - scale) < 0.01:
                    self._scale_combo.setCurrentIndex(i)
                    return
            self._scale_combo.setCurrentIndex(0)
        except Exception:
            self._initial_scale = 2.0
            self._scale_combo.setCurrentIndex(0)

    def _save_ui_scale(self) -> bool:
        """Save UI scale. Returns True if scale changed from current value."""
        import json
        from pathlib import Path
        try:
            state_file = Path.home() / ".config" / "lgb" / "gui_state.json"
            data = {}
            if state_file.exists():
                data = json.loads(state_file.read_text())
            old_scale = data.get("ui_scale", 2.0)
            new_scale = self._scale_combo.currentData() or 2.0
            data["ui_scale"] = new_scale
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(data, indent=2))
            return abs(old_scale - new_scale) > 0.01
        except Exception:
            return False

    # --- Links ---

    @staticmethod
    def _open_url(url: str):
        import webbrowser
        webbrowser.open(url)
