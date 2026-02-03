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
        "default_duration": 30,  # seconds
        "gpu_preference": None,  # PCI address of preferred GPU
        "gpu_display_name": None,  # Display name for preferred GPU
        # Game Settings Defaults
        "default_preset": None,
        "default_raytracing": None,
        "default_upscaling": None,
        "default_upscaling_quality": None,
        "default_framegen": None,
        "default_aa": None,
        "default_hdr": None,
        "default_vsync": None,
        "default_framelimit": None,
        "default_cpu_oc": None,
        "default_gpu_oc": None,
    }

    # Valid options for game settings (used for validation)
    VALID_OPTIONS = {
        "preset": ["none", "low", "medium", "high", "ultra", "custom"],
        "raytracing": ["none", "low", "medium", "high", "ultra", "pathtracing"],
        "upscaling": ["none", "fsr1", "fsr2", "fsr3", "fsr4", "dlss", "dlss2", "dlss3", "dlss3.5", "dlss4", "dlss4.5", "xess", "xess1", "xess2", "tsr"],
        "upscaling_quality": ["none", "performance", "balanced", "quality", "ultra-quality", "ultra quality"],
        "framegen": ["none", "fsr3-fg", "dlss3-fg", "dlss4-fg", "dlss4-mfg", "xess-fg", "afmf", "afmf2", "afmf3", "smooth-motion"],
        "aa": ["none", "fxaa", "smaa", "taa", "dlaa", "msaa"],
        "hdr": ["on", "off"],
        "vsync": ["on", "off"],
        "framelimit": ["none", "30", "60", "120", "144", "165", "180", "240", "360"],
        "cpu_oc": ["yes", "no"],
        "gpu_oc": ["yes", "no"],
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

    @property
    def duration(self) -> int:
        """Get default benchmark duration in seconds."""
        return self._prefs.get("default_duration", 30)

    @duration.setter
    def duration(self, value: int) -> None:
        """Set default benchmark duration (30-300 seconds)."""
        if 30 <= value <= 300:
            self._prefs["default_duration"] = value
            self._save()

    @property
    def gpu_preference(self) -> Optional[str]:
        """Get preferred GPU PCI address."""
        return self._prefs.get("gpu_preference")

    @gpu_preference.setter
    def gpu_preference(self, value: Optional[str]) -> None:
        """Set preferred GPU PCI address."""
        self._prefs["gpu_preference"] = value
        self._save()

    @property
    def gpu_display_name(self) -> Optional[str]:
        """Get preferred GPU display name."""
        return self._prefs.get("gpu_display_name")

    @gpu_display_name.setter
    def gpu_display_name(self, value: Optional[str]) -> None:
        """Set preferred GPU display name."""
        self._prefs["gpu_display_name"] = value
        self._save()

    def clear_gpu_preference(self) -> None:
        """Clear GPU preference (reset to ask each time)."""
        self._prefs["gpu_preference"] = None
        self._prefs["gpu_display_name"] = None
        self._save()

    # Game Settings Defaults - generic getter/setter
    def _get_game_setting(self, key: str) -> Optional[str]:
        """Get a game setting default."""
        return self._prefs.get(f"default_{key}")

    def _set_game_setting(self, key: str, value: Optional[str]) -> bool:
        """Set a game setting default with validation."""
        if value is None:
            self._prefs[f"default_{key}"] = None
            self._save()
            return True
        val_lower = value.lower().strip()
        valid = self.VALID_OPTIONS.get(key, [])
        if val_lower not in valid:
            return False
        self._prefs[f"default_{key}"] = val_lower
        self._save()
        return True

    @property
    def default_preset(self) -> Optional[str]:
        return self._get_game_setting("preset")

    @default_preset.setter
    def default_preset(self, value: Optional[str]) -> None:
        self._set_game_setting("preset", value)

    @property
    def default_raytracing(self) -> Optional[str]:
        return self._get_game_setting("raytracing")

    @default_raytracing.setter
    def default_raytracing(self, value: Optional[str]) -> None:
        self._set_game_setting("raytracing", value)

    @property
    def default_upscaling(self) -> Optional[str]:
        return self._get_game_setting("upscaling")

    @default_upscaling.setter
    def default_upscaling(self, value: Optional[str]) -> None:
        self._set_game_setting("upscaling", value)

    @property
    def default_upscaling_quality(self) -> Optional[str]:
        return self._get_game_setting("upscaling_quality")

    @default_upscaling_quality.setter
    def default_upscaling_quality(self, value: Optional[str]) -> None:
        self._set_game_setting("upscaling_quality", value)

    @property
    def default_framegen(self) -> Optional[str]:
        return self._get_game_setting("framegen")

    @default_framegen.setter
    def default_framegen(self, value: Optional[str]) -> None:
        self._set_game_setting("framegen", value)

    @property
    def default_aa(self) -> Optional[str]:
        return self._get_game_setting("aa")

    @default_aa.setter
    def default_aa(self, value: Optional[str]) -> None:
        self._set_game_setting("aa", value)

    @property
    def default_hdr(self) -> Optional[str]:
        return self._get_game_setting("hdr")

    @default_hdr.setter
    def default_hdr(self, value: Optional[str]) -> None:
        self._set_game_setting("hdr", value)

    @property
    def default_vsync(self) -> Optional[str]:
        return self._get_game_setting("vsync")

    @default_vsync.setter
    def default_vsync(self, value: Optional[str]) -> None:
        self._set_game_setting("vsync", value)

    @property
    def default_framelimit(self) -> Optional[str]:
        return self._get_game_setting("framelimit")

    @default_framelimit.setter
    def default_framelimit(self, value: Optional[str]) -> None:
        self._set_game_setting("framelimit", value)

    @property
    def default_cpu_oc(self) -> Optional[str]:
        return self._get_game_setting("cpu_oc")

    @default_cpu_oc.setter
    def default_cpu_oc(self, value: Optional[str]) -> None:
        self._set_game_setting("cpu_oc", value)

    @property
    def default_gpu_oc(self) -> Optional[str]:
        return self._get_game_setting("gpu_oc")

    @default_gpu_oc.setter
    def default_gpu_oc(self, value: Optional[str]) -> None:
        self._set_game_setting("gpu_oc", value)

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
