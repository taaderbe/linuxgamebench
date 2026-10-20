"""Which Steam game is the running one? Looks at /proc (the process that writes the log, or the Steam 'reaper' of the game)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ENV_KEYS = ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID")
_REAPER = re.compile(r"SteamLaunch\x00AppId=(\d+)|SteamLaunch AppId=(\d+)")


@dataclass(frozen=True)
class GameInfo:
    app_id: int
    name: str


def newest_log(log_dir: Path, max_age: float = 60.0, now: Optional[float] = None) -> Optional[Path]:
    """The log MangoHud is writing right now: newest *.csv (not a _summary) touched within max_age seconds."""
    now = time.time() if now is None else now
    best: Optional[tuple[float, Path]] = None
    try:
        candidates = list(Path(log_dir).glob("*.csv"))
    except OSError:
        return None
    for path in candidates:
        if path.name.endswith("_summary.csv"):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if now - mtime <= max_age and (best is None or mtime > best[0]):
            best = (mtime, path)
    return best[1] if best else None


def _pids(proc: Path) -> list[Path]:
    try:
        return [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return []


def app_id_from_environ(pid_dir: Path) -> Optional[int]:
    try:
        raw = (pid_dir / "environ").read_bytes()
    except OSError:
        return None
    env = {}
    for entry in raw.split(b"\x00"):
        key, _, value = entry.partition(b"=")
        env[key.decode(errors="replace")] = value.decode(errors="replace")
    for key in _ENV_KEYS:
        value = env.get(key, "")
        if value.isdigit() and int(value) > 0:
            return int(value)
    return None


def log_writer_app_id(csv_path: Path, proc: Path = Path("/proc")) -> Optional[int]:
    """App id of the process that has the log open."""
    target = str(csv_path)
    for pid_dir in _pids(proc):
        try:
            fds = list((pid_dir / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                if str(fd.readlink()) == target:
                    app_id = app_id_from_environ(pid_dir)
                    if app_id:
                        return app_id
            except OSError:
                continue
    return None


def running_steam_games(proc: Path = Path("/proc")) -> set[int]:
    """App ids of every Steam launch ('reaper SteamLaunch AppId=N') - the fallback when the log writer is hidden."""
    ids = set()
    for pid_dir in _pids(proc):
        try:
            cmdline = (pid_dir / "cmdline").read_bytes().decode(errors="replace")
        except OSError:
            continue
        match = _REAPER.search(cmdline)
        if match:
            ids.add(int(match.group(1) or match.group(2)))
    return ids


def game_name(app_id: int) -> str:
    try:
        from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
        game = SteamLibraryScanner().get_game_by_id(app_id)
        if game and game.get("name"):
            return str(game["name"])
    except Exception:
        pass
    return f"App {app_id}"


def identify(csv_path: Path, proc: Path = Path("/proc")) -> Optional[GameInfo]:
    app_id = log_writer_app_id(csv_path, proc)
    if not app_id:
        games = running_steam_games(proc)
        if len(games) == 1:
            app_id = next(iter(games))
    if not app_id:
        return None
    return GameInfo(app_id=app_id, name=game_name(app_id))
