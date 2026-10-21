"""One-time setup on the Deck: MangoHud (Desktop Mode flight recorder, Game Mode log on command), systemd user service, sounds.

Everything is written below $HOME (SteamOS updates replace the system image, never /home) and
every function is idempotent, so running the setup again repairs a broken install.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Optional

from linux_game_benchmark.deck import config as deck_config

MARKER_START = "### LGB-MANAGED-START"
MARKER_END = "### LGB-MANAGED-END"
UNIT_NAME = "lgb-deck.service"

# the sensors that end up in the CSV (a sensor MangoHud is told about is logged; the overlay itself stays invisible)
SENSORS = [
    "fps", "frametime", "cpu_stats", "cpu_temp", "cpu_power", "cpu_mhz", "gpu_stats", "gpu_temp", "gpu_core_clock",
    "gpu_mem_clock", "gpu_power", "vram", "ram", "battery", "battery_watt", "battery_time", "fan", "throttling_status",
    "core_load", "swap", "procmem", "procmem_shared", "procmem_virt", "io_read", "io_write", "resolution", "refresh_rate",
    "wine", "vulkan_driver", "engine_version",
]

MANGOHUD_CONF_TEMPLATE = f"""\
# Written by Linux Game Bench - the lines between the markers are managed and rewritten by 'lgb deck setup'.
{MARKER_START}
output_folder={{out_dir}}
autostart_log=1
log_interval=0

# sensors written to the log
{chr(10).join(SENSORS)}

# the overlay stays invisible (it has to exist, MangoHud logs only while the HUD is on)
alpha=0
background_alpha=0
font_size=1
position=top-right
{MARKER_END}
"""

# Game Mode points MANGOHUD_CONFIGFILE at a file of its own (Steam's performance overlay), so our config file is never read
# there and the MangoHud layer inside the games stays quiet. Game Mode is recorded through Steam's overlay program instead
# (it sees every game): its drop-in below only says where the log goes - a log is written when the recorder asks for one.
MANGOAPP_DROPIN = "gamescope-mangoapp.service.d/linuxgamebench.conf"
MANGOAPP_UNIT = "gamescope-mangoapp.service"
# Steam itself runs as this unit in Game Mode only (never in Desktop Mode); every game inherits the environment it gets.
STEAM_DROPIN = "steam-launcher.service.d/linuxgamebench.conf"
MANGOAPP_FALLBACK_COMMAND = "/usr/bin/mangoapp"


def mangoapp_env_options(out_dir: Optional[Path] = None) -> str:
    """`read_cfg` first, then where the log goes and one row per frame. No `autostart_log` (the recorder starts a log with
    `mangohudctl set log_session`) and no sensor list, so what Steam's overlay shows stays as the player set it.

    `read_cfg` is what keeps Steam's performance overlay switch working: as soon as MANGOHUD_CONFIG is set MangoHud ignores the
    config file (the one Steam writes its level - Off, Minimal ... - into) unless it is told to read it as well. Without it the
    overlay would show MangoHud's default HUD all the time and "Off" in Steam would do nothing."""
    out_dir = out_dir or deck_config.mangoapp_log_dir()
    return ",".join(["read_cfg", f"output_folder={out_dir}", "log_interval=0"])


def home() -> Path:
    return Path(os.path.expanduser("~"))


def mangohud_conf_path() -> Path:
    return home() / ".config/MangoHud/MangoHud.conf"


def env_file_path() -> Path:
    return home() / ".config/environment.d/linuxgamebench.conf"      # same name the GUI Auto-Mode used


def unit_path() -> Path:
    return home() / ".config/systemd/user" / UNIT_NAME


def is_managed(path: Path) -> bool:
    try:
        return MARKER_START in path.read_text(errors="replace")
    except OSError:
        return False


def write_mangohud_conf(path: Optional[Path] = None, out_dir: Optional[Path] = None) -> Path:
    """Flight recorder: MangoHud logs every game from its first seconds on. A foreign config is backed up first."""
    path = path or mangohud_conf_path()
    out_dir = out_dir or deck_config.log_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not is_managed(path):
        shutil.copy(path, path.with_name(f"{path.name}.lgb-backup-{int(time.time())}"))
    path.write_text(MANGOHUD_CONF_TEMPLATE.format(out_dir=out_dir))
    return path


def write_env_file(path: Optional[Path] = None, conf: Optional[Path] = None) -> Path:
    """MANGOHUD=1 and our config for everything the user session starts (read at the next login). Meant for Desktop Mode: the
    user manager keeps running between the modes (linger), so Steam in Game Mode would inherit MANGOHUD=1 as well - and the
    MangoHud layer inside a game cannot read Steam's config file there (it is not visible inside the game's container), so it
    would draw its default overlay next to Steam's own. The Steam drop-in below takes the variable away again in Game Mode,
    where Steam's overlay program records instead."""
    path = path or env_file_path()
    conf = conf or mangohud_conf_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Written by Linux Game Bench\nMANGOHUD=1\n"
                    f"MANGOHUD_CONFIGFILE={conf}\n")
    write_mangoapp_dropin()
    write_steam_dropin()
    return path


def steam_dropin_path() -> Path:
    return home() / ".config/systemd/user" / STEAM_DROPIN


def write_steam_dropin() -> Path:
    """Game Mode starts Steam without MANGOHUD (as SteamOS ships it): no MangoHud layer in the games, only Steam's own overlay."""
    path = steam_dropin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Written by Linux Game Bench: Game Mode shows only Steam's own performance overlay - the MangoHud layer that MANGOHUD=1 (Desktop Mode) switches on inside the games would draw a second one\n"
        "[Service]\n"
        "UnsetEnvironment=MANGOHUD\n")
    return path


def game_mode_layer_leak(proc: Path = Path("/proc")) -> Optional[bool]:
    """Game Mode only: does the running Steam client carry MANGOHUD=1, so that every game loads the MangoHud layer and draws a
    second overlay next to Steam's? True = yes (the drop-in is missing or SteamOS changed how Steam is started), False = no,
    None = cannot tell (no readable Steam process, or it is not the Game Mode one). Read from /proc, so it also notices a
    change after a SteamOS update."""
    try:
        entries = [e for e in proc.iterdir() if e.name.isdigit()]
    except OSError:
        return None
    for entry in entries:
        try:
            if (entry / "comm").read_text().strip() != "steam":
                continue
            env = dict(item.partition(b"=")[::2] for item in (entry / "environ").read_bytes().split(b"\0") if item)
        except OSError:
            continue
        if env.get(b"STEAM_USE_MANGOAPP") == b"1":                    # set by SteamOS' Game Mode session only
            return env.get(b"MANGOHUD") == b"1"
    return None


def mangoapp_dropin_path() -> Path:
    return home() / ".config/systemd/user" / MANGOAPP_DROPIN


def vendor_mangoapp_command() -> str:
    """The command SteamOS starts the overlay with (read from the unit, so a changed path or argument is followed)."""
    try:
        result = _systemctl("cat", MANGOAPP_UNIT)
        text = result.stdout if result is not None and result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        text = ""
    source = ""
    for line in text.splitlines():
        if line.startswith("# /"):
            source = line[2:].strip()
        elif line.startswith("ExecStart=") and ".service.d/" not in source:
            command = line[len("ExecStart="):].strip().lstrip("-@:+!")
            if command and "$" not in command and "%" not in command:
                return command
    return MANGOAPP_FALLBACK_COMMAND


def _unit_quote(text: str) -> str:
    """One argument of a systemd Exec line (specifiers and variables escaped, whole thing in double quotes)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def write_mangoapp_dropin() -> Path:
    """Steam's own performance overlay (mangoapp) writes the log of every game in Game Mode - on command.

    MangoHud's Vulkan layer cannot see OpenGL games (Brotato, Godot, many native titles), but Gamescope hands the frame data
    of EVERY game to mangoapp. So mangoapp gets its own variable with the folder for the logs (the plain session value never
    reaches it, that is what UnsetEnvironment is for); what it shows on screen stays exactly as the player set it in Steam."""
    path = mangoapp_dropin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    deck_config.mangoapp_log_dir().mkdir(parents=True, exist_ok=True)
    command = vendor_mangoapp_command()
    path.write_text(
        "# Written by Linux Game Bench: the recorder tells this overlay program to log a game (also OpenGL) while it records; the overlay looks the same\n"
        "[Service]\n"
        "UnsetEnvironment=MANGOHUD_CONFIG\n"
        "ExecStart=\n"
        f"ExecStart=/usr/bin/env {_unit_quote('MANGOHUD_CONFIG=' + mangoapp_env_options())} {command}\n")
    return path


def reload_mangoapp() -> None:
    """Make a changed drop-in count now: reload systemd and restart the overlay program if it runs (Game Mode)."""
    try:
        _systemctl("daemon-reload")
        result = _systemctl("is-active", MANGOAPP_UNIT)
        if result is not None and (result.stdout or "").strip() == "active":
            _systemctl("restart", MANGOAPP_UNIT)
    except (OSError, subprocess.SubprocessError):
        pass


LAUNCHER_NAME = "linuxgamebench-link.desktop"


def link_launcher_path() -> Path:
    return home() / ".local/share/applications" / LAUNCHER_NAME


def app_command() -> str:
    """The program as a person types it: the AppImage when we run from one, else `lgb`."""
    return os.environ.get("APPIMAGE") or shutil.which("lgb") or sys.argv[0]


def _desktop_quote(text: str) -> str:
    """One argument of a .desktop Exec line (reserved characters escaped, whole thing in double quotes)."""
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in text.replace("%", "%%")) + '"'


def write_link_launcher(command: Optional[str] = None) -> Path:
    """An entry in the application menu (Desktop Mode) that starts the account link - so linking later is one click."""
    path = link_launcher_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Linux Game Bench - link account\n"
        "Comment=Connect this Steam Deck to your Linux Game Bench account (optional)\n"
        f"Exec={_desktop_quote(command or app_command())} deck link --pause\n"
        "Terminal=true\n"
        "Icon=applications-games\n"
        "Categories=Game;Utility;\n"
    )
    return path


def service_command() -> str:
    """How systemd starts the service: the AppImage when we run from one, else the lgb script."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return f'"{appimage}" deck run'
    exe = shutil.which("lgb") or sys.argv[0]
    return f'"{exe}" deck run'


def unit_text(command: Optional[str] = None) -> str:
    # The one-line installer sets this when FUSE is missing; systemd would not inherit it, so the unit carries it on
    extract = "Environment=APPIMAGE_EXTRACT_AND_RUN=1\n" if os.environ.get("APPIMAGE_EXTRACT_AND_RUN") == "1" else ""
    return (
        "[Unit]\n"
        "Description=Linux Game Bench - Steam Deck recorder\n"
        "After=default.target\n\n"
        "[Service]\n"
        f"ExecStart={command or service_command()}\n"
        f"{extract}"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        # An AppImage runs next to its FUSE helper: SIGTERM for both unmounts the program under Python's feet (SIGBUS).
        # `mixed` stops Python first, then the helper.
        "KillMode=mixed\n"
        "Nice=10\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, env=env, timeout=30)


def install_service(enable: bool = True, command: Optional[str] = None) -> tuple[bool, str]:
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text(command))
    if not enable:
        return True, f"unit written to {path}"
    try:
        reload_mangoapp()                                            # daemon-reload, and the overlay program picks up its drop-in
        result = _systemctl("enable", "--now", UNIT_NAME)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip() or "systemctl failed"
        # `--now` leaves a service that already runs alone: after an update it would keep the old program in memory
        _systemctl("restart", UNIT_NAME)
        subprocess.run(["loginctl", "enable-linger", os.environ.get("USER", "")],
                       capture_output=True, timeout=15)          # best effort: keeps the service alive between sessions
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return True, "service enabled and started"


def service_state() -> str:
    try:
        return _systemctl("is-active", UNIT_NAME).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def remove_all() -> list[str]:
    """Undo the setup (recordings in the data folder stay)."""
    done = []
    try:
        _systemctl("disable", "--now", UNIT_NAME)
    except (OSError, subprocess.SubprocessError):
        pass
    for path in (unit_path(), env_file_path(), mangoapp_dropin_path(), steam_dropin_path(), link_launcher_path()):
        if path.exists():
            path.unlink()
            done.append(str(path))
    reload_mangoapp()                                                  # the overlay program runs as SteamOS ships it again
    conf = mangohud_conf_path()
    if conf.exists() and is_managed(conf):
        backups = sorted(conf.parent.glob(conf.name + ".lgb-backup-*"))
        if backups:
            shutil.copy(backups[-1], conf)
        else:
            conf.unlink()
        done.append(str(conf))
    return done


# ----- sounds ------------------------------------------------------------------

_SOUNDS = {
    "start": [(660, 0.09), (880, 0.14)],
    "stop": [(880, 0.09), (660, 0.14)],
    "cancel": [(520, 0.08), (390, 0.08), (260, 0.16)],
    "done": [(660, 0.07), (880, 0.07), (1100, 0.16)],
    "error": [(200, 0.30)],
}


def write_sound(path: Path, notes: list[tuple[int, float]], rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for freq, seconds in notes:
            count = int(rate * seconds)
            for i in range(count):
                fade = min(1.0, i / 200, (count - i) / 200)        # no clicks
                frames += struct.pack("<h", int(9000 * fade * math.sin(2 * math.pi * freq * i / rate)))
        wav.writeframes(bytes(frames))
    return path


def ensure_sounds(directory: Optional[Path] = None) -> dict[str, Path]:
    directory = directory or deck_config.data_dir() / "sounds"
    paths = {}
    for name, notes in _SOUNDS.items():
        path = directory / f"{name}.wav"
        if not path.exists():
            write_sound(path, notes)
        paths[name] = path
    return paths


def play(path: Path) -> bool:
    """Play a short sound without blocking; first player that exists wins."""
    for player in ("pw-play", "paplay", "aplay"):
        exe = shutil.which(player)
        if exe:
            try:
                subprocess.Popen([exe, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except OSError:
                return False
    return False
