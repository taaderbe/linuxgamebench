"""QThread workers for all backend operations.

Each worker runs a single backend operation off the main thread and emits
signals with the result. Workers are one-shot: create, connect, start().
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap


class SteamScanWorker(QThread):
    """Scan Steam library for installed games."""
    finished = Signal(list)   # list[dict]
    error = Signal(str)

    def run(self):
        try:
            from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
            scanner = SteamLibraryScanner()
            games = scanner.scan()
            self.finished.emit(games)
        except Exception as e:
            self.error.emit(str(e))


class SystemInfoWorker(QThread):
    """Detect system hardware info."""
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            from linux_game_benchmark.system.hardware_info import get_system_info
            info = get_system_info()
            self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class LoginWorker(QThread):
    """Authenticate user with email/password/2FA."""
    finished = Signal(bool, str)  # (success, message_or_username)

    def __init__(self, email: str, password: str, totp_code: str = "", parent=None):
        super().__init__(parent)
        self._email = email
        self._password = password
        self._totp = totp_code

    def run(self):
        try:
            from linux_game_benchmark.api.auth import TokenManager
            tm = TokenManager()
            success, msg = tm.login(self._email, self._password, self._totp or None)
            self.finished.emit(success, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class LogoutWorker(QThread):
    """Log out current user."""
    finished = Signal(bool, str)

    def run(self):
        try:
            from linux_game_benchmark.api.auth import TokenManager
            tm = TokenManager()
            success, msg = tm.logout()
            self.finished.emit(success, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class AuthVerifyWorker(QThread):
    """Verify stored auth token is still valid."""
    finished = Signal(bool, str)  # (valid, username_or_empty)

    def run(self):
        try:
            from linux_game_benchmark.api.client import verify_auth
            from linux_game_benchmark.api.auth import get_current_session
            valid, _ = verify_auth()
            if valid:
                session = get_current_session()
                username = session.get_username() if session else ""
                self.finished.emit(True, username)
            else:
                self.finished.emit(False, "")
        except Exception:
            self.finished.emit(False, "")


class HealthCheckWorker(QThread):
    """Check if the API server is reachable."""
    finished = Signal(bool)

    def run(self):
        try:
            from linux_game_benchmark.api.client import check_api_status
            self.finished.emit(check_api_status())
        except Exception:
            self.finished.emit(False)


class UpdateCheckWorker(QThread):
    """Check for client updates."""
    finished = Signal(object)  # Optional[str] - new version or None

    def run(self):
        try:
            from linux_game_benchmark.api.client import check_for_updates
            result = check_for_updates()
            self.finished.emit(result)
        except Exception:
            self.finished.emit(None)


# --- Benchmark Workers ---


class MangoHudSetupWorker(QThread):
    """Set MangoHud config for benchmarking and set Steam launch options."""
    finished = Signal(bool, str, str)  # (success, error_msg, log_dir)

    def __init__(self, app_id: int, output_dir: Path, gpu_pci: str = "",
                 log_duration: int = 0, parent=None):
        super().__init__(parent)
        self._app_id = app_id
        self._output_dir = output_dir
        self._gpu_pci = gpu_pci
        self._log_duration = log_duration

    def run(self):
        try:
            from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
            from linux_game_benchmark.steam.launch_options import set_launch_options

            mgr = MangoHudConfigManager()
            mgr.backup_config()

            log_dir = self._output_dir
            log_dir.mkdir(parents=True, exist_ok=True)

            mgr.set_benchmark_config(
                output_folder=log_dir,
                show_hud=True,
                log_interval=0,
                manual_logging=True,
                log_duration=self._log_duration,
                gpu_pci_dev=self._gpu_pci or None,
            )

            set_launch_options(self._app_id, "MANGOHUD=1 %command%")

            self.finished.emit(True, "", str(log_dir))
        except Exception as e:
            self.finished.emit(False, str(e), "")


class MangoHudRestoreWorker(QThread):
    """Restore MangoHud config and Steam launch options after benchmark."""
    finished = Signal()

    def __init__(self, app_id: int, parent=None):
        super().__init__(parent)
        self._app_id = app_id

    def run(self):
        try:
            from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
            from linux_game_benchmark.steam.launch_options import restore_launch_options
            MangoHudConfigManager().restore_config()
            restore_launch_options(self._app_id)
        except Exception:
            pass
        self.finished.emit()


class GameLaunchWorker(QThread):
    """Launch a Steam game."""
    finished = Signal(bool, str)  # (success, error_msg)

    def __init__(self, app_id: int, parent=None):
        super().__init__(parent)
        self._app_id = app_id

    def run(self):
        try:
            from linux_game_benchmark.benchmark.game_launcher import GameLauncher
            launcher = GameLauncher()
            success = launcher.launch(self._app_id)
            if success:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "Failed to launch game")
        except Exception as e:
            self.finished.emit(False, str(e))


class BenchmarkMonitorWorker(QThread):
    """Monitor output directory for MangoHud log files.

    Detects when recording starts (new CSV appears) and stops
    (file size stabilizes).
    """
    recording_started = Signal(str)   # log file path
    recording_done = Signal(str)      # log file path
    error = Signal(str)

    def __init__(self, log_dir: str, parent=None):
        super().__init__(parent)
        self._log_dir = Path(log_dir)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import time

        try:
            initial_logs = set(self._log_dir.glob("*.csv"))
            timeout = 1800  # 30 minutes
            start = time.time()

            # Phase 1: Wait for new CSV file (recording start)
            log_path = None
            while not self._cancelled and (time.time() - start) < timeout:
                current = set(self._log_dir.glob("*.csv"))
                new = current - initial_logs
                if new:
                    log_path = max(new, key=lambda p: p.stat().st_mtime)
                    self.recording_started.emit(str(log_path))
                    break
                time.sleep(0.5)

            if self._cancelled or log_path is None:
                if not self._cancelled:
                    self.error.emit("Timeout waiting for recording to start")
                return

            # Phase 2: Wait for file to stop growing (recording stop)
            last_size = -1
            stable_count = 0
            while not self._cancelled and (time.time() - start) < timeout:
                try:
                    size = log_path.stat().st_size
                except FileNotFoundError:
                    time.sleep(0.3)
                    continue

                if size > 0 and size == last_size:
                    stable_count += 1
                    if stable_count >= 3:  # 3 * 0.5s = 1.5s stable
                        self.recording_done.emit(str(log_path))
                        return
                else:
                    stable_count = 0
                last_size = size
                time.sleep(0.5)

            if not self._cancelled:
                self.error.emit("Timeout waiting for recording to complete")

        except Exception as e:
            self.error.emit(str(e))


class AnalyzeWorker(QThread):
    """Analyze a MangoHud CSV log file."""
    finished = Signal(dict)   # metrics dict from FrametimeAnalyzer.analyze()
    error = Signal(str)

    def __init__(self, log_path: str, parent=None):
        super().__init__(parent)
        self._log_path = Path(log_path)

    def run(self):
        try:
            from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
            analyzer = FrametimeAnalyzer(self._log_path)
            metrics = analyzer.analyze()
            # Attach raw frametimes for upload (server needs them)
            metrics["_frametimes"] = getattr(analyzer, "frametimes", [])
            self.finished.emit(metrics)
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    """Upload benchmark results to server."""
    finished = Signal(bool, str, str)  # (success, error_or_url, benchmark_url)

    def __init__(self, upload_kwargs: dict, parent=None):
        super().__init__(parent)
        self._kwargs = upload_kwargs

    def run(self):
        try:
            from linux_game_benchmark.api.client import BenchmarkAPIClient
            client = BenchmarkAPIClient()
            result = client.upload_benchmark(**self._kwargs, require_auth=False)
            if result.success:
                self.finished.emit(True, "", result.url or "")
            else:
                self.finished.emit(False, result.error or "Upload failed", "")
        except Exception as e:
            self.finished.emit(False, str(e), "")


# --- System Info Workers ---


class FullSystemInfoWorker(QThread):
    """Gather comprehensive system info including all GPUs, governor, scheduler, steam."""
    finished = Signal(dict)   # full info dict
    error = Signal(str)

    def run(self):
        try:
            from linux_game_benchmark.system.hardware_info import (
                get_system_info, detect_all_gpus, get_cpu_governor,
                detect_sched_ext, get_steam_info,
            )

            info = get_system_info()

            # Extra data not in base get_system_info()
            try:
                info["all_gpus"] = detect_all_gpus()
            except Exception:
                info["all_gpus"] = []

            try:
                info["cpu_governor"] = get_cpu_governor()
            except Exception:
                info["cpu_governor"] = None

            try:
                info["scheduler"] = detect_sched_ext()
            except Exception:
                info["scheduler"] = None

            try:
                info["steam_info"] = get_steam_info()
            except Exception:
                info["steam_info"] = {}

            try:
                import shutil
                info["mangohud_installed"] = shutil.which("mangohud") is not None
            except Exception:
                info["mangohud_installed"] = False

            self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))


# --- My Benchmarks Workers ---


class FetchUserBenchmarksWorker(QThread):
    """Fetch user's benchmarks from the server."""
    finished = Signal(dict)   # full response dict
    error = Signal(str)

    def run(self):
        try:
            from linux_game_benchmark.api.client import get_user_benchmarks
            result = get_user_benchmarks(include_details=False)
            if "error" in result and result["error"]:
                self.error.emit(result["error"])
            else:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class LocalBenchmarksWorker(QThread):
    """Scan local benchmark storage for individual runs."""
    finished = Signal(list)   # list of individual run dicts
    error = Signal(str)

    def run(self):
        try:
            from linux_game_benchmark.benchmark.storage import BenchmarkStorage
            storage = BenchmarkStorage()
            games = storage.get_all_games()
            runs_list = []

            for game_id in games:
                display_name = storage.get_game_display_name(game_id)
                systems_data = storage.get_all_systems_data(game_id)
                has_report = storage.get_report_path(game_id).exists()

                for sys_id, sys_data in systems_data.items():
                    for res, runs in sys_data.get("resolutions", {}).items():
                        for run in runs:
                            metrics = run.get("metrics", {})
                            fps = metrics.get("fps", {})
                            runs_list.append({
                                "game_id": game_id,
                                "display_name": display_name,
                                "system_id": sys_id,
                                "resolution": res,
                                "timestamp": run.get("timestamp", ""),
                                "avg_fps": fps.get("average", 0),
                                "fps_1low": fps.get("1_percent_low", 0),
                                "stutter_rating": metrics.get("stutter", {}).get("rating", "--"),
                                "consistency_rating": metrics.get("frame_pacing", {}).get("consistency_rating", "--"),
                                "has_report": has_report,
                                "run_number": run.get("run_number", 0),
                            })

            # Sort by timestamp, newest first
            runs_list.sort(key=lambda r: r["timestamp"], reverse=True)
            self.finished.emit(runs_list)
        except Exception as e:
            self.error.emit(str(e))
