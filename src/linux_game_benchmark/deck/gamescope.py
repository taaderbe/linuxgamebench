"""What Gamescope (the Deck's Game Mode compositor) knows about the game that is running: the size it renders at, the
frame limit and the scaling Steam applied.

MangoHud's log has no resolution column, so the size has to come from the screen server the game draws on:
Gamescope runs one Xwayland per role - the "control" one (Steam itself, root properties such as GAMESCOPE_FOCUSED_WINDOW)
and the one the games live on (their DISPLAY). The focused window's size on the game display is the resolution the game
renders at; Gamescope scales it to the panel afterwards.

Everything here asks the standard X tools (xprop, xwininfo) and gives back only what was actually read: a value that
cannot be read is missing, never guessed. Outside Game Mode, without those tools, or when Steam shows something else
than the game (menu, overlay), the answer is an empty dict.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Optional

X_SOCKET_DIR = Path("/tmp/.X11-unix")
TOOL_TIMEOUT = 1.5

CONTROL_PROPS = ("GAMESCOPE_FOCUSED_APP", "GAMESCOPE_FOCUSED_WINDOW", "GAMESCOPE_FPS_LIMIT",
                 "GAMESCOPE_NEW_SCALING_FILTER", "GAMESCOPE_NEW_SCALING_SCALER", "GAMESCOPE_FSR_SHARPNESS")
# the order of `gamescope --help`: "-F, --filter (linear, nearest, fsr, nis, pixel)", "-S, --scaler (auto, integer, fit, fill, stretch)"
FILTERS = ("linear", "nearest", "fsr", "nis", "pixel")
SCALERS = ("auto", "integer", "fit", "fill", "stretch")

MIN_SIDE, MAX_SIDE = 160, 16384          # anything outside is not a game window
_LEAK = ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH")

Runner = Callable[[list], str]


def host_env() -> dict:
    """The environment for host tools: the AppImage's own library paths must not leak into /usr/bin/xprop."""
    return {k: v for k, v in os.environ.items() if k not in _LEAK}


def run_tool(args: list) -> str:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=TOOL_TIMEOUT, env=host_env())
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


# ----- parsing (pure) ---------------------------------------------------------------------------------------------------

_PROP = re.compile(r"^(?P<name>[A-Z0-9_]+)\((?:CARDINAL|INTEGER)\)\s*=\s*(?P<value>-?\d+)")


def parse_props(text: str) -> dict:
    """`xprop -root` output -> {NAME: first number}. Lines like "NAME:  not defined." and non-numbers are skipped."""
    out = {}
    for line in (text or "").splitlines():
        match = _PROP.match(line.strip())
        if match:
            out[match.group("name")] = int(match.group("value"))
    return out


def parse_window(text: str) -> Optional[tuple[int, int]]:
    """`xwininfo -id` output -> (width, height) of a window that is on screen, else None."""
    width = re.search(r"^\s*Width:\s*(\d+)", text or "", re.M)
    height = re.search(r"^\s*Height:\s*(\d+)", text or "", re.M)
    if not width or not height or "IsViewable" not in (text or ""):
        return None
    return int(width.group(1)), int(height.group(1))


_TREE_CHILD = re.compile(r'^ {5}(0x[0-9a-f]+) (?:"[^"]*"|\(has no name\)): \((?:"([^"]*)")?(?: "([^"]*)")?\)\s+(\d+)x(\d+)\+', re.I)


def parse_tree(text: str) -> list[tuple[str, str, int, int]]:
    """`xwininfo -root -tree` output -> [(window id, class, width, height)] of the top-level windows."""
    out = []
    for line in (text or "").splitlines():
        match = _TREE_CHILD.match(line)
        if match:
            out.append((match.group(1), match.group(3) or match.group(2) or "", int(match.group(4)), int(match.group(5))))
    return out


def plausible(size: Optional[tuple[int, int]]) -> bool:
    return bool(size) and all(MIN_SIDE <= side <= MAX_SIDE for side in size)


def settings_from(props: dict) -> dict:
    """The per-game settings Steam writes into Gamescope's root properties (frame limit, scaling filter, scaling mode)."""
    out = {}
    if props.get("GAMESCOPE_FPS_LIMIT") is not None and 0 <= props["GAMESCOPE_FPS_LIMIT"] <= 1000:
        out["fps_limit"] = props["GAMESCOPE_FPS_LIMIT"]                       # 0 = no limit
    index = props.get("GAMESCOPE_NEW_SCALING_FILTER")
    if index is not None and 0 <= index < len(FILTERS):
        out["scaling_filter"] = FILTERS[index]
    index = props.get("GAMESCOPE_NEW_SCALING_SCALER")
    if index is not None and 0 <= index < len(SCALERS):
        out["scaling_mode"] = SCALERS[index]
    sharp = props.get("GAMESCOPE_FSR_SHARPNESS")
    if out.get("scaling_filter") == "fsr" and sharp is not None and 0 <= sharp <= 20:
        out["fsr_sharpness"] = sharp                                          # 0 = sharpest, 20 = softest
    return out


# ----- reading ----------------------------------------------------------------------------------------------------------

def x_displays() -> list[str]:
    try:
        names = sorted(p.name for p in X_SOCKET_DIR.iterdir() if re.fullmatch(r"X\d+", p.name))
    except OSError:
        return []
    return [":" + n[1:] for n in names]


def game_display(pid: Optional[int], root: str = "/") -> Optional[str]:
    """The DISPLAY the game process was started with."""
    if not pid:
        return None
    try:
        data = Path(root, "proc", str(pid), "environ").read_bytes()
    except OSError:
        return None
    for item in data.split(b"\0"):
        if item.startswith(b"DISPLAY="):
            value = item[8:].decode("utf-8", "replace")
            return value if re.fullmatch(r":\d+(\.\d+)?", value) else None
    return None


def probe(pid: Optional[int], app_id: Optional[int], run: Runner = run_tool,
          displays: Callable[[], Iterable[str]] = x_displays, display_of: Callable[[Optional[int]], Optional[str]] = game_display) -> dict:
    """One look at the running game. Keys (only those that were read): render_mode "1280x720", fps_limit, scaling_filter,
    scaling_mode, fsr_sharpness."""
    result: dict = {}
    on = display_of(pid)

    control: dict = {}
    for display in displays():
        props = parse_props(run(["xprop", "-display", display, "-root", *CONTROL_PROPS]))
        if "GAMESCOPE_FOCUSED_WINDOW" in props or "GAMESCOPE_FOCUSED_APP" in props:
            control = props
            break

    size = None
    if control:
        focused_game = control.get("GAMESCOPE_FOCUSED_APP")
        if app_id and focused_game not in (None, app_id):
            return {}                                       # Steam shows something else (menu, another app): not our game
        result.update(settings_from(control))
        window = control.get("GAMESCOPE_FOCUSED_WINDOW")
        if window and on:
            size = parse_window(run(["xwininfo", "-display", on, "-id", hex(window)]))

    if not plausible(size) and on and app_id:
        # no Game Mode focus information: the largest top-level window of the game's own class
        wanted = f"steam_app_{app_id}"
        windows = [(w, h) for _, cls, w, h in parse_tree(run(["xwininfo", "-display", on, "-root", "-tree"])) if cls == wanted]
        size = max(windows, key=lambda s: s[0] * s[1], default=None)

    if plausible(size):
        result["render_mode"] = f"{size[0]}x{size[1]}"
    return result


def condense(samples: Iterable[dict]) -> dict:
    """Several looks during one recording -> one answer: the resolution that was seen most often (a menu or a loading
    screen may show another for a moment), the settings as they were last seen."""
    samples = [s for s in samples if s]
    out: dict = {}
    modes = Counter(s["render_mode"] for s in samples if s.get("render_mode"))
    if modes:
        out["render_mode"] = modes.most_common(1)[0][0]
    for sample in samples:
        for key in ("fps_limit", "scaling_filter", "scaling_mode", "fsr_sharpness"):
            if key in sample:
                out[key] = sample[key]
    if out.get("scaling_filter") != "fsr":
        out.pop("fsr_sharpness", None)
    return out
