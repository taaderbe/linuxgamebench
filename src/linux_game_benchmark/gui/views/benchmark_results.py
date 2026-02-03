"""Benchmark results panel with comment prompt, auto-upload, and FPS display."""

import webbrowser

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal

from linux_game_benchmark.gui.constants import (
    BG_SURFACE, BG_CARD, ACCENT, ACCENT_HOVER, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER, SUCCESS, ERROR,
)
from linux_game_benchmark.gui.widgets.fps_display import FpsDisplay
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import UploadWorker


class BenchmarkResults(QWidget):
    """Results panel with two-phase flow: comment/upload first, then show FPS."""

    record_again = Signal()
    end_session = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._metrics = {}
        self._game = {}
        self._system_info = {}
        self._log_path = ""
        self._upload_worker = None
        self._auto_upload = False

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stack: phase 1 (comment/upload) vs phase 2 (results)
        self._stack = QStackedWidget()

        # === Phase 1: Comment + Upload/Skip ===
        phase1 = QWidget()
        phase1.setStyleSheet("background: transparent;")
        p1_layout = QVBoxLayout(phase1)
        p1_layout.setContentsMargins(0, 0, 0, 0)
        p1_layout.setSpacing(16)

        # Status message (shows "Uploading..." or "Saved locally")
        self._phase1_status = QLabel("")
        self._phase1_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._phase1_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 600; "
            "background: transparent;"
        )
        p1_layout.addWidget(self._phase1_status)

        # Comment field (only shown when auto-upload is ON)
        self._comment_frame = QFrame()
        self._comment_frame.setProperty("class", "card")
        self._comment_frame.setStyleSheet(
            f"QFrame {{ border: 1px solid {ACCENT}; border-radius: 10px; "
            f"background-color: rgba(0, 173, 181, 0.06); }}"
        )
        cf_layout = QVBoxLayout(self._comment_frame)
        cf_layout.setContentsMargins(14, 12, 14, 12)
        cf_layout.setSpacing(8)

        comment_label = QLabel("Comment (optional)")
        comment_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 700; "
            "background: transparent;"
        )
        cf_layout.addWidget(comment_label)

        self._comment = QLineEdit()
        self._comment.setPlaceholderText("Add extra info or notes about this run...")
        self._comment.setFixedHeight(40)
        self._comment.returnPressed.connect(self._on_ok_clicked)
        cf_layout.addWidget(self._comment)

        p1_layout.addWidget(self._comment_frame)

        # OK button (upload or continue)
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setFixedHeight(48)
        self._ok_btn.setStyleSheet(f"""
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
        self._ok_btn.clicked.connect(self._on_ok_clicked)
        p1_layout.addWidget(self._ok_btn)

        p1_layout.addStretch(1)
        self._stack.addWidget(phase1)

        # === Phase 2: FPS Results ===
        phase2 = QWidget()
        phase2.setStyleSheet("background: transparent;")
        p2_layout = QVBoxLayout(phase2)
        p2_layout.setContentsMargins(0, 0, 0, 0)
        p2_layout.setSpacing(16)

        # Upload status at top
        self._result_status = QLabel("")
        self._result_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_status.setStyleSheet(
            f"color: {SUCCESS}; font-size: 14px; font-weight: 600; "
            "background: transparent;"
        )
        p2_layout.addWidget(self._result_status)

        # URL display (shown after upload)
        self._url_label = QLabel("")
        self._url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; background: transparent; "
            "text-decoration: underline;"
        )
        self._url_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url_label.setVisible(False)
        self._url_label.mousePressEvent = self._open_url
        p2_layout.addWidget(self._url_label)

        # FPS display
        self._fps_display = FpsDisplay()
        p2_layout.addWidget(self._fps_display)

        # Duration + frames info
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p2_layout.addWidget(self._info_label)

        # Action buttons
        actions = QWidget()
        actions.setStyleSheet("background: transparent;")
        act_layout = QHBoxLayout(actions)
        act_layout.setContentsMargins(0, 12, 0, 0)
        act_layout.setSpacing(10)

        record_btn = QPushButton("Record Another")
        record_btn.setFixedHeight(38)
        record_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SURFACE};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT_PRIMARY}; }}
        """)
        record_btn.clicked.connect(self.record_again.emit)
        act_layout.addWidget(record_btn, 1)

        end_btn = QPushButton("End Session")
        end_btn.setFixedHeight(38)
        end_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SURFACE};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {ERROR}; color: {ERROR}; }}
        """)
        end_btn.clicked.connect(self.end_session.emit)
        act_layout.addWidget(end_btn, 1)

        p2_layout.addWidget(actions)
        p2_layout.addStretch(1)

        self._stack.addWidget(phase2)
        layout.addWidget(self._stack)

    # --- Set data ---

    def set_results(self, metrics: dict, game: dict, system_info: dict, log_path: str):
        self._metrics = metrics
        self._game = game
        self._system_info = system_info
        self._log_path = log_path

        # Check auto-upload setting
        self._auto_upload = self._get_auto_upload_setting()

        # Reset state
        self._comment.clear()
        self._url_label.setVisible(False)
        self._result_status.setText("")
        self._ok_btn.setEnabled(True)
        self._ok_btn.setText("OK")

        if self._auto_upload:
            # Show comment field, OK button will upload
            self._phase1_status.setText("Add a comment and click OK to upload")
            self._comment_frame.setVisible(True)
            self._stack.setCurrentIndex(0)
        else:
            # No upload - skip directly to results
            self._result_status.setText("Benchmark saved locally")
            self._result_status.setStyleSheet(
                f"color: {SUCCESS}; font-size: 14px; font-weight: 600; "
                "background: transparent;"
            )
            self._show_results()

    def _get_auto_upload_setting(self) -> bool:
        """Check if auto-upload is enabled in settings."""
        try:
            from linux_game_benchmark.config.preferences import preferences
            return preferences.upload == "y"
        except Exception:
            pass
        return True  # Default to yes

    # --- Phase 1: OK button handler ---

    def _on_ok_clicked(self):
        if self._auto_upload:
            self._do_upload()
        else:
            self._show_results()

    def _do_upload(self):
        self._ok_btn.setEnabled(False)
        self._ok_btn.setText("Uploading...")
        self._phase1_status.setText("Uploading benchmark...")

        from linux_game_benchmark.config.preferences import Preferences
        from linux_game_benchmark.utils.formatting import (
            short_gpu, short_cpu, short_os, short_kernel, normalize_resolution,
        )

        # Flatten metrics
        fps = self._metrics.get("fps", {})
        stutter = self._metrics.get("stutter", {})
        frame_pacing = self._metrics.get("frame_pacing", {})
        frametimes = self._metrics.get("_frametimes", [])

        flat_metrics = {
            "fps_avg": fps.get("average", 0),
            "fps_min": fps.get("minimum", 0),
            "fps_1low": fps.get("1_percent_low", 0),
            "fps_01low": fps.get("0.1_percent_low", 0),
            "stutter_rating": stutter.get("stutter_rating"),
            "consistency_rating": frame_pacing.get("consistency_rating"),
            "duration_seconds": fps.get("duration_seconds", 0),
            "frame_count": fps.get("frame_count", 0),
        }

        # Flatten system_info
        si = self._system_info
        flat_system = {
            "gpu": short_gpu(si.get("gpu", {}).get("model", "Unknown")),
            "cpu": short_cpu(si.get("cpu", {}).get("model", "Unknown")),
            "os": short_os(si.get("os", {}).get("name", "Linux")),
            "kernel": short_kernel(si.get("os", {}).get("kernel", "")),
            "gpu_driver": si.get("gpu", {}).get("driver_version"),
            "vulkan": si.get("gpu", {}).get("vulkan_version"),
            "ram_gb": int(si.get("ram", {}).get("total_gb", 0)),
            "scheduler": si.get("scheduler"),
            "gpu_device_id": si.get("gpu", {}).get("device_id"),
            "gpu_lspci_raw": si.get("gpu", {}).get("lspci_raw"),
        }

        # Compress MangoHud log
        mangohud_log_compressed = None
        try:
            import gzip
            import base64
            from pathlib import Path
            log_file = Path(self._log_path)
            if log_file.exists():
                raw = log_file.read_bytes()
                mangohud_log_compressed = base64.b64encode(
                    gzip.compress(raw)
                ).decode("ascii")
        except Exception:
            pass

        # Map GUI setting keys to server/CLI keys
        raw_settings = self._game.get("_settings", {})
        SETTING_KEY_MAP = {
            "preset": "game_preset",
            "raytracing": "ray_tracing",
            "upscaling": "upscaling",
            "upscaling_quality": "upscaling_quality",
            "framegen": "frame_generation",
            "aa": "anti_aliasing",
            "hdr": "hdr",
            "vsync": "vsync",
            "framelimit": "frame_limit",
            "cpu_oc": "cpu_overclock",
            "gpu_oc": "gpu_overclock",
            "cpu_oc_info": "cpu_overclock_info",
            "gpu_oc_info": "gpu_overclock_info",
        }
        game_settings = {}
        for gui_key, server_key in SETTING_KEY_MAP.items():
            val = raw_settings.get(gui_key)
            if val is not None:
                game_settings[server_key] = val

        upload_kwargs = {
            "steam_app_id": self._game.get("app_id", 0),
            "game_name": self._game.get("name", "Unknown"),
            "resolution": normalize_resolution(
                Preferences.RESOLUTION_NAMES.get(
                    self._game.get("_resolution_key", "2"), "FHD"
                ).split("(")[0].strip()
            ),
            "system_info": flat_system,
            "metrics": flat_metrics,
            "frametimes": frametimes if frametimes else None,
            "mangohud_log_compressed": mangohud_log_compressed,
            "comment": self._comment.text().strip() or None,
            "game_settings": game_settings if game_settings else None,
        }

        self._upload_worker = UploadWorker(upload_kwargs, parent=self)
        self._upload_worker.finished.connect(self._on_upload_done)
        self._upload_worker.start()

    def _on_upload_done(self, success: bool, error_or_empty: str, url: str):
        if success:
            self._result_status.setText("Uploaded!")
            self._result_status.setStyleSheet(
                f"color: {SUCCESS}; font-size: 14px; font-weight: 600; "
                "background: transparent;"
            )
            if url:
                self._url_label.setText(url)
                self._url_label.setVisible(True)
                self._result_url = url
        else:
            self._result_status.setText(f"Upload failed: {error_or_empty}")
            self._result_status.setStyleSheet(
                f"color: {ERROR}; font-size: 14px; font-weight: 600; "
                "background: transparent;"
            )

        self._show_results()

    # --- Phase 2: Show results ---

    def _show_results(self):
        self._fps_display.set_metrics(self._metrics)

        fps = self._metrics.get("fps", {})
        duration = fps.get("duration_seconds", 0)
        frames = fps.get("frame_count", 0)
        mins = int(duration) // 60
        secs = int(duration) % 60
        self._info_label.setText(
            f"Duration: {mins:02d}:{secs:02d}  |  Frames: {frames:,}"
        )

        self._stack.setCurrentIndex(1)

    def _open_url(self, event):
        url = getattr(self, "_result_url", "")
        if url:
            webbrowser.open(url)
