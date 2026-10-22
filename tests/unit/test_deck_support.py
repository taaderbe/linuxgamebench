"""Deck helpers: config, setup files, queue housekeeping, pairing, game identification."""

import os
import time
import wave

import httpx
import re

import pytest

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import game, pairing
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.queue import Queue, move_logs, prune_logs


# ----- config ------------------------------------------------------------------

def test_config_defaults_roundtrip_and_broken_values(tmp_path):
    path = tmp_path / "deck.json"
    assert deck_config.DeckConfig.load(path).auto_upload is True            # on by default on the Deck
    cfg = deck_config.DeckConfig(chord="L4+R4>A", auto_upload=False)
    cfg.save(path)
    loaded = deck_config.DeckConfig.load(path)
    assert loaded.chord == "L4+R4>A" and loaded.auto_upload is False
    path.write_text('{"chord": "nonsense", "unknown_key": 1}')
    assert deck_config.DeckConfig.load(path).chord == "LB+RB>VIEW"        # never stop the service over a typo
    path.write_text("not json")
    assert deck_config.DeckConfig.load(path).min_seconds == 30.0


def test_data_dir_follows_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LGB_DATA_DIR", str(tmp_path / "d"))
    assert deck_config.log_dir() == tmp_path / "d/deck/logs"
    assert deck_config.queue_dir() == tmp_path / "d/deck/queue"


# ----- setup files ---------------------------------------------------------------

@pytest.fixture
def fake_home(monkeypatch, tmp_path):
    monkeypatch.setattr(deck_setup, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("LGB_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "home"


def test_flight_recorder_config_is_invisible_logging_and_idempotent(fake_home, tmp_path):
    path = deck_setup.write_mangohud_conf()
    text = path.read_text()
    assert path == fake_home / ".config/MangoHud/MangoHud.conf"
    assert "autostart_log=1" in text and "alpha=0" in text and f"output_folder={tmp_path / 'data/deck/logs'}" in text
    assert "no_display" not in text.replace("# ", "")            # no_display would stop MangoHud from logging
    assert "output_format" not in text                            # unknown option in MangoHud 0.8
    assert deck_setup.is_managed(path)
    deck_setup.write_mangohud_conf()
    assert not list(path.parent.glob("*.lgb-backup-*"))           # our own file is not backed up


def test_a_foreign_mangohud_config_is_backed_up_and_restored_on_removal(fake_home, monkeypatch):
    path = deck_setup.mangohud_conf_path()
    path.parent.mkdir(parents=True)
    path.write_text("fps\nmy_own_setting=1\n")
    monkeypatch.setattr(deck_setup, "_systemctl", lambda *a: None)
    deck_setup.write_mangohud_conf()
    backups = list(path.parent.glob("*.lgb-backup-*"))
    assert len(backups) == 1 and "my_own_setting" in backups[0].read_text()
    deck_setup.write_env_file()
    removed = deck_setup.remove_all()
    assert "my_own_setting" in path.read_text() and not deck_setup.env_file_path().exists()
    assert any("MangoHud.conf" in r for r in removed)


def test_environment_file_points_at_the_config(fake_home):
    text = deck_setup.write_env_file().read_text()
    assert "MANGOHUD=1" in text and f"MANGOHUD_CONFIGFILE={fake_home}/.config/MangoHud/MangoHud.conf" in text


def test_service_unit_uses_the_appimage_when_there_is_one(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/home/deck/Applications/LinuxGameBench-x86_64.AppImage")
    unit = deck_setup.unit_text()
    assert 'ExecStart="/home/deck/Applications/LinuxGameBench-x86_64.AppImage" deck run' in unit
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit
    assert "KillMode=mixed" in unit, "stopping the AppImage service must not unmount it under the running Python (SIGBUS)"


def test_service_unit_unpacks_itself_when_the_installer_found_no_fuse(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/home/deck/Applications/LinuxGameBench-x86_64.AppImage")
    monkeypatch.setenv("APPIMAGE_EXTRACT_AND_RUN", "1")
    assert "Environment=APPIMAGE_EXTRACT_AND_RUN=1\n" in deck_setup.unit_text()
    monkeypatch.delenv("APPIMAGE_EXTRACT_AND_RUN")
    assert "APPIMAGE_EXTRACT_AND_RUN" not in deck_setup.unit_text()


def test_install_service_without_enabling_only_writes_the_unit(fake_home):
    ok, _ = deck_setup.install_service(enable=False, command="/x/lgb deck run")
    assert ok and "ExecStart=/x/lgb deck run" in deck_setup.unit_path().read_text()


def test_sounds_are_valid_short_wav_files(tmp_path):
    paths = deck_setup.ensure_sounds(tmp_path)
    assert set(paths) == {"start", "stop", "cancel", "done", "error"}
    with wave.open(str(paths["start"])) as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 22050 and 0.1 < wav.getnframes() / 22050 < 1.0


def _levels(path, parts=22):
    """Loudness of the file in `parts` equal slices (peak of each slice)."""
    import struct
    with wave.open(str(path)) as wav:
        data = wav.readframes(wav.getnframes())
    samples = struct.unpack(f"<{len(data) // 2}h", data)
    size = len(samples) // parts
    return [max(abs(x) for x in samples[i * size:(i + 1) * size]) for i in range(parts)]


def test_the_error_sound_is_two_quick_beeps_high_enough_for_the_decks_speakers(tmp_path):
    """Thomas did not hear the old error tone (one 200 Hz tone - too low for the small speakers). Now: two short beeps."""
    notes = deck_setup._SOUNDS["error"]
    tones = [f for f, _ in notes if f]
    assert len(tones) == 2 and min(tones) >= 400 and sum(d for _, d in notes) <= 0.4
    levels = _levels(deck_setup.ensure_sounds(tmp_path)["error"])
    loud = [level > 3000 for level in levels]
    assert loud[2] and loud[-3] and not all(loud), levels           # beep, pause, beep
    runs = "".join("x" if x else "." for x in loud).strip(".").split(".")
    assert len([r for r in runs if r]) == 2, levels


def test_an_old_sound_file_is_replaced_after_an_update(tmp_path):
    old = tmp_path / "error.wav"
    deck_setup.write_sound(old, [(200, 0.30)])                       # what versions before had written
    paths = deck_setup.ensure_sounds(tmp_path)
    assert paths["error"].read_bytes() == deck_setup.sound_bytes(deck_setup._SOUNDS["error"])
    stamp = paths["error"].stat().st_mtime_ns
    deck_setup.ensure_sounds(tmp_path)
    assert paths["error"].stat().st_mtime_ns == stamp                 # unchanged sounds are not written again


# ----- queue / log housekeeping -------------------------------------------------------

def test_queue_prune_keeps_pending_and_removes_old_finished(tmp_path):
    q = Queue(tmp_path / "q")
    now = 10_000_000.0
    old_done = q.add(_csv(tmp_path, "a"), {"created": now - 40 * 86400}); q.update(old_done, status="uploaded")
    old_pending = q.add(_csv(tmp_path, "b"), {"created": now - 40 * 86400})
    new_done = q.add(_csv(tmp_path, "c"), {"created": now - 86400}); q.update(new_done, status="uploaded")
    assert q.prune(30, now=now) == 1
    assert {i.id for i in q.items()} == {old_pending.id, new_done.id}


def _csv(tmp_path, name):
    path = tmp_path / f"{name}.csv"
    path.write_text("fps\n")
    return path


def test_backoff_grows_and_caps(tmp_path):
    q = Queue(tmp_path / "q")
    item = q.add(_csv(tmp_path, "x"), {"created": 1.0})
    delays = []
    for _ in range(6):
        q.failed_attempt(item, "offline", retry=True, now=1000.0)
        delays.append(item.meta["next_try"] - 1000.0)
    assert delays == [300, 900, 3600, 21600, 21600, 21600]
    assert q.due(now=1000.0 + 100) == [] and q.due(now=1000.0 + 21601) == [item]


def test_old_logs_are_pruned_but_the_active_one_stays(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    now = time.time()
    for name, age_days in (("old.csv", 5), ("recent.csv", 1), ("active.csv", 9)):
        path = logs / name
        path.write_text("x" * 100)
        os.utime(path, (now - age_days * 86400, now - age_days * 86400))
    assert prune_logs(logs, keep_days=3, active=logs / "active.csv", now=now) == 1
    assert sorted(p.name for p in logs.iterdir()) == ["active.csv", "recent.csv"]
    assert prune_logs(logs, keep_days=30, max_bytes=150, active=logs / "active.csv", now=now) == 1     # size cap drops the oldest


# ----- pairing ---------------------------------------------------------------------------

START = {"device_code": "dev123", "user_code": "ABCD-EFGH", "verification_url": "https://linuxgamebench.com/link",
         "expires_in": 600, "interval": 1}


def _fake_post(answers):
    calls = []

    def post(url, json=None, timeout=None):
        calls.append(url)
        status, body = answers.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))
    return post, calls


def test_pairing_waits_for_the_approval_and_returns_the_tokens(monkeypatch):
    post, calls = _fake_post([
        (200, START), (200, {"status": "pending"}), (200, {"status": "pending"}),
        (200, {"status": "approved", "access_token": "a", "refresh_token": "r", "user": {"username": "deckuser"}}),
    ])
    monkeypatch.setattr(pairing.httpx, "post", post)
    shown = []
    session = pairing.pair(shown.append, base_url="http://x/api/v1", sleep=lambda s: None, save=False)
    assert shown[0]["user_code"] == "ABCD-EFGH"
    assert session.get_username() == "deckuser" and session.access_token == "a"
    assert [c.rsplit("/", 1)[1] for c in calls] == ["start", "poll", "poll", "poll"]


def test_pairing_gives_up_when_the_code_expires(monkeypatch):
    post, _ = _fake_post([(200, {**START, "expires_in": 3}), (200, {"status": "pending"}), (200, {"status": "pending"}),
                          (200, {"status": "pending"}), (200, {"status": "pending"})])
    monkeypatch.setattr(pairing.httpx, "post", post)
    clock = iter(range(0, 100))
    with pytest.raises(pairing.PairingError, match="expired"):
        pairing.pair(lambda info: None, base_url="http://x", sleep=lambda s: None, clock=lambda: next(clock), save=False)


def test_pairing_reports_a_denied_code(monkeypatch):
    post, _ = _fake_post([(200, START), (403, {"detail": "denied by the user"})])
    monkeypatch.setattr(pairing.httpx, "post", post)
    with pytest.raises(pairing.PairingError, match="denied"):
        pairing.pair(lambda info: None, base_url="http://x", sleep=lambda s: None, save=False)


def test_a_server_error_on_start_is_a_clear_error(monkeypatch):
    post, _ = _fake_post([(500, {})])
    monkeypatch.setattr(pairing.httpx, "post", post)
    with pytest.raises(pairing.PairingError, match="refused"):
        pairing.start("http://x")


# ----- game identification ---------------------------------------------------------------------

def _proc(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    return proc


def _process(proc, pid, environ=None, cmdline=None, open_file=None):
    d = proc / str(pid)
    (d / "fd").mkdir(parents=True)
    (d / "environ").write_bytes(b"\x00".join(f"{k}={v}".encode() for k, v in (environ or {}).items()))
    (d / "cmdline").write_bytes((cmdline or "bash").encode())
    if open_file is not None:
        (d / "fd" / "7").symlink_to(open_file)


def test_the_process_that_writes_the_log_names_the_game(tmp_path):
    proc = _proc(tmp_path)
    log = tmp_path / "logs" / "game.exe_2026-10-20_18-00-00.csv"
    log.parent.mkdir()
    log.write_text("x")
    _process(proc, 100, environ={"HOME": "/home/deck"})
    _process(proc, 200, environ={"SteamAppId": "1245620", "HOME": "/home/deck"}, open_file=log)
    assert game.log_writer_app_id(log, proc) == 1245620


def test_fallback_to_the_single_running_steam_launch(tmp_path):
    proc = _proc(tmp_path)
    log = tmp_path / "x_2026-10-20_18-00-00.csv"
    log.write_text("x")
    _process(proc, 300, cmdline="reaper\x00SteamLaunch\x00AppId=1091500\x00--\x00proton")
    assert game.identify(log, proc).app_id == 1091500
    _process(proc, 301, cmdline="reaper\x00SteamLaunch\x00AppId=999\x00--")
    assert game.identify(log, proc) is None            # two games running: do not guess


def test_newest_log_ignores_summaries_and_stale_files(tmp_path):
    now = time.time()
    for name, age in (("a_2026-10-20_18-00-00.csv", 500), ("b_2026-10-20_18-10-00.csv", 5), ("b_2026-10-20_18-10-00_summary.csv", 1)):
        path = tmp_path / name
        path.write_text("x")
        os.utime(path, (now - age, now - age))
    assert game.newest_log(tmp_path, now=now).name == "b_2026-10-20_18-10-00.csv"
    assert game.newest_log(tmp_path, max_age=2, now=now) is None
    assert game.newest_log(tmp_path / "missing") is None


def test_mangohud_template_uses_only_options_mangohud_0_8_knows():
    """cpu_load / gpu_load / gpu_vram_used are CSV column names, not config options (MangoHud 0.8.4: "Unknown option")."""
    lines = {l.strip() for l in deck_setup.MANGOHUD_CONF_TEMPLATE.splitlines()}
    for wrong in ("cpu_load", "gpu_load", "gpu_vram_used", "no_display"):
        assert wrong not in lines
    for right in ("cpu_stats", "gpu_stats", "vram", "ram", "battery", "battery_watt", "fan", "frametime", "fps", "alpha=0"):
        assert right in lines


def test_enabling_the_service_also_restarts_it_so_an_update_takes_effect(fake_home, monkeypatch):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(deck_setup, "_systemctl", lambda *args: calls.append(args) or Done())
    monkeypatch.setattr(deck_setup.subprocess, "run", lambda *a, **k: Done())
    ok, _ = deck_setup.install_service(command="/x/lgb deck run")
    assert ok and ("daemon-reload",) in calls and calls.index(("restart", deck_setup.UNIT_NAME)) > calls.index(("enable", "--now", deck_setup.UNIT_NAME))


# ----- Game Mode: Steam owns MANGOHUD_CONFIGFILE there, the games' MangoHud layer stays quiet -----------------------

def env_lines(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))


def test_environment_file_only_points_the_desktop_mode_layer_at_our_config(fake_home):
    env = env_lines(deck_setup.write_env_file())
    assert env["MANGOHUD"] == "1" and env["MANGOHUD_CONFIGFILE"] == str(deck_setup.mangohud_conf_path())
    assert "MANGOHUD_CONFIG" not in env, \
        "a logging variable for every game would make the layer inside the games log all the time in Game Mode, too"


def test_the_desktop_mode_config_still_logs_all_the_time_with_every_sensor():
    text = deck_setup.MANGOHUD_CONF_TEMPLATE
    assert "autostart_log=1" in text and set(deck_setup.SENSORS) <= {l.strip() for l in text.splitlines()}


def test_removing_the_setup_takes_the_dropin_away_too(fake_home, monkeypatch):
    monkeypatch.setattr(deck_setup, "_systemctl", lambda *a: None)
    deck_setup.write_env_file()
    assert deck_setup.steam_dropin_path().exists()
    deck_setup.remove_all()
    assert not deck_setup.env_file_path().exists()
    assert not deck_setup.steam_dropin_path().exists(), "Steam has to start in Game Mode exactly as SteamOS ships it again"


def write_legacy_dropin():
    path = deck_setup.mangoapp_dropin_path()
    path.parent.mkdir(parents=True)
    path.write_text('[Service]\nExecStart=\nExecStart=/usr/bin/env "MANGOHUD_CONFIG=read_cfg,output_folder=/x,log_interval=0" /usr/bin/mangoapp\n')
    return path


def test_an_install_leaves_steams_overlay_program_exactly_as_steamos_ships_it(fake_home):
    """Found on the real Deck: a drop-in with its own MANGOHUD_CONFIG (needed `read_cfg` to keep Steam's level working) made
    MangoHud read Steam's config twice - Steam's level 1 showed the FPS twice. The overlay program needs nothing of ours: it logs one
    row per frame into the home folder when told to."""
    deck_setup.write_env_file()
    assert not deck_setup.mangoapp_dropin_path().exists()
    written = [p for p in fake_home.rglob("*") if p.is_file()]
    assert written, "the install wrote nothing?"
    assert not [p for p in written if re.search(r"MANGOHUD_CONFIG(?!FILE)|read_cfg", p.read_text(errors="replace"))], \
        "no file of ours may set MANGOHUD_CONFIG or read_cfg: the session value would reach Steam and every game"


def test_an_install_removes_the_old_dropin_of_builds_up_to_20(fake_home):
    old = write_legacy_dropin()
    deck_setup.write_env_file()
    assert not old.exists() and not old.parent.exists(), "the empty drop-in folder goes too"
    assert deck_setup.remove_legacy_mangoapp_dropin() is False                # nothing left to remove


def test_a_foreign_file_in_the_dropin_folder_stays(fake_home):
    old = write_legacy_dropin()
    (old.parent / "mine.conf").write_text("[Service]\n")
    assert deck_setup.remove_legacy_mangoapp_dropin() is True
    assert (old.parent / "mine.conf").exists()


def test_steam_in_game_mode_starts_without_the_desktop_mode_variable(fake_home):
    """Found on the real Deck: the user manager lives on between the modes (linger), so Steam in Game Mode inherited MANGOHUD=1;
    the MangoHud layer in a Proton game cannot read Steam's config file there and drew its default overlay next to Steam's."""
    deck_setup.write_env_file()
    path = deck_setup.steam_dropin_path()
    lines = path.read_text().splitlines()
    assert path.parent.name == "steam-launcher.service.d" and "[Service]" in lines
    assert "UnsetEnvironment=MANGOHUD" in lines
    assert "MANGOHUD_CONFIGFILE" not in path.read_text(), "Steam's own config file (the overlay level) must stay"
    assert "ExecStart" not in path.read_text(), "Steam is started exactly as SteamOS ships it - nothing but the variable changes"


def fake_proc(tmp_path, *processes):
    """A /proc with the given (comm, {env}) processes."""
    for number, (comm, env) in enumerate(processes, start=100):
        entry = tmp_path / str(number)
        entry.mkdir()
        (entry / "comm").write_text(comm + "\n")
        (entry / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0")
    return tmp_path


@pytest.mark.parametrize("env, expected", [
    ({"STEAM_USE_MANGOAPP": "1", "MANGOHUD": "1"}, True),                  # Game Mode, variable still there
    ({"STEAM_USE_MANGOAPP": "1", "MANGOHUD_CONFIGFILE": "/run/x"}, False),  # Game Mode, as SteamOS ships it
    ({"MANGOHUD": "1"}, None),                                               # Desktop Mode: the variable is wanted there
])
def test_a_leaked_desktop_variable_in_game_mode_is_noticed(tmp_path, env, expected):
    assert deck_setup.game_mode_layer_leak(fake_proc(tmp_path, ("steam", env))) is expected


def test_the_leak_check_says_nothing_without_a_readable_steam_process(tmp_path):
    assert deck_setup.game_mode_layer_leak(fake_proc(tmp_path, ("bash", {"MANGOHUD": "1"}))) is None
    assert deck_setup.game_mode_layer_leak(tmp_path / "does-not-exist") is None


# ----- Game Mode: the overlay program (mangoapp) logs every game, also the OpenGL ones ----------------------------------

class FakeSystemctl:
    """Stands in for deck_setup._systemctl: returns canned text per command, records every call."""
    def __init__(self, cat="", active="inactive", cat_ok=True):
        self.calls, self.cat, self.active, self.cat_ok = [], cat, active, cat_ok

    def __call__(self, *args):
        from types import SimpleNamespace
        self.calls.append(args)
        if args[:1] == ("cat",):
            return SimpleNamespace(stdout=self.cat, stderr="", returncode=0 if self.cat_ok else 1)
        if args[:1] == ("is-active",):
            return SimpleNamespace(stdout=self.active + "\n", stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)


def test_a_missing_systemctl_does_not_break_the_setup(fake_home, monkeypatch):
    def boom(*a):
        raise FileNotFoundError("systemctl")
    monkeypatch.setattr(deck_setup, "_systemctl", boom)
    deck_setup.reload_mangoapp()                                               # must not raise


@pytest.mark.parametrize("state, restarted", [("active", True), ("inactive", False), ("failed", False)])
def test_the_overlay_program_is_restarted_only_when_it_runs(monkeypatch, state, restarted):
    fake = FakeSystemctl(active=state)
    monkeypatch.setattr(deck_setup, "_systemctl", fake)
    deck_setup.reload_mangoapp()
    assert ("daemon-reload",) in fake.calls
    assert (("restart", deck_setup.MANGOAPP_UNIT) in fake.calls) is restarted


def test_removing_the_setup_gives_the_overlay_program_back_to_steamos(fake_home, monkeypatch):
    fake = FakeSystemctl(active="active")
    monkeypatch.setattr(deck_setup, "_systemctl", fake)
    write_legacy_dropin()
    deck_setup.remove_all()
    assert not deck_setup.mangoapp_dropin_path().exists()
    assert ("restart", deck_setup.MANGOAPP_UNIT) in fake.calls               # it runs as SteamOS ships it again


# ----- logs of Steam's overlay program: they land in the home folder, only those files are ever moved ---------------------

def test_only_finished_overlay_logs_leave_the_home_folder(tmp_path):
    import os
    home, ours, now = tmp_path / "home", tmp_path / "ours", 1_000_000.0
    home.mkdir()
    old = {"mangoapp_2026-10-21_16-00-00.csv": "log", "mangoapp_2026-10-21_16-00-00_summary.csv": "summary"}
    for name, text in old.items():
        (home / name).write_text(text)
        os.utime(home / name, (now - 3600, now - 3600))
    (home / "mangoapp_2026-10-21_16-30-00.csv").write_text("still being written")            # younger than the grace time
    os.utime(home / "mangoapp_2026-10-21_16-30-00.csv", (now - 30, now - 30))
    for name in ("results.csv", "mangoapp_notes.txt", "budget_2026.csv"):                     # not ours, however old
        (home / name).write_text("mine")
        os.utime(home / name, (now - 99999, now - 99999))
    assert move_logs(home, ours, "mangoapp_*.csv", now=now) == 2
    assert sorted(p.name for p in ours.iterdir()) == sorted(old)
    assert sorted(p.name for p in home.iterdir()) == ["budget_2026.csv", "mangoapp_2026-10-21_16-30-00.csv",
                                                      "mangoapp_notes.txt", "results.csv"]


def test_the_log_being_written_is_never_moved(tmp_path):
    import os
    home = tmp_path / "home"
    home.mkdir()
    active = home / "mangoapp_2026-10-21_16-00-00.csv"
    active.write_text("x")
    os.utime(active, (1, 1))
    assert move_logs(home, tmp_path / "ours", "mangoapp_*.csv", keep=active, now=1_000_000.0) == 0 and active.exists()


def test_a_missing_folder_is_nothing_to_move(tmp_path):
    assert move_logs(tmp_path / "nowhere", tmp_path / "ours", "mangoapp_*.csv") == 0
