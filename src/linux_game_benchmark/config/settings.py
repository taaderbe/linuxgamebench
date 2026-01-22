"""
Application settings and configuration paths.
"""

from pathlib import Path
from typing import Optional
import os
import json


class Settings:
    """Application settings."""

    # Config directory (XDG compliant)
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lgb"

    # Auth file path
    AUTH_FILE = CONFIG_DIR / "auth.json"

    # Config file path (for stage etc.)
    CONFIG_FILE = CONFIG_DIR / "config.json"

    # Stage configuration
    STAGES = {
        "dev": "http://192.168.0.126:8000/api/v1",      # GameDEV (direct)
        "rc": "http://192.168.0.70/api/v1",             # Release Candidate (nginx)
        "preprod": "http://192.168.0.112/api/v1",       # Pre-Production (nginx)
        "prod": "https://linuxgamebench.com/api/v1",    # Production
    }

    # Client version
    CLIENT_VERSION = "0.1.45"

    def _load_config(self) -> dict:
        """Load config from file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_config(self, config: dict) -> None:
        """Save config to file."""
        self.ensure_config_dir()
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

    @property
    def CURRENT_STAGE(self) -> str:
        """Get current stage: env var > config file > default (prod)."""
        # 1. Environment variable has highest priority
        env_stage = os.environ.get("LGB_STAGE")
        if env_stage:
            return env_stage
        # 2. Config file
        config = self._load_config()
        if config.get("stage"):
            return config["stage"]
        # 3. Default - MUST be prod for released clients!
        return "prod"

    def set_stage(self, stage: str) -> bool:
        """Set stage persistently in config file."""
        if stage not in self.STAGES:
            return False
        config = self._load_config()
        config["stage"] = stage
        self._save_config(config)
        return True

    @property
    def API_BASE_URL(self) -> str:
        """Get API URL - from LGB_API_URL env or based on stage (read at runtime)."""
        override = os.environ.get("LGB_API_URL")
        if override:
            return override
        return self.STAGES.get(self.CURRENT_STAGE, self.STAGES["prod"])

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

    @classmethod
    def get_stage_url(cls, stage: str) -> Optional[str]:
        """Get API URL for a specific stage."""
        return cls.STAGES.get(stage)

    def get_default_gpu(self) -> Optional[str]:
        """Get default GPU PCI address from config."""
        config = self._load_config()
        return config.get("default_gpu_pci")

    def set_default_gpu(self, pci_address: str) -> None:
        """Set default GPU PCI address in config."""
        config = self._load_config()
        config["default_gpu_pci"] = pci_address
        self._save_config(config)

    def clear_default_gpu(self) -> None:
        """Clear default GPU setting."""
        config = self._load_config()
        if "default_gpu_pci" in config:
            del config["default_gpu_pci"]
            self._save_config(config)


# Singleton instance
settings = Settings()
