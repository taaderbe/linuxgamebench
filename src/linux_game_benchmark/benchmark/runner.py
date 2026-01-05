"""
Benchmark Runner.

Orchestrates the complete benchmark process:
1. Setup MangoHud logging
2. Launch game
3. Monitor and record
4. Collect results
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

from linux_game_benchmark.mangohud.manager import MangoHudManager, check_mangohud_installation
from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
from linux_game_benchmark.benchmark.game_launcher import GameLauncher
from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer, FPSTargetEvaluator
from linux_game_benchmark.system.hardware_info import get_system_info
from linux_game_benchmark.steam.launch_options import (
    set_launch_options,
    restore_launch_options,
    get_launch_options,
)
from linux_game_benchmark.benchmark.storage import BenchmarkStorage
from linux_game_benchmark.analysis.report_generator import generate_overview_report


class BenchmarkType(Enum):
    """Type of benchmark to run."""
    BUILTIN = "builtin"  # Game has builtin benchmark mode (auto-starts)
    TIMED = "timed"      # Record for fixed duration
    MANUAL = "manual"    # User manually triggers benchmark, we wait for game exit


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""
    app_id: int
    game_name: str
    benchmark_type: BenchmarkType = BenchmarkType.TIMED
    launch_args: list[str] = field(default_factory=list)
    duration_seconds: int = 60
    runs: int = 3
    warmup_runs: int = 1
    cooldown_seconds: int = 10
    proton_version: Optional[str] = None
    use_gamescope: bool = False
    gamescope_args: list[str] = field(default_factory=list)
    show_hud: bool = True
    manual_logging: bool = True  # User presses Shift+F2 to start/stop recording
    extra_env: dict[str, str] = field(default_factory=dict)
    fps_targets: list[int] = field(default_factory=lambda: [60, 120, 144])


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    run_number: int
    is_warmup: bool
    log_path: Optional[Path] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    metrics: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class BenchmarkSession:
    """Complete benchmark session with multiple runs."""
    config: BenchmarkConfig
    system_info: dict = field(default_factory=dict)
    results: list[BenchmarkResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    output_dir: Optional[Path] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class BenchmarkRunner:
    """Runs game benchmarks with MangoHud logging."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory for results. Defaults to ~/benchmark_results.
            on_status: Callback for status messages.
            on_progress: Callback for progress (current, total).
        """
        self.output_dir = output_dir or Path.home() / "benchmark_results"
        self.on_status = on_status or (lambda msg: None)
        self.on_progress = on_progress or (lambda c, t: None)

        self.mangohud = MangoHudManager(output_dir=self.output_dir)
        self.launcher: Optional[GameLauncher] = None
        self._current_session: Optional[BenchmarkSession] = None

    def _log(self, message: str) -> None:
        """Log a status message."""
        self.on_status(message)

    def check_requirements(self) -> dict:
        """
        Check if all requirements are met for benchmarking.

        Returns:
            Dictionary with status of each requirement.
        """
        requirements = {
            "mangohud": check_mangohud_installation(),
            "steam": {"installed": False, "path": None},
            "gamescope": {"installed": False},
        }

        # Check Steam
        try:
            launcher = GameLauncher()
            requirements["steam"]["installed"] = True
            requirements["steam"]["path"] = str(launcher.steam_path)
        except FileNotFoundError:
            pass

        # Check Gamescope
        import shutil
        requirements["gamescope"]["installed"] = shutil.which("gamescope") is not None

        return requirements

    def run(self, config: BenchmarkConfig) -> BenchmarkSession:
        """
        Run a complete benchmark session.

        Args:
            config: Benchmark configuration.

        Returns:
            BenchmarkSession with all results.
        """
        session = BenchmarkSession(
            config=config,
            started_at=datetime.now(),
        )

        # Gather system info
        self._log("Gathering system information...")
        session.system_info = get_system_info()

        # Prepare output directory
        session.output_dir = self.mangohud.prepare_log_directory(
            config.game_name,
            run_id=f"session_{datetime.now().strftime('%H%M%S')}",
        )
        self._log(f"Output directory: {session.output_dir}")

        # Setup MangoHud config - replace default config temporarily
        self._log("Setting up MangoHud logging...")
        mangohud_manager = MangoHudConfigManager()
        mangohud_manager.backup_config()
        mangohud_manager.set_benchmark_config(
            output_folder=session.output_dir,
            show_hud=config.show_hud,
            manual_logging=config.manual_logging,
        )
        if config.manual_logging:
            self._log("MangoHud config set - Press Shift+F2 to START/STOP recording")
        else:
            self._log("MangoHud config set for benchmark logging")
        self._mangohud_manager = mangohud_manager

        # Set Steam launch options (just MANGOHUD=1 %command%)
        self._log("Setting Steam launch options...")
        try:
            set_launch_options(config.app_id, "MANGOHUD=1 %command%")
            self._log("Launch options: MANGOHUD=1 %command%")
        except Exception as e:
            self._log(f"Warning: Could not set launch options: {e}")
            self._log("Please set manually in Steam: MANGOHUD=1 %command%")

        # Initialize launcher
        self.launcher = GameLauncher(
            use_gamescope=config.use_gamescope,
            gamescope_args=config.gamescope_args,
        )

        # Calculate total runs
        total_runs = config.warmup_runs + config.runs
        current_run = 0
        self._current_app_id = config.app_id

        try:
            # Warmup runs
            for i in range(config.warmup_runs):
                current_run += 1
                self.on_progress(current_run, total_runs)
                self._log(f"Warmup run {i + 1}/{config.warmup_runs}")

                result = self._run_single(
                    config,
                    run_number=i + 1,
                    is_warmup=True,
                    output_dir=session.output_dir,
                )
                session.results.append(result)

                # Cooldown between runs
                if i < config.warmup_runs - 1 or config.runs > 0:
                    self._log(f"Cooling down for {config.cooldown_seconds}s...")
                    time.sleep(config.cooldown_seconds)

            # Actual benchmark runs
            for i in range(config.runs):
                current_run += 1
                self.on_progress(current_run, total_runs)
                self._log(f"Benchmark run {i + 1}/{config.runs}")

                result = self._run_single(
                    config,
                    run_number=i + 1,
                    is_warmup=False,
                    output_dir=session.output_dir,
                )
                session.results.append(result)

                # Cooldown between runs
                if i < config.runs - 1:
                    self._log(f"Cooling down for {config.cooldown_seconds}s...")
                    time.sleep(config.cooldown_seconds)

        except Exception as e:
            self._log(f"Error during benchmark: {e}")
            session.results.append(BenchmarkResult(
                run_number=current_run,
                is_warmup=False,
                error=str(e),
            ))

        finally:
            # Restore original MangoHud config
            try:
                self._log("Restoring original MangoHud config...")
                if hasattr(self, '_mangohud_manager'):
                    self._mangohud_manager.restore_config()
            except Exception as e:
                self._log(f"Warning: Could not restore MangoHud config: {e}")

            # Restore original Steam launch options
            try:
                self._log("Restoring original Steam launch options...")
                restore_launch_options(config.app_id)
            except Exception as e:
                self._log(f"Warning: Could not restore launch options: {e}")

        session.finished_at = datetime.now()

        # Generate summary
        session.summary = self._generate_summary(session)

        # Save session data
        self._save_session(session)

        # Regenerate overview report automatically
        try:
            self._log("Regenerating overview report...")
            storage = BenchmarkStorage()
            all_games = storage.get_all_games()

            if all_games:
                all_games_data = {}
                for game_name in all_games:
                    systems_data = storage.get_all_systems_data(game_name)
                    if systems_data:
                        all_games_data[game_name] = systems_data

                if all_games_data:
                    output_path = storage.base_dir / "index.html"
                    generate_overview_report(all_games_data, output_path)
                    self._log(f"Overview report updated: {output_path}")
        except Exception as e:
            self._log(f"Warning: Could not regenerate overview report: {e}")

        return session

    def _wait_for_log_completion(
        self,
        output_dir: Path,
        timeout: float = 1800.0,
    ) -> Optional[Path]:
        """
        Wait for MangoHud log file to appear and complete.

        Args:
            output_dir: Directory where logs are saved.
            timeout: Maximum time to wait in seconds.

        Returns:
            Path to completed log file, or None if timeout.
        """
        start = time.time()
        log_path = None
        initial_logs = set(output_dir.glob("*.csv"))

        self._log("Waiting for benchmark recording to start (Shift+F2)...")

        # Wait for new .csv file to appear
        while time.time() - start < timeout:
            current_logs = set(output_dir.glob("*.csv"))
            new_logs = current_logs - initial_logs

            if new_logs:
                log_path = max(new_logs, key=lambda p: p.stat().st_mtime)
                self._log(f"Recording started: {log_path.name}")
                break
            time.sleep(1)

        if not log_path:
            return None

        # Wait for file to stop growing (user pressed Shift+F2 to stop)
        self._log("Recording in progress... Press Shift+F2 to stop when done.")
        last_size = 0
        stable_count = 0

        while stable_count < 3 and (time.time() - start) < timeout:
            try:
                size = log_path.stat().st_size
                if size == last_size and size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                last_size = size
            except FileNotFoundError:
                pass
            time.sleep(1)

        if stable_count >= 3:
            self._log("Recording complete.")
        return log_path

    def _run_single(
        self,
        config: BenchmarkConfig,
        run_number: int,
        is_warmup: bool,
        output_dir: Path,
    ) -> BenchmarkResult:
        """Run a single benchmark iteration."""
        result = BenchmarkResult(
            run_number=run_number,
            is_warmup=is_warmup,
            start_time=datetime.now(),
        )

        # Launch game - launch options are already set at session level
        self._log(f"Launching {config.game_name}...")

        success = self.launcher.launch(
            app_id=config.app_id,
            launch_args=None,
            env=None,
        )

        if not success:
            result.error = "Failed to launch game"
            result.end_time = datetime.now()
            return result

        self._log("Game launch initiated.")
        self._log("Start the game, then press Shift+F2 to begin recording.")

        # Wait for log file to be created and completed
        log_path = self._wait_for_log_completion(output_dir, timeout=1800.0)

        result.end_time = datetime.now()
        result.duration_seconds = (result.end_time - result.start_time).total_seconds()

        # Validate and analyze log
        if log_path:
            result.log_path = log_path
            validation = self.mangohud.validate_log(log_path)

            if validation["valid"]:
                try:
                    analyzer = FrametimeAnalyzer(log_path)
                    result.metrics = analyzer.analyze()
                    self._log(f"Captured {validation['rows']} frames")
                except Exception as e:
                    result.error = f"Analysis error: {e}"
            else:
                result.error = f"Invalid log: {validation.get('error', 'Unknown')}"
        else:
            result.error = "No log file found - did you press Shift+F2?"

        return result

    def _generate_summary(self, session: BenchmarkSession) -> dict:
        """Generate summary statistics from all runs."""
        # Filter to actual runs (not warmup)
        actual_results = [r for r in session.results if not r.is_warmup and r.metrics]

        if not actual_results:
            return {"error": "No valid results to summarize"}

        # Collect FPS metrics from all runs
        fps_data = {
            "average": [],
            "minimum": [],
            "maximum": [],
            "1_percent_low": [],
            "0.1_percent_low": [],
        }

        stutter_data = {
            "stutter_index": [],
            "gameplay_stutter_index": [],
            "event_count": [],
            "transition_count": [],
            "gameplay_stutter_count": [],
        }

        for result in actual_results:
            fps = result.metrics.get("fps", {})
            for key in fps_data:
                if key in fps:
                    fps_data[key].append(fps[key])

            stutter = result.metrics.get("stutter", {})
            for key in stutter_data:
                if key in stutter:
                    stutter_data[key].append(stutter[key])

        # Calculate averages and consistency
        summary = {
            "runs_completed": len(actual_results),
            "fps": {},
            "stutter": {},
            "consistency": {},
        }

        for key, values in fps_data.items():
            if values:
                avg = sum(values) / len(values)
                summary["fps"][key] = round(avg, 2)

                # Calculate consistency (coefficient of variation)
                if len(values) > 1 and avg > 0:
                    import statistics
                    std = statistics.stdev(values)
                    cv = (std / avg) * 100
                    summary["consistency"][f"{key}_cv"] = round(cv, 2)

        for key, values in stutter_data.items():
            if values:
                summary["stutter"][key] = round(sum(values) / len(values), 2)

        # Get stutter rating from first result (ratings don't average well)
        if actual_results:
            first_stutter = actual_results[0].metrics.get("stutter", {})
            if "stutter_rating" in first_stutter:
                summary["stutter"]["stutter_rating"] = first_stutter["stutter_rating"]

        # FPS target evaluation
        if summary["fps"]:
            evaluator = FPSTargetEvaluator(session.config.fps_targets)
            summary["fps_targets"] = evaluator.evaluate({"fps": summary["fps"]})

        return summary

    def _save_session(self, session: BenchmarkSession) -> Path:
        """Save session data to JSON."""
        if not session.output_dir:
            return None

        # Prepare serializable data
        data = {
            "config": {
                "app_id": session.config.app_id,
                "game_name": session.config.game_name,
                "benchmark_type": session.config.benchmark_type.value,
                "duration_seconds": session.config.duration_seconds,
                "runs": session.config.runs,
                "warmup_runs": session.config.warmup_runs,
                "fps_targets": session.config.fps_targets,
            },
            "system_info": session.system_info,
            "results": [],
            "summary": session.summary,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        }

        for result in session.results:
            data["results"].append({
                "run_number": result.run_number,
                "is_warmup": result.is_warmup,
                "log_path": str(result.log_path) if result.log_path else None,
                "start_time": result.start_time.isoformat() if result.start_time else None,
                "end_time": result.end_time.isoformat() if result.end_time else None,
                "duration_seconds": result.duration_seconds,
                "metrics": result.metrics,
                "error": result.error,
            })

        output_path = session.output_dir / "session.json"
        output_path.write_text(json.dumps(data, indent=2))

        return output_path
