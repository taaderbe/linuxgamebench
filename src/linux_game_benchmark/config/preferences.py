"""
User Preferences for Linux Game Benchmark.

Handles loading/saving user preferences from ~/.config/lgb/preferences.json
"""

import json
from pathlib import Path
from typing import Optional


class Preferences:
    """Manages user preferences."""

    DEFAULTS = {
        "default_resolution": "2",  # FHD
        "default_upload": "y",
        "default_continue": "c",
    }

    RESOLUTION_NAMES = {
        "1": "HD (1280x720)",
        "2": "FHD (1920x1080)",
        "3": "WQHD (2560x1440)",
        "4": "UWQHD (3440x1440)",
        "5": "UHD (3840x2160)",
    }

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "lgb"
        self.config_file = self.config_dir / "preferences.json"
        self._prefs = self._load()

    def _load(self) -> dict:
        """Load preferences from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    saved = json.load(f)
                # Merge with defaults (in case new settings are added)
                return {**self.DEFAULTS, **saved}
            except (json.JSONDecodeError, IOError):
                pass
        return self.DEFAULTS.copy()

    def _save(self) -> bool:
        """Save preferences to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self._prefs, f, indent=2)
            return True
        except IOError:
            return False

    @property
    def resolution(self) -> str:
        """Get default resolution (1-5)."""
        return self._prefs.get("default_resolution", "2")

    @resolution.setter
    def resolution(self, value: str) -> None:
        """Set default resolution."""
        if value in ("1", "2", "3", "4", "5"):
            self._prefs["default_resolution"] = value
            self._save()

    @property
    def upload(self) -> str:
        """Get default upload choice (y/n)."""
        return self._prefs.get("default_upload", "y")

    @upload.setter
    def upload(self, value: str) -> None:
        """Set default upload choice."""
        if value.lower() in ("y", "n"):
            self._prefs["default_upload"] = value.lower()
            self._save()

    @property
    def continue_session(self) -> str:
        """Get default continue choice (c/e)."""
        return self._prefs.get("default_continue", "c")

    @continue_session.setter
    def continue_session(self, value: str) -> None:
        """Set default continue choice."""
        if value.lower() in ("c", "e"):
            self._prefs["default_continue"] = value.lower()
            self._save()

    def get_resolution_name(self, key: Optional[str] = None) -> str:
        """Get resolution name for display."""
        key = key or self.resolution
        return self.RESOLUTION_NAMES.get(key, "Unknown")

    def reset(self) -> None:
        """Reset all preferences to defaults."""
        self._prefs = self.DEFAULTS.copy()
        self._save()


# Global instance
preferences = Preferences()
