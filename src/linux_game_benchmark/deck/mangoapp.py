"""Steam's overlay program (mangoapp) in Game Mode: it sees every game - OpenGL, Vulkan, Proton - and writes a log on command.

`mangohudctl set log_session true|false` starts and ends one log file, so one recording is exactly one file and nothing is
logged in between. While a log runs MangoHud draws a red dot in its overlay (visible when the player has Steam's performance
overlay switched on). mangohudctl talks to mangoapp only, never to the MangoHud layer inside a game.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from linux_game_benchmark.deck.gamescope import host_env

PROGRAM = "mangoapp"
CONTROL = "mangohudctl"


def running(proc: Path = Path("/proc")) -> bool:
    """Is Steam's overlay program running? (it only does in Game Mode)"""
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip() == PROGRAM:
                return True
        except OSError:
            continue
    return False


def set_logging(on: bool, run: Callable = subprocess.run, which: Callable = shutil.which) -> bool:
    """Start or end the overlay program's log. True when mangohudctl accepted the command (idempotent on its side)."""
    exe = which(CONTROL)
    if not exe:
        return False
    try:
        done = run([exe, "set", "log_session", "true" if on else "false"], capture_output=True, timeout=5, env=host_env())
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
