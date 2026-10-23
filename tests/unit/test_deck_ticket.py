"""The install button of the website: the install file carries a one-time key (LGB_LINK_TICKET) that links the account
during `deck setup` - no code to type or approve. Without the key (or when it does not work) the old ways stay."""

import os

import httpx
import pytest
from typer.testing import CliRunner

from linux_game_benchmark.deck import cli as deck_cli
from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import pairing
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.detect import DeckInfo

runner = CliRunner()
TICKET = "T" * 43


def flat(result) -> str:
    return " ".join(result.output.split())


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


APPROVED = {"status": "approved", "access_token": "acc", "refresh_token": "ref", "user": {"username": "tom", "email": "t@x.test"}}


# ----- pairing.redeem ----------------------------------------------------------------------------------------------------

def test_redeem_collects_the_session_of_the_ticket(monkeypatch):
    seen = []
    monkeypatch.setattr(pairing.httpx, "post", lambda url, **kw: seen.append((url, kw["json"])) or Reply(APPROVED))
    session = pairing.redeem(f"  {TICKET}\n", base_url="https://x.test/api/v1", save=False)
    assert session.access_token == "acc" and session.refresh_token == "ref" and session.get_username() == "tom"
    assert seen == [("https://x.test/api/v1/auth/device/poll", {"device_code": TICKET})]


@pytest.mark.parametrize("status", [403, 404, 410])
def test_redeem_says_so_when_the_ticket_is_unknown_used_or_expired(monkeypatch, status):
    monkeypatch.setattr(pairing.httpx, "post", lambda url, **kw: Reply({"detail": "This code was already used"}, status))
    with pytest.raises(pairing.PairingError, match="already used"):
        pairing.redeem(TICKET, base_url="https://x.test/api/v1", save=False)


def test_a_network_blip_is_retried_and_the_ticket_is_not_lost(monkeypatch):
    answers = [httpx.ConnectError("down"), httpx.ConnectError("still down"), Reply(APPROVED)]

    def post(url, **kw):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    pauses = []
    monkeypatch.setattr(pairing.httpx, "post", post)
    session = pairing.redeem(TICKET, base_url="https://x.test/api/v1", save=False, sleep=pauses.append)
    assert session.get_username() == "tom" and pauses == [2.0, 2.0]


def test_when_the_server_never_answers_it_gives_up_after_a_few_tries(monkeypatch):
    def post(url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(pairing.httpx, "post", post)
    with pytest.raises(pairing.PairingError, match="did not answer"):
        pairing.redeem(TICKET, base_url="https://x.test/api/v1", save=False, tries=3, sleep=lambda s: None)


# ----- deck setup --------------------------------------------------------------------------------------------------------

@pytest.fixture
def deck_env(monkeypatch, tmp_path):
    state = {"pair": 0, "redeem": [], "env_in_service": "unset", "logged_in": False}
    monkeypatch.setattr(deck_setup, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("LGB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(deck_config, "config_path", lambda: tmp_path / "deck.json")          # not the real ~/.config/lgb/deck.json
    monkeypatch.setenv("APPIMAGE", "/home/deck/Applications/LinuxGameBench.AppImage")
    monkeypatch.delenv("LGB_ANON", raising=False)
    monkeypatch.delenv("LGB_LINK_TICKET", raising=False)

    def install_service(**kw):
        state["env_in_service"] = os.environ.get("LGB_LINK_TICKET")      # what a child process started here would inherit
        return True, "service enabled and started"

    def pair(allow_skip=False):
        state["pair"] += 1
        return "skipped"

    monkeypatch.setattr(deck_setup, "install_service", install_service)
    monkeypatch.setattr(deck_cli, "detect_steam_deck", lambda: DeckInfo(is_deck=True, model="LCD", steamos_version="3.8", game_mode=False))
    monkeypatch.setattr(deck_cli, "_pair", pair)
    monkeypatch.setattr("linux_game_benchmark.api.auth.is_logged_in", lambda: state["logged_in"])
    return state


def redeem_works(state, monkeypatch, username="tom"):
    class Session:
        def get_username(self):
            return username

    def redeem(ticket, **kw):
        state["redeem"].append(ticket)
        return Session()

    monkeypatch.setattr(pairing, "redeem", redeem)


def redeem_fails(state, monkeypatch, message="This code was already used"):
    def redeem(ticket, **kw):
        state["redeem"].append(ticket)
        raise pairing.PairingError(message)

    monkeypatch.setattr(pairing, "redeem", redeem)


def test_the_ticket_links_the_account_without_a_code(deck_env, monkeypatch):
    redeem_works(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET})
    assert result.exit_code == 0, flat(result)
    assert deck_env["redeem"] == [TICKET] and deck_env["pair"] == 0
    assert "linked as tom" in flat(result) and "from the install file" in flat(result)
    assert "Now switch back to Game Mode" in flat(result)


def test_the_ticket_is_never_printed_and_not_handed_to_child_processes(deck_env, monkeypatch):
    redeem_works(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET})
    assert TICKET not in result.output
    assert deck_env["env_in_service"] is None, "the key was still in the environment when the service was set up"


def test_a_ticket_that_does_not_work_falls_back_to_the_code_and_says_why(deck_env, monkeypatch):
    redeem_fails(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET})
    assert result.exit_code == 0, flat(result)
    assert deck_env["pair"] == 1, "no ticket, no link - the normal code flow must follow"
    assert "did not work" in flat(result) and "already used" in flat(result) and "30 minutes" in flat(result)
    assert TICKET not in result.output


def test_a_new_ticket_replaces_an_account_that_was_linked_before(deck_env, monkeypatch):
    deck_env["logged_in"] = True
    redeem_works(deck_env, monkeypatch, username="other")
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET})
    assert deck_env["redeem"] == [TICKET] and "linked as other" in flat(result) and "already linked" not in flat(result)


def test_a_broken_ticket_keeps_the_account_that_was_linked_before(deck_env, monkeypatch):
    deck_env["logged_in"] = True
    redeem_fails(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET})
    assert deck_env["pair"] == 0 and "account already linked" in flat(result) and "did not work" in flat(result)


def test_anonymous_wins_over_a_ticket(deck_env, monkeypatch):
    redeem_works(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"], env={"LGB_LINK_TICKET": TICKET, "LGB_ANON": "1"})
    assert deck_env["redeem"] == [] and deck_env["pair"] == 0 and "upload anonymously" in flat(result)


def test_without_a_ticket_nothing_changes(deck_env, monkeypatch):
    redeem_works(deck_env, monkeypatch)
    result = runner.invoke(deck_cli.deck_app, ["setup", "--yes"])
    assert deck_env["redeem"] == [] and deck_env["pair"] == 1


def test_the_option_stays_out_of_the_help(deck_env):
    result = runner.invoke(deck_cli.deck_app, ["setup", "--help"])
    assert "link-ticket" not in result.output
