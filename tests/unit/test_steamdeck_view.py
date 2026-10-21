"""The Steam Deck tab of the desktop app, painted offscreen from a fake overview."""

import pytest

pytest.importorskip("PySide6")

from linux_game_benchmark.deck.overview import DeckOverview, Recording  # noqa: E402


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


SUMMARY = {
    "runs": 21, "games": 3, "players": 2,
    "models": {"steam_deck_lcd": {"runs": 15}, "steam_deck_oled": {"runs": 6}},
    "top_games": [
        {"name": "Hades", "steam_app_id": 1145360, "runs": 3, "fps_avg": 59, "fps_1low": 50,
         "models": {"steam_deck_lcd": {"runs": 2, "fps_avg": 59, "fps_1low": 50}, "steam_deck_oled": {"runs": 1, "fps_avg": 60, "fps_1low": 55}}},
        {"name": "Elden Ring", "steam_app_id": 1245620, "runs": 4, "fps_avg": 36, "fps_1low": 28,
         "models": {"steam_deck_lcd": {"runs": 4, "fps_avg": 32, "fps_1low": 25}}},
    ],
}
RUNS = [{"id": 7, "timestamp": "2026-10-20T19:50:21", "device_class": "steam_deck_lcd", "resolution": "1280x800", "username": "tom",
         "run": {"metrics": {"fps": {"average": 45.4, "1_percent_low": 36.2}}},
         "device_state": {"power": {"source": "battery"}, "limits": {"tdp_w": 12}}}]


def make_view(monkeypatch, state, summary=None, runs=None, error=""):
    from linux_game_benchmark.gui.views import steamdeck_view
    monkeypatch.setattr(steamdeck_view.deck_overview, "collect", lambda scan_controllers=True: state)

    def fetch_summary():
        if error:
            raise RuntimeError(error)
        return summary if summary is not None else SUMMARY

    monkeypatch.setattr(steamdeck_view.deck_results, "fetch_summary", fetch_summary)
    monkeypatch.setattr(steamdeck_view.deck_results, "fetch_runs", lambda name: RUNS if runs is None else runs)
    view = steamdeck_view.SteamDeckView()
    view._timer.stop()
    settle(view)
    return view


def settle(view):
    """Let the background request finish and deliver its answer."""
    from PySide6.QtWidgets import QApplication
    if view._summary_job is not None:
        view._summary_job.wait(5000)
    for _ in range(5):
        QApplication.processEvents()


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
    assert "2. Hold L1 + R1, then press VIEW (the small button left of the screen with two overlapping squares)." in text and "After 60 seconds the recording ends by itself and uploads" in text
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
    assert "No account - recordings upload anonymously" in text and "Nothing recorded yet." in text


def test_main_window_still_finds_the_detector():
    from linux_game_benchmark.gui.views.steamdeck_view import detect_steamdeck
    is_deck, label = detect_steamdeck()
    assert isinstance(is_deck, bool) and isinstance(label, str)


# ----- the results page (same numbers as the website) ---------------------------------------------------------------

def game_names(view):
    return [row._row["name"] for row in view._rows]


def test_a_deck_that_is_not_set_up_starts_at_the_setup_everybody_else_at_the_results(app, monkeypatch):
    assert make_view(monkeypatch, DeckOverview(is_deck=True, model="LCD"))._stack.currentIndex() == 1
    assert make_view(monkeypatch, DeckOverview(is_deck=True, model="LCD", configured=True, service="active"))._stack.currentIndex() == 0
    assert make_view(monkeypatch, DeckOverview(is_deck=False))._stack.currentIndex() == 0


def test_results_show_the_stats_and_games_best_first(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=False))
    assert game_names(view) == ["Hades", "Elden Ring"]
    text = labels(view)
    assert "21" in text and "RUNS" in text and "LCD RUNS" in text and "OLED RUNS" in text
    assert "LCD 59  OLED 60" in text and "4 runs" in text


def test_model_filter_search_and_sort(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=False))
    view._set_model("steam_deck_oled")
    assert game_names(view) == ["Hades"]
    view._set_model("steam_deck_lcd")
    assert game_names(view) == ["Hades", "Elden Ring"]
    view._search.setText("elden")
    assert game_names(view) == ["Elden Ring"]
    view._search.setText("")
    view._set_sort("name")
    assert game_names(view) == ["Elden Ring", "Hades"]
    view._set_sort("runs")
    assert game_names(view) == ["Elden Ring", "Hades"]
    view._search.setText("nothing like this")
    assert game_names(view) == [] and "No games match this filter." in labels(view)


def test_opening_a_game_loads_its_runs(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=False, site="http://s"))
    row = view._rows[0]
    row._toggle()
    row._job.wait(5000)
    settle(view)
    text = labels(view)
    assert "2026-10-20  -  LCD  -  1280x800  -  45 FPS (1% low 36)  -  Battery - 12 W TDP  -  tom" in text
    assert not row._body.isHidden()
    row._toggle()
    assert row._body.isHidden()


def test_a_failed_request_is_explained(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=False), error="offline")
    assert "could not be loaded (offline)" in labels(view) and game_names(view) == []


def test_no_runs_yet_invites_to_set_up(app, monkeypatch):
    view = make_view(monkeypatch, DeckOverview(is_deck=False), summary={"runs": 0, "games": 0, "players": 0, "top_games": []})
    assert "No Deck runs yet" in labels(view)


def test_nothing_is_cut_off_on_a_narrow_window(app, monkeypatch):
    """The Deck's screen is 1280x800 with large text: cards wrap, the search row is its own, no horizontal scrolling."""
    from PySide6.QtWidgets import QScrollArea
    view = make_view(monkeypatch, DeckOverview(is_deck=False, site="http://s"))
    view.resize(640, 800)
    view.show()
    settle(view)
    for index in (0, 1):
        view._show_page(index)
        settle(view)
        scroll = view._stack.currentWidget()
        assert isinstance(scroll, QScrollArea)
        assert scroll.horizontalScrollBar().maximum() == 0, f"page {index} scrolls sideways at 640 px"
    view.resize(1200, 800)
    settle(view)
    assert len({view._stats_box.getItemPosition(i)[0] for i in range(view._stats_box.count())}) == 1, "five cards fit one row on a wide window"
    view.resize(400, 800)
    settle(view)
    assert len({view._stats_box.getItemPosition(i)[0] for i in range(view._stats_box.count())}) > 1, "cards wrap on a narrow window"


def test_a_deck_starts_the_app_at_normal_size_everything_else_at_the_4k_default(monkeypatch, tmp_path):
    from linux_game_benchmark.deck import detect
    from linux_game_benchmark.gui import app as gui_app

    class Info:
        def __init__(self, is_deck): self.is_deck = is_deck

    monkeypatch.setattr(detect, "detect_steam_deck", lambda: Info(True))
    assert gui_app.default_ui_scale() == 1.0
    monkeypatch.setattr(detect, "detect_steam_deck", lambda: Info(False))
    assert gui_app.default_ui_scale() == 2.0

    monkeypatch.setattr(detect, "detect_steam_deck", lambda: Info(True))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    gui_app._apply_ui_scale()
    import os
    assert os.environ["QT_SCALE_FACTOR"] == "1.0"
    (tmp_path / ".config/lgb").mkdir(parents=True)
    (tmp_path / ".config/lgb/gui_state.json").write_text('{"ui_scale": 1.5}')
    gui_app._apply_ui_scale()
    assert os.environ["QT_SCALE_FACTOR"] == "1.5", "a scale the user chose always wins"
    os.environ.pop("QT_SCALE_FACTOR", None)
