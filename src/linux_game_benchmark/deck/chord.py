"""Controller chord: hold two buttons, press a third one.

Pure logic (ChordTracker / ChordLearner / gamepad discovery) plus a small reader that
parses raw Linux input events from /dev/input/event* - no third-party packages, so it
works with the Python that SteamOS ships. The Steam Input layer decides which buttons
show up on the virtual gamepad, which is why the chord can be changed and even learned.

A game with a keyboard / mouse layout (Dyson Sphere Program's community layout: L1 = Shift,
R1 = middle mouse, VIEW = Caps Lock) sends nothing to the virtual gamepad, so the chord was
never seen (Thomas, 2026-10-23). The reader therefore also reads the Deck's own controller
from /dev/hidraw* (the state report Steam keeps enabled; readable for the logged-in user):
those are the physical buttons, whatever layout a game uses.
"""

from __future__ import annotations

import errno
import os
import select
import struct
import time
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

# What the Deck itself prints on the buttons: the shoulder buttons are L1 / R1 (the Xbox names LB / RB stay the ids in the config
# file, so every setting that exists keeps working; both spellings are accepted when typing a chord).
ALIASES = {"L1": "LB", "R1": "RB"}
LABELS = {"LB": "L1", "RB": "R1"}
VIEW_HINT = "the small button left of the screen with two overlapping squares"


def button_label(name: str) -> str:
    """The name of a button as a person finds it on the Deck ('LB' -> 'L1')."""
    name = name.strip()
    return LABELS.get(name.upper(), name)


def chord_label(chord: str) -> str:
    """'LB+RB>VIEW' -> 'L1 + R1 > VIEW' (for output; the config keeps the id)."""
    held, _, pressed = chord.partition(">")
    return f"{' + '.join(button_label(p) for p in held.split('+') if p.strip())} > {button_label(pressed)}"


@dataclass(frozen=True)
class Chord:
    hold: tuple[int, int]
    press: int

    def __str__(self) -> str:
        return format_chord(self)


def button_name(code: int) -> str:
    return _NAMES.get(code, f"0x{code:x}")


def button_code(name: str) -> int:
    key = ALIASES.get(name.strip().upper(), name.strip().upper())
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
        raise ValueError("chord format is HOLD1+HOLD2>PRESS, e.g. L1+R1>VIEW")
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


#: The Steam Deck's built-in controller (Valve 28DE:1205) on the USB HID bus.
DECK_HID_ID = "0003:000028DE:00001205"
DECK_STATE_REPORT = 0x09
# Bits of the state report (byte, bit) -> the key code the virtual gamepad uses for that button (layout as in the kernel's
# hid-steam.c: byte 8 = shoulders / face buttons, 9 = d-pad / VIEW / MENU / L5, 10 = R5 / L3, 11 = R3, 13 = L4 / R4).
# Triggers and the Steam button are left out (no chord buttons).
DECK_BUTTON_BITS: dict[tuple[int, int], int] = {
    (8, 2): BUTTONS["RB"], (8, 3): BUTTONS["LB"],
    (8, 4): BUTTONS["Y"], (8, 5): BUTTONS["B"], (8, 6): BUTTONS["X"], (8, 7): BUTTONS["A"],
    (9, 4): BUTTONS["VIEW"], (9, 6): BUTTONS["MENU"], (9, 7): BUTTONS["L5"],
    (10, 0): BUTTONS["R5"], (10, 6): BUTTONS["L3"], (11, 2): BUTTONS["R3"],
    (13, 1): BUTTONS["L4"], (13, 2): BUTTONS["R4"],
}
_HID_REPORT_SIZE = 64


def deck_buttons(report: bytes) -> Optional[frozenset[int]]:
    """Buttons held in one report of the Deck's controller; None for every other report."""
    if len(report) < 14 or report[0] != 0x01 or report[2] != DECK_STATE_REPORT:
        return None
    return frozenset(code for (byte, bit), code in DECK_BUTTON_BITS.items() if report[byte] >> bit & 1)


def find_deck_hidraw(sys_root: str = "/sys/class/hidraw", dev_root: str = "/dev") -> list[str]:
    """/dev/hidrawN of the Deck's controller (it has three; only one sends the state report)."""
    try:
        entries = sorted(Path(sys_root).iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        try:
            uevent = (entry / "device" / "uevent").read_text(errors="replace").upper()
        except OSError:
            continue
        if f"HID_ID={DECK_HID_ID}" in uevent:
            found.append(f"{dev_root}/{entry.name}")
    return found


class GamepadReader:
    """Reads key events of all gamepads; devices that come and go (Steam re-creates its virtual pad) are re-scanned.

    The Deck's own controller (hidraw) gives the physical buttons, the evdev pads give what Steam Input passes on. Both feed
    the same events - ChordTracker / ChordLearner ignore a second "down" of a button that is already held.
    """

    def __init__(self, devices_file: str = "/proc/bus/input/devices", hidraw_root: str = "/sys/class/hidraw",
                 dev_root: str = "/dev"):
        self._devices_file = devices_file
        self._hidraw_root, self._dev_root = hidraw_root, dev_root
        self._fds: dict[str, int] = {}
        self._hid: set[str] = set()                      # which of the open paths are the Deck's controller (hidraw)
        self._held: dict[str, frozenset[int]] = {}       # hidraw: buttons held in its last report
        self.denied: list[str] = []         # devices we are not allowed to read

    @property
    def active(self) -> bool:
        return bool(self._fds)

    def rescan(self) -> list[str]:
        try:
            text = Path(self._devices_file).read_text(errors="replace")
            wanted = {path for _, path in find_gamepads(text)}
        except OSError:
            wanted = {path for path in self._fds if path not in self._hid}
        hid = set(find_deck_hidraw(self._hidraw_root, self._dev_root))
        wanted |= hid
        for path in list(self._fds):
            if path not in wanted:
                self._close(path)
        self.denied = []
        for path in sorted(wanted - set(self._fds)):
            try:
                self._fds[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                self.denied.append(path)
                continue
            except OSError:
                continue
            if path in hid:
                self._hid.add(path)
        return list(self._fds)

    def _close(self, path: str) -> frozenset[int]:
        """Close a device; returns the buttons its last report held (hidraw)."""
        fd = self._fds.pop(path, None)
        self._hid.discard(path)
        held = self._held.pop(path, frozenset())
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return held

    def _read_hid(self, path: str, fd: int) -> list[tuple[int, int]]:
        """Drain the waiting reports and turn changes of the held buttons into key events."""
        events: list[tuple[int, int]] = []
        for _ in range(256):                             # ~1 s of reports at most, then the loop gets its turn again
            try:
                report = os.read(fd, _HID_REPORT_SIZE)
            except BlockingIOError:
                break
            if not report:
                break
            now = deck_buttons(report)
            if now is None:
                continue
            before = self._held.get(path, frozenset())
            events.extend((code, 0) for code in sorted(before - now))
            events.extend((code, 1) for code in sorted(now - before))
            self._held[path] = now
        return events

    def read(self, timeout: float) -> list[tuple[int, int]]:
        """Key events of all devices, waiting up to `timeout` for the first one. The Deck's controller reports ~250 times a
        second without any change; such a report does not end the wait (the service loop would spin otherwise)."""
        if not self._fds:
            return []
        end = time.monotonic() + timeout
        while True:
            left = max(0.0, end - time.monotonic())
            ready, _, _ = select.select(list(self._fds.values()), [], [], left)
            events: list[tuple[int, int]] = []
            for path, fd in list(self._fds.items()):
                if fd not in ready:
                    continue
                try:
                    if path in self._hid:
                        events.extend(self._read_hid(path, fd))
                    else:
                        events.extend(parse_events(os.read(fd, _EVENT.size * 64)))
                except BlockingIOError:
                    continue
                except OSError as exc:
                    if exc.errno in (errno.ENODEV, errno.EBADF, errno.EIO):
                        events.extend((code, 0) for code in sorted(self._close(path)))   # gone: nothing is held any more
            if events or not ready or time.monotonic() >= end or not self._fds:
                return events

    def close(self) -> None:
        for path in list(self._fds):
            self._close(path)
