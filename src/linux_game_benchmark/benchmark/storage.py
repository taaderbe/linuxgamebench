"""
Benchmark Storage Manager.

Handles storing and aggregating benchmark results per game,
with support for multiple resolutions, runs, and MULTIPLE SYSTEMS.

Uses Steam App ID as canonical identifier for games.
Folder structure: steam_{app_id}/

IMPORTANT: Data is NEVER archived or deleted. All benchmark data from
all systems is kept and can be viewed/compared in the reports.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
import shutil


@dataclass
class SystemFingerprint:
    """Unique identifier for system configuration."""
    gpu_model: str
    cpu_model: str
    mesa_version: str
    vulkan_version: str
    kernel_version: str
    ram_gb: int
    os_name: str = "Linux"

    def to_dict(self) -> dict:
        return {
            "gpu_model": self.gpu_model,
            "cpu_model": self.cpu_model,
            "mesa_version": self.mesa_version,
            "vulkan_version": self.vulkan_version,
            "kernel_version": self.kernel_version,
            "ram_gb": self.ram_gb,
            "os_name": self.os_name,
        }

    def hash(self) -> str:
        """Generate a hash of the system configuration (excludes OS name for stability)."""
        # Hash based on hardware, not OS name (so same HW = same hash)
        data = json.dumps({
            "gpu_model": self.gpu_model,
            "cpu_model": self.cpu_model,
            "mesa_version": self.mesa_version,
            "ram_gb": self.ram_gb,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def get_system_id(self) -> str:
        """Get a readable system identifier like 'CachyOS_c21b11a6'."""
        os_clean = self.os_name.replace(" ", "").replace("/", "-")[:20]
        return f"{os_clean}_{self.hash()}"

    @classmethod
    def from_system_info(cls, system_info: dict) -> "SystemFingerprint":
        """Create fingerprint from system info dictionary."""
        gpu = system_info.get("gpu", {})
        cpu = system_info.get("cpu", {})
        os_info = system_info.get("os", {})
        ram = system_info.get("ram", {})

        return cls(
            gpu_model=gpu.get("model", "Unknown"),
            cpu_model=cpu.get("model", "Unknown"),
            mesa_version=gpu.get("driver_version", "Unknown"),
            vulkan_version=gpu.get("vulkan_version", "Unknown"),
            kernel_version=os_info.get("kernel", "Unknown"),
            ram_gb=int(ram.get("total_gb", 0)),
            os_name=os_info.get("name", "Linux"),
        )


RESOLUTION_MAP = {
    "1920x1080": "FHD",
    "2560x1440": "WQHD",
    "3840x2160": "UHD",
}

RESOLUTION_DISPLAY = {
    "FHD": "1920×1080",
    "WQHD": "2560×1440",
    "UHD": "3840×2160",
}


class BenchmarkStorage:
    """
    Manages benchmark storage with per-game, per-system, per-resolution organization.

    Uses Steam App ID as canonical identifier. No duplicates from typos possible.

    IMPORTANT: Data is NEVER archived or deleted. All systems are kept.

    Structure:
        ~/benchmark_results/
            games.json                  - Game registry
            steam_1091500/              - Cyberpunk 2077
                game_info.json
                EndeavourOS_54f880f1/   - System 1
                    fingerprint.json
                    system_info.json
                    FHD/
                    WQHD/
                    UHD/
                CachyOS_c21b11a6/       - System 2
                    fingerprint.json
                    system_info.json
                    UHD/
                report.html             - Combined report for ALL systems
            steam_1086940/              - Baldur's Gate 3
                ...
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.home() / "benchmark_results"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._current_system_id: Optional[str] = None

    def get_game_dir(self, game_id: Union[int, str]) -> Path:
        """
        Get or create directory for a game.

        Args:
            game_id: Steam App ID (int) or canonical ID string (e.g., "steam_1091500")
                     Legacy: Also accepts game names for backwards compatibility

        Returns:
            Path to game directory
        """
        # Handle Steam App ID (int)
        if isinstance(game_id, int):
            folder_name = f"steam_{game_id}"
        # Handle canonical ID string (steam_XXXXX)
        elif isinstance(game_id, str) and game_id.startswith("steam_"):
            folder_name = game_id
        else:
            # Legacy: sanitize game name for backwards compatibility
            safe_name = "".join(c for c in game_id if c.isalnum() or c in " _-").strip()
            safe_name = safe_name.replace(" ", "_")
            folder_name = safe_name

        game_dir = self.base_dir / folder_name
        game_dir.mkdir(parents=True, exist_ok=True)
        return game_dir

    def get_system_dir(self, game_id: Union[int, str], system_id: str) -> Path:
        """Get or create directory for a specific system within a game."""
        game_dir = self.get_game_dir(game_id)
        system_dir = game_dir / system_id
        system_dir.mkdir(parents=True, exist_ok=True)
        return system_dir

    def get_all_games(self) -> list[str]:
        """
        Get list of all games that have benchmark data.

        Returns:
            List of game names (readable format for legacy, steam_XXXXX for new format)
        """
        games = []
        if not self.base_dir.exists():
            return games

        for item in self.base_dir.iterdir():
            # Skip recording_session, games.json and other non-game directories
            if not item.is_dir() or item.name in ["recording_session"]:
                continue

            # Check if it has actual benchmark data (in any system subfolder)
            has_data = False
            for subdir in item.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("archive"):
                    # Check for resolution folders or direct resolution folders (legacy)
                    for res in ["FHD", "WQHD", "UHD"]:
                        if (subdir / res).exists() and any((subdir / res).glob("*.json")):
                            has_data = True
                            break
                        # Also check legacy structure
                        if subdir.name == res and any(subdir.glob("*.json")):
                            has_data = True
                            break
                if has_data:
                    break

            if has_data:
                # For steam_XXXXX folders, keep as-is
                # For legacy folders, convert underscores back to spaces
                if item.name.startswith("steam_"):
                    games.append(item.name)
                else:
                    # Legacy: convert folder name back to readable name
                    games.append(item.name.replace("_", " "))

        return sorted(games)

    def get_all_systems(self, game_id: Union[int, str]) -> list[str]:
        """Get list of all system IDs that have data for a game."""
        game_dir = self.get_game_dir(game_id)
        systems = []

        for item in game_dir.iterdir():
            if item.is_dir() and not item.name.startswith("archive"):
                # Check if it's a system folder (has fingerprint.json or resolution folders)
                if (item / "fingerprint.json").exists():
                    systems.append(item.name)
                # Also check for legacy structure (resolution folders directly in game dir)
                elif item.name in ["FHD", "WQHD", "UHD"]:
                    # This is legacy structure, skip for system detection
                    pass

        return sorted(systems)

    def check_fingerprint(self, game_id: Union[int, str], current_fp: SystemFingerprint) -> bool:
        """
        Check if current system already has data for this game.

        Returns True if system already exists (no migration needed).
        With multi-system support, this always returns True (no archiving).
        """
        # With multi-system support, we never need to archive
        # Each system gets its own folder
        return True

    def archive_old_data(self, game_id: Union[int, str]) -> Optional[Path]:
        """
        DEPRECATED: No longer archives data. All systems are kept.

        This method now does nothing and returns None.
        Data from all systems is preserved.
        """
        # NO ARCHIVING - all data is kept
        return None

    def save_fingerprint(self, game_id: Union[int, str], fp: SystemFingerprint, system_info: dict) -> None:
        """Save system fingerprint and full system info."""
        system_id = fp.get_system_id()
        self._current_system_id = system_id
        system_dir = self.get_system_dir(game_id, system_id)

        # Save fingerprint
        fp_data = fp.to_dict()
        fp_data["hash"] = fp.hash()
        fp_data["system_id"] = system_id
        fp_data["saved_at"] = datetime.now().isoformat()
        (system_dir / "fingerprint.json").write_text(json.dumps(fp_data, indent=2))

        # Save full system info
        (system_dir / "system_info.json").write_text(json.dumps(system_info, indent=2))

    def save_run(
        self,
        game_id: Union[int, str],
        resolution: str,
        metrics: dict,
        log_path: Optional[Path] = None,
        frametimes: Optional[list[float]] = None,
        system_id: Optional[str] = None,
    ) -> Path:
        """
        Save a benchmark run.

        Args:
            game_id: Steam App ID (int) or canonical ID string (e.g., "steam_1091500")
            resolution: Resolution string (e.g., "1920x1080")
            metrics: Metrics dictionary from analyzer
            log_path: Optional path to original CSV log
            frametimes: Optional list of frametime values for charting
            system_id: Optional system ID (uses current if not specified)

        Returns:
            Path to saved run file
        """
        # Use provided system_id or the current one
        sid = system_id or self._current_system_id
        if not sid:
            raise ValueError("No system_id provided and no current system set. Call save_fingerprint first.")

        system_dir = self.get_system_dir(game_id, sid)

        # Get resolution folder name
        res_folder = RESOLUTION_MAP.get(resolution, "OTHER")
        res_dir = system_dir / res_folder
        res_dir.mkdir(exist_ok=True)

        # Find next run number
        existing = list(res_dir.glob("run_*.json"))
        run_num = len(existing) + 1

        # Sample frametimes for charting (every 10th frame to keep size manageable)
        sampled_frametimes = None
        if frametimes:
            sampled_frametimes = frametimes[::10]  # Every 10th frame

        # Save run data
        run_data = {
            "run_number": run_num,
            "resolution": resolution,
            "system_id": sid,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "log_file": str(log_path) if log_path else None,
            "frametimes": sampled_frametimes,
        }

        run_file = res_dir / f"run_{run_num:03d}.json"
        run_file.write_text(json.dumps(run_data, indent=2))

        # Copy log file if provided
        if log_path and log_path.exists():
            shutil.copy2(log_path, res_dir / f"run_{run_num:03d}.csv")

        # Auto-regenerate reports
        self.regenerate_game_report(game_id)
        self.regenerate_overview_report()

        return run_file

    def get_runs(self, game_id: Union[int, str], resolution: str, system_id: Optional[str] = None) -> list[dict]:
        """Get all runs for a game at a specific resolution, optionally for a specific system."""
        game_dir = self.get_game_dir(game_id)
        res_folder = RESOLUTION_MAP.get(resolution, "OTHER")

        runs = []

        if system_id:
            # Get runs for specific system
            res_dir = game_dir / system_id / res_folder
            if res_dir.exists():
                for run_file in sorted(res_dir.glob("run_*.json")):
                    run_data = json.loads(run_file.read_text())
                    run_data["system_id"] = system_id
                    runs.append(run_data)
        else:
            # Get runs for all systems
            for system_dir in game_dir.iterdir():
                if system_dir.is_dir() and not system_dir.name.startswith("archive"):
                    res_dir = system_dir / res_folder
                    if res_dir.exists():
                        for run_file in sorted(res_dir.glob("run_*.json")):
                            run_data = json.loads(run_file.read_text())
                            run_data["system_id"] = system_dir.name
                            runs.append(run_data)

            # Also check legacy structure (resolution folders directly in game dir)
            legacy_res_dir = game_dir / res_folder
            if legacy_res_dir.exists() and legacy_res_dir.is_dir():
                for run_file in sorted(legacy_res_dir.glob("run_*.json")):
                    run_data = json.loads(run_file.read_text())
                    run_data["system_id"] = run_data.get("system_id", "legacy")
                    runs.append(run_data)

        return runs

    def get_all_resolutions(self, game_id: Union[int, str], system_id: Optional[str] = None) -> dict[str, list[dict]]:
        """Get all runs for all resolutions, optionally for a specific system."""
        result = {}
        for resolution, folder in RESOLUTION_MAP.items():
            runs = self.get_runs(game_id, resolution, system_id)
            if runs:
                result[resolution] = runs
        return result

    def get_all_systems_data(self, game_id: Union[int, str]) -> dict[str, dict]:
        """
        Get all data organized by system.

        Returns:
            Dict mapping system_id -> {
                "system_info": {...},
                "fingerprint": {...},
                "resolutions": {resolution -> [runs]}
            }
        """
        game_dir = self.get_game_dir(game_id)
        result = {}

        for system_dir in game_dir.iterdir():
            if system_dir.is_dir() and not system_dir.name.startswith("archive"):
                system_id = system_dir.name

                # Skip if it's a resolution folder (legacy structure)
                if system_id in ["FHD", "WQHD", "UHD"]:
                    continue

                # Load system info
                system_info = None
                info_file = system_dir / "system_info.json"
                if info_file.exists():
                    system_info = json.loads(info_file.read_text())

                # Load fingerprint
                fingerprint = None
                fp_file = system_dir / "fingerprint.json"
                if fp_file.exists():
                    fingerprint = json.loads(fp_file.read_text())

                # Get resolutions
                resolutions = self.get_all_resolutions(game_id, system_id)

                if resolutions:  # Only include if there's actual data
                    result[system_id] = {
                        "system_info": system_info,
                        "fingerprint": fingerprint,
                        "resolutions": resolutions,
                    }

        # Also check for legacy structure
        legacy_resolutions = {}
        for resolution, folder in RESOLUTION_MAP.items():
            legacy_res_dir = game_dir / folder
            if legacy_res_dir.exists() and legacy_res_dir.is_dir():
                runs = []
                for run_file in sorted(legacy_res_dir.glob("run_*.json")):
                    run_data = json.loads(run_file.read_text())
                    run_data["system_id"] = "legacy"
                    runs.append(run_data)
                if runs:
                    legacy_resolutions[resolution] = runs

        if legacy_resolutions:
            # Try to load legacy system info
            legacy_info = None
            legacy_info_file = game_dir / "system_info.json"
            if legacy_info_file.exists():
                legacy_info = json.loads(legacy_info_file.read_text())

            legacy_fp = None
            legacy_fp_file = game_dir / "fingerprint.json"
            if legacy_fp_file.exists():
                legacy_fp = json.loads(legacy_fp_file.read_text())

            result["legacy"] = {
                "system_info": legacy_info,
                "fingerprint": legacy_fp,
                "resolutions": legacy_resolutions,
            }

        return result

    def aggregate_runs(self, runs: list[dict]) -> dict:
        """
        Aggregate multiple runs into averaged metrics.

        Args:
            runs: List of run dictionaries

        Returns:
            Aggregated metrics dictionary
        """
        if not runs:
            return {}

        if len(runs) == 1:
            return runs[0].get("metrics", {})

        # Collect FPS values across runs
        fps_keys = ["average", "minimum", "maximum", "median", "1_percent_low", "0.1_percent_low"]
        fps_sums = {key: 0.0 for key in fps_keys}
        total_frames = 0
        total_duration = 0.0

        for run in runs:
            fps = run.get("metrics", {}).get("fps", {})
            for key in fps_keys:
                fps_sums[key] += fps.get(key, 0)
            total_frames += fps.get("frame_count", 0)
            total_duration += fps.get("duration_seconds", 0)

        n = len(runs)
        aggregated_fps = {key: round(fps_sums[key] / n, 2) for key in fps_keys}
        aggregated_fps["frame_count"] = total_frames
        aggregated_fps["duration_seconds"] = round(total_duration, 2)
        aggregated_fps["run_count"] = n

        # Use last run's stutter, frame_pacing and hardware data (or could aggregate these too)
        last_metrics = runs[-1].get("metrics", {})

        return {
            "fps": aggregated_fps,
            "stutter": last_metrics.get("stutter", {}),
            "frame_pacing": last_metrics.get("frame_pacing", {}),
            "hardware": last_metrics.get("hardware", {}),
            "summary": last_metrics.get("summary", {}),
        }

    def get_system_info(self, game_id: Union[int, str], system_id: Optional[str] = None) -> Optional[dict]:
        """Get stored system info for a game, optionally for a specific system."""
        game_dir = self.get_game_dir(game_id)

        if system_id:
            info_file = game_dir / system_id / "system_info.json"
        else:
            # Try current system or legacy
            if self._current_system_id:
                info_file = game_dir / self._current_system_id / "system_info.json"
            else:
                info_file = game_dir / "system_info.json"  # Legacy

        if info_file.exists():
            return json.loads(info_file.read_text())
        return None

    def get_report_path(self, game_id: Union[int, str]) -> Path:
        """Get path for the HTML report."""
        return self.get_game_dir(game_id) / "report.html"

    def regenerate_game_report(self, game_id: Union[int, str]) -> Optional[Path]:
        """
        Regenerate the HTML report for a specific game.

        Returns:
            Path to generated report, or None if failed
        """
        try:
            from linux_game_benchmark.analysis.report_generator import generate_multi_system_report

            systems_data = self.get_all_systems_data(game_id)
            if not systems_data:
                return None

            display_name = self.get_game_display_name(game_id)

            # Extract app_id if it's a steam game
            app_id = None
            if isinstance(game_id, int):
                app_id = game_id
            elif isinstance(game_id, str) and game_id.startswith("steam_"):
                try:
                    app_id = int(game_id.replace("steam_", ""))
                except ValueError:
                    pass

            output_path = self.get_report_path(game_id)
            generate_multi_system_report(display_name, app_id, systems_data, output_path)
            return output_path
        except Exception:
            # Silently fail - report generation is not critical
            return None

    def get_game_display_name(self, game_id: Union[int, str]) -> str:
        """
        Get the display name for a game.

        Reads from game_info.json if available, otherwise returns the folder name.

        Args:
            game_id: Steam App ID (int) or folder name (str)

        Returns:
            Display name string
        """
        game_dir = self.get_game_dir(game_id)
        info_file = game_dir / "game_info.json"

        if info_file.exists():
            try:
                data = json.loads(info_file.read_text())
                return data.get("display_name", game_dir.name)
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: convert folder name to readable format
        folder_name = game_dir.name
        if folder_name.startswith("steam_"):
            return f"Steam App {folder_name.replace('steam_', '')}"
        return folder_name.replace("_", " ")

    def regenerate_overview_report(self) -> Optional[Path]:
        """
        Regenerate the overview report with all games.

        Returns:
            Path to generated report, or None if failed
        """
        try:
            # Import here to avoid circular imports
            from linux_game_benchmark.analysis.report_generator import generate_overview_report

            all_games = self.get_all_games()
            if not all_games:
                return None

            all_games_data = {}
            for game_name in all_games:
                systems_data = self.get_all_systems_data(game_name)
                if systems_data:
                    all_games_data[game_name] = systems_data

            if not all_games_data:
                return None

            output_path = self.base_dir / "index.html"
            generate_overview_report(all_games_data, output_path)
            return output_path
        except Exception:
            # Silently fail - report generation is not critical
            return None
