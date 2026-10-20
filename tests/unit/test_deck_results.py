"""The website's Deck results as the desktop app uses them: filter, sort, describe."""

from linux_game_benchmark.deck import results

DATA = {
    "runs": 21, "games": 3, "players": 2,
    "models": {"steam_deck_lcd": {"runs": 15}, "steam_deck_oled": {"runs": 6}},
    "top_games": [
        {"name": "Hades", "steam_app_id": 1145360, "runs": 3, "fps_avg": 59, "fps_1low": 50,
         "models": {"steam_deck_lcd": {"runs": 2, "fps_avg": 59, "fps_1low": 50}, "steam_deck_oled": {"runs": 1, "fps_avg": 60, "fps_1low": 55}}},
        {"name": "Elden Ring", "steam_app_id": 1245620, "runs": 4, "fps_avg": 36, "fps_1low": 28,
         "models": {"steam_deck_lcd": {"runs": 4, "fps_avg": 32, "fps_1low": 25}}},
        {"name": "Baldur's Gate 3", "steam_app_id": 1086940, "runs": 2, "fps_avg": 28, "fps_1low": 20,
         "models": {"steam_deck_oled": {"runs": 2, "fps_avg": 31, "fps_1low": 24}}},
    ],
}


def names(**kw):
    return [r["name"] for r in results.games(DATA, **kw)]


def test_default_order_is_top_fps():
    assert names() == ["Hades", "Elden Ring", "Baldur's Gate 3"]


def test_other_orders():
    assert names(sort="runs") == ["Elden Ring", "Hades", "Baldur's Gate 3"]
    assert names(sort="name") == ["Baldur's Gate 3", "Elden Ring", "Hades"]


def test_model_filter_uses_the_numbers_of_that_model():
    rows = results.games(DATA, model="steam_deck_lcd")
    assert [r["name"] for r in rows] == ["Hades", "Elden Ring"]
    assert {r["name"]: (r["fps"], r["runs"]) for r in rows} == {"Hades": (59, 2), "Elden Ring": (32, 4)}
    assert names(model="steam_deck_oled") == ["Hades", "Baldur's Gate 3"]


def test_search_is_case_insensitive_and_combines_with_the_model():
    assert names(query="  ELDEN ") == ["Elden Ring"]
    assert names(query="elden", model="steam_deck_oled") == []
    assert names(query="zzz") == []


def test_stats_row_has_a_chip_per_model_that_exists():
    assert results.stats(DATA) == [("runs", "21"), ("games", "3"), ("players", "2"), ("LCD runs", "15"), ("OLED runs", "6")]
    assert results.stats({"runs": 0})[:3] == [("runs", "0"), ("games", "0"), ("players", "0")]


def test_fps_levels_match_the_website():
    assert [results.fps_level(v) for v in (60, 55, 54.9, 30, 29.9, 0)] == ["good", "good", "mid", "mid", "low", "low"]


def test_power_line():
    state = {"power": {"source": "battery", "battery_power_avg_w": 12.0}, "limits": {"tdp_w": 12}}
    assert results.describe_power(state, 48) == "Battery - 12 W TDP - 4.0 FPS/W"
    assert results.describe_power({"power": {"source": "ac"}, "limits": {"tdp_w": 15.0}}, 60) == "Plugged in - 15 W TDP"
    assert results.describe_power(None) == "" and results.describe_power({}) == ""


def test_run_line_and_model_filter_for_runs():
    runs = [
        {"id": 1, "timestamp": "2026-10-20T19:50:21", "device_class": "steam_deck_lcd", "resolution": "1280x800", "username": "tom",
         "run": {"metrics": {"fps": {"average": 45.4, "1_percent_low": 36.2}}}, "device_state": None},
        {"id": 2, "timestamp": "2026-10-19T10:00:00", "device_class": "steam_deck_oled", "resolution": "1280x800", "username": None,
         "run": {"metrics": {"fps": {"average": 60}}}},
    ]
    line = results.describe_run(runs[0])
    assert (line["date"], line["model"], line["fps"], line["low1"], line["player"]) == ("2026-10-20", "LCD", 45, 36, "tom")
    assert [r["id"] for r in results.runs_for(runs)] == [1, 2]
    assert [r["id"] for r in results.runs_for(runs, "steam_deck_oled")] == [2]
    assert results.runs_for(runs, "steam_deck_oled")[0]["player"] == "anonymous"


def test_a_game_name_with_a_slash_is_encoded_for_the_url(monkeypatch):
    seen = {}

    class Reply:
        def raise_for_status(self): pass
        def json(self): return {"runs": []}

    monkeypatch.setattr(results.httpx, "get", lambda url, **kw: seen.update(url=url, params=kw["params"]) or Reply())
    results.fetch_runs("SHENZHEN I/O")
    assert seen["url"].endswith("/game/SHENZHEN%20I%2FO/all-runs") and seen["params"] == {"device": "steamdeck"}
