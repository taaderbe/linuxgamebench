"""Deck helpers: config, setup files, queue housekeeping, pairing, game identification."""

import os
import time
import wave

import httpx
import pytest

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import game, pairing
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.queue import Queue, prune_logs


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


# ----- Game Mode: Steam owns MANGOHUD_CONFIGFILE there, so the options also go in MANGOHUD_CONFIG -------------------

def env_lines(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))


def test_environment_file_carries_the_logging_options_as_one_variable(fake_home):
    env = env_lines(deck_setup.write_env_file())
    options = env["MANGOHUD_CONFIG"].split(",")
    assert options[0].startswith("output_folder=") and "autostart_log=1" in options and "log_interval=0" in options
    assert set(deck_setup.SENSORS) <= set(options)
    assert "no_display" not in options and not any(o.startswith(("alpha", "font_size")) for o in options), \
        "the overlay look must not travel to Steam's own performance overlay"


def test_config_file_and_variable_list_the_same_sensors():
    in_file = {l.strip() for l in deck_setup.MANGOHUD_CONF_TEMPLATE.splitlines()}
    assert set(deck_setup.SENSORS) <= in_file


def test_steams_performance_overlay_does_not_get_the_variable(fake_home):
    deck_setup.write_env_file()
    text = deck_setup.mangoapp_dropin_path().read_text()
    assert deck_setup.mangoapp_dropin_path().parent.name == "gamescope-mangoapp.service.d"
    assert "[Service]" in text and "UnsetEnvironment=MANGOHUD_CONFIG" in text


def test_removing_the_setup_takes_the_dropin_away_too(fake_home, monkeypatch):
    monkeypatch.setattr(deck_setup, "_systemctl", lambda *a: None)
    deck_setup.write_env_file()
    assert deck_setup.mangoapp_dropin_path().exists()
    deck_setup.remove_all()
    assert not deck_setup.mangoapp_dropin_path().exists() and not deck_setup.env_file_path().exists()
