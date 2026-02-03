"""GUI views (tab content panels)."""

from linux_game_benchmark.gui.views.games_view import GamesView
from linux_game_benchmark.gui.views.benchmark_view import BenchmarkView
from linux_game_benchmark.gui.views.my_benchmarks_view import MyBenchmarksView
from linux_game_benchmark.gui.views.system_info_view import SystemInfoView
from linux_game_benchmark.gui.views.settings_view import SettingsView

__all__ = [
    "GamesView",
    "BenchmarkView",
    "MyBenchmarksView",
    "SystemInfoView",
    "SettingsView",
]
