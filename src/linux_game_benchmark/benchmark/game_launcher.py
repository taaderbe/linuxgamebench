"""
Game Launcher.

Handles launching Steam games with MangoHud for benchmarking.
Simplified version - no PID detection, user controls benchmark manually.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


class GameLauncher:
    """Launches Steam games for benchmarking."""

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

    def _find_steam(self) -> Path:
        """Find Steam executable."""
        candidates = [
            Path("/usr/bin/steam"),
            Path("/usr/games/steam"),
            Path.home() / ".local" / "share" / "Steam" / "steam.sh",
        ]

        for path in candidates:
            if path.exists():
                return path

        import shutil
        steam_path = shutil.which("steam")
        if steam_path:
            return Path(steam_path)

        raise FileNotFoundError("Steam executable not found")

    def build_launch_command(
        self,
        app_id: int,
        launch_args: Optional[list[str]] = None,
        mangohud_config: Optional[Path] = None,
    ) -> list[str]:
        """
        Build command to launch a Steam game.

        Args:
            app_id: Steam App ID.
            launch_args: Additional launch arguments.
            mangohud_config: Path to MangoHud config.

        Returns:
            Command list to execute.
        """
        cmd = []

        if self.use_gamescope:
            cmd.extend(["gamescope"])
            cmd.extend(self.gamescope_args)
            cmd.append("--")

        if mangohud_config:
            cmd.extend(["mangohud", "--config", str(mangohud_config)])

        if launch_args:
            args_str = "%20".join(launch_args)
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

        if mangohud_env:
            env.update(mangohud_env)

        env.setdefault("DXVK_LOG_LEVEL", "none")
        env.setdefault("VKD3D_LOG_LEVEL", "none")

        if proton_version:
            env["STEAM_COMPAT_DATA_PATH"] = proton_version

        if extra_env:
            env.update(extra_env)

        return env

    def launch(
        self,
        app_id: int,
        launch_args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Launch a Steam game.

        Simply starts the game via Steam URL - no PID detection.
        User controls the benchmark manually via Shift+F2.

        Args:
            app_id: Steam App ID.
            launch_args: Additional launch arguments.
            env: Environment variables.

        Returns:
            True if launch command executed successfully.
        """
        cmd = self.build_launch_command(app_id, launch_args)
        full_env = env or os.environ.copy()

        try:
            subprocess.Popen(
                cmd,
                env=full_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False
