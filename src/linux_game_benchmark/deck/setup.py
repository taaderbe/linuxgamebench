"""One-time setup on the Deck: MangoHud (Desktop Mode flight recorder, Game Mode log on command), systemd user service, sounds.

Everything is written below $HOME (SteamOS updates replace the system image, never /home) and
every function is idempotent, so running the setup again repairs a broken install.
"""

from __future__ import annotations

import io
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

# Game Mode is recorded through Steam's own overlay program (mangoapp, it sees every game - also OpenGL): the recorder tells it
# `mangohudctl set log_session true|false`. It needs NO setting of ours: it logs one row per frame and writes into the home
# folder, the recorder finds the file through mangoapp's open file descriptors. (Builds up to 20 wrapped mangoapp in a drop-in
# with its own MANGOHUD_CONFIG; MangoHud then reads Steam's config twice, which showed Steam's level 1 with the FPS twice - the
# drop-in is only kept as a name so that an old one is removed.)
MANGOAPP_DROPIN = "gamescope-mangoapp.service.d/linuxgamebench.conf"
MANGOAPP_UNIT = "gamescope-mangoapp.service"
# Steam itself runs as this unit in Game Mode only (never in Desktop Mode); every game inherits the environment it gets.
STEAM_DROPIN = "steam-launcher.service.d/linuxgamebench.conf"


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
    remove_legacy_mangoapp_dropin()
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


def remove_legacy_mangoapp_dropin() -> bool:
    """Builds up to 20 put a drop-in around Steam's overlay program; with it Steam's performance level 1 showed the FPS twice.
    An install removes it (the overlay program runs as SteamOS ships it again). True when there was one."""
    path = mangoapp_dropin_path()
    if not path.exists():
        return False
    path.unlink()
    try:
        path.parent.rmdir()                         # only when it is empty now
    except OSError:
        pass
    return True


def reload_mangoapp() -> None:
    """Make changed drop-ins count now: reload systemd and restart the overlay program if it runs (Game Mode), so it runs as SteamOS ships it."""
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
    # two quick, high, louder beeps: one 200 Hz tone and then two 440 Hz beeps were both missed on the Deck's small speakers
    # (the 440 Hz beeps were measurably in the output - too low a pitch for those speakers next to the game's sound)
    "error": [(1047, 0.09), (0, 0.07), (1047, 0.09)],
}
_GAIN = {"error": 1.6}                                     # louder than the others (1.0 = amplitude 9000 of 32767)


def sound_bytes(notes: list[tuple[int, float]], rate: int = 22050, gain: float = 1.0) -> bytes:
    """A mono 16-bit WAV of the notes (frequency 0 = silence)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for freq, seconds in notes:
            count = int(rate * seconds)
            for i in range(count):
                fade = min(1.0, i / 200, (count - i) / 200)        # no clicks
                frames += struct.pack("<h", int(9000 * gain * fade * math.sin(2 * math.pi * freq * i / rate)))
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def write_sound(path: Path, notes: list[tuple[int, float]], rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sound_bytes(notes, rate))
    return path


def ensure_sounds(directory: Optional[Path] = None) -> dict[str, Path]:
    """The sound files, written again whenever a sound changed (an update must not keep playing the old tone)."""
    directory = directory or deck_config.data_dir() / "sounds"
    paths = {}
    for name, notes in _SOUNDS.items():
        path = directory / f"{name}.wav"
        wanted = sound_bytes(notes, gain=_GAIN.get(name, 1.0))
        try:
            same = path.read_bytes() == wanted
        except OSError:
            same = False
        if not same:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(wanted)
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
