"""Which Steam game is the running one? Looks at /proc (the process that writes the log, or the Steam 'reaper' of the game)."""

from __future__ import annotations

import re
import shlex
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ENV_KEYS = ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID")
_REAPER = re.compile(r"SteamLaunch\x00AppId=(\d+)|SteamLaunch AppId=(\d+)")


@dataclass(frozen=True)
class GameInfo:
    app_id: int
    name: str
    pid: Optional[int] = None         # the process that writes the log (its environment holds the launch options)
    launcher: Optional[str] = None    # a shortcut (no Steam app): what starts it - "RPCS3", "eden", "Heroic (GOG)"

    @property
    def non_steam(self) -> bool:
        return is_shortcut(self.app_id)


# ----- shortcuts: games added to Steam that are no Steam app (emulators, Heroic, own builds) --------------------------------

UNKNOWN_SHORTCUT = "Non-Steam game"   # a shortcut in no list: never uploaded under this name (all of them would become one game)
SHORTCUT_MIN_ID = 1 << 31             # Steam gives a shortcut crc32(exe + name) | 0x80000000; store app ids are far below
_HEROIC_STORES = {"legendary": "Epic", "gog": "GOG", "nile": "Amazon", "sideload": "sideload"}
_HEROIC_URL = re.compile(r"heroic://launch(?:/(\w+)/|\?[^\s\"']*?runner=(\w+))", re.IGNORECASE)
_EXTENSIONS = re.compile(r"\.(sh|exe|appimage|x86_64|x86|bin|py|bat|desktop)$", re.IGNORECASE)
_NOT_PLAIN = re.compile(r"[^A-Za-z0-9 .+_()\-]")


# programs that start other games: a shortcut to one of them itself (named "Heroic", "Eden", "RetroArch", "Google Chrome")
# says nothing about the game played inside - such a run is not uploaded under the program's name
FRONTENDS = ("heroic", "lutris", "bottles", "eden", "yuzu", "suyu", "sudachi", "citron", "ryujinx", "rpcs3", "retroarch",
             "dolphin", "dolphinemu", "pcsx2", "ppsspp", "cemu", "duckstation", "xemu", "xenia", "vita3k", "melonds", "azahar",
             "lime3ds", "citra", "emulationstation", "esde", "pegasus", "srm", "steamrommanager", "chrome", "chromium",
             "firefox", "brave", "edge", "minigalaxy", "itch", "legendary", "gamehub")


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_frontend_itself(name: str, launcher: Optional[str]) -> bool:
    """A shortcut that opens a launcher / emulator / browser itself, not one game in it."""
    if not launcher or "(" in launcher:                        # "Heroic (GOG)": Heroic's own "Add to Steam" for one game
        return False
    tool, title = _plain(launcher), _plain(name)
    return tool in FRONTENDS and bool(title) and (tool in title or title in tool)


def is_shortcut(app_id) -> bool:
    return isinstance(app_id, int) and app_id >= SHORTCUT_MIN_ID


def read_binary_vdf(data: bytes) -> dict:
    """Steam's binary key-value format (shortcuts.vdf): 0x00 nested map, 0x01 text, 0x02 32-bit number, 0x08 end of a map.
    Raises ValueError on anything it cannot read."""
    def parse(i: int) -> tuple[dict, int]:
        out: dict = {}
        while True:
            if i >= len(data):
                raise ValueError("unexpected end")
            kind = data[i]
            i += 1
            if kind == 0x08:
                return out, i
            end = data.index(b"\x00", i)
            key = data[i:end].decode("utf-8", "replace")
            i = end + 1
            if kind == 0x00:
                value, i = parse(i)
            elif kind == 0x01:
                end = data.index(b"\x00", i)
                value, i = data[i:end].decode("utf-8", "replace"), end + 1
            elif kind == 0x02:
                if i + 4 > len(data):
                    raise ValueError("unexpected end")
                value, i = struct.unpack("<I", data[i:i + 4])[0], i + 4
            else:
                raise ValueError(f"unknown type {kind}")
            out[key] = value
    try:
        return parse(0)[0]
    except IndexError as exc:                                  # data.index found no end of a text
        raise ValueError("unexpected end") from exc


def _steam_roots(home: Path) -> list[Path]:
    return [home / ".local/share/Steam", home / ".steam/steam", home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]


def _field(entry: dict, name: str):
    for key, value in entry.items():                           # Steam has written both "AppName" and "appname"
        if key.lower() == name:
            return value
    return None


def shortcut_launcher(entry: dict) -> Optional[str]:
    """What starts a shortcut, as a short name: Heroic with its store, a Flatpak app's last name part, else the program's name."""
    exe = str(_field(entry, "exe") or "")
    options = str(_field(entry, "launchoptions") or "")
    text = f"{exe} {options}"
    heroic = _HEROIC_URL.search(text)
    if heroic:
        runner = (heroic.group(1) or heroic.group(2) or "").lower()
        store = _HEROIC_STORES.get(runner)
        return f"Heroic ({store})" if store else "Heroic"
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    name = ""
    flatpak = str(_field(entry, "flatpakappid") or "")
    if flatpak:
        name = flatpak.rsplit(".", 1)[-1]
    elif tokens and Path(tokens[0]).name == "flatpak" and "run" in tokens:
        rest = [t for t in tokens[tokens.index("run") + 1:] if not t.startswith("-")]
        if rest:
            name = rest[0].rsplit(".", 1)[-1]
    elif tokens:
        name = _EXTENSIONS.sub("", Path(tokens[0]).name)
    if "heroicgameslauncher" in text.lower() or name.lower() in ("heroic", "hgl"):
        return "Heroic"
    name = _NOT_PLAIN.sub("", name).strip()[:40]
    return name or None


def shortcuts(home: Optional[Path] = None) -> dict[int, dict]:
    """Every shortcut of every Steam account on this machine: {app id: {"name", "launcher"}}. The most recently changed
    list wins when two accounts have the same id (the id comes from the program and the name, so they mean the same game)."""
    home = Path.home() if home is None else Path(home)
    files: list[tuple[float, Path]] = []
    for root in _steam_roots(home):
        try:
            for path in root.glob("userdata/*/config/shortcuts.vdf"):
                try:
                    files.append((path.stat().st_mtime, path))
                except OSError:
                    continue
        except OSError:
            continue
    found: dict[int, dict] = {}
    for _, path in sorted(files, reverse=True):
        try:
            data = read_binary_vdf(path.read_bytes())
        except (OSError, ValueError):
            continue
        entries = _field(data, "shortcuts")
        if not isinstance(entries, dict):
            continue
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            name = str(_field(entry, "appname") or "").strip()
            if not name:
                continue
            app_id = _field(entry, "appid")
            if not isinstance(app_id, int) or not app_id:      # very old lists: Steam derives the id
                app_id = zlib.crc32((str(_field(entry, "exe") or "") + name).encode()) | 0x80000000
            found.setdefault(app_id, {"name": name, "launcher": shortcut_launcher(entry)})
    return found


def shortcut(app_id: int, home: Optional[Path] = None) -> Optional[dict]:
    return shortcuts(home).get(app_id) if is_shortcut(app_id) else None


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


OVERLAY_LOG_PATTERN = "mangoapp_*.csv"          # what Steam's overlay program names its logs (it writes into the home folder)


def log_names(log_dir: Path, pattern: str = "*.csv") -> set[str]:
    """The log files that exist right now - taken before a log is started on command, to tell the new one apart."""
    try:
        return {p.name for p in Path(log_dir).glob(pattern)}
    except OSError:
        return set()


def new_log(log_dir: Path, before: set[str], pattern: str = "*.csv") -> Optional[Path]:
    """The log file that appeared after `before` was taken (the newest one; a _summary never counts)."""
    best: Optional[tuple[float, Path]] = None
    try:
        candidates = list(Path(log_dir).glob(pattern))
    except OSError:
        return None
    for path in candidates:
        if path.name in before or path.name.endswith("_summary.csv"):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
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
    found = log_writer(csv_path, proc)
    return found[0] if found else None


def log_writer(csv_path: Path, proc: Path = Path("/proc")) -> Optional[tuple[int, int]]:
    """(app id, pid) of the process that has the log open."""
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
                        return app_id, int(pid_dir.name)
            except OSError:
                continue
    return None


def _rss_kb(pid_dir: Path) -> int:
    try:
        for line in (pid_dir / "status").read_text(errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def game_pid(app_id: int, proc: Path = Path("/proc")) -> Optional[int]:
    """The game's own process: of everything Steam started for this app (reaper, runtime, wine servers, the game) the one that
    uses the most memory. Its environment holds the launch options and the DISPLAY the game draws on."""
    best: Optional[tuple[int, int]] = None
    for pid_dir in _pids(proc):
        if app_id_from_environ(pid_dir) != app_id:
            continue
        rss = _rss_kb(pid_dir)
        if best is None or rss > best[0]:
            best = (rss, int(pid_dir.name))
    return best[1] if best else None


def describe(app_id: int) -> "GameInfo":
    pid = game_pid(app_id)
    return _info(app_id, pid)


def _info(app_id: int, pid: Optional[int]) -> GameInfo:
    if is_shortcut(app_id):
        found = shortcut(app_id) or {}
        return GameInfo(app_id=app_id, name=found.get("name") or UNKNOWN_SHORTCUT, pid=pid, launcher=found.get("launcher"))
    return GameInfo(app_id=app_id, name=game_name(app_id), pid=pid)


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


def launch_tools(app_id: int, proc: Path = Path("/proc")) -> Optional[dict]:
    """How Steam started this game, read from the 'reaper SteamLaunch AppId=N -- ...' command line:
    {"proton_dir": ..., "runtime_dir": ...} for a Proton game, {} for a native Linux game, None when the launch is not found."""
    marker = f"AppId={app_id}"
    for pid_dir in _pids(proc):
        try:
            args = (pid_dir / "cmdline").read_bytes().decode(errors="replace").split("\x00")
        except OSError:
            continue
        if "SteamLaunch" not in args or marker not in args:
            continue
        found: dict = {}
        for arg in args:
            name = arg.rsplit("/", 1)[-1]
            if name == "proton" and "/" in arg and "proton_dir" not in found:
                found["proton_dir"] = arg.rsplit("/", 1)[0]
            elif name == "_v2-entry-point" and "/" in arg and "runtime_dir" not in found:
                found["runtime_dir"] = arg.rsplit("/", 1)[0]
        return found
    return None


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
    found = log_writer(csv_path, proc)
    app_id, pid = found if found else (None, None)
    if not app_id:
        games = running_steam_games(proc)
        if len(games) == 1:
            app_id = next(iter(games))
    if not app_id:
        return None
    return _info(app_id, pid)
