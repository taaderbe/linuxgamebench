"""
Game Launcher.

Handles launching Steam games with MangoHud for benchmarking.
"""

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil


class GameLauncher:
    """Launches and manages Steam games for benchmarking."""

    # Common game process names that indicate the game is running
    GAME_PROCESS_INDICATORS = [
        "wine",
        "wine64",
        "wineserver",
        "proton",
        ".exe",  # Windows executables via Proton
    ]

    # Known native Linux game executables
    NATIVE_GAME_INDICATORS = [
        "tombraider",
        "riseofthetombraider",
        "shadowofthetombraider",
        "metroexodus",
        "metro2033",
        "metrolastlight",
        "dota2",
        "cs2",
        "csgo",
        "portal2",
        "hl2",
        "tf2",
        "left4dead",
        "borderlands",
        "bioshock",
        "xcom",
        "civilization",
        "totalwar",
        "7daystodie",
        "7d2d",
        "feral",  # Feral Interactive ports
        "aspyr",  # Aspyr ports
    ]

    def __init__(
        self,
        steam_path: Optional[Path] = None,
        use_gamescope: bool = False,
        gamescope_args: Optional[list[str]] = None,
    ):
        """
        Initialize game launcher.

        Args:
            steam_path: Path to Steam installation.
            use_gamescope: Whether to wrap with Gamescope.
            gamescope_args: Additional Gamescope arguments.
        """
        self.steam_path = steam_path or self._find_steam()
        self.use_gamescope = use_gamescope
        self.gamescope_args = gamescope_args or []
        self._game_process: Optional[subprocess.Popen] = None
        self._game_pids: list[int] = []

    def _find_steam(self) -> Path:
        """Find Steam executable."""
        # Check common locations
        candidates = [
            Path("/usr/bin/steam"),
            Path("/usr/games/steam"),
            Path.home() / ".local" / "share" / "Steam" / "steam.sh",
        ]

        for path in candidates:
            if path.exists():
                return path

        # Fall back to PATH lookup
        import shutil
        steam_path = shutil.which("steam")
        if steam_path:
            return Path(steam_path)

        raise FileNotFoundError("Steam executable not found")

    def build_launch_command(
        self,
        app_id: int,
        launch_args: Optional[list[str]] = None,
        proton_version: Optional[str] = None,
        mangohud_config: Optional[Path] = None,
    ) -> list[str]:
        """
        Build command to launch a Steam game.

        Args:
            app_id: Steam App ID.
            launch_args: Additional launch arguments (e.g., -benchmark).
            proton_version: Specific Proton version to use.

        Returns:
            Command list to execute.
        """
        cmd = []

        # Gamescope wrapper (if enabled)
        if self.use_gamescope:
            cmd.extend(["gamescope"])
            cmd.extend(self.gamescope_args)
            cmd.append("--")

        # MangoHud wrapper - needed because Steam doesn't pass env vars to games
        if mangohud_config:
            cmd.extend(["mangohud", "--config", str(mangohud_config)])

        # Steam launch command using steam:// URL for better argument handling
        # Format: steam://run/<appid>//<args>/
        if launch_args:
            args_str = "%20".join(launch_args)  # URL encode spaces
            steam_url = f"steam://run/{app_id}//{args_str}/"
        else:
            steam_url = f"steam://run/{app_id}"

        cmd.extend([str(self.steam_path), steam_url])

        return cmd

    def build_environment(
        self,
        mangohud_env: Optional[dict[str, str]] = None,
        proton_version: Optional[str] = None,
        extra_env: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """
        Build environment variables for game launch.

        Args:
            mangohud_env: MangoHud environment variables.
            proton_version: Proton version to force.
            extra_env: Additional environment variables.

        Returns:
            Complete environment dictionary.
        """
        env = os.environ.copy()

        # MangoHud environment
        if mangohud_env:
            env.update(mangohud_env)

        # Proton/Wine optimizations
        env.setdefault("DXVK_LOG_LEVEL", "none")  # Reduce DXVK spam
        env.setdefault("VKD3D_LOG_LEVEL", "none")  # Reduce VKD3D spam

        # Force specific Proton version (if specified)
        if proton_version:
            env["STEAM_COMPAT_DATA_PATH"] = proton_version

        # Additional environment
        if extra_env:
            env.update(extra_env)

        return env

    def launch(
        self,
        app_id: int,
        launch_args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        wait_for_ready: bool = True,
        ready_timeout: float = 60.0,
        verbose: bool = False,
    ) -> bool:
        """
        Launch a Steam game.

        Args:
            app_id: Steam App ID.
            launch_args: Additional launch arguments.
            env: Environment variables.
            wait_for_ready: Whether to wait for game to start.
            ready_timeout: Timeout in seconds for game to be ready.

        Returns:
            True if game launched successfully.
        """
        cmd = self.build_launch_command(app_id, launch_args)
        full_env = env or os.environ.copy()

        try:
            # Record PIDs before launch
            pids_before = self._get_game_pids()

            # Launch via Steam
            self._game_process = subprocess.Popen(
                cmd,
                env=full_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            if not wait_for_ready:
                return True

            # Wait for game to start
            start_time = time.time()
            last_fallback_check = 0
            last_report = 0

            while time.time() - start_time < ready_timeout:
                time.sleep(1.0)
                elapsed = time.time() - start_time

                # Progress report every 5 seconds if verbose
                if verbose and elapsed - last_report > 5.0:
                    last_report = elapsed
                    print(f"[{int(elapsed)}s] Waiting for game process...")

                # Check for new game processes (known indicators)
                current_pids = self._get_game_pids()
                new_pids = current_pids - pids_before

                if new_pids:
                    # Verify these aren't just launcher scripts - wait a bit and check if still running
                    if verbose:
                        print(f"[{int(elapsed)}s] Found potential game PIDs: {new_pids}, verifying...")

                    time.sleep(3.0)  # Wait for launcher to exit

                    # Re-check which are still running
                    still_running = set()
                    for pid in new_pids:
                        try:
                            proc = psutil.Process(pid)
                            if proc.is_running():
                                still_running.add(pid)
                        except:
                            pass

                    if still_running:
                        if verbose:
                            print(f"[{int(elapsed)}s] Verified game PIDs: {still_running}")
                        self._game_pids = list(still_running)
                        time.sleep(1.0)
                        return True
                    else:
                        # Launcher exited, look for child processes it may have spawned
                        if verbose:
                            print(f"[{int(elapsed)}s] PIDs were just launchers (exited), searching for child processes...")

                        # Check for new processes that appeared while launcher was running
                        current_all = self._get_game_pids()
                        new_after_launcher = current_all - pids_before - new_pids
                        if new_after_launcher:
                            if verbose:
                                print(f"[{int(elapsed)}s] Found child processes: {new_after_launcher}")
                            self._game_pids = list(new_after_launcher)
                            time.sleep(1.0)
                            return True

                # Fallback: After 5 seconds, check for ANY new non-Steam processes
                # This catches games not in our indicator lists
                if elapsed > 5.0 and elapsed - last_fallback_check > 2.0:
                    last_fallback_check = elapsed
                    fallback_pids = self._find_new_processes_fallback(pids_before)
                    if fallback_pids:
                        if verbose:
                            print(f"[{int(elapsed)}s] Fallback found PIDs: {fallback_pids}")
                        self._game_pids = list(fallback_pids)
                        time.sleep(2.0)
                        return True

            return False

        except Exception:
            return False

    def _find_new_processes_fallback(self, pids_before: set[int]) -> set[int]:
        """
        Fallback: Find new processes that look like games but aren't in our indicator lists.

        Args:
            pids_before: PIDs that existed before launch.

        Returns:
            Set of PIDs that are likely the game.
        """
        steam_exclusions = [
            "steam", "steamwebhelper", "steamerrorreporter", "steamservice",
            "fossilize", "reaper", "gldriverquery", "sh", "bash", "python",
            "zenity", "xdg-", "dbus", "systemd", "pulseaudio", "pipewire"
        ]

        candidates = set()

        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                pid = proc.info["pid"]
                name = proc.info.get("name", "").lower()

                # Skip if existed before
                if pid in pids_before:
                    continue

                # Skip Steam and system processes
                skip = False
                for excl in steam_exclusions:
                    if excl in name:
                        skip = True
                        break
                if skip:
                    continue

                # Must be using at least 100MB RAM (games are usually larger)
                mem_info = proc.info.get("memory_info")
                if mem_info and mem_info.rss > 100 * 1024 * 1024:  # 100 MB
                    candidates.add(pid)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return candidates

    def _get_game_pids(self) -> set[int]:
        """Get PIDs of processes that look like games."""
        game_pids = set()

        # Steam processes to exclude from fallback detection
        steam_exclusions = [
            "steam", "steamwebhelper", "steamerrorreporter", "steamservice",
            "fossilize", "reaper", "gldriverquery", "sh", "bash", "python",
            "gameoverlayui", "steamlaunch"  # Also exclude launcher wrapper
        ]

        for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
            try:
                name = proc.info.get("name", "").lower()
                cmdline = " ".join(proc.info.get("cmdline", []) or []).lower()
                exe = (proc.info.get("exe") or "").lower()

                # Skip if this is just a launcher script
                if "steamlaunch" in name or "/launch" in exe:
                    continue

                # Skip Steam-internal processes
                skip = False
                for excl in steam_exclusions:
                    if excl in name:
                        skip = True
                        break
                if skip:
                    continue

                # Check for Proton/Wine game indicators
                for indicator in self.GAME_PROCESS_INDICATORS:
                    if indicator in name or indicator in cmdline:
                        game_pids.add(proc.info["pid"])
                        break

                # Check for native Linux game indicators
                for indicator in self.NATIVE_GAME_INDICATORS:
                    if indicator in name or indicator in cmdline or indicator in exe:
                        game_pids.add(proc.info["pid"])
                        break

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return game_pids

    def is_running(self) -> bool:
        """Check if the game is still running."""
        if not self._game_pids:
            return False

        for pid in self._game_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False

    def wait_for_exit(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the game to exit.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if game exited, False if timeout.
        """
        start_time = time.time()

        while self.is_running():
            if timeout and (time.time() - start_time) > timeout:
                return False
            time.sleep(0.5)

        return True

    def terminate(self, force: bool = False) -> bool:
        """
        Terminate the game.

        Args:
            force: Use SIGKILL instead of SIGTERM.

        Returns:
            True if terminated successfully.
        """
        sig = signal.SIGKILL if force else signal.SIGTERM

        for pid in self._game_pids:
            try:
                proc = psutil.Process(pid)
                proc.send_signal(sig)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Note: We intentionally do NOT terminate self._game_process here
        # because that's the Steam launcher process - terminating it would
        # close the entire Steam client window, not just the game.

        # Wait a moment and verify
        time.sleep(1.0)
        return not self.is_running()

    def get_process_stats(self) -> dict:
        """
        Get current process statistics.

        Returns:
            Dictionary with CPU, memory, and other stats.
        """
        stats = {
            "cpu_percent": 0.0,
            "memory_mb": 0,
            "threads": 0,
            "running": False,
        }

        for pid in self._game_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    stats["running"] = True
                    stats["cpu_percent"] += proc.cpu_percent(interval=0.1)
                    stats["memory_mb"] += proc.memory_info().rss / (1024 * 1024)
                    stats["threads"] += proc.num_threads()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return stats


def find_game_process_by_name(game_name: str) -> Optional[int]:
    """
    Find a game process by name.

    Args:
        game_name: Partial name to match.

    Returns:
        PID if found, None otherwise.
    """
    name_lower = game_name.lower()

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_name = proc.info.get("name", "").lower()
            cmdline = " ".join(proc.info.get("cmdline", []) or []).lower()

            if name_lower in proc_name or name_lower in cmdline:
                return proc.info["pid"]

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None


def get_running_games() -> list[dict]:
    """
    Get list of currently running games.

    Returns:
        List of dictionaries with process info.
    """
    games = []
    seen_pids = set()

    for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info"]):
        try:
            name = proc.info.get("name", "")
            cmdline = " ".join(proc.info.get("cmdline", []) or [])

            # Look for game indicators
            is_game = False
            if ".exe" in name.lower() or ".exe" in cmdline.lower():
                is_game = True
            elif "wine" in name.lower() and "wineserver" not in name.lower():
                is_game = True

            if is_game and proc.info["pid"] not in seen_pids:
                seen_pids.add(proc.info["pid"])
                games.append({
                    "pid": proc.info["pid"],
                    "name": name,
                    "cmdline": cmdline[:100],
                    "cpu_percent": proc.info.get("cpu_percent", 0),
                    "memory_mb": (
                        proc.info.get("memory_info").rss / (1024 * 1024)
                        if proc.info.get("memory_info")
                        else 0
                    ),
                })

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return games
