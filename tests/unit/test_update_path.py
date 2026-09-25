"""
Update path of the client: version check against the server and the
instructions shown for pipx installs vs. the AppImage.

The check runs against a local fake server (GET /version), so the release
scenario is covered without touching a real stage:
- server announces a newer version  -> update offered
- same or older version on the server -> nothing offered (no update loop)
- server unreachable / broken answer -> nothing offered, no exception
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from linux_game_benchmark.api import client as api_client
from linux_game_benchmark.api.client import BenchmarkAPIClient
from linux_game_benchmark.config.settings import settings
from linux_game_benchmark.gui.update_info import PIPX_COMMAND, site_url, update_instructions


@pytest.fixture
def version_server():
    state = {"body": b"{}", "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/api/v1/version"
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(state["body"])

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def announce(version=None, status=200, raw=None):
        state["status"] = status
        state["body"] = raw if raw is not None else json.dumps({"version": version}).encode()

    yield f"http://127.0.0.1:{server.server_port}/api/v1", announce
    server.shutdown()


def test_newer_server_version_is_offered(version_server, monkeypatch):
    url, announce = version_server
    monkeypatch.setattr(settings, "CLIENT_VERSION", "0.1.46")
    announce("0.1.47")
    assert BenchmarkAPIClient(base_url=url).check_for_updates() == "0.1.47"


@pytest.mark.parametrize("server_version", ["0.1.47", "0.1.46", "0.1.9"])
def test_same_or_older_server_version_is_not_offered(version_server, monkeypatch, server_version):
    """After the release (client 0.1.47) nothing is offered -> no update loop."""
    url, announce = version_server
    monkeypatch.setattr(settings, "CLIENT_VERSION", "0.1.47")
    announce(server_version)
    assert BenchmarkAPIClient(base_url=url).check_for_updates() is None


def test_versions_compare_numerically():
    assert api_client._is_newer_version("0.1.10", "0.1.9")
    assert not api_client._is_newer_version("0.1.9", "0.1.10")


@pytest.mark.parametrize("status, raw", [(500, b"oops"), (200, b"not json"), (200, b'{"version": null}')])
def test_broken_server_answer_offers_nothing(version_server, monkeypatch, status, raw):
    url, announce = version_server
    monkeypatch.setattr(settings, "CLIENT_VERSION", "0.1.46")
    announce(status=status, raw=raw)
    assert BenchmarkAPIClient(base_url=url).check_for_updates() is None


def test_unreachable_server_offers_nothing():
    assert BenchmarkAPIClient(base_url="http://127.0.0.1:9/api/v1").check_for_updates() is None


def test_versions_in_sync():
    """pyproject.toml and settings.py must carry the same version (else update loop)."""
    import tomllib
    from pathlib import Path
    pyproject = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == settings.CLIENT_VERSION


# --- instructions: pipx vs AppImage ---

def test_pipx_install_gets_copy_command():
    how = update_instructions("https://linuxgamebench.com/api/v1", env={})
    assert how.kind == "pipx"
    assert how.copy_text == PIPX_COMMAND and PIPX_COMMAND in how.text
    assert how.open_url is None


def test_appimage_gets_download_page():
    how = update_instructions("https://linuxgamebench.com/api/v1",
                              env={"APPIMAGE": "/home/user/Apps/LinuxGameBench-x86_64.AppImage"})
    assert how.kind == "appimage"
    assert how.open_url == "https://linuxgamebench.com/faq.html#install-gui"
    assert "/home/user/Apps/LinuxGameBench-x86_64.AppImage" in how.text
    assert "pipx" not in how.text
    assert how.copy_text is None


@pytest.mark.parametrize("api, site", [
    ("https://linuxgamebench.com/api/v1", "https://linuxgamebench.com"),
    ("http://192.168.0.70/api/v1/", "http://192.168.0.70"),
    ("http://example.org", "http://example.org"),
])
def test_site_url(api, site):
    assert site_url(api) == site
