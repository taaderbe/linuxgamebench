"""
Steam Library Scanner.

Finds and parses Steam's appmanifest files to get installed games.
"""

import re
from pathlib import Path
from typing import Optional

# Known games with builtin benchmarks
GAMES_WITH_BUILTIN_BENCHMARK = {
    750920: {"name": "Shadow of the Tomb Raider", "args": ["-benchmark"]},
    412020: {"name": "Metro Exodus", "args": ["-benchmark"]},
    287390: {"name": "Metro Last Light Redux", "args": ["-benchmark"]},
    203160: {"name": "Tomb Raider (2013)", "args": ["-benchmark"]},
    391220: {"name": "Rise of the Tomb Raider", "args": ["-benchmark"]},
    1659040: {"name": "Hitman 3", "args": ["-benchmark"]},
    1151640: {"name": "Horizon Zero Dawn", "args": ["-benchmark"]},
    2108330: {"name": "F1 24", "args": ["-benchmark"]},
    1172620: {"name": "Sea of Thieves", "args": ["-benchmark"]},
}

# Steam runtime and tools to exclude from game list
EXCLUDED_APP_IDS = {
    228980,   # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    2180100,  # Steam Linux Runtime 1.0 (scout)
    1493710,  # Proton Experimental
    2805730,  # Proton Hotfix
    961940,   # Proton 3.7
    1054830,  # Proton 4.2
    1113280,  # Proton 4.11
    1245040,  # Proton 5.0
    1420170,  # Proton 5.13
    1580130,  # Proton 6.3
    1887720,  # Proton 7.0
    2348590,  # Proton 8.0
    2180110,  # Proton EasyAntiCheat Runtime
    1826330,  # Proton BattlEye Runtime
}


class SteamLibraryScanner:
    """Scans Steam library for installed games."""

    def __init__(self, steam_path: Optional[Path] = None):
        """
        Initialize scanner.

        Args:
            steam_path: Path to Steam installation. Auto-detected if None.
        """
        self.steam_path = steam_path or self._find_steam_path()
        self._games_cache: list[dict] = []

    def _find_steam_path(self) -> Path:
        """Find Steam installation path (native or Flatpak)."""
        candidates = [
            Path.home() / ".steam" / "steam",
            Path.home() / ".steam" / "root",
            Path.home() / ".local" / "share" / "Steam",
            # Flatpak Steam
            Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",
            Path("/opt/steam"),
        ]

        for path in candidates:
            if path.exists() and (path / "steamapps").exists():
                return path

        raise FileNotFoundError(
            "Steam installation not found. "
            "Please specify path with --steam-path"
        )

    def scan(self) -> list[dict]:
        """
        Scan Steam library and return list of installed games.

        Returns:
            List of game dictionaries with app_id, name, path, etc.
        """
        games_by_id: dict[int, dict] = {}
        steamapps_dirs = self._get_steamapps_dirs()

        for steamapps_dir in steamapps_dirs:
            for manifest_file in steamapps_dir.glob("appmanifest_*.acf"):
                game = self._parse_manifest(manifest_file)
                if game and game["app_id"] not in EXCLUDED_APP_IDS:
                    # Deduplicate by app_id
                    if game["app_id"] not in games_by_id:
                        games_by_id[game["app_id"]] = game

        self._games_cache = list(games_by_id.values())
        return self._games_cache

    def _get_steamapps_dirs(self) -> list[Path]:
        """Get all steamapps directories (including library folders)."""
        dirs = [self.steam_path / "steamapps"]

        # Check for additional library folders
        library_folders = self.steam_path / "steamapps" / "libraryfolders.vdf"
        if library_folders.exists():
            content = library_folders.read_text()
            # Parse VDF format (simplified - looks for "path" entries)
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                lib_path = Path(match.group(1)) / "steamapps"
                if lib_path.exists() and lib_path not in dirs:
                    dirs.append(lib_path)

        return dirs

    def _parse_manifest(self, manifest_path: Path) -> Optional[dict]:
        """Parse an appmanifest_*.acf file."""
        try:
            content = manifest_path.read_text()

            # Extract app_id
            app_id_match = re.search(r'"appid"\s+"(\d+)"', content)
            if not app_id_match:
                return None
            app_id = int(app_id_match.group(1))

            # Extract name
            name_match = re.search(r'"name"\s+"([^"]+)"', content)
            name = name_match.group(1) if name_match else f"Unknown ({app_id})"

            # Extract install dir
            install_match = re.search(r'"installdir"\s+"([^"]+)"', content)
            install_dir = install_match.group(1) if install_match else ""

            # Check if it uses Proton (has compatdata)
            compatdata_path = manifest_path.parent / "compatdata" / str(app_id)
            requires_proton = compatdata_path.exists()

            # Check for builtin benchmark
            has_benchmark = app_id in GAMES_WITH_BUILTIN_BENCHMARK
            benchmark_args = (
                GAMES_WITH_BUILTIN_BENCHMARK[app_id]["args"]
                if has_benchmark
                else []
            )

            return {
                "app_id": app_id,
                "name": name,
                "install_dir": install_dir,
                "manifest_path": str(manifest_path),
                "requires_proton": requires_proton,
                "has_builtin_benchmark": has_benchmark,
                "benchmark_args": benchmark_args,
            }

        except Exception:
            return None

    def get_game_by_id(self, app_id: int) -> Optional[dict]:
        """Get a game by its App ID."""
        if not self._games_cache:
            self.scan()

        for game in self._games_cache:
            if game["app_id"] == app_id:
                return game
        return None

    def get_game_by_name(self, name: str) -> Optional[dict]:
        """Get a game by name (prefers exact match, then partial match)."""
        if not self._games_cache:
            self.scan()

        name_lower = name.lower().strip()

        # First: try exact match (case-insensitive)
        for game in self._games_cache:
            if game["name"].lower() == name_lower:
                return game

        # Second: try partial match, but prefer shorter names (more specific)
        # This prevents "Path of Exile" from matching "Path of Exile 2" first
        matches = []
        for game in self._games_cache:
            if name_lower in game["name"].lower():
                matches.append(game)

        if matches:
            # Sort by name length (shorter = more specific match)
            matches.sort(key=lambda g: len(g["name"]))
            return matches[0]

        return None

    def get_proton_versions(self) -> list[dict]:
        """Get installed Proton versions."""
        protons = []

        # Official Proton in common folder
        common_dir = self.steam_path / "steamapps" / "common"
        if common_dir.exists():
            for folder in common_dir.glob("Proton*"):
                if folder.is_dir():
                    protons.append({
                        "name": folder.name,
                        "path": str(folder),
                        "type": "official",
                    })

        # Custom Proton (GE-Proton, etc.) in compatibilitytools.d
        compat_dir = self.steam_path / "compatibilitytools.d"
        if compat_dir.exists():
            for folder in compat_dir.iterdir():
                if folder.is_dir():
                    protons.append({
                        "name": folder.name,
                        "path": str(folder),
                        "type": "custom",
                    })

        return sorted(protons, key=lambda x: x["name"])
