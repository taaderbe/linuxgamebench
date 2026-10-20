"""What the desktop app's Steam Deck tab shows, read against a fake home folder."""

import json
import time

import pytest

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import overview
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.queue import Queue


@pytest.fixture()
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("LGB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(deck_setup, "home", lambda: tmp_path)
    monkeypatch.setattr(deck_setup, "service_state", lambda: "active")
    monkeypatch.setattr(overview, "detect_steam_deck", lambda: _Deck())
    monkeypatch.setattr(deck_config, "config_path", lambda: tmp_path / "deck.json")
    monkeypatch.setattr(overview.GamepadReader, "rescan", lambda self: ["/dev/input/event10"])
    return tmp_path


class _Deck:
    is_deck, model, steamos_version, game_mode = True, "LCD", "3.8.28", False


def test_a_fresh_deck_is_not_ready_and_says_so(home):
    state = overview.collect()
    assert state.is_deck and state.model == "LCD" and state.steamos == "3.8.28"
    assert state.configured is False and state.ready is False
    assert state.chord == "LB+RB>VIEW" and state.seconds == 60 and state.auto_upload is True
    assert state.controllers == ["/dev/input/event10"] and state.recordings == []


def test_ready_needs_the_config_the_environment_and_a_running_service(home):
    deck_setup.write_mangohud_conf()
    assert overview.collect().ready is False                      # environment file missing
    deck_setup.write_env_file()
    assert overview.collect().ready is True


def test_recorder_status_and_latest_recordings(home):
    data = deck_config.data_dir()
    data.mkdir(parents=True)
    (data / "status.json").write_text(json.dumps({"phase": "recording", "message": "stops by itself", "time": time.time() - 3}))
    queue = Queue(deck_config.queue_dir())
    segment = home / "segment.csv"
    for n in range(7):
        segment.write_text("fps\n60\n")                          # the queue takes the file along
        queue.add(segment, {"game_name": f"Game {n}", "seconds": 60, "status": "uploaded", "url": f"http://x/run/{n}", "created": 1_700_000_000 + n * 100})
    state = overview.collect()
    assert state.phase == "recording" and state.message == "stops by itself" and 2 <= state.recorder_age <= 10
    assert [r.game for r in state.recordings] == [f"Game {n}" for n in (6, 5, 4, 3, 2)]      # newest first, five at most
    assert state.recordings[0].status == "uploaded" and state.recordings[0].url == "http://x/run/6"


def test_site_url_drops_the_api_prefix(monkeypatch):
    monkeypatch.setenv("LGB_API_URL", "http://192.168.0.126:8000/api/v1")
    assert overview.site_url() == "http://192.168.0.126:8000"


def test_chord_in_words():
    assert overview.chord_words("LB+RB>VIEW") == "hold LB + RB, then press VIEW"
    assert overview.chord_words("L4+R4>A") == "hold L4 + R4, then press A"
