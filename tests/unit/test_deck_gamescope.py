"""Gamescope's view of the running game: render resolution, frame limit, scaling. The texts are real outputs from a Steam Deck in Game Mode."""

import pytest

from linux_game_benchmark.deck import gamescope

CONTROL = """GAMESCOPE_FSR_SHARPNESS(CARDINAL) = 2
GAMESCOPE_NEW_SCALING_SCALER(CARDINAL) = 0
GAMESCOPE_NEW_SCALING_FILTER(CARDINAL) = 2
GAMESCOPE_FPS_LIMIT(CARDINAL) = 40
GAMESCOPE_FOCUSED_WINDOW(CARDINAL) = 23068673
GAMESCOPE_FOCUSED_APP(CARDINAL) = 1672970
"""
NOT_CONTROL = """GAMESCOPE_FSR_SHARPNESS:  not defined.
GAMESCOPE_NEW_SCALING_SCALER:  not defined.
GAMESCOPE_NEW_SCALING_FILTER:  not defined.
GAMESCOPE_FPS_LIMIT:  not defined.
GAMESCOPE_FOCUSED_WINDOW:  not defined.
GAMESCOPE_FOCUSED_APP:  not defined.
"""
WINDOW = """
xwininfo: Window id: 0x1600001 "Minecraft Dungeons  "

  Absolute upper-left X:  0
  Absolute upper-left Y:  0
  Relative upper-left X:  0
  Relative upper-left Y:  0
  Width: 1280
  Height: 720
  Depth: 24
  Map State: IsViewable
"""
TREE = """
xwininfo: Window id: 0x345 (the root window) (has no name)

  Root window id: 0x345 (the root window) (has no name)
  Parent window id: 0x0 (none)
     23 children:
     0x1600001 "Minecraft Dungeons  ": ("steam_app_1672970" "steam_app_1672970")  1280x720+0+0  +0+0
        1 child:
        0x1400048 (has no name): ()  1280x720+0+0  +0+0
     0x1600005 (has no name): ("steam_app_1672970" "steam_app_1672970")  112x27+0+0  +0+0
     0x1600004 (has no name): ("steam_app_1672970" "steam_app_1672970")  960x600+0+0  +0+0
     0x1400046 (has no name): ()  1x1+-1+-1  +-1+-1
     0x1200001 "Steam": ("steam_app_1672970" "steam_app_1672970")  400x300+40+40  +40+40
     0x800001 (has no name): ()  1280x720+0+0  +0+0
"""
APP, PID = 1672970, 41471


def fake(control=CONTROL, window=WINDOW, tree=TREE, calls=None):
    """A runner that answers like xprop / xwininfo would, and records what was asked."""
    def run(args):
        if calls is not None:
            calls.append(args)
        if args[0] == "xprop":
            return control if args[2] == ":0" else NOT_CONTROL
        if args[0] == "xwininfo" and "-tree" in args:
            return tree
        if args[0] == "xwininfo":
            return window
        return ""
    return run


def probe(**kw):
    runner = fake(**{k: kw.pop(k) for k in ("control", "window", "tree", "calls") if k in kw})
    return gamescope.probe(kw.get("pid", PID), kw.get("app", APP), run=runner,
                           displays=lambda: kw.get("displays", [":0", ":1"]), display_of=lambda pid: kw.get("on", ":1"))


def test_the_real_texts_parse():
    assert gamescope.parse_props(CONTROL) == {"GAMESCOPE_FSR_SHARPNESS": 2, "GAMESCOPE_NEW_SCALING_SCALER": 0,
                                              "GAMESCOPE_NEW_SCALING_FILTER": 2, "GAMESCOPE_FPS_LIMIT": 40,
                                              "GAMESCOPE_FOCUSED_WINDOW": 23068673, "GAMESCOPE_FOCUSED_APP": 1672970}
    assert gamescope.parse_props(NOT_CONTROL) == {} and gamescope.parse_props("") == {}
    assert gamescope.parse_window(WINDOW) == (1280, 720)
    assert gamescope.parse_window(WINDOW.replace("IsViewable", "IsUnMapped")) is None and gamescope.parse_window("") is None
    tree = gamescope.parse_tree(TREE)
    assert ("0x1600001", "steam_app_1672970", 1280, 720) in tree and ("0x1600004", "steam_app_1672970", 960, 600) in tree
    assert all(entry[0] != "0x1400048" for entry in tree), "children of a window are not top-level windows"


def test_the_game_in_game_mode_gives_its_render_size_and_the_steam_settings():
    assert probe() == {"render_mode": "1280x720", "fps_limit": 40, "scaling_filter": "fsr", "scaling_mode": "auto", "fsr_sharpness": 2}


def test_the_focused_window_is_asked_for_on_the_games_display_not_on_the_control_display():
    calls = []
    probe(calls=calls)
    window_call = next(c for c in calls if c[0] == "xwininfo")
    assert window_call == ["xwininfo", "-display", ":1", "-id", "0x1600001"]


def test_no_limit_is_a_zero_and_other_filters_have_no_sharpness():
    control = CONTROL.replace("GAMESCOPE_FPS_LIMIT(CARDINAL) = 40", "GAMESCOPE_FPS_LIMIT(CARDINAL) = 0").replace("FILTER(CARDINAL) = 2", "FILTER(CARDINAL) = 1")
    seen = probe(control=control)
    assert seen["fps_limit"] == 0 and seen["scaling_filter"] == "nearest" and "fsr_sharpness" not in seen


@pytest.mark.parametrize("index, name", list(enumerate(gamescope.FILTERS)))
def test_every_filter_index_has_its_name(index, name):
    assert gamescope.settings_from({"GAMESCOPE_NEW_SCALING_FILTER": index})["scaling_filter"] == name


def test_the_order_is_the_one_gamescope_documents():
    assert gamescope.FILTERS == ("linear", "nearest", "fsr", "nis", "pixel")
    assert gamescope.SCALERS == ("auto", "integer", "fit", "fill", "stretch")


def test_unknown_numbers_are_left_out():
    assert gamescope.settings_from({"GAMESCOPE_NEW_SCALING_FILTER": 9, "GAMESCOPE_NEW_SCALING_SCALER": 7, "GAMESCOPE_FPS_LIMIT": 5000}) == {}


def test_another_app_in_front_gives_the_games_size_but_not_the_settings_of_that_other_app():
    control = CONTROL.replace("FOCUSED_APP(CARDINAL) = 1672970", "FOCUSED_APP(CARDINAL) = 769")        # the Steam menu is in front
    seen = probe(control=control)
    assert seen == {"render_mode": "1280x720"}, "the frame limit and scaling shown now are those of Steam's own screen"


def test_the_focused_window_of_another_app_is_not_used_for_the_size():
    control = CONTROL.replace("FOCUSED_APP(CARDINAL) = 1672970", "FOCUSED_APP(CARDINAL) = 769")
    calls = []
    probe(control=control, calls=calls)
    assert not any(c[0] == "xwininfo" and "-id" in c for c in calls), "asked for the focused window although it is not the game's"


def test_without_gamescope_the_games_own_window_is_found_by_its_class():
    seen = probe(displays=[":1"])
    assert seen == {"render_mode": "1280x720"}, "settings come from Gamescope only; the window by class is the largest of the game's windows"


def test_a_window_of_another_program_is_not_taken():
    tree = TREE.replace("steam_app_1672970", "firefox")
    assert probe(displays=[":1"], tree=tree) == {}


def test_nothing_is_guessed_when_the_tools_say_nothing():
    runner = lambda args: ""
    assert gamescope.probe(PID, APP, run=runner, displays=lambda: [":0"], display_of=lambda pid: ":1") == {}
    assert gamescope.probe(None, None, run=runner, displays=lambda: [], display_of=lambda pid: None) == {}


def test_tiny_or_huge_windows_are_not_a_game_resolution():
    for window in (WINDOW.replace("Width: 1280", "Width: 1").replace("Height: 720", "Height: 1"),
                   WINDOW.replace("Width: 1280", "Width: 90000")):
        assert "render_mode" not in probe(window=window, displays=[":0", ":1"], tree="")


def test_the_most_common_resolution_wins_over_a_moment_in_a_menu():
    looks = [{"render_mode": "1280x720", "fps_limit": 40}, {"render_mode": "1280x800"}, {"render_mode": "1280x720", "fps_limit": 30}]
    assert gamescope.condense(looks) == {"render_mode": "1280x720", "fps_limit": 30}
    assert gamescope.condense([{}, {}]) == {} and gamescope.condense([]) == {}


def test_sharpness_only_counts_with_fsr():
    assert "fsr_sharpness" not in gamescope.condense([{"scaling_filter": "linear", "fsr_sharpness": 2}])
    assert gamescope.condense([{"scaling_filter": "fsr", "fsr_sharpness": 2}])["fsr_sharpness"] == 2


def test_the_games_display_is_read_from_its_environment(tmp_path):
    (tmp_path / "proc" / "41471").mkdir(parents=True)
    (tmp_path / "proc" / "41471" / "environ").write_bytes(b"HOME=/home/deck\0DISPLAY=:1\0SteamAppId=1672970\0")
    assert gamescope.game_display(41471, root=str(tmp_path)) == ":1"
    (tmp_path / "proc" / "41471" / "environ").write_bytes(b"DISPLAY=evil;rm\0")
    assert gamescope.game_display(41471, root=str(tmp_path)) is None
    assert gamescope.game_display(99999, root=str(tmp_path)) is None and gamescope.game_display(None) is None


def test_host_tools_do_not_inherit_the_appimages_library_path(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_x/usr/lib")
    monkeypatch.setenv("PYTHONHOME", "/tmp/.mount_x/usr")
    env = gamescope.host_env()
    assert "LD_LIBRARY_PATH" not in env and "PYTHONHOME" not in env and "PATH" in env


def test_a_missing_tool_is_just_nothing():
    assert gamescope.run_tool(["/nonexistent/xprop", "-root"]) == ""
