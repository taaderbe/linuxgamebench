"""
Proton build detection.

Finds out which Proton build a game ran with, including rolling channels
(Proton Experimental / Hotfix), GE-Proton and distro builds (proton-cachyos).

How it works (verified against Proton's own `proton` script):
- Every Proton launch writes `compatdata/<appid>/version` (prefix version).
- `compatdata/<appid>/config_info` is rewritten whenever the Proton version or
  the tool directory changes; line 2 is `<tool dir>/files/share/fonts/`.
- Every Proton tool directory has a `version` file: "<unix ts> <build>",
  e.g. "1789805668 experimental-11.0-20260917b-x86_64".

The prefix is only trusted if Proton actually ran for this benchmark: either a
running process uses it (STEAM_COMPAT_DATA_PATH) or its `version` file was
written after the benchmark session started. Otherwise nothing is reported -
a native run must not get a stale Proton label.
"""

import os
from pathlib import Path
from typing import Optional

MAX_BUILD_LEN = 100

# Tolerance for file mtime vs. session start (clock granularity)
MTIME_SLACK_SECONDS = 5


def _compatdata_dirs(app_id: int) -> list[Path]:
    """All existing compatdata/<app_id> folders across Steam library folders."""
    from linux_game_benchmark.steam.library_scanner import (
        SteamLibraryScanner, find_steam_path,
    )

    steam_path = find_steam_path()
    if not steam_path:
        return []
    try:
        steamapps_dirs = SteamLibraryScanner(steam_path)._get_steamapps_dirs()
    except Exception:
        steamapps_dirs = [steam_path / "steamapps"]

    dirs = []
    for steamapps in steamapps_dirs:
        candidate = steamapps / "compatdata" / str(app_id)
        if candidate.is_dir() and candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _prefixes_in_use() -> set[str]:
    """Real paths of all compatdata prefixes used by running processes of this user."""
    in_use = set()
    uid = os.getuid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue
        for var in environ.split(b"\0"):
            if var.startswith(b"STEAM_COMPAT_DATA_PATH="):
                value = var.split(b"=", 1)[1].decode("utf-8", "replace")
                in_use.add(os.path.realpath(value))
                break
    return in_use


def _host_path(path_str: str) -> Path:
    """Map a path seen inside the Steam Runtime container back to the host."""
    path = Path(path_str)
    if not path.exists() and path_str.startswith("/run/host/"):
        path = Path(path_str[len("/run/host"):])
    return path


def _tool_dir_from_fonts_dir(fonts_dir: str) -> Optional[Path]:
    """`<tool>/files/share/fonts/` (or `dist/...` on old Proton) -> `<tool>`."""
    path = _host_path(fonts_dir.strip().rstrip("/"))
    for parent in [path, *path.parents][:5]:
        if (parent / "version").is_file() and (parent / "proton").is_file():
            return parent
    return None


def read_tool_version(tool_dir: Path) -> tuple[Optional[str], Optional[int]]:
    """Read `<tool>/version` -> (build, unix timestamp)."""
    try:
        content = (tool_dir / "version").read_text(errors="replace").strip()
    except OSError:
        return None, None
    if not content:
        return None, None
    parts = content.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].strip()[:MAX_BUILD_LEN], int(parts[0])
    return content[:MAX_BUILD_LEN], None


def read_prefix_proton(compatdata: Path) -> dict:
    """
    Proton build recorded in a prefix (no check whether it is current).

    Returns dict with proton_build / proton_tool / proton_build_ts, or {}.
    """
    try:
        lines = (compatdata / "config_info").read_text(errors="replace").splitlines()
    except OSError:
        lines = []

    prefix_version = lines[0].strip() if lines else ""
    if not prefix_version:
        try:
            prefix_version = (compatdata / "version").read_text(errors="replace").strip()
        except OSError:
            prefix_version = ""

    tool_dir = _tool_dir_from_fonts_dir(lines[1]) if len(lines) > 1 else None
    build, build_ts = read_tool_version(tool_dir) if tool_dir else (None, None)
    build = build or prefix_version[:MAX_BUILD_LEN] or None
    if not build:
        return {}

    return {
        "proton_build": build,
        "proton_tool": tool_dir.name[:MAX_BUILD_LEN] if tool_dir else None,
        "proton_build_ts": build_ts,
    }


def detect_proton(app_id: int, since: Optional[float] = None) -> dict:
    """
    Detect the Proton build used for a benchmark of `app_id`.

    Args:
        app_id: Steam App ID of the game.
        since: Unix time the benchmark session started. A prefix written after
            this time counts as "used for this benchmark".

    Returns:
        {"proton_build", "proton_tool", "proton_build_ts"} or {} if the game
        did not run through Proton (native) or it cannot be determined.
    """
    try:
        if not app_id:
            return {}
        compat_dirs = _compatdata_dirs(int(app_id))
        if not compat_dirs:
            return {}

        # Newest prefix first (a game can have prefixes in several libraries)
        compat_dirs.sort(key=lambda d: _mtime(d / "version"), reverse=True)

        in_use = None
        for compatdata in compat_dirs:
            fresh = since is not None and _mtime(compatdata / "version") >= since - MTIME_SLACK_SECONDS
            if not fresh:
                if in_use is None:
                    in_use = _prefixes_in_use()
                if os.path.realpath(compatdata) not in in_use:
                    continue
            return read_prefix_proton(compatdata)
    except Exception:
        pass
    return {}
