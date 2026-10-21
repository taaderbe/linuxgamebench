"""The account is optional on the Deck: press Enter to go on without one, and starting the link later is one step away."""

import os
import pty

import pytest
from typer.testing import CliRunner

from linux_game_benchmark.deck.detect import DeckInfo
from linux_game_benchmark.deck import cli as deck_cli
from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import pairing
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.ttyinput import EnterWatcher

runner = CliRunner()


def flat(result) -> str:
    """The output with line breaks and runs of spaces folded (the console wraps long lines)."""
    return " ".join(result.output.split())


# ----- Enter on the terminal --------------------------------------------------------------------------------------------

@pytest.fixture
def terminal():
    master, slave = pty.openpty()
    yield master, os.ttyname(slave)
    os.close(master)
    os.close(slave)


def test_enter_ends_the_wait_at_once(terminal):
    master, path = terminal
    watcher = EnterWatcher(path)
    assert watcher.available
    os.write(master, b"\n")
    assert watcher.wait(2.0) is True
    watcher.close()


def test_without_a_key_press_the_wait_runs_out(terminal):
    _, path = terminal
    watcher = EnterWatcher(path)
    assert watcher.wait(0.1) is False
    watcher.close()


def test_other_keys_without_enter_do_not_skip(terminal):
    master, path = terminal
    watcher = EnterWatcher(path)
    os.write(master, b"abc")                       # the line is not finished: a terminal hands it over only with Enter
    assert watcher.wait(0.2) is False
    watcher.close()


def test_no_terminal_means_nothing_can_be_skipped(tmp_path):
    watcher = EnterWatcher(str(tmp_path / "no-such-tty"))
    assert not watcher.available and watcher.wait(0.01) is False


# ----- the flow stops cleanly ---------------------------------------------------------------------------------------------

def fake_server(monkeypatch):
    class Reply:
        def __init__(self, data, status=200):
            self.data, self.status_code = data, status

        def json(self):
            return self.data

    start = {"device_code": "dev", "user_code": "ABCD-EFGH", "verification_url": "https://x/link", "expires_in": 600, "interval": 3}

    def post(url, **kwargs):
        return Reply(start if url.endswith("/start") else {"status": "pending"})

    monkeypatch.setattr(pairing.httpx, "post", post)


def test_pressing_enter_ends_the_pairing_without_an_error(monkeypatch):
    fake_server(monkeypatch)
    with pytest.raises(pairing.PairingSkipped):
        pairing.pair(lambda info: None, base_url="http://x", interrupt=lambda seconds: True, save=False)


def test_the_interrupt_replaces_the_sleep(monkeypatch):
    fake_server(monkeypatch)
    waits = []
    ticks = iter([0, 1, 2, 3, 10_000])
    with pytest.raises(pairing.PairingError, match="expired"):
        pairing.pair(lambda info: None, base_url="http://x", clock=lambda: next(ticks), save=False,
                     sleep=lambda s: waits.append(("slept", s)), interrupt=lambda s: waits.append(("waited", s)) or False)
    assert waits and all(kind == "waited" for kind, _ in waits)


# ----- the commands ----------------------------------------------------------------------------------------------------------

@pytest.fixture
def deck_env(monkeypatch, tmp_path):
    monkeypatch.setattr(deck_setup, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("LGB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(deck_config, "config_path", lambda: tmp_path / "deck.json")          # not the real ~/.config/lgb/deck.json
    monkeypatch.setenv("APPIMAGE", "/home/deck/Applications/LinuxGameBench.AppImage")
    monkeypatch.delenv("LGB_ANON", raising=False)
    monkeypatch.setattr(deck_setup, "install_service", lambda **k: (True, "service enabled and started"))
    monkeypatch.setattr(deck_cli, "detect_steam_deck", lambda: DeckInfo(is_deck=True, model="LCD", steamos_version="3.8", game_mode=False))
    calls = {"pair": 0}

    def pair(allow_skip=False):
        calls["pair"] += 1
        return "skipped"

    monkeypatch.setattr(deck_cli, "_pair", pair)
    monkeypatch.setattr("linux_game_benchmark.api.auth.is_logged_in", lambda: False)
    return calls


def test_setup_with_the_anonymous_option_never_asks_for_an_account(deck_env):
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes", "--anonymous"])
    assert result.exit_code == 0, flat(result)
    assert deck_env["pair"] == 0
    assert "upload anonymously" in flat(result) and "deck link" in flat(result)


def test_the_environment_variable_does_the_same_for_the_one_line_installer(deck_env, monkeypatch):
    monkeypatch.setenv("LGB_ANON", "1")
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"])
    assert result.exit_code == 0 and deck_env["pair"] == 0 and "upload anonymously" in flat(result)


def test_skipping_the_link_during_setup_still_finishes_and_says_how_to_link_later(deck_env):
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"])
    assert result.exit_code == 0, flat(result)
    assert deck_env["pair"] == 1
    assert "An account is optional" in flat(result) and "deck link" in flat(result)
    assert "Now switch back to Game Mode" in flat(result)


def test_setup_puts_a_link_entry_into_the_application_menu(deck_env, tmp_path):
    runner.invoke(deck_cli.deck_app, ["setup", "--yes", "--anonymous"])
    launcher = tmp_path / "home/.local/share/applications/linuxgamebench-link.desktop"
    text = launcher.read_text()
    assert 'Exec="/home/deck/Applications/LinuxGameBench.AppImage" deck link --pause' in text
    assert "Terminal=true" in text and "Name=Linux Game Bench - link account" in text


def test_the_launcher_quotes_odd_paths_and_goes_away_on_remove(deck_env, tmp_path):
    path = deck_setup.write_link_launcher('/home/deck/My Apps/100% $HOME "x"/lgb.AppImage')
    line = [l for l in path.read_text().splitlines() if l.startswith("Exec=")][0]
    assert line == 'Exec="/home/deck/My Apps/100%% \\$HOME \\"x\\"/lgb.AppImage" deck link --pause'
    assert str(path) in deck_setup.remove_all() and not path.exists()


def test_link_says_so_when_an_account_is_already_linked(monkeypatch):
    session = type("S", (), {"get_username": lambda self: "tom"})()
    monkeypatch.setattr("linux_game_benchmark.api.auth.get_current_session", lambda: session)
    monkeypatch.setattr(deck_cli, "_pair", lambda allow_skip=False: pytest.fail("must not start a second link"))
    result = runner.invoke(deck_cli.deck_app, ["link"])
    assert result.exit_code == 0 and "Already linked as tom" in flat(result) and "deck unlink" in flat(result)


def test_link_starts_the_flow_and_pair_is_still_there_as_the_old_name(monkeypatch):
    monkeypatch.setattr("linux_game_benchmark.api.auth.get_current_session", lambda: None)
    seen = []
    monkeypatch.setattr(deck_cli, "_pair", lambda allow_skip=False: seen.append(allow_skip) or "linked")
    assert runner.invoke(deck_cli.deck_app, ["link"]).exit_code == 0
    assert runner.invoke(deck_cli.deck_app, ["pair"]).exit_code == 0
    assert seen == [True, True]                        # Enter can always cancel a later link as well


def test_a_failed_link_gives_a_failing_exit_code(monkeypatch):
    monkeypatch.setattr("linux_game_benchmark.api.auth.get_current_session", lambda: None)
    monkeypatch.setattr(deck_cli, "_pair", lambda allow_skip=False: "failed")
    assert runner.invoke(deck_cli.deck_app, ["link"]).exit_code == 1


def test_the_menu_entry_waits_for_enter_so_the_window_stays_open(monkeypatch):
    monkeypatch.setattr("linux_game_benchmark.api.auth.get_current_session", lambda: None)
    monkeypatch.setattr(deck_cli, "_pair", lambda allow_skip=False: "linked")
    result = runner.invoke(deck_cli.deck_app, ["link", "--pause"], input="\n")
    assert result.exit_code == 0 and "Press Enter to close" in flat(result)


def test_unlink_goes_back_to_anonymous(monkeypatch):
    session = type("S", (), {"get_username": lambda self: "tom"})()
    state = {"session": session}
    monkeypatch.setattr("linux_game_benchmark.api.auth.get_current_session", lambda: state["session"])
    monkeypatch.setattr("linux_game_benchmark.api.auth.logout", lambda: state.update(session=None) or (True, "ok"))
    result = runner.invoke(deck_cli.deck_app, ["unlink"])
    assert result.exit_code == 0 and "tom unlinked" in flat(result) and "anonymously" in flat(result)
    again = runner.invoke(deck_cli.deck_app, ["unlink"])
    assert again.exit_code == 0 and "already upload anonymously" in flat(again)
