"""PySide6 GUI for Linux Game Benchmark.

Optional GUI frontend. Install with: pip install linux-game-benchmark[gui]
"""

import sys


def launch():
    """Entry point for lgb-gui command."""
    try:
        from PySide6 import QtWidgets  # noqa: F401
    except ImportError:
        print(
            "ERROR: PySide6 is not installed.\n"
            "Install it with: pip install linux-game-benchmark[gui]\n"
            "Or: pip install PySide6"
        )
        sys.exit(1)

    from linux_game_benchmark.gui.app import run_app
    sys.exit(run_app())
