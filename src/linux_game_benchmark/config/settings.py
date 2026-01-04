"""
Application settings and configuration paths.
"""

from pathlib import Path
from typing import Optional
import os


class Settings:
    """Application settings."""

    # Config directory (XDG compliant)
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lgb"

    # Auth file path
    AUTH_FILE = CONFIG_DIR / "auth.json"

    # API settings
    API_BASE_URL = os.environ.get("LGB_API_URL", "https://linuxgamebench.com/api/v1")

    # Client version
    CLIENT_VERSION = "0.1.5"

    # Steam OpenID settings
    STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

    # Local callback server settings
    CALLBACK_HOST = "127.0.0.1"
    CALLBACK_PORT_RANGE = (8400, 8450)  # Try ports in this range

    @classmethod
    def ensure_config_dir(cls) -> Path:
        """Ensure config directory exists and return path."""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return cls.CONFIG_DIR

    @classmethod
    def get_auth_file(cls) -> Path:
        """Get auth file path, ensuring directory exists."""
        cls.ensure_config_dir()
        return cls.AUTH_FILE


# Singleton instance
settings = Settings()
