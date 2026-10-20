"""The whole Deck flow without a Deck: chord -> cut from the flight-recorder log -> queue -> upload / cancel / retry."""

from datetime import datetime
from pathlib import Path

import pytest

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import segments, upload
from linux_game_benchmark.deck.chord import BUTTONS
from linux_game_benchmark.deck.detect import DeckInfo
from linux_game_benchmark.deck.game import GameInfo
from linux_game_benchmark.deck.queue import Queue
from linux_game_benchmark.deck.service import DeckService

LB, RB, VIEW = BUTTONS["LB"], BUTTONS["RB"], BUTTONS["VIEW"]
T0 = datetime(2026, 10, 20, 18, 0, 0).timestamp()
HEADER = ("os,cpu,gpu,ram,kernel,driver,cpuscheduler\n"
          "SteamOS,AMD Custom APU 0405,AMD Custom GPU 0405,15000000,6.5.0,Mesa 25.1,none\n"
          "fps,frametime,cpu_load,gpu_load,resolution,elapsed\n")
SYSTEM = {"os": {"name": "SteamOS", "kernel": "6.5.0"}, "gpu": {"driver_version": "Mesa 25.1"},
          "ram": {"total_gb": 15}, "cpu": {"model": "AMD Custom APU 0405"}}
DECK = DeckInfo(is_deck=True, model="LCD", steamos_version="3.7", game_mode=True)


def write_log(directory: Path, seconds=300, fps=60, name="eldenring.exe_2026-10-20_18-00-00.csv") -> Path:
    step = 1_000_000_000 // fps
    rows = "".join(f"{fps},{1000 / fps:.3f},40.0,90.0,1280x800,{i * step}\n" for i in range(seconds * fps))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(HEADER + rows)
    return path


class Rig:
    def __init__(self, tmp_path, **config):
        self.log_dir = tmp_path / "logs"
        self.log = write_log(self.log_dir)
        self.cfg = deck_config.DeckConfig(**config)
        self.sounds, self.said, self.sent = [], [], []
        self.send_result = (True, "https://linuxgamebench.com/benchmark/1", "")
        self.game = GameInfo(1245620, "Elden Ring")
        self.newest = self.log
        self.queue = Queue(tmp_path / "queue")
        self.service = DeckService(
            self.cfg, DECK, queue=self.queue, log_dir=self.log_dir, work_dir=tmp_path / "work",
            play=self.sounds.append, say=self.said.append,
            newest_log=lambda d: self.newest, identify=lambda p: self.game,
            wait_flushed=lambda *a, **k: True,
            prepare=lambda seg, game, deck: upload.prepare(seg, game, deck, system_info=SYSTEM),
            send=self._send,
        )

    def _send(self, kwargs):
        self.sent.append(kwargs)
        return self.send_result

    def chord(self, at):
        """Hold LB+RB, press VIEW at time `at` (and release)."""
        s = self.service
        for code in (LB, RB):
            s.on_key(code, 1, at - 0.2)
        s.on_key(VIEW, 1, at)
        for code in (VIEW, RB, LB):
            s.on_key(code, 0, at + 0.1)

    def statuses(self):
        return [i.status for i in self.queue.items()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_record_then_upload_after_the_cancel_window(rig):
    rig.chord(T0 + 20)
    assert rig.sounds == ["start"] and rig.service.session.phase.value == "recording"
    rig.chord(T0 + 80)
    assert rig.sounds == ["start", "stop"] and rig.statuses() == ["pending"]
    rig.service.tick(T0 + 85)
    assert rig.sent == []                                   # still inside the cancel window
    rig.service.tick(T0 + 91)
    assert len(rig.sent) == 1 and rig.statuses() == ["uploaded"] and rig.sounds[-1] == "done"
    payload = rig.sent[0]
    assert payload["steam_app_id"] == 1245620 and payload["game_name"] == "Elden Ring"
    assert payload["resolution"] == "1280x800"
    assert payload["system_info"]["device_class"] == "steam_deck_lcd"
    assert payload["system_info"]["gpu"] == "Steam Deck LCD"
    assert payload["metrics"]["fps_avg"] == pytest.approx(60, abs=1)
    assert payload["metrics"]["duration_seconds"] == pytest.approx(60, abs=1)
    assert 3590 <= len(payload["frametimes"]) <= 3610
    item = rig.queue.items()[0]
    assert item.meta["url"].endswith("/benchmark/1") and item.meta["fps_avg"] == pytest.approx(60, abs=1)


def test_the_chord_inside_the_window_cancels_the_upload(rig):
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.chord(T0 + 84)
    assert rig.statuses() == ["cancelled"] and rig.sounds[-1] == "cancel"
    rig.service.tick(T0 + 200)
    assert rig.sent == []


def test_a_second_chord_too_early_keeps_recording(rig):
    rig.chord(T0 + 20)
    rig.chord(T0 + 25)
    assert rig.sounds == ["start", "error"] and rig.service.session.phase.value == "recording"
    rig.chord(T0 + 70)
    assert rig.statuses() == ["pending"]


def test_without_a_running_game_nothing_starts(rig):
    rig.newest = None
    rig.chord(T0 + 20)
    assert rig.sounds == ["error"] and rig.service.session.phase.value == "idle"
    rig.newest = rig.log
    rig.chord(T0 + 30)                                      # works again as soon as a game runs
    assert rig.service.session.phase.value == "recording"


def test_a_game_restart_during_the_recording_discards_it(rig):
    rig.chord(T0 + 20)
    rig.newest = rig.log.with_name("eldenring.exe_2026-10-20_18-02-00.csv")
    rig.chord(T0 + 80)
    assert rig.statuses() == [] and rig.sounds[-1] == "error" and rig.service.session.phase.value == "idle"


def test_offline_upload_is_retried_with_backoff(rig):
    rig.send_result = (False, "Connection to https://x failed. Server unreachable.", "")
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    item = rig.queue.items()[0]
    assert item.status == "pending" and item.meta["attempts"] == 1 and item.meta["next_try"] == pytest.approx(T0 + 91 + 300, abs=5)
    rig.service.tick(T0 + 200)
    assert len(rig.sent) == 1                               # not yet due
    rig.send_result = (True, "https://linuxgamebench.com/benchmark/2", "")
    rig.service.tick(T0 + 91 + 301 + 30)
    assert rig.statuses() == ["uploaded"] and len(rig.sent) == 2


def test_a_server_rejection_is_not_retried(rig):
    rig.send_result = (False, "Upload failed (422): bad frametimes", "")
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    item = rig.queue.items()[0]
    assert item.status == "failed" and "422" in item.meta["error"]
    rig.service.tick(T0 + 5000)
    assert len(rig.sent) == 1


def test_unknown_game_is_kept_but_not_uploaded(rig):
    rig.game = None
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    assert rig.sent == [] and rig.statuses() == ["failed"]
    assert "identified" in rig.queue.items()[0].meta["error"]


def test_without_auto_upload_the_recording_stays_local(tmp_path):
    rig = Rig(tmp_path, auto_upload=False)
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 500)
    assert rig.statuses() == ["local"] and rig.sent == []
    assert rig.service.upload_item(rig.queue.items()[0]) is True          # `lgb deck upload` does this by hand
    assert rig.statuses() == ["uploaded"]


def test_a_segment_the_validator_rejects_is_not_sent(rig):
    rig.cfg.min_seconds = 5
    rig.service.session.min_seconds = 5
    rig.chord(T0 + 20)
    rig.chord(T0 + 27)                                      # 7 s: above the chord minimum, below the 30 s server rule
    rig.service.tick(T0 + 40)
    assert rig.sent == [] and rig.statuses() == ["failed"]


def test_the_service_survives_an_internal_error(rig):
    rig.service._identify = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
    rig.chord(T0 + 20)                                      # must not raise
    assert rig.sounds[-1] == "error"
