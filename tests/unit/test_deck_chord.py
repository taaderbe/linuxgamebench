"""Controller chord: parsing, hold-two-press-one detection, learning, gamepad discovery, raw events."""

import struct

import pytest

from linux_game_benchmark.deck.chord import (
    BUTTONS, Chord, ChordLearner, ChordTracker, DEFAULT_CHORD, find_gamepads, format_chord,
    parse_chord, parse_events,
)

LB, RB, VIEW, A = BUTTONS["LB"], BUTTONS["RB"], BUTTONS["VIEW"], BUTTONS["A"]


def test_parse_and_format_roundtrip():
    chord = parse_chord(DEFAULT_CHORD)
    assert chord == Chord(hold=(LB, RB), press=VIEW)
    assert format_chord(chord) == "LB+RB>VIEW"
    assert parse_chord(" lb + rb > view ".replace(" ", "")).press == VIEW


@pytest.mark.parametrize("bad", ["", "LB>VIEW", "LB+RB", "LB+RB+A>VIEW", "LB+LB>VIEW", "LB+RB>LB", "LB+RB>nope"])
def test_bad_chords_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_chord(bad)


def test_unknown_codes_survive_as_hex():
    chord = parse_chord("0x2c0+0x2c1>A")
    assert format_chord(chord) == "L4+R4>A"
    assert format_chord(Chord(hold=(0x999, LB), press=A)) == "0x999+LB>A"


def test_trigger_needs_both_holds_then_the_press():
    t = ChordTracker(parse_chord("LB+RB>VIEW"))
    assert not t.feed(VIEW, 1, 0.0)            # press alone
    t.feed(VIEW, 0, 0.1)
    t.feed(LB, 1, 1.0)
    assert not t.feed(VIEW, 1, 1.1)            # only one hold
    t.feed(VIEW, 0, 1.2)
    t.feed(RB, 1, 2.0)
    assert t.feed(VIEW, 1, 2.1)                # both holds + press
    assert not t.feed(VIEW, 2, 2.2)            # auto-repeat is ignored


def test_press_before_the_holds_does_not_count_and_release_resets():
    t = ChordTracker(parse_chord("LB+RB>VIEW"))
    t.feed(VIEW, 1, 0.0)
    t.feed(LB, 1, 0.1)
    t.feed(RB, 1, 0.2)
    assert not t.feed(VIEW, 1, 0.3)            # VIEW is already down: no new press edge... but repeat value 1 again
    t.feed(RB, 0, 0.4)
    t.feed(VIEW, 0, 0.5)
    assert not t.feed(VIEW, 1, 0.6)            # RB was released


def test_cooldown_prevents_double_triggers():
    t = ChordTracker(parse_chord("LB+RB>VIEW"), cooldown=1.0)
    t.feed(LB, 1, 0.0)
    t.feed(RB, 1, 0.0)
    assert t.feed(VIEW, 1, 1.0)
    t.feed(VIEW, 0, 1.1)
    assert not t.feed(VIEW, 1, 1.5)            # within the cooldown
    t.feed(VIEW, 0, 1.6)
    assert t.feed(VIEW, 1, 2.2)


def test_learner_reports_the_chord_after_two_holds_and_a_press():
    learner = ChordLearner()
    assert learner.feed(BUTTONS["R4"], 1) is None
    assert learner.feed(BUTTONS["L4"], 1) is None
    chord = learner.feed(BUTTONS["Y"], 1)
    assert chord == Chord(hold=(BUTTONS["R4"], BUTTONS["L4"]), press=BUTTONS["Y"])
    assert format_chord(chord) == "R4+L4>Y"


def test_learner_ignores_repeats_and_releases():
    learner = ChordLearner()
    learner.feed(LB, 1)
    assert learner.feed(LB, 2) is None
    learner.feed(LB, 0)
    learner.feed(RB, 1)
    assert learner.feed(A, 1) is None          # only one button was held when A went down


DEVICES = """\
I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event3 leds
B: PROP=0
B: EV=120013
B: KEY=402000000 3803078f800d001 feffffdfffefffff fffffffffffffffe

I: Bus=0003 Vendor=045e Product=028e Version=0110
N: Name="Microsoft X-Box 360 pad"
H: Handlers=event5 js0
B: PROP=0
B: EV=20000b
B: KEY=7cdb000000000000 0 0 0 0
B: ABS=3003f

I: Bus=0003 Vendor=28de Product=1205 Version=0111
N: Name="Valve Software Steam Deck Controller"
H: Handlers=mouse2 event7
B: PROP=0
B: EV=17
B: KEY=1f0000 0 0 0 0
"""


def test_only_devices_with_gamepad_buttons_are_found():
    assert find_gamepads(DEVICES) == [("Microsoft X-Box 360 pad", "/dev/input/event5")]


def test_empty_or_garbage_device_list():
    assert find_gamepads("") == []
    assert find_gamepads("N: Name=\"x\"\nB: KEY=zz\nH: Handlers=event1") == []


def test_raw_events_keep_only_key_events():
    def ev(etype, code, value):
        return struct.pack("llHHi", 1, 2, etype, code, value)
    data = ev(0, 0, 0) + ev(1, VIEW, 1) + ev(3, 0, 5) + ev(1, VIEW, 0)
    assert parse_events(data) == [(VIEW, 1), (VIEW, 0)]
    assert parse_events(data[:-5]) == [(VIEW, 1)]       # truncated last event is dropped
