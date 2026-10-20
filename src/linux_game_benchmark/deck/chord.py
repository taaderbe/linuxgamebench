"""Controller chord: hold two buttons, press a third one.

Pure logic (ChordTracker / ChordLearner / gamepad discovery) plus a small reader that
parses raw Linux input events from /dev/input/event* - no third-party packages, so it
works with the Python that SteamOS ships. The Steam Input layer decides which buttons
show up on the virtual gamepad, which is why the chord can be changed and even learned.
"""

from __future__ import annotations

import errno
import os
import select
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

EV_KEY = 1

# Button names as used on the Steam Deck (Xbox layout) -> linux/input-event-codes.h
BUTTONS: dict[str, int] = {
    "A": 0x130, "B": 0x131, "X": 0x133, "Y": 0x134,
    "LB": 0x136, "RB": 0x137,
    "VIEW": 0x13A, "MENU": 0x13B,
    "L3": 0x13D, "R3": 0x13E,
    "L4": 0x2C0, "R4": 0x2C1, "L5": 0x2C2, "R5": 0x2C3,   # BTN_TRIGGER_HAPPY1-4 (when exposed)
}
_NAMES = {code: name for name, code in BUTTONS.items()}
BTN_GAMEPAD = 0x130


@dataclass(frozen=True)
class Chord:
    hold: tuple[int, int]
    press: int

    def __str__(self) -> str:
        return format_chord(self)


def button_name(code: int) -> str:
    return _NAMES.get(code, f"0x{code:x}")


def button_code(name: str) -> int:
    key = name.strip().upper()
    if key in BUTTONS:
        return BUTTONS[key]
    try:
        return int(key, 16) if key.startswith("0X") else int(key)
    except ValueError:
        raise ValueError(f"unknown button '{name}' (known: {', '.join(BUTTONS)})") from None


DEFAULT_CHORD = "LB+RB>VIEW"


def parse_chord(text: str) -> Chord:
    """'LB+RB>VIEW' = hold LB and RB, press VIEW."""
    held, sep, pressed = text.partition(">")
    names = [part for part in held.split("+") if part.strip()]
    if not sep or len(names) != 2 or not pressed.strip():
        raise ValueError("chord format is HOLD1+HOLD2>PRESS, e.g. LB+RB>VIEW")
    hold = (button_code(names[0]), button_code(names[1]))
    press = button_code(pressed)
    if len({hold[0], hold[1], press}) != 3:
        raise ValueError("the three buttons of a chord must be different")
    return Chord(hold=hold, press=press)


def format_chord(chord: Chord) -> str:
    return f"{button_name(chord.hold[0])}+{button_name(chord.hold[1])}>{button_name(chord.press)}"


class ChordTracker:
    """Feed key events, get True when the press button goes down while both hold buttons are held."""

    def __init__(self, chord: Chord, cooldown: float = 1.0):
        self.chord = chord
        self.cooldown = cooldown
        self._held: set[int] = set()
        self._last_trigger = -1e9

    def feed(self, code: int, value: int, now: float) -> bool:
        if value == 0:
            self._held.discard(code)
            return False
        if value == 2:                      # auto-repeat
            return False
        fire = (
            code == self.chord.press
            and code not in self._held            # a real press edge, not a repeated "down"
            and all(btn in self._held for btn in self.chord.hold)
            and now - self._last_trigger >= self.cooldown
        )
        self._held.add(code)
        if fire:
            self._last_trigger = now
        return fire

    def reset(self) -> None:
        self._held.clear()


class ChordLearner:
    """'Hold two buttons, press a third' once and the chord is known."""

    def __init__(self) -> None:
        self._held: list[int] = []

    def feed(self, code: int, value: int) -> Optional[Chord]:
        if value == 0:
            if code in self._held:
                self._held.remove(code)
            return None
        if value == 2 or code in self._held:
            return None
        if len(self._held) == 2:
            chord = Chord(hold=(self._held[0], self._held[1]), press=code)
            self._held.append(code)
            return chord
        self._held.append(code)
        return None


# ----- gamepad discovery -------------------------------------------------------

def _has_key(bitmap: str, code: int) -> bool:
    """Test a bit of the 'B: KEY=' line of /proc/bus/input/devices (64-bit words, highest first)."""
    words = bitmap.split()
    index = len(words) - 1 - code // 64
    if index < 0:
        return False
    try:
        return bool((int(words[index], 16) >> (code % 64)) & 1)
    except ValueError:
        return False


def find_gamepads(devices_text: str) -> list[tuple[str, str]]:
    """Parse /proc/bus/input/devices: [(name, '/dev/input/eventN')] of everything with a gamepad button."""
    found: list[tuple[str, str]] = []
    for block in devices_text.strip().split("\n\n"):
        name = event = key = ""
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("H: Handlers="):
                event = next((h for h in line.split("=", 1)[1].split() if h.startswith("event")), "")
            elif line.startswith("B: KEY="):
                key = line.split("=", 1)[1]
        if event and key and _has_key(key, BTN_GAMEPAD):
            found.append((name, f"/dev/input/{event}"))
    return found


_EVENT = struct.Struct("llHHi")     # struct input_event on 64-bit Linux (24 bytes)


def parse_events(data: bytes) -> list[tuple[int, int]]:
    """Raw input_event bytes -> [(key code, value)] (only EV_KEY)."""
    events = []
    for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
        _, _, etype, code, value = _EVENT.unpack_from(data, offset)
        if etype == EV_KEY:
            events.append((code, value))
    return events


class GamepadReader:
    """Reads key events of all gamepads; devices that come and go (Steam re-creates its virtual pad) are re-scanned."""

    def __init__(self, devices_file: str = "/proc/bus/input/devices"):
        self._devices_file = devices_file
        self._fds: dict[str, int] = {}
        self.denied: list[str] = []         # devices we are not allowed to read

    @property
    def active(self) -> bool:
        return bool(self._fds)

    def rescan(self) -> list[str]:
        try:
            text = Path(self._devices_file).read_text(errors="replace")
        except OSError:
            return list(self._fds)
        wanted = {path for _, path in find_gamepads(text)}
        for path in list(self._fds):
            if path not in wanted:
                self._close(path)
        self.denied = []
        for path in wanted - set(self._fds):
            try:
                self._fds[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                self.denied.append(path)
            except OSError:
                pass
        return list(self._fds)

    def _close(self, path: str) -> None:
        fd = self._fds.pop(path, None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def read(self, timeout: float) -> list[tuple[int, int]]:
        if not self._fds:
            return []
        ready, _, _ = select.select(list(self._fds.values()), [], [], timeout)
        events: list[tuple[int, int]] = []
        for path, fd in list(self._fds.items()):
            if fd not in ready:
                continue
            try:
                events.extend(parse_events(os.read(fd, _EVENT.size * 64)))
            except BlockingIOError:
                continue
            except OSError as exc:
                if exc.errno in (errno.ENODEV, errno.EBADF, errno.EIO):
                    self._close(path)
        return events

    def close(self) -> None:
        for path in list(self._fds):
            self._close(path)
