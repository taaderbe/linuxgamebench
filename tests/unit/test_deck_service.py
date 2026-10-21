"""The whole Deck flow without a Deck: chord -> cut from the flight-recorder log -> queue -> upload / cancel / retry."""

from datetime import datetime
from pathlib import Path

import pytest

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import segments, telemetry, upload
from linux_game_benchmark.deck.chord import BUTTONS
from linux_game_benchmark.deck.detect import DeckInfo
from linux_game_benchmark.deck.game import GameInfo
from linux_game_benchmark.deck.queue import Queue
from linux_game_benchmark.deck.service import DeckService

from .test_deck_telemetry import build_deck

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
    def __init__(self, tmp_path, mangoapp=False, **config):
        self.log_dir = tmp_path / "logs"
        self.log = write_log(self.log_dir)
        # Game Mode: Steam's overlay program writes a log of its own (it sees every game, also OpenGL ones)
        self.mangoapp_dir = tmp_path / "mangoapp-logs" if mangoapp else None
        self.mangoapp_log = write_log(self.mangoapp_dir, name="mangoapp_2026-10-20_18-00-00.csv") if mangoapp else None
        self.newest_by_dir: dict = {}                 # per folder: what "the newest log" is (default: self.newest for every folder)
        self.running = {1245620}                      # app ids Steam is running right now
        self.restarts: list = []                      # times the overlay program was asked to start a new log
        self.cfg = deck_config.DeckConfig(**config)
        self.sounds, self.said, self.sent = [], [], []
        self.send_result = (True, "https://linuxgamebench.com/benchmark/1", "")
        self.display_seen: dict = {}                  # what "Gamescope" says about the game's window; nothing by default
        self.display_looks = 0
        self.game = GameInfo(1245620, "Elden Ring", pid=4242)
        self.sysroot = build_deck(tmp_path / "sysroot")
        self.newest = self.log
        self.queue = Queue(tmp_path / "queue")
        self.service = DeckService(
            self.cfg, DECK, queue=self.queue, log_dir=self.log_dir, work_dir=tmp_path / "work",
            play=self.sounds.append, say=self.said.append,
            newest_log=lambda d: self.newest_by_dir[d] if d in self.newest_by_dir else self.newest,
            identify=lambda p: self.game,
            mangoapp_log_dir=self.mangoapp_dir, running_games=lambda: set(self.running),
            restart_mangoapp=lambda: self.restarts.append(1),
            wait_flushed=lambda *a, **k: True,
            prepare=lambda seg, game, deck, device_state=None: upload.prepare(seg, game, deck, system_info=SYSTEM, device_state=device_state),
            send=self._send,
            sampler_factory=lambda: telemetry.Sampler(self.sysroot),
            read_env=lambda pid: {"PROTON_NO_ESYNC": "1", "HOME": "/home/deck"} if pid == 4242 else {},
            read_software=lambda game: {"compat": "proton", "proton": "Proton 9.0 (Beta)"} if game else {},
            read_display=self._read_display,
        )

    def _read_display(self, game):
        self.display_looks += 1
        return dict(self.display_seen) if game else {}

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
    """The behaviour with a cancel window (cancel_window > 0) and no time limit - the chord alone ends a recording."""
    return Rig(tmp_path, cancel_window=10.0, record_seconds=0)


@pytest.fixture
def auto(tmp_path):
    """The defaults: a recording ends by itself after 60 s and is uploaded right away."""
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


# ---- the defaults: 60 s, automatic end, immediate upload ----------------------------------------------------------------

def test_defaults_are_one_minute_and_no_waiting(auto):
    assert auto.cfg.record_seconds == 60 and auto.cfg.cancel_window == 0 and auto.cfg.auto_upload is True


def test_one_press_records_one_minute_and_uploads_by_itself(auto):
    auto.chord(T0 + 20)
    assert auto.sounds == ["start"] and auto.service.session.phase.value == "recording"
    auto.service.tick(T0 + 50)
    assert auto.sent == [] and auto.service.session.phase.value == "recording"
    auto.service.tick(T0 + 80.4)                           # the 60 s are over: finish, cut, upload - no second press
    assert auto.sounds == ["start", "stop", "done"] and auto.statuses() == ["uploaded"]
    assert len(auto.sent) == 1
    assert auto.sent[0]["metrics"]["duration_seconds"] == pytest.approx(60, abs=1)
    assert auto.service.session.phase.value == "idle"
    auto.service.tick(T0 + 200)
    assert len(auto.sent) == 1                             # exactly once


def test_start_and_stop_sound_differ(auto):
    from linux_game_benchmark.deck import setup as deck_setup
    assert deck_setup._SOUNDS["start"] != deck_setup._SOUNDS["stop"]
    assert [f for f, _ in deck_setup._SOUNDS["start"]] == [f for f, _ in reversed(deck_setup._SOUNDS["stop"])]   # same notes, other direction


def test_the_chord_during_a_recording_ends_it_early_and_uploads_at_once(auto):
    auto.chord(T0 + 20)
    auto.chord(T0 + 55)                                    # 35 s: past the 30 s minimum
    assert auto.statuses() == ["uploaded"] and auto.sounds == ["start", "stop", "done"]
    assert auto.sent[0]["metrics"]["duration_seconds"] == pytest.approx(35, abs=1)


def test_a_late_tick_still_cuts_exactly_one_minute(auto):
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 95)                             # the service was busy (or the Deck slept) - length stays 60 s
    assert auto.sent[0]["metrics"]["duration_seconds"] == pytest.approx(60, abs=1)


def test_the_stop_sound_comes_before_the_cutting(auto):
    order = []
    auto.service._cut = lambda *a, **k: (order.append("cut"), segments.cut_log(*a, **k))[1]
    auto.service.play = lambda name: order.append(name)
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 81)
    assert order[:3] == ["start", "stop", "cut"]


def test_a_game_that_closes_during_the_minute_keeps_what_was_logged(auto):
    auto.chord(T0 + 20)
    auto.newest = None                                     # no log any more: the game is gone
    auto.service.tick(T0 + 81)
    assert auto.service.session.phase.value == "idle" and len(auto.sent) <= 1


def test_record_seconds_is_clamped_to_what_the_server_accepts(tmp_path):
    path = tmp_path / "deck.json"
    deck_config.DeckConfig(record_seconds=5).save(path)
    assert deck_config.DeckConfig.load(path).record_seconds == 30
    deck_config.DeckConfig(record_seconds=9999).save(path)
    assert deck_config.DeckConfig.load(path).record_seconds == 300
    path.write_text('{"record_seconds": "soon"}')
    assert deck_config.DeckConfig.load(path).record_seconds == 60


# ---- the device state travels with the upload ---------------------------------------------------------------------------

def test_the_upload_carries_what_the_deck_reported(auto):
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 40)                             # a sample while it runs
    auto.service.tick(T0 + 81)
    state = auto.sent[0]["device_state"]
    assert state["power"]["source"] == "battery" and state["power"]["battery_pct_start"] == 80
    assert state["limits"]["tdp_w"] == 15 and state["display"]["internal_mode"] == "1280x800"
    assert state["device"]["steamos"] == "3.7.8" and state["device"]["board"] == "Jupiter"
    assert state["launch"] == {"env": {"PROTON_NO_ESYNC": "1"}}
    assert state["software"] == {"compat": "proton", "proton": "Proton 9.0 (Beta)"}
    assert "serial" not in str(state).lower()
    assert auto.queue.items()[0].meta["device_state"]["v"] == 1       # kept with the recording, so a retry sends it too


def test_a_failing_software_reader_never_loses_the_recording(auto):
    def broken(game):
        raise OSError("steam folder unreadable")
    auto.service._read_software = broken
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 81)
    state = auto.sent[0]["device_state"]
    assert "software" not in state and state["power"]["source"] == "battery"


def test_plugged_in_is_reported(tmp_path):
    rig = Rig(tmp_path)
    build_deck(rig.sysroot, ac=True, status="Charging")
    rig.chord(T0 + 20)
    rig.service.tick(T0 + 81)
    assert rig.sent[0]["device_state"]["power"]["source"] == "ac"


def test_a_broken_sysfs_never_costs_the_recording(tmp_path):
    rig = Rig(tmp_path)
    def broken():
        raise OSError("sysfs is gone")
    rig.service._sampler_factory = broken
    rig.chord(T0 + 20)
    rig.service.tick(T0 + 81)
    assert len(rig.sent) == 1 and rig.sent[0]["device_state"] is None


def test_the_pad_list_is_rescanned_every_two_seconds_even_while_a_pad_is_read():
    """Steam re-creates its virtual pad when a game starts - a rescan every 10 s left a blind spot for the chord."""
    from linux_game_benchmark.deck.service import run_forever

    class Reader:
        active = True
        scans = 0

        def rescan(self):
            Reader.scans += 1

        def read(self, timeout):
            return []

    class Service:
        def on_key(self, *a):
            pass

        def tick(self, now):
            pass

    clock = {"t": 0.0}

    def now():
        clock["t"] += 0.5
        return clock["t"]

    run_forever(Service(), Reader(), stop=lambda: clock["t"] >= 20, clock=now)
    assert Reader.scans >= 9, Reader.scans          # ~20 s of loop time -> a scan every 2 s


def test_the_games_render_resolution_and_steam_limits_end_up_in_the_upload(rig):
    rig.display_seen = {"render_mode": "1280x720", "fps_limit": 40, "scaling_filter": "fsr", "scaling_mode": "auto", "fsr_sharpness": 2}
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    payload = rig.sent[0]
    assert payload["resolution"] == "1280x720", "the measured size replaces the Deck's native 1280x800"
    display = payload["device_state"]["display"]
    assert display["render_mode"] == "1280x720" and display["fps_limit"] == 40 and display["scaling_filter"] == "fsr"
    assert display["internal_mode"] and display["fsr_sharpness"] == 2, "the panel's own mode stays next to it"


def test_without_a_measurement_the_panel_mode_is_used_and_no_render_mode_is_claimed(rig):
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    payload = rig.sent[0]
    assert payload["resolution"] == "1280x800"
    assert "render_mode" not in payload["device_state"]["display"]


def test_the_window_is_looked_at_while_the_recording_runs_not_only_at_the_ends(auto):
    auto.display_seen = {"render_mode": "1280x720"}
    auto.chord(T0 + 20)
    looks_at_start = auto.display_looks
    for second in range(21, 80, 5):
        auto.service.tick(T0 + second)
    assert auto.display_looks - looks_at_start >= 2, "a look every 20 s while it records"


def test_a_failing_look_never_costs_the_recording(rig):
    def broken(game):
        raise RuntimeError("xprop exploded")
    rig.service._read_display = broken
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 91)
    assert len(rig.sent) == 1 and rig.sent[0]["resolution"] == "1280x800"


# ----- Game Mode: OpenGL games are only visible to Steam's overlay program -------------------------------------------------

@pytest.fixture
def opengl(tmp_path):
    """An OpenGL game (Brotato): MangoHud's Vulkan layer is not in it, so only the overlay program's log exists."""
    r = Rig(tmp_path, mangoapp=True, cancel_window=10.0, record_seconds=0)
    r.newest_by_dir = {r.log_dir: None, r.mangoapp_dir: r.mangoapp_log}
    r.game = GameInfo(1942280, "Brotato")             # no pid: the log belongs to the overlay program, not to the game
    r.running = {1942280}
    return r


def test_an_opengl_game_is_recorded_from_the_overlay_log(opengl):
    opengl.chord(T0 + 20)
    assert opengl.sounds == ["start"] and opengl.service.session.phase.value == "recording"
    opengl.chord(T0 + 80)
    assert opengl.statuses() == ["pending"]
    opengl.service.tick(T0 + 91)
    assert len(opengl.sent) == 1 and opengl.sent[0]["steam_app_id"] == 1942280 and opengl.sent[0]["game_name"] == "Brotato"
    assert opengl.sent[0]["metrics"]["fps_avg"] == pytest.approx(60, abs=1)


def test_a_vulkan_game_still_uses_its_own_log(tmp_path):
    r = Rig(tmp_path, mangoapp=True, cancel_window=10.0, record_seconds=0)
    r.newest_by_dir = {r.log_dir: r.log, r.mangoapp_log.parent: r.mangoapp_log}         # both exist: the game's own wins
    cut_from = []
    real_cut = r.service._cut
    r.service._cut = lambda src, *a, **k: (cut_from.append(Path(src)), real_cut(src, *a, **k))[1]
    r.chord(T0 + 20)
    r.chord(T0 + 80)
    assert cut_from == [r.log] and r.statuses() == ["pending"]


def test_the_overlay_log_in_the_menu_is_not_a_game(opengl):
    """Steam's menu is logged too: with no game running the chord must not start a recording of the menu."""
    opengl.running = set()
    opengl.game = None
    opengl.chord(T0 + 20)
    assert opengl.sounds == ["error"] and opengl.service.session.phase.value == "idle"
    assert "no running game found" in opengl.said[-1]


def test_two_running_games_are_not_guessed(opengl):
    opengl.running = {1942280, 1245620}
    opengl.game = None                                  # identify cannot tell
    opengl.chord(T0 + 20)
    assert opengl.sounds == ["error"] and "could not tell which game" in opengl.said[-1]


def test_a_game_without_any_log_explains_itself(opengl):
    """Desktop Mode / an old setup: a game runs but nothing writes data for it - say so, do not just beep."""
    opengl.newest_by_dir = {opengl.log_dir: None, opengl.mangoapp_dir: None}
    opengl.chord(T0 + 20)
    assert opengl.sounds == ["error"] and opengl.service.session.phase.value == "idle"
    assert "no performance data for this game" in opengl.said[-1] and "OpenGL" in opengl.said[-1] and "Game Mode" in opengl.said[-1]


def test_no_game_and_no_log_still_says_start_a_game(opengl):
    opengl.newest_by_dir = {opengl.log_dir: None, opengl.mangoapp_dir: None}
    opengl.running = set()
    opengl.chord(T0 + 20)
    assert "no running game found - start a game first" in opengl.said[-1]


def test_a_game_closed_during_the_recording_saves_nothing_from_the_menu_frames(opengl):
    opengl.chord(T0 + 20)
    opengl.running = set()                              # the game quit, Steam's menu is on screen (and in the log)
    opengl.chord(T0 + 80)
    assert opengl.statuses() == [] and opengl.sounds[-1] == "error" and "game was closed" in opengl.said[-1]


def test_without_an_overlay_folder_nothing_changes(tmp_path):
    r = Rig(tmp_path, cancel_window=10.0, record_seconds=0)           # older setups: no overlay log at all
    r.newest = None
    r.running = set()
    r.chord(T0 + 20)
    assert r.sounds == ["error"] and "no running game found" in r.said[-1]


def test_a_huge_overlay_log_makes_the_overlay_program_start_a_new_one_when_idle(opengl, monkeypatch):
    from linux_game_benchmark.deck import service as deck_service
    monkeypatch.setattr(deck_service, "MANGOAPP_LOG_LIMIT", 1000)         # the fixture log is a few MB
    opengl.service._tidy_mangoapp_logs()
    assert opengl.restarts == [1]


def test_the_overlay_program_is_left_alone_while_recording(opengl, monkeypatch):
    from linux_game_benchmark.deck import service as deck_service
    monkeypatch.setattr(deck_service, "MANGOAPP_LOG_LIMIT", 1000)
    opengl.chord(T0 + 20)
    opengl.service._tidy_mangoapp_logs()
    assert opengl.restarts == []                                          # a restart would end the log under the recording


def test_old_overlay_logs_go_but_the_running_one_stays(opengl):
    old = write_log(opengl.mangoapp_dir, seconds=1, name="mangoapp_2026-10-10_08-00-00.csv")
    import os
    os.utime(old, (T0 - 10 * 86400, T0 - 10 * 86400))
    opengl.service._tidy_mangoapp_logs()
    assert not old.exists() and opengl.mangoapp_log.exists()

