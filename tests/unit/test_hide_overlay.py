"""Overlay hiding: nothing visible in the corner, but MangoHud keeps logging every sensor.

MangoHud 0.8 stops writing its log with `no_display`, so "hidden" must be a transparent overlay - these tests pin that.
"""
import json

import pytest

from linux_game_benchmark.config.preferences import Preferences
from linux_game_benchmark.mangohud.config_manager import HIDDEN_OVERLAY_LINES, MangoHudConfigManager
from linux_game_benchmark.mangohud.manager import MangoHudManager


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path


def active_lines(text: str) -> list:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_hidden_overlay_is_transparent_never_no_display(home, tmp_path):
    mgr = MangoHudConfigManager()
    assert mgr.set_benchmark_config(tmp_path / "logs", show_hud=False, manual_logging=True)
    lines = active_lines(mgr.config_file.read_text())
    assert "no_display" not in lines, "no_display stops MangoHud 0.8 from logging"
    for needed in ("alpha=0", "background_alpha=0", "font_size=1"):
        assert needed in lines
    assert "font_size=24" not in lines, "the visible layout must not be in the hidden config"


def test_hidden_overlay_still_logs_every_sensor(home, tmp_path):
    shown, hidden = MangoHudConfigManager(), MangoHudConfigManager()
    shown.set_benchmark_config(tmp_path / "a", show_hud=True, manual_logging=True)
    shown_lines = set(active_lines(shown.config_file.read_text()))
    hidden.set_benchmark_config(tmp_path / "b", show_hud=False, manual_logging=True)
    hidden_lines = set(active_lines(hidden.config_file.read_text()))
    sensors = {"cpu_stats", "gpu_stats", "cpu_temp", "gpu_temp", "gpu_power", "vram", "frametime", "fps"}
    assert sensors <= shown_lines and sensors <= hidden_lines
    assert "toggle_logging=Shift_L+F2" in hidden_lines


def test_visible_overlay_is_unchanged(home, tmp_path):
    mgr = MangoHudConfigManager()
    mgr.set_benchmark_config(tmp_path / "logs", show_hud=True, manual_logging=True)
    lines = active_lines(mgr.config_file.read_text())
    assert "font_size=24" in lines and "background_alpha=0.5" in lines and "alpha=0" not in lines


def test_second_generator_hides_the_same_way(tmp_path):
    text = MangoHudManager(output_dir=tmp_path).generate_config(tmp_path / "logs", show_hud=False)
    lines = active_lines(text)
    assert "no_display" not in lines
    assert all(line in lines for line in HIDDEN_OVERLAY_LINES if not line.startswith("#"))


def test_preference_defaults_to_visible_and_is_remembered(home):
    assert Preferences().hide_overlay is False
    Preferences().hide_overlay = True
    assert Preferences().hide_overlay is True                      # a fresh object reads it from disk
    assert json.loads((home / ".config" / "lgb" / "preferences.json").read_text())["hide_overlay"] is True
    Preferences().hide_overlay = False
    assert Preferences().hide_overlay is False


def test_old_preferences_file_without_the_key_means_visible(home):
    path = home / ".config" / "lgb" / "preferences.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"default_resolution": "3"}))
    prefs = Preferences()
    assert prefs.hide_overlay is False and prefs.resolution == "3"


def test_cli_help_mentions_both_flags():
    from typer.testing import CliRunner
    from linux_game_benchmark.cli import app
    out = CliRunner().invoke(app, ["benchmark", "--help"]).output
    assert "--show-hud" in out and "--no-hud" in out


def test_settings_panel_checkbox_follows_and_saves_the_preference(home, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from linux_game_benchmark.gui.widgets.settings_panel import SettingsPanel
    app = QApplication.instance() or QApplication([])
    panel = SettingsPanel()
    assert panel.get_show_overlay() is True                        # default: overlay visible
    panel._hide_overlay.setChecked(True)
    assert panel.get_show_overlay() is False
    assert Preferences().hide_overlay is True                      # written on click, the CLI reads the same value
    assert SettingsPanel().get_show_overlay() is False             # next start remembers it
    panel._hide_overlay.setChecked(False)
    assert Preferences().hide_overlay is False
    del app


def test_cli_flag_beats_the_saved_choice_and_default_follows_it(home):
    from linux_game_benchmark.cli import _overlay_visible
    assert _overlay_visible(None) is True                          # nothing saved: visible
    Preferences().hide_overlay = True
    assert _overlay_visible(None) is False                         # saved choice applies without a flag
    assert _overlay_visible(True) is True and _overlay_visible(False) is False
    Preferences().hide_overlay = False
    assert _overlay_visible(False) is False
