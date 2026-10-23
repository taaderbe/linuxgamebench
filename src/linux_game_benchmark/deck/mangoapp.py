"""Steam's overlay program (mangoapp) in Game Mode: it sees every game - OpenGL, Vulkan, Proton - and writes a log on command.

`mangohudctl set log_session true|false` starts and ends one log file, so one recording is exactly one file and nothing is
logged in between. While a log runs MangoHud draws a red dot in its overlay (visible when the player has Steam's performance
overlay switched on); when the log ends it shows a "Logging Finished" summary for 12 seconds, squeezed into the overlay's
narrow box at Steam's level 1. mangohudctl talks to mangoapp only, never to the MangoHud layer inside a game.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Optional

from linux_game_benchmark.deck.gamescope import host_env

PROGRAM = "mangoapp"
CONTROL = "mangohudctl"
SUMMARY_SECONDS = 12.0          # how long MangoHud shows the summary after a log ended (a fixed 12 s in its overlay code)


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


def open_log(exclude: Iterable[str] = (), proc: Path = Path("/proc")) -> Optional[Path]:
    """The log file the overlay program has open right now, found through its file descriptors - so it does not matter which
    folder it writes to (its own default is the home folder, nothing is configured for it). Names in `exclude` (logs that existed
    before the start) and `_summary.csv` files are skipped."""
    skip = set(exclude)
    try:
        entries = [e for e in proc.iterdir() if e.name.isdigit()]
    except OSError:
        return None
    for entry in entries:
        try:
            if (entry / "comm").read_text().strip() != PROGRAM:
                continue
            fds = list((entry / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = Path(os.readlink(fd))
            except OSError:
                continue
            if target.suffix == ".csv" and not target.stem.endswith("_summary") and target.name not in skip:
                return target
    return None


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


def set_display(show: bool, run: Callable = subprocess.run, which: Callable = shutil.which) -> bool:
    """Hide the overlay (show=False) or give it back to what the player chose in Steam (show=True).

    Showing is done by re-reading Steam's own overlay file, not by `no_display false`: that would also switch the overlay on
    for a player who chose "off". True when mangohudctl accepted the command."""
    exe = which(CONTROL)
    if not exe:
        return False
    args = ["set", "reload_config", "true"] if show else ["set", "no_display", "true"]
    try:
        done = run([exe, *args], capture_output=True, timeout=5, env=host_env())
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
