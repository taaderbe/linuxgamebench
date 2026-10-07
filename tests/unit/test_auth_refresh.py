"""
Tests for token renewal when several lgb processes (CLI, GUI) share ~/.config/lgb/auth.json.

The server issues single-use refresh tokens (each /auth/refresh consumes the token and returns a new one).
A process that still holds a consumed token must NOT log the user out: it takes the newer tokens from
auth.json. Only a refresh token the server rejects (401) ends the login; rate limits, server errors and
network problems keep it.

A tiny fake server (httpx.MockTransport) stands in for the real one, no network needed.
"""

import base64
import json
import os
import stat
import threading
import time
from pathlib import Path

import httpx
import pytest

from linux_game_benchmark.api import auth
from linux_game_benchmark.api.auth import AuthSession, TokenManager
from linux_game_benchmark.config.settings import settings

REAL_CLIENT = httpx.Client


def make_jwt(exp: float) -> str:
    """Unsigned JWT-shaped token; the client only reads `exp`."""
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64({'exp': int(exp), 'n': time.time_ns()})}.sig"


class FakeServer:
    """Single-use refresh tokens, like the real /auth/refresh."""

    def __init__(self, delay: float = 0.0):
        self.valid = set()
        self.calls = []
        self.forced_status = None
        self.delay = delay
        self.on_first_call = None
        self._n = 0
        self._lock = threading.Lock()

    def issue(self) -> str:
        with self._lock:
            self._n += 1
            token = f"refresh-{self._n}"
            self.valid.add(token)
            return token

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/auth/refresh")
        token = json.loads(request.content)["refresh_token"]
        self.calls.append(token)
        if self.on_first_call and len(self.calls) == 1:
            self.on_first_call()
        if self.delay:
            time.sleep(self.delay)
        if self.forced_status:
            return httpx.Response(self.forced_status, json={"detail": "nope"})
        with self._lock:
            if token not in self.valid:
                return httpx.Response(401, json={"detail": "Session expired or revoked"})
            self.valid.discard(token)
        return httpx.Response(200, json={
            "access_token": make_jwt(time.time() + 900), "refresh_token": self.issue(),
            "token_type": "bearer", "expires_in": 900,
        })


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """Isolated auth.json + fake server that every httpx.Client created by the module talks to."""
    auth_file = tmp_path / "auth.json"
    monkeypatch.setattr(settings, "get_auth_file", lambda: auth_file)
    server = FakeServer()

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return REAL_CLIENT(transport=httpx.MockTransport(server.handler), **kwargs)

    monkeypatch.setattr(auth.httpx, "Client", client_factory)

    class Env:
        pass

    e = Env()
    e.file, e.server = auth_file, server

    def login(expired: bool = True) -> AuthSession:
        session = AuthSession(
            access_token=make_jwt(time.time() - 30 if expired else time.time() + 900),
            refresh_token=server.issue(), user={"username": "tester"}, stage="rc")
        session.save()
        return session

    e.login = login
    return e


class TestAuthFile:
    def test_saved_file_is_private(self, env):
        env.login()
        assert stat.S_IMODE(env.file.stat().st_mode) == 0o600

    def test_save_replaces_existing_file_without_leftovers(self, env):
        env.login()
        env.login()
        assert [p.name for p in env.file.parent.iterdir() if p.name != "auth.json.lock"] == ["auth.json"]
        assert AuthSession.load() is not None

    def test_overwrite_tightens_an_old_world_readable_file(self, env):
        env.file.write_text("{}")
        os.chmod(env.file, 0o644)
        env.login()
        assert stat.S_IMODE(env.file.stat().st_mode) == 0o600


class TestRefresh:
    def test_expired_token_is_refreshed_and_stored(self, env):
        old = env.login()
        manager = TokenManager()
        token = manager.get_access_token()
        assert token and token != old.access_token
        assert AuthSession.load().refresh_token != old.refresh_token
        assert len(env.server.calls) == 1

    def test_valid_token_does_not_touch_the_server(self, env):
        env.login(expired=False)
        assert TokenManager().get_access_token()
        assert env.server.calls == []

    def test_stale_gui_takes_tokens_another_process_just_renewed(self, env):
        """The reported bug: GUI keeps R1 in memory, CLI renews (R1 consumed), GUI must stay logged in."""
        env.login()
        gui = TokenManager()
        gui._get_session()                         # GUI loaded auth.json (R1)
        assert TokenManager().get_access_token()   # CLI renewed -> R1 consumed, R2 on disk
        calls_before = len(env.server.calls)

        token = gui.get_access_token()             # GUI's own access token is expired too
        assert token
        assert env.file.exists()
        assert len(env.server.calls) == calls_before, "GUI should reuse the CLI's fresh tokens, not call the server"

    def test_stale_gui_uses_disk_refresh_token_when_disk_access_token_is_expired_too(self, env):
        env.login()
        gui = TokenManager()
        gui._get_session()
        cli = TokenManager()
        assert cli.get_access_token()
        disk = AuthSession.load()
        disk.access_token = make_jwt(time.time() - 30)   # CLI's token ran out as well, its refresh token is current
        disk.save()

        assert gui.get_access_token()
        assert env.server.calls[-1] == disk.refresh_token  # sent the current token, not the consumed R1
        assert env.file.exists()

    def test_401_with_nothing_newer_logs_out(self, env):
        env.login()
        env.server.valid.clear()                    # session revoked on the server
        manager = TokenManager()
        assert manager.get_access_token() is None
        assert not env.file.exists()

    def test_401_while_another_process_rotated_meanwhile_retries_with_the_new_tokens(self, env):
        env.login()

        def other_process_renews():
            env.server.valid.discard("refresh-1")   # R1 consumed by the other process -> this call answers 401
            AuthSession(access_token=make_jwt(time.time() - 30), refresh_token=env.server.issue(),
                        user={"username": "tester"}, stage="rc").save()

        env.server.on_first_call = other_process_renews
        assert TokenManager().get_access_token()
        assert env.file.exists()
        assert len(env.server.calls) == 2 and env.server.calls[0] != env.server.calls[1]

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_busy_server_keeps_the_login(self, env, status):
        env.login()
        before = env.file.read_text()
        env.server.forced_status = status
        manager = TokenManager()
        assert manager.get_access_token() is None   # no token this time ...
        assert env.file.exists() and env.file.read_text() == before   # ... but still logged in
        env.server.forced_status = None
        assert manager.get_access_token()           # next call works

    def test_network_error_keeps_the_login(self, env, monkeypatch):
        env.login()
        before = env.file.read_text()

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(auth.httpx, "Client", boom)
        assert TokenManager().get_access_token() is None
        assert env.file.read_text() == before

    def test_two_processes_refresh_at_once_with_one_server_call(self, env):
        """Both start with the same expired session; the lock makes the second one reuse the first one's result."""
        env.server.delay = 0.3                     # widen the window so both really overlap
        env.login()
        results, errors = [], []

        def worker():
            try:
                results.append(TokenManager().get_access_token())
            except Exception as exc:               # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert not errors
        assert all(results) and len(results) == 4
        assert len(env.server.calls) == 1
        assert env.file.exists()
