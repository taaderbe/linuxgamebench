"""One-time setup on the Deck: MangoHud flight recorder, environment, systemd user service, sounds.

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

# Game Mode points MANGOHUD_CONFIGFILE at a file of its own (Steam's performance overlay, "no_display" by default), so
# our config file is never read there. MANGOHUD_CONFIG (the same options as one variable) wins over that file.
MANGOAPP_DROPIN = "gamescope-mangoapp.service.d/linuxgamebench.conf"


def mangohud_env_options(out_dir: Optional[Path] = None) -> str:
    out_dir = out_dir or deck_config.log_dir()
    return ",".join([f"output_folder={out_dir}", "autostart_log=1", "log_interval=0", *SENSORS])


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
    """MANGOHUD=1 for everything the user session starts (read at the next login, e.g. switching to Game Mode)."""
    path = path or env_file_path()
    conf = conf or mangohud_conf_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Written by Linux Game Bench\nMANGOHUD=1\n"
                    f"MANGOHUD_CONFIGFILE={conf}\n"
                    f"MANGOHUD_CONFIG={mangohud_env_options()}\n")
    write_mangoapp_dropin()
    return path


def mangoapp_dropin_path() -> Path:
    return home() / ".config/systemd/user" / MANGOAPP_DROPIN


def write_mangoapp_dropin() -> Path:
    """Steam's own performance overlay (mangoapp) must not pick up our logging options: it would show all of them."""
    path = mangoapp_dropin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Written by Linux Game Bench: keeps Steam's performance overlay as it is\n[Service]\nUnsetEnvironment=MANGOHUD_CONFIG\n")
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
        _systemctl("daemon-reload")
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
    for path in (unit_path(), env_file_path(), mangoapp_dropin_path()):
        if path.exists():
            path.unlink()
            done.append(str(path))
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
