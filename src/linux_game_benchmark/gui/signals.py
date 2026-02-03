"""Centralized signal hub for cross-component communication."""

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """Singleton signal hub. Access via AppSignals.instance()."""

    # Auth
    auth_changed = Signal(bool, str)  # (logged_in, username)

    # Games
    games_loaded = Signal(list)       # list of game dicts
    game_selected = Signal(dict)      # single game dict

    # Benchmark
    benchmark_started = Signal()
    benchmark_recording = Signal()
    benchmark_finished = Signal(dict)  # results dict
    benchmark_error = Signal(str)

    # System
    system_info_loaded = Signal(dict)

    # Settings
    settings_saved = Signal()  # emitted when settings are saved

    # General
    status_message = Signal(str, str)  # (message, level: info/success/error/warning)

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
