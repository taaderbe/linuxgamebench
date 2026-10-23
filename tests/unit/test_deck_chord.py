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


# ----- the names on the Deck's buttons: L1 / R1 (the ids LB / RB stay in the config file) -------------------------------------

def test_both_spellings_of_the_shoulder_buttons_are_the_same_chord():
    from linux_game_benchmark.deck.chord import chord_label, button_label
    assert parse_chord("L1+R1>VIEW") == parse_chord("LB+RB>VIEW") == parse_chord("lb+rb>view")
    assert format_chord(parse_chord("L1+R1>VIEW")) == "LB+RB>VIEW", "what is stored stays the id every old setting uses"
    assert button_label("LB") == "L1" and button_label("rb") == "R1" and button_label("VIEW") == "VIEW" and button_label("L4") == "L4"
    assert chord_label("LB+RB>VIEW") == "L1 + R1 > VIEW" and chord_label("L1+R1>VIEW") == "L1 + R1 > VIEW"



def test_the_chord_command_speaks_l1_and_r1_and_stores_the_id(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from linux_game_benchmark.deck import cli as deck_cli
    from linux_game_benchmark.deck import config as deck_config
    monkeypatch.setattr(deck_config, "config_path", lambda: tmp_path / "deck.json")
    runner = CliRunner()
    shown = " ".join(runner.invoke(deck_cli.deck_app, ["chord"]).output.split())
    assert "L1 + R1 > VIEW" in shown and "hold L1 + R1, then press VIEW (the small button left of the screen" in shown
    assert "LB" not in shown and "RB" not in shown
    result = runner.invoke(deck_cli.deck_app, ["chord", "--set", "l1+r1>menu"])
    assert result.exit_code == 0 and "L1 + R1 > MENU" in " ".join(result.output.split())
    assert deck_config.DeckConfig.load(tmp_path / "deck.json").chord == "LB+RB>MENU", "the config keeps the ids"
    assert runner.invoke(deck_cli.deck_app, ["chord", "--set", "L1+R1>L1"]).exit_code == 1, "three different buttons are still required"


def test_the_setup_ends_with_the_buttons_as_the_deck_prints_them():
    from linux_game_benchmark.deck import cli as deck_cli
    from linux_game_benchmark.deck import config as deck_config
    text = deck_cli.record_with_text(deck_config.DeckConfig())
    assert "hold L1 + R1, then press VIEW (the small button left of the screen with two overlapping squares)" in text
    assert "LB" not in text and "RB" not in text
    assert "records 60 s, stops by itself and uploads" in text


# ----- the Deck's own controller (hidraw): the chord works whatever layout a game uses ---------------------------------------
# Dyson Sphere Program's community layout makes L1 = Shift, R1 = middle mouse, VIEW = Caps Lock: nothing reached the virtual
# gamepad, the chord was never seen (Thomas, 2026-10-23).

def deck_report(*bits, kind=0x09):
    """A 64-byte state report of the Deck's controller with the given (byte, bit) set."""
    data = bytearray(64)
    data[0], data[2], data[3] = 0x01, kind, 0x40
    for byte, bit in bits:
        data[byte] |= 1 << bit
    return bytes(data)


L1_BIT, R1_BIT, VIEW_BIT, A_BIT = (8, 3), (8, 2), (9, 4), (8, 7)


def test_the_deck_state_report_gives_the_physical_buttons():
    from linux_game_benchmark.deck.chord import deck_buttons
    assert deck_buttons(deck_report()) == frozenset()
    assert deck_buttons(deck_report(L1_BIT, R1_BIT, VIEW_BIT)) == {LB, RB, VIEW}
    assert deck_buttons(deck_report(A_BIT, (9, 6), (13, 1), (10, 0))) == {A, BUTTONS["MENU"], BUTTONS["L4"], BUTTONS["R5"]}
    assert deck_buttons(deck_report((8, 0), (8, 1), (9, 5))) == frozenset(), "triggers and the Steam button are no chord buttons"
    assert deck_buttons(deck_report(L1_BIT, kind=0x01)) is None, "other reports are not button states"
    assert deck_buttons(b"\x01\x00\x09") is None


def fake_hidraw(tmp_path, ids):
    """sysfs with hidraw devices of the given HID_IDs; returns (sys_root, dev_root)."""
    sys_root, dev_root = tmp_path / "sys", tmp_path / "dev"
    dev_root.mkdir()
    for i, hid_id in enumerate(ids):
        (sys_root / f"hidraw{i}" / "device").mkdir(parents=True)
        (sys_root / f"hidraw{i}" / "device" / "uevent").write_text(f"DRIVER=hid-steam\nHID_ID={hid_id}\nHID_NAME=x\n")
    return sys_root, dev_root


def test_only_the_decks_controller_is_read_from_hidraw(tmp_path):
    from linux_game_benchmark.deck.chord import find_deck_hidraw
    sys_root, dev_root = fake_hidraw(tmp_path, ["0003:000028DE:00001205", "0018:00002808:00001015", "0003:000028de:00001205"])
    assert find_deck_hidraw(str(sys_root), str(dev_root)) == [f"{dev_root}/hidraw0", f"{dev_root}/hidraw2"]
    assert find_deck_hidraw(str(tmp_path / "missing")) == []


def test_the_chord_on_the_physical_buttons_triggers_without_any_virtual_gamepad(tmp_path):
    import os
    from linux_game_benchmark.deck.chord import GamepadReader
    sys_root, dev_root = fake_hidraw(tmp_path, ["0003:000028DE:00001205"])
    pipe = dev_root / "hidraw0"
    os.mkfifo(pipe)
    devices = tmp_path / "devices"
    devices.write_text("")                                  # a keyboard / mouse layout: no gamepad at all
    reader = GamepadReader(str(devices), str(sys_root), str(dev_root))
    try:
        assert reader.rescan() == [str(pipe)]
        writer = os.open(pipe, os.O_WRONLY)
        try:
            for _ in range(5):
                os.write(writer, deck_report())             # ~250 a second, nothing pressed
            assert reader.read(0.2) == [], "unchanged reports are no events (and the wait lasts the timeout)"
            tracker = ChordTracker(parse_chord(DEFAULT_CHORD))
            os.write(writer, deck_report(L1_BIT))
            os.write(writer, deck_report(L1_BIT, R1_BIT))
            os.write(writer, deck_report(L1_BIT, R1_BIT))
            os.write(writer, deck_report(L1_BIT, R1_BIT, VIEW_BIT))
            events = reader.read(1.0)
            assert events == [(LB, 1), (RB, 1), (VIEW, 1)]
            assert [tracker.feed(code, value, 10.0) for code, value in events] == [False, False, True]
            os.write(writer, deck_report())
            assert reader.read(1.0) == [(LB, 0), (RB, 0), (VIEW, 0)]
        finally:
            os.close(writer)
    finally:
        reader.close()


def test_the_same_press_from_the_virtual_pad_and_the_controller_triggers_once():
    tracker = ChordTracker(parse_chord(DEFAULT_CHORD))
    feed = [(LB, 1), (LB, 1), (RB, 1), (RB, 1), (VIEW, 1), (VIEW, 1), (VIEW, 0), (VIEW, 0)]   # each from both sources
    assert sum(tracker.feed(code, value, 5.0) for code, value in feed) == 1
    learner = ChordLearner()
    found = [learner.feed(code, value) for code, value in feed]
    assert [f for f in found if f] == [Chord(hold=(LB, RB), press=VIEW)]
