"""
Unit tests for Steam path detection (incl. Snap + saved --steam-path)
and Proton build detection.

All filesystem state lives in tmp_path; the real ~/.config/lgb is never touched.
"""

import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from linux_game_benchmark.config.settings import Settings
from linux_game_benchmark.steam import library_scanner, proton_detect
from linux_game_benchmark.steam.library_scanner import (
    SteamLibraryScanner, find_steam_path, is_excluded_tool,
)
from linux_game_benchmark.steam.proton_detect import (
    detect_proton, read_prefix_proton, read_tool_version,
)


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect ~/.config/lgb/config.json into tmp_path."""
    config_dir = tmp_path / "config" / "lgb"
    monkeypatch.setattr(Settings, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Settings, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.delenv("LGB_STEAM_PATH", raising=False)
    return config_dir / "config.json"


def make_steam(root: Path, games: dict[int, str] = None) -> Path:
    """Create a minimal Steam dir with appmanifests."""
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    for app_id, name in (games or {}).items():
        (steamapps / f"appmanifest_{app_id}.acf").write_text(
            f'"AppState"\n{{\n\t"appid"\t\t"{app_id}"\n\t"name"\t\t"{name}"\n'
            f'\t"installdir"\t\t"{name}"\n}}\n'
        )
    return root


def make_tool(root: Path, version_line: str) -> Path:
    """Create a Proton tool dir with proton script + version file."""
    (root / "files" / "share" / "fonts").mkdir(parents=True)
    (root / "proton").write_text("#!/usr/bin/env python3\n")
    (root / "version").write_text(version_line + "\n")
    return root


def make_prefix(steam: Path, app_id: int, tool: Path, prefix_version: str) -> Path:
    """Create compatdata/<app_id> the way Proton writes it."""
    compat = steam / "steamapps" / "compatdata" / str(app_id)
    compat.mkdir(parents=True)
    (compat / "config_info").write_text(
        f"{prefix_version}\n{tool}/files/share/fonts/\n{tool}/files/lib/\n"
    )
    (compat / "version").write_text(prefix_version + "\n")
    return compat


class TestSteamPathDetection:
    def test_snap_path_is_auto_detected(self, tmp_path, monkeypatch, isolated_config):
        snap = make_steam(tmp_path / "snap" / "steam" / "common" / ".local" / "share" / "Steam")
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES",
                            [tmp_path / "nothing", snap])
        assert find_steam_path() == snap

    def test_saved_path_wins_over_candidates(self, tmp_path, monkeypatch, isolated_config):
        default = make_steam(tmp_path / "default")
        custom = make_steam(tmp_path / "custom")
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [default])
        Settings().set_steam_path(str(custom))
        assert find_steam_path() == custom

    def test_env_var_wins_over_saved_path(self, tmp_path, monkeypatch, isolated_config):
        saved = make_steam(tmp_path / "saved")
        env = make_steam(tmp_path / "env")
        Settings().set_steam_path(str(saved))
        monkeypatch.setenv("LGB_STEAM_PATH", str(env))
        assert find_steam_path() == env

    def test_invalid_saved_path_falls_back(self, tmp_path, monkeypatch, isolated_config):
        default = make_steam(tmp_path / "default")
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [default])
        Settings().set_steam_path(str(tmp_path / "gone"))
        assert find_steam_path() == default

    def test_nothing_found_gives_helpful_error(self, tmp_path, monkeypatch, isolated_config):
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [tmp_path / "none"])
        with pytest.raises(FileNotFoundError, match="--steam-path"):
            SteamLibraryScanner()


class TestScanCommandPersistsPath:
    def test_scan_saves_path_and_list_games_uses_it(self, tmp_path, monkeypatch, isolated_config):
        from linux_game_benchmark.cli import app

        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [tmp_path / "none"])
        snap = make_steam(tmp_path / "snap_steam", {620: "Portal 2"})
        runner = CliRunner()

        result = runner.invoke(app, ["scan", "--steam-path", str(snap)])
        assert result.exit_code == 0, result.output
        assert "Found 1 installed games" in result.output
        assert Settings().get_steam_path() == str(snap.resolve())

        # The reported bug: list-games crashed without --steam-path
        result = runner.invoke(app, ["list-games"])
        assert result.exit_code == 0, result.output
        assert "Portal 2" in result.output

    def test_scan_rejects_non_steam_dir(self, tmp_path, isolated_config):
        from linux_game_benchmark.cli import app

        result = CliRunner().invoke(app, ["scan", "--steam-path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Not a Steam installation" in result.output
        assert Settings().get_steam_path() is None

    def test_list_games_without_steam_shows_error_not_traceback(self, tmp_path, monkeypatch, isolated_config):
        from linux_game_benchmark.cli import app

        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [tmp_path / "none"])
        result = CliRunner().invoke(app, ["list-games"])
        assert result.exit_code == 1
        assert "--steam-path" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_reset_steam_path(self, tmp_path, monkeypatch, isolated_config):
        from linux_game_benchmark.cli import app

        default = make_steam(tmp_path / "default")
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [default])
        Settings().set_steam_path(str(make_steam(tmp_path / "old")))
        result = CliRunner().invoke(app, ["scan", "--reset-steam-path"])
        assert result.exit_code == 0, result.output
        assert Settings().get_steam_path() is None


class TestToolExclusion:
    @pytest.mark.parametrize("app_id,name", [
        (2180100, "Proton Hotfix"),
        (2805730, "Proton 9.0"),
        (9999991, "Proton 11.0"),              # future App ID, caught by name
        (9999992, "Proton - Experimental"),
        (4183110, "Steam Linux Runtime 4.0"),
        (9999993, "Steam Linux Runtime 5.0"),
        (228980, "Steamworks Common Redistributables"),
    ])
    def test_tools_are_excluded(self, app_id, name):
        assert is_excluded_tool(app_id, name)

    @pytest.mark.parametrize("name", ["Cyberpunk 2077", "Protonaut", "Portal 2"])
    def test_games_are_kept(self, name):
        assert not is_excluded_tool(1234, name)


class TestProtonDetection:
    @pytest.fixture
    def steam(self, tmp_path, monkeypatch, isolated_config):
        steam = make_steam(tmp_path / "Steam")
        monkeypatch.setattr(library_scanner, "STEAM_PATH_CANDIDATES", [steam])
        # No real processes: the test decides what is "in use"
        monkeypatch.setattr(proton_detect, "_prefixes_in_use", lambda: set())
        return steam

    def test_rolling_experimental_build(self, steam):
        tool = make_tool(steam / "steamapps" / "common" / "Proton - Experimental",
                         "1789805668 experimental-11.0-20260917b-x86_64")
        make_prefix(steam, 1091500, tool, "11.0-100")
        info = detect_proton(1091500, since=time.time() - 60)
        assert info == {
            "proton_build": "experimental-11.0-20260917b-x86_64",
            "proton_tool": "Proton - Experimental",
            "proton_build_ts": 1789805668,
        }

    def test_hotfix_and_distro_builds(self, steam, tmp_path):
        hotfix = make_tool(steam / "steamapps" / "common" / "Proton Hotfix",
                           "1787945902 hotfix-20260828-ptr-x86_64")
        make_prefix(steam, 1, hotfix, "11.0-100")
        assert detect_proton(1, since=time.time() - 60)["proton_build"] == "hotfix-20260828-ptr-x86_64"

        cachyos = make_tool(tmp_path / "usr" / "compatibilitytools.d" / "proton-cachyos-native",
                            "1786990484 cachyos-11.0-20260703-native")
        make_prefix(steam, 2, cachyos, "CachyOS-11.0-100")
        info = detect_proton(2, since=time.time() - 60)
        assert info["proton_build"] == "cachyos-11.0-20260703-native"
        assert info["proton_tool"] == "proton-cachyos-native"

    def test_stale_prefix_is_ignored(self, steam):
        """Native run of a game that once used Proton: no stale label."""
        tool = make_tool(steam / "steamapps" / "common" / "Proton 9.0", "1749140930 proton-9.0-4f")
        compat = make_prefix(steam, 42, tool, "9.0-4")
        old = time.time() - 7 * 86400
        os.utime(compat / "version", (old, old))
        assert detect_proton(42, since=time.time() - 60) == {}

    def test_prefix_in_use_counts_even_if_old(self, steam, monkeypatch):
        """Game was already running before the session started."""
        tool = make_tool(steam / "steamapps" / "common" / "Proton 9.0", "1749140930 proton-9.0-4f")
        compat = make_prefix(steam, 43, tool, "9.0-4")
        old = time.time() - 3600
        os.utime(compat / "version", (old, old))
        monkeypatch.setattr(proton_detect, "_prefixes_in_use",
                            lambda: {os.path.realpath(compat)})
        assert detect_proton(43, since=time.time())["proton_build"] == "proton-9.0-4f"

    def test_native_game_without_prefix(self, steam):
        assert detect_proton(570, since=time.time() - 60) == {}

    def test_missing_tool_dir_falls_back_to_prefix_version(self, steam, tmp_path):
        compat = steam / "steamapps" / "compatdata" / "7"
        compat.mkdir(parents=True)
        (compat / "config_info").write_text(f"GE-Proton10-15\n{tmp_path}/removed/files/share/fonts/\n")
        (compat / "version").write_text("GE-Proton10-15\n")
        assert read_prefix_proton(compat) == {
            "proton_build": "GE-Proton10-15", "proton_tool": None, "proton_build_ts": None,
        }

    def test_version_file_without_timestamp(self, tmp_path):
        tool = make_tool(tmp_path / "GE-Proton10-15", "GE-Proton10-15")
        assert read_tool_version(tool) == ("GE-Proton10-15", None)

    def test_never_raises(self, steam, monkeypatch):
        monkeypatch.setattr(proton_detect, "_compatdata_dirs",
                            lambda app_id: (_ for _ in ()).throw(PermissionError()))
        assert detect_proton(1, since=0) == {}
