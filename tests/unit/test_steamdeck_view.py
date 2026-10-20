"""The Steam Deck tab of the desktop app, painted offscreen from a fake overview."""

import pytest

pytest.importorskip("PySide6")

from linux_game_benchmark.deck.overview import DeckOverview, Recording  # noqa: E402


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def make_view(monkeypatch, state):
    from linux_game_benchmark.gui.views import steamdeck_view
    monkeypatch.setattr(steamdeck_view.deck_overview, "collect", lambda: state)
    view = steamdeck_view.SteamDeckView()
    view._timer.stop()
    return view


def labels(view):
    from PySide6.QtWidgets import QLabel
    return " | ".join(label.text() for label in view.findChildren(QLabel) if label.text())


def test_a_ready_deck_shows_model_chord_account_and_recordings(app, monkeypatch):
    state = DeckOverview(is_deck=True, model="LCD", steamos="3.8.28", configured=True, service="active", account="tom",
                         controllers=["/dev/input/event10"], site="http://192.168.0.126:8000",
                         recordings=[Recording("1", "Elden Ring", 60, "uploaded", url="http://x/run/1"),
                                     Recording("2", "Hades", 60, "failed", error="offline")])
    text = labels(make_view(monkeypatch, state))
    assert "Steam Deck LCD  (SteamOS 3.8.28)" in text and "Ready - waiting for the chord" in text
    assert "Linked as tom" in text and "controller found (1)" in text
    assert "2. Hold LB + RB, then press VIEW." in text and "After 60 seconds the recording ends by itself and uploads" in text
    assert "Elden Ring  -  60 s  -  uploaded" in text and "Hades  -  60 s  -  failed  (offline)" in text
    assert "cancel" not in text.lower(), "the old 'unless you cancel it' wording must be gone"


def test_a_pc_gets_the_install_line_for_the_deck(app, monkeypatch):
    state = DeckOverview(is_deck=False, site="http://192.168.0.126:8000")
    view = make_view(monkeypatch, state)
    assert "This computer is not a Steam Deck" in labels(view)
    assert view._install_line.text() == "curl -fsSL http://192.168.0.126:8000/deck | bash"
    assert not view._install_line.isHidden() and not view._install_row.isHidden()


def test_a_deck_does_not_need_the_install_line(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=True, model="OLED", site="http://s"))
    assert view._install_line.isHidden() and view._install_row.isHidden()


@pytest.mark.parametrize("configured, service, expected", [
    (False, "inactive", "Not set up"),
    (True, "inactive", "Set up, but the background service is inactive"),
    (True, "failed", "Set up, but the background service is failed"),
])
def test_setup_state_is_spelled_out(app, monkeypatch, configured, service, expected):
    view = make_view(monkeypatch, DeckOverview(is_deck=True, model="LCD", configured=configured, service=service))
    assert expected in labels(view)
    assert view._teardown_btn.isEnabled() is configured
    assert view._setup_btn.text() == ("Repair / re-apply" if configured else "Set up recorder")


def test_not_linked_says_that_uploads_are_anonymous(app, monkeypatch):
    text = labels(make_view(monkeypatch, DeckOverview(is_deck=True, model="LCD")))
    assert "Not linked - recordings upload anonymously" in text and "Nothing recorded yet." in text


def test_main_window_still_finds_the_detector():
    from linux_game_benchmark.gui.views.steamdeck_view import detect_steamdeck
    is_deck, label = detect_steamdeck()
    assert isinstance(is_deck, bool) and isinstance(label, str)
