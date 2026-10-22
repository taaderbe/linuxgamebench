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
    def __init__(self, tmp_path, overlay=False, **config):
        self.log_dir = tmp_path / "logs"
        self.log = write_log(self.log_dir)
        # Game Mode: Steam's overlay program sees every game and writes a log of its own - when it is told to
        self.overlay_dir = tmp_path / "mangoapp-logs" if overlay else None
        self.overlay_running = overlay
        self.overlay_calls: list = []                 # what the service told the overlay program: True = start a log, False = end it
        self.overlay_fails: set = set()               # {True} / {False}: mangohudctl answers "no" to that command
        self.overlay_writes = True                    # the overlay program really opens a log file when told to
        self.overlay_files: list = []
        self.display_calls: list = []                 # what the service told the overlay about showing: False = hide, True = Steam's setting again
        self.display_fails: set = set()
        self.events: list = []                        # ("log"|"display", value) in the order the service did it
        self.logging_now = False
        self.front = None                             # what Gamescope shows in front: None = cannot be read, 769 = Steam's menu
        self.running = {1245620}                      # app ids Steam is running right now
        self.cfg = deck_config.DeckConfig(**config)
        self.sounds, self.said, self.sent = [], [], []
        self.send_result = (True, "https://linuxgamebench.com/benchmark/1", "")
        self.display_seen: dict = {}                  # what "Gamescope" says about the game's window; nothing by default
        self.display_looks = 0
        self.shader_sizes: list = []                  # what the shader-cache reader answers, one per call; nothing by default
        self.closed_waits: list = []
        self.game = GameInfo(1245620, "Elden Ring", pid=4242)
        self.sysroot = build_deck(tmp_path / "sysroot")
        self.newest = self.log
        self.queue = Queue(tmp_path / "queue")
        self.service = DeckService(
            self.cfg, DECK, queue=self.queue, log_dir=self.log_dir, work_dir=tmp_path / "work",
            play=self.sounds.append, say=self.said.append,
            newest_log=lambda d: self.newest,
            identify=lambda p: self.game,
            mangoapp_log_dir=self.overlay_dir, running_games=lambda: set(self.running),
            overlay_running=lambda: self.overlay_running, overlay_log=self._overlay_log, overlay_display=self._overlay_display,
            focused_app=lambda: self.front,
            describe=lambda app_id: self.game if self.game and self.game.app_id == app_id else GameInfo(app_id, f"App {app_id}"),
            wait_closed=self._wait_closed, overlay_wait=0.2,
            wait_flushed=lambda *a, **k: True,
            prepare=lambda seg, game, deck, device_state=None: upload.prepare(seg, game, deck, system_info=SYSTEM, device_state=device_state),
            send=self._send,
            sampler_factory=lambda: telemetry.Sampler(self.sysroot),
            read_env=lambda pid: {"PROTON_NO_ESYNC": "1", "HOME": "/home/deck"} if pid == 4242 else {},
            read_software=lambda game: {"compat": "proton", "proton": "Proton 9.0 (Beta)"} if game else {},
            read_display=self._read_display,
            read_shader_cache=self._read_shader_cache,
        )

    def _read_shader_cache(self, app_id):
        return self.shader_sizes.pop(0) if self.shader_sizes else None

    def _overlay_display(self, show):
        """mangohudctl set no_display true (hide) / reload_config true (Steam's own setting again)."""
        self.display_calls.append(show)
        self.events.append(("display", show))
        return show not in self.display_fails

    def _overlay_log(self, on):
        """mangohudctl set log_session true|false: a new file per start, nothing in between."""
        self.overlay_calls.append(on)
        self.events.append(("log", on))
        if on in self.overlay_fails:
            return False
        if on and self.overlay_writes and not self.logging_now:
            name = f"mangoapp_2026-10-20_18-00-{len(self.overlay_files):02d}.csv"
            self.overlay_files.append(write_log(self.overlay_dir, name=name))      # elapsed 0 = the moment of the command
        self.logging_now = on
        return True

    def _wait_closed(self, path):
        self.closed_waits.append(path)
        return True

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


def test_the_shader_cache_at_the_start_and_how_much_it_grew(auto):
    auto.shader_sizes = [940.0, 952.5]                     # MB when the recording starts, MB when it ends
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 81)
    software = auto.sent[0]["device_state"]["software"]
    assert software["shader_cache_mb"] == 940.0 and software["shader_cache_grew_mb"] == 12.5 and software["proton"] == "Proton 9.0 (Beta)"


def test_a_game_without_a_shader_cache_sends_no_shader_values(auto):
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 81)
    assert "shader_cache_mb" not in auto.sent[0]["device_state"]["software"]


def test_a_failing_shader_cache_reader_never_loses_the_recording(auto):
    def broken(app_id):
        raise OSError("library unreadable")
    auto.service._read_shader_cache = broken
    auto.chord(T0 + 20)
    auto.service.tick(T0 + 81)
    state = auto.sent[0]["device_state"]
    assert "shader_cache_mb" not in state["software"] and state["power"]["source"] == "battery"


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




# ----- Game Mode: every game is recorded through Steam's overlay program, one log per recording ----------------------------

@pytest.fixture
def overlay(tmp_path):
    """Game Mode: Elden Ring (Proton, Vulkan) runs and Steam's overlay program logs on command."""
    return Rig(tmp_path, overlay=True, cancel_window=10.0, record_seconds=0)


def cut_sources(rig):
    seen = []
    real = rig.service._cut
    rig.service._cut = lambda src, *a, **k: (seen.append(Path(src)), real(src, *a, **k))[1]
    return seen


def test_nothing_is_logged_before_the_chord(overlay):
    for second in range(0, 30, 3):
        overlay.service.tick(T0 + second)
    assert overlay.overlay_calls == [] and overlay.overlay_files == []
    overlay.chord(T0 + 30)
    assert overlay.overlay_calls == [True] and len(overlay.overlay_files) == 1


def test_one_recording_is_one_log_started_by_the_chord_and_ended_with_it(overlay):
    seen = cut_sources(overlay)
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["start"] and overlay.service.session.phase.value == "recording"
    overlay.chord(T0 + 80)
    assert overlay.overlay_calls == [True, False] and overlay.logging_now is False
    assert seen == overlay.overlay_files and overlay.statuses() == ["pending"]
    overlay.service.tick(T0 + 91)
    payload = overlay.sent[0]
    assert payload["steam_app_id"] == 1245620 and payload["game_name"] == "Elden Ring"
    assert payload["metrics"]["fps_avg"] == pytest.approx(60, abs=1)
    assert payload["metrics"]["duration_seconds"] == pytest.approx(60, abs=1)
    assert 3590 <= len(payload["frametimes"]) <= 3610


def test_the_log_is_closed_before_it_is_read(overlay):
    order = []
    overlay.service._wait_closed = lambda path: order.append("closed")
    real = overlay.service._cut
    overlay.service._cut = lambda *a, **k: (order.append("cut"), real(*a, **k))[1]
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    assert order == ["closed", "cut"] and overlay.logging_now is False


def test_the_time_limit_ends_the_log_by_itself(tmp_path):
    rig = Rig(tmp_path, overlay=True)                       # defaults: 60 s, upload right away
    rig.chord(T0 + 20)
    rig.service.tick(T0 + 50)
    assert rig.overlay_calls == [True] and rig.sent == []
    rig.service.tick(T0 + 80.4)
    assert rig.overlay_calls == [True, False] and rig.statuses() == ["uploaded"]
    assert rig.sent[0]["metrics"]["duration_seconds"] == pytest.approx(60, abs=1)
    rig.service.tick(T0 + 200)
    assert rig.overlay_calls == [True, False]               # nothing more is ever started or ended


def test_a_chord_that_comes_too_early_leaves_the_log_running(overlay):
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 25)
    assert overlay.sounds == ["start", "error"] and overlay.overlay_calls == [True]
    overlay.chord(T0 + 70)
    assert overlay.overlay_calls == [True, False] and overlay.statuses() == ["pending"]


def test_a_vulkan_game_keeps_its_launch_options_and_window(overlay):
    """The game's process is found by the app id, so the launch options and the render size are read as with the game's own log."""
    overlay.display_seen = {"render_mode": "1280x720"}
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    state = overlay.sent[0]["device_state"]
    assert state["launch"] == {"env": {"PROTON_NO_ESYNC": "1"}} and state["display"]["render_mode"] == "1280x720"


def test_an_opengl_game_is_recorded_the_same_way(overlay):
    overlay.game = GameInfo(1942280, "Brotato")             # a game whose process could not be found
    overlay.running = {1942280}
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    assert overlay.sent[0]["steam_app_id"] == 1942280 and overlay.sent[0]["game_name"] == "Brotato"
    assert overlay.overlay_calls == [True, False]


def test_without_a_running_game_no_log_is_started(overlay):
    overlay.running = set()
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["error"] and overlay.service.session.phase.value == "idle"
    assert "no running game found - start a game first" in overlay.said[-1] and overlay.overlay_calls == []


def test_two_running_games_the_one_in_front_is_recorded(overlay):
    overlay.running = {1245620, 1942280}
    overlay.front = 1942280
    overlay.game = GameInfo(1942280, "Brotato")
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    assert overlay.sent[0]["steam_app_id"] == 1942280


@pytest.mark.parametrize("front", [None, 769, 4711])
def test_two_running_games_with_none_in_front_are_not_guessed(overlay, front):
    overlay.running = {1245620, 1942280}
    overlay.front = front
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["error"] and "could not tell which game" in overlay.said[-1] and overlay.overlay_calls == []


def test_steams_menu_in_front_starts_nothing(overlay):
    """The overlay program logs what is in front: with the menu there it would log the menu."""
    overlay.front = 769
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["error"] and overlay.service.session.phase.value == "idle"
    assert "not in front" in overlay.said[-1] and overlay.overlay_calls == []
    overlay.front = 1245620
    overlay.chord(T0 + 30)                                  # works as soon as the game is back
    assert overlay.service.session.phase.value == "recording"


def test_a_log_the_overlay_program_refuses_to_start_is_explained(overlay):
    overlay.overlay_fails = {True}
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["error"] and overlay.service.session.phase.value == "idle"
    assert "could not start the log" in overlay.said[-1] and overlay.overlay_calls == [True]
    overlay.overlay_fails = set()
    overlay.chord(T0 + 30)
    assert overlay.service.session.phase.value == "recording"


def test_a_log_that_never_shows_up_is_ended_again(overlay):
    overlay.overlay_writes = False                          # e.g. the drop-in is not active yet: the file lands somewhere else
    overlay.chord(T0 + 20)
    assert overlay.sounds == ["error"] and overlay.service.session.phase.value == "idle"
    assert "did not start a log" in overlay.said[-1] and overlay.overlay_calls == [True, False]


def test_a_log_that_cannot_be_ended_is_ended_later(overlay):
    overlay.chord(T0 + 20)
    overlay.overlay_fails = {False}
    overlay.chord(T0 + 80)                                  # the recording is saved, but mangohudctl says no
    assert overlay.statuses() == ["pending"] and overlay.service._overlay_on
    overlay.service.tick(T0 + 85)
    overlay.service.tick(T0 + 86)                           # inside the retry pause: no second try
    assert overlay.overlay_calls == [True, False, False]
    overlay.overlay_fails = set()
    overlay.service.tick(T0 + 95)
    assert overlay.overlay_calls == [True, False, False, False] and overlay.logging_now is False
    overlay.service.tick(T0 + 120)
    assert overlay.overlay_calls == [True, False, False, False]


# ----- the "Logging Finished" summary MangoHud draws for 12 s after a log: hidden, then Steam's own setting again -----------

def test_the_summary_after_the_log_is_hidden_and_the_overlay_comes_back(overlay):
    overlay.chord(T0 + 20)
    overlay.service.tick(T0 + 50)
    assert overlay.display_calls == []                      # nothing is hidden while a log runs: the red dot has to show
    overlay.chord(T0 + 80)
    assert overlay.display_calls == [False]                 # hidden in the moment the log ends
    overlay.service.tick(T0 + 85)
    overlay.service.tick(T0 + 92)                           # MangoHud's 12 s are not over yet
    assert overlay.display_calls == [False]
    overlay.service.tick(T0 + 93)
    assert overlay.display_calls == [False, True]
    overlay.service.tick(T0 + 200)
    assert overlay.display_calls == [False, True]           # once, not again and again


def test_the_time_limit_hides_the_summary_too(tmp_path):
    rig = Rig(tmp_path, overlay=True)                       # defaults: 60 s, upload right away
    rig.chord(T0 + 20)
    rig.service.tick(T0 + 80.4)
    assert rig.display_calls == [False]
    rig.service.tick(T0 + 94)
    assert rig.display_calls == [False, True]


def test_a_recording_spoiled_by_steams_menu_hides_the_summary_as_well(overlay):
    overlay.chord(T0 + 20)
    overlay.front = 769
    overlay.service.tick(T0 + 30)
    overlay.front = 1245620
    overlay.service.tick(T0 + 45)
    overlay.chord(T0 + 80)
    assert overlay.statuses() == [] and overlay.display_calls == [False]    # nothing saved, but the log did end
    overlay.service.tick(T0 + 94)
    assert overlay.display_calls == [False, True]


def test_a_start_that_was_refused_hides_nothing(overlay):
    overlay.front = 769
    overlay.chord(T0 + 20)
    assert overlay.overlay_calls == [] and overlay.display_calls == []


def test_a_new_recording_during_the_summary_gets_the_overlay_back_before_the_log_starts(overlay):
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    assert overlay.display_calls == [False]
    overlay.events.clear()
    overlay.service.tick(T0 + 91)                           # the cancel window is over (the upload goes), MangoHud's 12 s are not
    assert overlay.display_calls == [False]
    overlay.chord(T0 + 92)                                  # a new recording while the old summary is still hidden
    assert overlay.service.session.phase.value == "recording"
    assert overlay.events[:2] == [("display", True), ("log", True)], overlay.events


def test_the_overlay_is_hidden_only_when_the_log_has_really_ended(overlay):
    overlay.chord(T0 + 20)
    overlay.overlay_fails = {False}
    overlay.chord(T0 + 80)                                  # mangohudctl cannot end the log: no summary is coming yet
    assert overlay.display_calls == []
    overlay.overlay_fails = set()
    overlay.service.tick(T0 + 95)                           # the safety net ends it
    assert overlay.display_calls == [False]


def test_a_hide_that_failed_is_not_undone(overlay):
    overlay.display_fails = {False}
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 200)
    assert overlay.display_calls == [False]                 # nothing was hidden, so nothing is given back


def test_a_show_that_failed_is_tried_again_later(overlay):
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.display_fails = {True}
    overlay.service.tick(T0 + 93)
    overlay.service.tick(T0 + 94)                           # inside the retry pause: no second try
    assert overlay.display_calls == [False, True]
    overlay.display_fails = set()
    overlay.service.tick(T0 + 99)
    assert overlay.display_calls == [False, True, True]
    overlay.service.tick(T0 + 130)
    assert overlay.display_calls == [False, True, True]


def test_stopping_the_service_never_leaves_the_overlay_hidden(overlay):
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.close()
    assert overlay.display_calls == [False, True]
    overlay.service.close()
    assert overlay.display_calls == [False, True]


def test_stopping_the_service_during_a_recording_ends_the_log_and_shows_the_overlay(overlay):
    overlay.chord(T0 + 20)
    overlay.service.close()
    assert overlay.overlay_calls == [True, False] and overlay.display_calls == [False, True]


def test_the_start_of_the_service_gives_a_hidden_overlay_back(overlay):
    overlay.service.recover()                               # a service killed during the summary left the overlay hidden
    assert overlay.display_calls == [True]


def test_desktop_mode_never_touches_the_overlay(tmp_path):
    rig = Rig(tmp_path, cancel_window=10.0, record_seconds=0)
    rig.service.recover()
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    rig.service.tick(T0 + 200)
    rig.service.close()
    assert rig.display_calls == []


def test_a_game_closed_during_the_recording_saves_nothing_from_the_menu_frames(overlay):
    overlay.chord(T0 + 20)
    overlay.running = set()                                 # the game quit, Steam's menu is on screen (and in the log)
    overlay.chord(T0 + 80)
    assert overlay.statuses() == [] and overlay.sounds[-1] == "error" and "game was closed" in overlay.said[-1]
    assert overlay.overlay_calls == [True, False] and overlay.service.session.phase.value == "idle"


def test_a_long_look_at_steams_menu_spoils_the_minute(overlay):
    overlay.chord(T0 + 20)
    overlay.front = 769
    overlay.service.tick(T0 + 30)
    overlay.front = 1245620
    overlay.service.tick(T0 + 45)                           # 15 s away from the game
    overlay.chord(T0 + 80)
    assert overlay.statuses() == [] and "not in front for 15 s" in overlay.said[-1] and overlay.overlay_calls == [True, False]


def test_a_short_look_at_steams_menu_is_fine(overlay):
    overlay.chord(T0 + 20)
    overlay.front = 769
    overlay.service.tick(T0 + 30)
    overlay.front = 1245620
    overlay.service.tick(T0 + 33)                           # 3 s: the Steam button was pressed and let go
    overlay.chord(T0 + 80)
    assert overlay.statuses() == ["pending"]


def test_the_menu_still_in_front_when_the_minute_ends_counts(overlay):
    overlay.chord(T0 + 20)
    overlay.front = 769
    overlay.service.tick(T0 + 70)
    overlay.chord(T0 + 80)                                  # 10 s in the menu up to the end
    assert overlay.statuses() == [] and "not in front for 10 s" in overlay.said[-1]


def test_a_front_app_that_cannot_be_read_is_no_reason_to_lose_the_recording(overlay):
    overlay.chord(T0 + 20)
    overlay.front = None
    for second in range(22, 80, 2):
        overlay.service.tick(T0 + second)
    overlay.chord(T0 + 80)
    assert overlay.statuses() == ["pending"]


def test_the_front_app_is_looked_at_every_two_seconds_not_every_tick(overlay):
    calls = []
    overlay.service._focused_app = lambda: calls.append(1) or 1245620
    overlay.chord(T0 + 20)
    first = len(calls)
    for step in range(0, 40):
        overlay.service.tick(T0 + 21 + step * 0.25)         # ten seconds in quarter-second ticks
    assert 4 <= len(calls) - first <= 6


def test_stopping_the_service_never_leaves_a_log_running(overlay):
    overlay.chord(T0 + 20)
    overlay.service.close()
    assert overlay.overlay_calls == [True, False] and overlay.logging_now is False
    overlay.service.close()
    assert overlay.overlay_calls == [True, False]           # nothing to end any more


def test_a_log_left_open_by_a_crashed_service_is_closed_at_the_next_start(overlay):
    overlay.service.recover()
    assert overlay.overlay_calls == [False]


def test_a_log_nobody_records_for_is_ended_by_the_safety_net(overlay):
    assert overlay.service._start_overlay_log() is True     # e.g. a start whose recording was dropped on the way
    overlay.service.tick(T0 + 10)
    assert overlay.overlay_calls == [True, False]


def test_without_the_overlay_program_nothing_is_ever_started_on_command(tmp_path):
    """Desktop Mode: MangoHud's layer inside the game logs all the time and the recording is cut out of that log."""
    rig = Rig(tmp_path, cancel_window=10.0, record_seconds=0)
    rig.service.recover()
    seen = cut_sources(rig)
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    assert rig.overlay_calls == [] and seen == [rig.log] and rig.statuses() == ["pending"]


def test_a_setup_without_an_overlay_folder_uses_the_games_own_log(tmp_path):
    rig = Rig(tmp_path, cancel_window=10.0, record_seconds=0)
    rig.overlay_running = True                              # the program runs, but this setup does not know a folder for it
    seen = cut_sources(rig)
    rig.chord(T0 + 20)
    rig.chord(T0 + 80)
    assert rig.overlay_calls == [] and seen == [rig.log]


def test_a_game_without_any_log_explains_itself(tmp_path):
    """Desktop Mode: an OpenGL game runs, but nothing writes data for it - say so, do not just beep."""
    rig = Rig(tmp_path, cancel_window=10.0, record_seconds=0)
    rig.newest = None
    rig.chord(T0 + 20)
    assert rig.sounds == ["error"] and rig.service.session.phase.value == "idle"
    assert "no performance data for this game" in rig.said[-1] and "OpenGL" in rig.said[-1] and "Game Mode" in rig.said[-1]


def test_no_game_and_no_log_still_says_start_a_game(tmp_path):
    rig = Rig(tmp_path, cancel_window=10.0, record_seconds=0)
    rig.newest = None
    rig.running = set()
    rig.chord(T0 + 20)
    assert "no running game found - start a game first" in rig.said[-1]


def test_old_overlay_logs_go_but_the_recording_in_progress_stays(overlay):
    import os
    old = write_log(overlay.overlay_dir, seconds=1, name="mangoapp_2026-10-10_08-00-00.csv")
    os.utime(old, (T0 - 10 * 86400, T0 - 10 * 86400))
    overlay.chord(T0 + 20)
    overlay.service.tick(T0 + 21)                           # the hourly housekeeping runs at the first tick
    assert not old.exists() and overlay.overlay_files[0].exists()


def test_the_recording_starts_with_the_first_frame_the_log_holds(overlay):
    """The log begins at the chord: elapsed 0 is the moment of the press, so nothing may be skipped at the start or the end."""
    real = overlay._overlay_log

    def marked(on):
        ok = real(on)
        if on and overlay.overlay_files:
            path = overlay.overlay_files[-1]
            lines = path.read_text().splitlines(keepends=True)
            first = next(i for i, line in enumerate(lines) if line.startswith("fps,")) + 1
            lines[first] = "60,99.000,40.0,90.0,1280x800,0\n"             # a recognisable first frame
            path.write_text("".join(lines))
        return ok
    overlay.service._overlay_log = marked
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    frametimes = overlay.sent[0]["frametimes"]
    assert frametimes[0] == pytest.approx(99.0) and 3590 <= len(frametimes) <= 3610


# ----- Game Mode as it really is: Steam's overlay program writes into the home folder, nothing configures it ----------------

@pytest.fixture
def home_overlay(tmp_path):
    """Like `overlay`, but the overlay program writes into a home folder (with other people's files in it) and the service
    keeps its own logs in `mangoapp-logs`."""
    rig = Rig(tmp_path, overlay=True, cancel_window=10.0, record_seconds=0)
    rig.home = tmp_path / "home"
    rig.home.mkdir()
    rig.service.mangoapp_intake_dir = rig.home

    def overlay_log(on):
        rig.overlay_calls.append(on)
        if on and not rig.logging_now:
            name = f"mangoapp_2026-10-20_18-00-{len(rig.overlay_files):02d}.csv"
            rig.overlay_files.append(write_log(rig.home, name=name))
        elif not on and rig.logging_now:
            (rig.home / (rig.overlay_files[-1].stem + "_summary.csv")).write_text("summary")
        rig.logging_now = on
        return True
    rig.service._overlay_log = overlay_log
    return rig


def home_mangoapp_files(rig):
    return sorted(p.name for p in rig.home.glob("mangoapp_*"))


def test_a_log_in_the_home_folder_is_recorded_and_then_moved_to_our_own_folder(home_overlay):
    home_overlay.chord(T0 + 20)
    home_overlay.chord(T0 + 80)
    home_overlay.service.tick(T0 + 91)
    assert home_overlay.sent and home_overlay.sent[0]["steam_app_id"] == 1245620
    assert home_mangoapp_files(home_overlay) == [], "the home folder is tidy again"
    assert sorted(p.name for p in home_overlay.overlay_dir.iterdir()) == [
        "mangoapp_2026-10-20_18-00-00.csv", "mangoapp_2026-10-20_18-00-00_summary.csv"]


def test_the_file_the_overlay_program_has_open_is_found_wherever_it_is(home_overlay, tmp_path):
    """Its default folder is the home folder, but nobody promised that: the open file descriptor tells."""
    elsewhere = tmp_path / "elsewhere"
    plain = home_overlay.service._overlay_log

    def into_other_folder(on):
        ok = plain(on)
        if on:                                                   # the file the overlay program "wrote" moves out of the scanned folder
            moved = elsewhere / home_overlay.overlay_files[-1].name
            elsewhere.mkdir(exist_ok=True)
            home_overlay.overlay_files[-1].replace(moved)
            home_overlay.overlay_files[-1] = moved
        elif home_overlay.overlay_files:
            (home_overlay.home / (home_overlay.overlay_files[-1].stem + "_summary.csv")).replace(
                elsewhere / (home_overlay.overlay_files[-1].stem + "_summary.csv"))
        return ok
    home_overlay.service._overlay_log = into_other_folder
    home_overlay.service._overlay_open_log = lambda before: home_overlay.overlay_files[-1] if home_overlay.overlay_files else None
    home_overlay.chord(T0 + 20)
    assert home_overlay.service.session.phase.value == "recording", home_overlay.said
    home_overlay.chord(T0 + 80)
    home_overlay.service.tick(T0 + 91)
    assert home_overlay.sent and not list(elsewhere.glob("*.csv")), "moved on to our own folder"
    assert (home_overlay.overlay_dir / "mangoapp_2026-10-20_18-00-00.csv").exists()


def test_a_dropped_recording_leaves_no_log_in_the_home_folder_either(home_overlay):
    home_overlay.chord(T0 + 20)
    home_overlay.running = set()                                 # the game was closed during the recording
    home_overlay.chord(T0 + 80)
    assert "the game was closed during the recording" in home_overlay.said[-1] and home_overlay.sent == []
    assert home_mangoapp_files(home_overlay) == []
    assert (home_overlay.overlay_dir / "mangoapp_2026-10-20_18-00-00.csv").exists()


def test_other_files_in_the_home_folder_are_never_touched(home_overlay):
    import os
    mine = {"results.csv": "my results", "budget_2026.csv": "money", "mangoapp_notes.txt": "notes"}
    for name, text in mine.items():
        (home_overlay.home / name).write_text(text)
        os.utime(home_overlay.home / name, (1, 1))              # years old - the housekeeping must still leave them alone
    import time
    stale = home_overlay.home / "mangoapp_2026-10-01_00-00-00.csv"
    stale.write_text("left behind by a crash")
    hour_ago = time.time() - 3600                               # past the grace time, far from the 3 days after which logs go
    os.utime(stale, (hour_ago, hour_ago))
    home_overlay.chord(T0 + 20)
    home_overlay.service.tick(T0 + 21)                          # the hourly housekeeping runs at the first tick
    assert {n: (home_overlay.home / n).read_text() for n in mine} == mine
    assert not stale.exists() and (home_overlay.overlay_dir / stale.name).exists(), "what a crash left behind is tidied up"
    assert home_overlay.overlay_files[0].exists(), "the log being written stays where it is"


def test_a_log_a_crash_left_behind_is_tidied_up_at_the_start(home_overlay):
    import os
    stale = home_overlay.home / "mangoapp_2026-10-01_00-00-00.csv"
    stale.write_text("left behind")
    os.utime(stale, (1, 1))
    home_overlay.service.recover()
    assert not stale.exists() and (home_overlay.overlay_dir / stale.name).exists()


# ----- a paused game: no frames for a while ------------------------------------------------------------------------------------

def cut_rows_after(rig, seconds):
    """Make the overlay program's next log end its frames `seconds` after the command (the game stops drawing)."""
    real = rig._overlay_log

    def stopping(on):
        ok = real(on)
        if on and rig.overlay_files:
            path = rig.overlay_files[-1]
            keep = [line for line in path.read_text().splitlines(keepends=True)
                    if not line[:1].isdigit() or int(line.rsplit(",", 1)[1]) < seconds * 1_000_000_000]
            path.write_text("".join(keep))
        return ok
    rig.service._overlay_log = stopping


def test_a_recording_in_which_the_game_stopped_drawing_is_not_saved(overlay):
    """Vampire Survivors behind Steam's menu draws nothing: the log ends after 4.5 s of a 60 s recording. Uploaded, it would be
    a 4.5 s run (refused by the server) or a shorter run labelled 60 s - so it is dropped with the error tone."""
    cut_rows_after(overlay, 4.5)
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    assert overlay.sent == [] and overlay.statuses() == []
    assert any("showed no frames for 56 s" in text and "nothing saved" in text for text in overlay.said), overlay.said
    assert overlay.sounds[-1] == "error"


def test_a_recording_without_a_hole_is_saved_as_before(overlay):
    cut_rows_after(overlay, 1000)
    overlay.chord(T0 + 20)
    overlay.chord(T0 + 80)
    overlay.service.tick(T0 + 91)
    assert len(overlay.sent) == 1 and not any("no frames" in text for text in overlay.said)


# ----- the game closes while it is being recorded ------------------------------------------------------------------------------

def test_a_game_closed_during_the_recording_ends_it_at_once(overlay):
    """Thomas on the Deck: Vampire Survivors closed during its recording, Brotato started, the chord in Brotato only ended the old
    recording. Now the recording ends within one look (2 s) after the game is gone: log off, error tone, nothing saved."""
    overlay.chord(T0 + 20)
    overlay.service.tick(T0 + 30)
    overlay.running = set()                                 # the game quit, Steam's menu is on screen
    overlay.service.tick(T0 + 32)
    assert overlay.service.session.phase.value == "idle" and overlay.overlay_calls == [True, False]
    assert overlay.said[-1] == "the game was closed during the recording - nothing saved" and overlay.sounds[-1] == "error"
    assert overlay.statuses() == [] and overlay.sent == []
    overlay.service.tick(T0 + 120)
    assert overlay.overlay_calls == [True, False] and overlay.statuses() == []    # nothing happens later on its own


def test_after_a_game_was_closed_the_next_chord_records_the_next_game(overlay):
    overlay.chord(T0 + 20)
    overlay.running = set()
    overlay.service.tick(T0 + 25)
    overlay.running, overlay.front = {1942280}, 1942280     # Brotato is started and in front
    overlay.chord(T0 + 40)
    assert overlay.service.session.phase.value == "recording" and overlay.said[-1].startswith("recording App 1942280")
    assert overlay.overlay_calls == [True, False, True]
    overlay.chord(T0 + 100)
    overlay.service.tick(T0 + 111)
    assert len(overlay.sent) == 1 and overlay.sent[0]["steam_app_id"] == 1942280, overlay.sent[0].keys()


def test_a_game_that_keeps_running_is_never_dropped(overlay):
    overlay.chord(T0 + 20)
    for second in range(21, 80):
        overlay.service.tick(T0 + second)
    assert overlay.service.session.phase.value == "recording"
    overlay.chord(T0 + 80)
    assert overlay.statuses() == ["pending"]


def test_a_dropped_recording_moves_its_log_out_of_the_home_folder(home_overlay):
    home_overlay.chord(T0 + 20)
    home_overlay.running = set()
    home_overlay.service.tick(T0 + 25)
    assert home_overlay.said[-1] == "the game was closed during the recording - nothing saved"
    assert home_mangoapp_files(home_overlay) == []
    assert (home_overlay.overlay_dir / "mangoapp_2026-10-20_18-00-00.csv").exists()


# ----- Steam's overlay level changed during a recording ------------------------------------------------------------------------

def overlay_ends_log_by_itself(rig):
    """What the overlay program does when Steam rewrites its file (level changed in the Quick Access Menu): it closes the log
    and writes the summary next to it."""
    log = rig.overlay_files[-1]
    log.with_name(log.stem + "_summary.csv").write_text("0.1% Min FPS,1% Min FPS\n30,40\n")


def test_a_log_the_overlay_program_ended_by_itself_ends_the_recording_at_once(overlay):
    overlay.chord(T0 + 20)
    overlay.service.tick(T0 + 22)
    assert overlay.service.session.phase.value == "recording"
    overlay_ends_log_by_itself(overlay)
    overlay.service.tick(T0 + 24)
    assert overlay.service.session.phase.value == "idle" and overlay.statuses() == [] and overlay.sent == []
    assert "performance overlay was changed during the recording" in overlay.said[-1] and overlay.sounds[-1] == "error"
    overlay.chord(T0 + 40)                                   # the next chord starts a new recording
    assert overlay.service.session.phase.value == "recording" and overlay.said[-1].startswith("recording")


def test_a_log_without_a_summary_keeps_recording(overlay):
    overlay.chord(T0 + 20)
    for second in range(21, 79):
        overlay.service.tick(T0 + second)
    assert overlay.service.session.phase.value == "recording"
