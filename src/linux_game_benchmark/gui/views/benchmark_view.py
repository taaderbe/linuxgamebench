"""Benchmark control view with state machine for the full benchmark flow."""

from datetime import datetime
from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, ACCENT, ACCENT_HOVER, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER, WARNING, ERROR,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.widgets.game_selector import GameSelector
from linux_game_benchmark.gui.widgets.settings_panel import SettingsPanel
from linux_game_benchmark.gui.widgets.profile_manager import ProfileManager
from linux_game_benchmark.gui.widgets.recording_monitor import RecordingMonitor
from linux_game_benchmark.gui.views.benchmark_results import BenchmarkResults
from linux_game_benchmark.gui.workers import (
    SystemInfoWorker, MangoHudSetupWorker, MangoHudRestoreWorker,
    GameLaunchWorker, BenchmarkMonitorWorker, AnalyzeWorker,
)


class BenchmarkState(Enum):
    IDLE = "idle"
    SETUP = "setup"
    LAUNCHING = "launching"
    WAITING = "waiting"
    RECORDING = "recording"
    ANALYZING = "analyzing"
    RESULTS = "results"


class BenchmarkView(QWidget):
    """Benchmark flow: select game -> configure -> start -> record -> results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = BenchmarkState.IDLE
        self._game: dict = {}
        self._system_info: dict = {}
        self._log_dir = ""
        self._log_path = ""
        self._metrics: dict = {}

        # Workers (keep references to prevent GC)
        self._sysinfo_worker = None
        self._setup_worker = None
        self._launch_worker = None
        self._monitor_worker = None
        self._analyze_worker = None
        self._restore_worker = None

        self._signals = AppSignals.instance()
        self._build_ui()

        # Listen for game selection from Games view
        self._signals.game_selected.connect(self._on_game_selected)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stack: setup panel (0) vs recording panel (1) vs results panel (2)
        self._panel_stack = QStackedWidget()

        # --- Panel 0: Setup (game selection + settings + start) ---
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        setup_scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DARK}; border: none; }}")

        setup_widget = QWidget()
        setup_widget.setStyleSheet("background: transparent;")
        setup_layout = QVBoxLayout(setup_widget)
        setup_layout.setContentsMargins(24, 16, 24, 24)
        setup_layout.setSpacing(16)

        heading = QLabel("Benchmark")
        heading.setProperty("class", "heading")
        setup_layout.addWidget(heading)

        # Game selector
        self._game_selector = GameSelector()
        self._game_selector.game_changed.connect(self._on_game_changed)
        setup_layout.addWidget(self._game_selector)

        # Profile manager - aligned with Game dropdown (184px preview + 12px spacing)
        profile_container = QWidget()
        profile_container.setStyleSheet("background: transparent;")
        profile_layout = QVBoxLayout(profile_container)
        profile_layout.setContentsMargins(196, 0, 0, 0)  # 184 + 12 = left margin
        profile_layout.setSpacing(4)

        pr_label = QLabel("Profile")
        pr_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        profile_layout.addWidget(pr_label)

        self._profile_mgr = ProfileManager()
        self._profile_mgr.profile_loaded.connect(self._on_profile_loaded)
        self._profile_mgr.profile_saved.connect(self._on_profile_save_requested)
        profile_layout.addWidget(self._profile_mgr)

        setup_layout.addWidget(profile_container)

        # Settings panel
        self._settings_panel = SettingsPanel()
        self._settings_panel.load_defaults_from_preferences()
        setup_layout.addWidget(self._settings_panel)

        # Start button
        self._start_btn = QPushButton("Start Benchmark")
        self._start_btn.setFixedHeight(48)
        self._start_btn.setEnabled(False)
        self._start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
            QPushButton:disabled {{
                background-color: {BG_SURFACE};
                color: {TEXT_MUTED};
            }}
        """)
        self._start_btn.clicked.connect(self._start_benchmark)
        setup_layout.addWidget(self._start_btn)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; background: transparent;"
        )
        self._error_label.setVisible(False)
        setup_layout.addWidget(self._error_label)

        setup_layout.addStretch(1)
        setup_scroll.setWidget(setup_widget)
        self._panel_stack.addWidget(setup_scroll)

        # --- Panel 1: Recording ---
        recording_widget = QWidget()
        recording_widget.setStyleSheet("background: transparent;")
        rec_layout = QVBoxLayout(recording_widget)
        rec_layout.setContentsMargins(24, 24, 24, 24)
        rec_layout.setSpacing(0)

        rec_heading = QLabel("Benchmark")
        rec_heading.setProperty("class", "heading")
        rec_layout.addWidget(rec_heading)
        rec_layout.addSpacing(8)

        self._rec_game_label = QLabel("")
        self._rec_game_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; background: transparent;"
        )
        rec_layout.addWidget(self._rec_game_label)
        rec_layout.addStretch(1)

        self._recording_monitor = RecordingMonitor()
        self._recording_monitor.cancel_requested.connect(self._cancel_benchmark)
        rec_layout.addWidget(self._recording_monitor)

        rec_layout.addStretch(1)
        self._panel_stack.addWidget(recording_widget)

        # --- Panel 2: Results ---
        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        results_scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DARK}; border: none; }}")

        results_container = QWidget()
        results_container.setStyleSheet("background: transparent;")
        res_layout = QVBoxLayout(results_container)
        res_layout.setContentsMargins(24, 16, 24, 24)
        res_layout.setSpacing(12)

        res_heading = QLabel("Results")
        res_heading.setProperty("class", "heading")
        res_layout.addWidget(res_heading)

        self._res_game_label = QLabel("")
        self._res_game_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; background: transparent;"
        )
        res_layout.addWidget(self._res_game_label)

        self._results_panel = BenchmarkResults()
        self._results_panel.record_again.connect(self._record_again)
        self._results_panel.end_session.connect(self._end_session)
        res_layout.addWidget(self._results_panel)
        res_layout.addStretch(1)

        results_scroll.setWidget(results_container)
        self._panel_stack.addWidget(results_scroll)

        layout.addWidget(self._panel_stack)

        # Initial pre-flight
        self._signals.auth_changed.connect(self._update_preflight)
        self._signals.settings_saved.connect(self._on_settings_saved)
        QTimer.singleShot(500, self._run_preflight)

        # Detect GPUs and populate settings panel dropdown
        QTimer.singleShot(800, self._detect_gpus)

    # --- Pre-flight (internal, enables/disables start button) ---

    def _run_preflight(self):
        self._update_preflight()

    def _on_settings_saved(self):
        """Reload defaults when settings are saved."""
        self._settings_panel.load_defaults_from_preferences()

    def _update_preflight(self, *args):
        game_ok = bool(self._game)

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

        can_start = game_ok and mango_ok and steam_ok
        self._start_btn.setEnabled(can_start)

    # --- GPU detection ---

    def _detect_gpus(self):
        """Detect GPUs and populate settings panel GPU dropdown."""
        try:
            from linux_game_benchmark.system.hardware_info import detect_all_gpus
            gpus = detect_all_gpus()
            if gpus:
                # Convert to format expected by settings_panel.set_gpus()
                gpu_list = []
                for g in gpus:
                    gpu_list.append({
                        "name": g.get("display_name", g.get("model", "Unknown")),
                        "model": g.get("model", "Unknown"),
                        "pci_address": g.get("pci_address", ""),
                        "type": "dGPU" if g.get("is_dgpu") else "iGPU",
                        "vendor": g.get("vendor", ""),
                    })
                self._settings_panel.set_gpus(gpu_list)

                # Auto-select saved default GPU
                from linux_game_benchmark.config.settings import settings
                default_pci = settings.get_default_gpu() or ""
                if default_pci:
                    for i in range(self._settings_panel._gpu_combo.count()):
                        if self._settings_panel._gpu_combo.itemData(i) == default_pci:
                            self._settings_panel._gpu_combo.setCurrentIndex(i)
                            break
        except Exception:
            pass

    # --- Game selection ---

    def _on_game_selected(self, game: dict):
        """Called from Games view or GameSelector."""
        self._game = game

    def _on_game_changed(self, game: dict):
        """Called when GameSelector combo changes."""
        self._game = game
        app_id = game.get("app_id", 0)
        if app_id:
            self._profile_mgr.set_game(app_id)
        self._update_preflight()

    # --- Profiles ---

    def _on_profile_loaded(self, settings: dict):
        if "resolution" in settings:
            self._settings_panel.set_resolution_key(settings.pop("resolution"))
        self._settings_panel.set_game_settings(settings)

    def _on_profile_save_requested(self, name: str):
        settings = self._settings_panel.get_game_settings()
        settings["resolution"] = self._settings_panel.get_resolution_key()
        self._profile_mgr.store_profile(name, settings)

    # --- Benchmark State Machine ---

    def _set_state(self, state: BenchmarkState):
        self._state = state
        if state == BenchmarkState.IDLE:
            self._panel_stack.setCurrentIndex(0)
        elif state in (
            BenchmarkState.SETUP, BenchmarkState.LAUNCHING,
            BenchmarkState.WAITING, BenchmarkState.RECORDING,
            BenchmarkState.ANALYZING,
        ):
            self._panel_stack.setCurrentIndex(1)
        elif state == BenchmarkState.RESULTS:
            self._panel_stack.setCurrentIndex(2)

    def _start_benchmark(self):
        """Begin the benchmark flow: detect system -> setup MangoHud -> launch game."""
        if not self._game:
            return

        self._error_label.setVisible(False)
        self._set_state(BenchmarkState.SETUP)
        self._rec_game_label.setText(self._game.get("name", ""))
        self._recording_monitor.set_total_duration(self._settings_panel.get_min_duration())
        self._recording_monitor.set_launching()

        # Step 1: Detect system info
        self._sysinfo_worker = SystemInfoWorker(self)
        self._sysinfo_worker.finished.connect(self._on_sysinfo_done)
        self._sysinfo_worker.error.connect(self._on_error)
        self._sysinfo_worker.start()

    def _on_sysinfo_done(self, info: dict):
        self._system_info = info

        # Override GPU info with selected or first discrete GPU
        gpu_pci = self._settings_panel.get_gpu_pci()
        try:
            from linux_game_benchmark.system.hardware_info import detect_all_gpus
            all_gpus = detect_all_gpus()
            target_gpu = None

            if gpu_pci:
                # Find the specifically selected GPU
                for g in all_gpus:
                    if g.get("pci_address") == gpu_pci:
                        target_gpu = g
                        break
            elif len(all_gpus) > 1:
                # Auto-select first discrete GPU
                for g in all_gpus:
                    if g.get("is_dgpu"):
                        target_gpu = g
                        break

            if target_gpu:
                orig_gpu = info.get("gpu", {})
                self._system_info["gpu"] = {
                    "model": target_gpu.get("model", orig_gpu.get("model", "Unknown")),
                    "vendor": target_gpu.get("vendor", orig_gpu.get("vendor", "Unknown")),
                    "driver": orig_gpu.get("driver", ""),
                    "driver_version": orig_gpu.get("driver_version", ""),
                    "vulkan_version": orig_gpu.get("vulkan_version", ""),
                    "vram_mb": target_gpu.get("vram_mb", orig_gpu.get("vram_mb", 0)),
                    "device_id": target_gpu.get("device_id", orig_gpu.get("device_id", "")),
                    "lspci_raw": target_gpu.get("lspci_raw", orig_gpu.get("lspci_raw", "")),
                }
        except Exception:
            pass

        # Step 2: Setup MangoHud + launch options
        app_id = self._game.get("app_id", 0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        game_name = self._game.get("name", "Unknown").replace(" ", "_")
        output_dir = Path.home() / "benchmark_results" / f"{game_name}_{timestamp}"

        gpu_pci = self._settings_panel.get_gpu_pci()
        # If no GPU explicitly selected but multi-GPU, use first dGPU PCI
        if not gpu_pci:
            try:
                from linux_game_benchmark.system.hardware_info import detect_all_gpus
                all_gpus = detect_all_gpus()
                if len(all_gpus) > 1:
                    for g in all_gpus:
                        if g.get("is_dgpu"):
                            gpu_pci = g.get("pci_address", "")
                            break
            except Exception:
                pass

        log_duration = self._settings_panel.get_min_duration()

        # Add 1 second buffer to ensure we meet minimum duration
        # (MangoHud timing can be slightly imprecise)
        actual_log_duration = log_duration + 1 if log_duration > 0 else 0

        self._setup_worker = MangoHudSetupWorker(
            app_id, output_dir, gpu_pci,
            log_duration=actual_log_duration, parent=self,
        )
        self._setup_worker.finished.connect(self._on_setup_done)
        self._setup_worker.start()

    def _on_setup_done(self, success: bool, error: str, log_dir: str):
        if not success:
            self._on_error(f"Setup failed: {error}")
            return

        self._log_dir = log_dir
        self._set_state(BenchmarkState.LAUNCHING)

        # Step 3: Launch game
        app_id = self._game.get("app_id", 0)
        self._launch_worker = GameLaunchWorker(app_id, parent=self)
        self._launch_worker.finished.connect(self._on_launch_done)
        self._launch_worker.start()

    def _on_launch_done(self, success: bool, error: str):
        if not success:
            self._on_error(f"Launch failed: {error}")
            return

        # Step 4: Start monitoring for recording
        self._set_state(BenchmarkState.WAITING)
        self._recording_monitor.set_waiting()

        self._monitor_worker = BenchmarkMonitorWorker(self._log_dir, parent=self)
        self._monitor_worker.recording_started.connect(self._on_recording_started)
        self._monitor_worker.recording_done.connect(self._on_recording_done)
        self._monitor_worker.error.connect(self._on_error)
        self._monitor_worker.start()

    def _on_recording_started(self, log_path: str):
        self._log_path = log_path
        self._set_state(BenchmarkState.RECORDING)
        self._recording_monitor.set_recording()

    def _on_recording_done(self, log_path: str):
        self._log_path = log_path
        self._set_state(BenchmarkState.ANALYZING)
        self._recording_monitor.set_analyzing()

        # Step 5: Analyze
        self._analyze_worker = AnalyzeWorker(log_path, parent=self)
        self._analyze_worker.finished.connect(self._on_analysis_done)
        self._analyze_worker.error.connect(self._on_error)
        self._analyze_worker.start()

    def _on_analysis_done(self, metrics: dict):
        self._metrics = metrics

        # Restore MangoHud and launch options
        app_id = self._game.get("app_id", 0)
        self._restore_worker = MangoHudRestoreWorker(app_id, parent=self)
        self._restore_worker.start()

        # Save locally (same as CLI)
        self._save_local_benchmark(metrics)

        # Store settings in game dict for upload
        game_with_settings = dict(self._game)
        game_with_settings["_settings"] = self._settings_panel.get_game_settings()
        game_with_settings["_resolution_key"] = self._settings_panel.get_resolution_key()

        # Show results
        self._set_state(BenchmarkState.RESULTS)
        self._res_game_label.setText(self._game.get("name", ""))
        self._results_panel.set_results(
            metrics, game_with_settings, self._system_info, self._log_path
        )

    def _save_local_benchmark(self, metrics: dict):
        """Save benchmark results locally, same structure as CLI."""
        try:
            from linux_game_benchmark.benchmark.storage import (
                BenchmarkStorage, SystemFingerprint,
            )
            from linux_game_benchmark.config.preferences import Preferences

            storage = BenchmarkStorage()
            app_id = self._game.get("app_id", 0)
            if not app_id:
                return

            # Save game display name
            game_dir = storage.get_game_dir(app_id)
            info_file = game_dir / "game_info.json"
            if not info_file.exists():
                import json
                info_file.write_text(json.dumps({
                    "steam_app_id": app_id,
                    "display_name": self._game.get("name", "Unknown"),
                }, indent=2))

            # Create fingerprint from system info
            fp = SystemFingerprint.from_system_info(self._system_info)
            storage.save_fingerprint(app_id, fp, self._system_info)

            # Resolve resolution string (e.g. "1920x1080")
            res_key = self._settings_panel.get_resolution_key()
            res_display = Preferences.RESOLUTION_NAMES.get(res_key, "FHD (1920x1080)")
            # Extract "1920x1080" from "FHD (1920x1080)"
            import re
            m = re.search(r"(\d+x\d+)", res_display)
            resolution = m.group(1) if m else "1920x1080"

            # Get frametimes for local storage
            frametimes = metrics.get("_frametimes", [])

            # Save run
            log_path = Path(self._log_path) if self._log_path else None
            storage.save_run(
                game_id=app_id,
                resolution=resolution,
                metrics=metrics,
                log_path=log_path,
                frametimes=frametimes if frametimes else None,
            )

            self._signals.status_message.emit(
                "Benchmark saved locally", "success"
            )
        except Exception as e:
            self._signals.status_message.emit(
                f"Local save failed: {e}", "warning"
            )

    # --- Error handling ---

    def _on_error(self, error: str):
        self._set_state(BenchmarkState.IDLE)
        self._recording_monitor.set_idle()
        self._error_label.setText(error)
        self._error_label.setVisible(True)

        # Restore MangoHud on error
        app_id = self._game.get("app_id", 0)
        if app_id:
            self._restore_worker = MangoHudRestoreWorker(app_id, parent=self)
            self._restore_worker.start()

    # --- Cancel ---

    def _cancel_benchmark(self):
        if self._monitor_worker:
            self._monitor_worker.cancel()
        self._on_error("Benchmark cancelled")

    # --- Session controls ---

    def _record_again(self):
        """Start another recording for the same game."""
        self._set_state(BenchmarkState.IDLE)
        self._recording_monitor.set_idle()
        # Pre-fill is preserved, user just clicks Start again

    def _end_session(self):
        """Return to idle state, clear selection."""
        self._set_state(BenchmarkState.IDLE)
        self._recording_monitor.set_idle()
        self._metrics = {}
        self._log_path = ""
