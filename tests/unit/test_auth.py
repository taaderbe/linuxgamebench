"""
Tests for Steam authentication module.

Tests AuthSession serialization, file operations, and utility functions.
Note: Actual Steam OpenID flow is not tested as it requires browser interaction.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

from linux_game_benchmark.api.auth import (
    AuthSession,
    get_current_session,
    is_logged_in,
    logout,
)


class TestAuthSession:
    """Tests for AuthSession dataclass."""

    def test_create_session(self):
        """Create a new AuthSession with required fields."""
        session = AuthSession(steam_id="76561198012345678")
        assert session.steam_id == "76561198012345678"
        assert session.steam_name is None
        assert session.authenticated_at != ""

    def test_create_session_with_name(self):
        """Create AuthSession with optional name."""
        session = AuthSession(
            steam_id="76561198012345678",
            steam_name="TestUser",
        )
        assert session.steam_id == "76561198012345678"
        assert session.steam_name == "TestUser"

    def test_to_dict(self):
        """AuthSession should serialize to dict."""
        session = AuthSession(
            steam_id="76561198012345678",
            steam_name="TestUser",
            authenticated_at="2025-01-01T12:00:00",
        )
        data = session.to_dict()

        assert data["steam_id"] == "76561198012345678"
        assert data["steam_name"] == "TestUser"
        assert data["authenticated_at"] == "2025-01-01T12:00:00"

    def test_from_dict(self):
        """AuthSession should deserialize from dict."""
        data = {
            "steam_id": "76561198012345678",
            "steam_name": "TestUser",
            "authenticated_at": "2025-01-01T12:00:00",
        }
        session = AuthSession.from_dict(data)

        assert session.steam_id == "76561198012345678"
        assert session.steam_name == "TestUser"
        assert session.authenticated_at == "2025-01-01T12:00:00"

    def test_from_dict_minimal(self):
        """AuthSession should handle minimal dict."""
        data = {"steam_id": "76561198012345678"}
        session = AuthSession.from_dict(data)

        assert session.steam_id == "76561198012345678"
        assert session.steam_name is None

    def test_authenticated_at_auto_set(self):
        """authenticated_at should be auto-set if not provided."""
        session = AuthSession(steam_id="76561198012345678")
        # Should be a valid ISO datetime
        datetime.fromisoformat(session.authenticated_at)


class TestAuthSessionFileOperations:
    """Tests for AuthSession save/load operations."""

    def test_save_and_load(self, tmp_path: Path):
        """Save and load AuthSession from file."""
        auth_file = tmp_path / "auth.json"

        session = AuthSession(
            steam_id="76561198012345678",
            steam_name="TestUser",
        )
        session.save(auth_file)

        # Verify file exists
        assert auth_file.exists()

        # Load and verify
        loaded = AuthSession.load(auth_file)
        assert loaded is not None
        assert loaded.steam_id == session.steam_id
        assert loaded.steam_name == session.steam_name

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Loading from nonexistent file should return None."""
        auth_file = tmp_path / "nonexistent.json"
        loaded = AuthSession.load(auth_file)
        assert loaded is None

    def test_load_invalid_json(self, tmp_path: Path):
        """Loading invalid JSON should return None."""
        auth_file = tmp_path / "invalid.json"
        auth_file.write_text("not valid json")

        loaded = AuthSession.load(auth_file)
        assert loaded is None

    def test_load_missing_required_fields(self, tmp_path: Path):
        """Loading JSON without steam_id should return None."""
        auth_file = tmp_path / "missing.json"
        auth_file.write_text('{"steam_name": "TestUser"}')

        loaded = AuthSession.load(auth_file)
        assert loaded is None

    def test_save_creates_file_content(self, tmp_path: Path):
        """Saved file should contain valid JSON."""
        auth_file = tmp_path / "auth.json"

        session = AuthSession(
            steam_id="76561198012345678",
            steam_name="TestUser",
        )
        session.save(auth_file)

        # Parse and verify
        with open(auth_file) as f:
            data = json.load(f)

        assert data["steam_id"] == "76561198012345678"
        assert data["steam_name"] == "TestUser"


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_is_logged_in_no_file(self, tmp_path: Path, monkeypatch):
        """is_logged_in should return False when no auth file."""
        from linux_game_benchmark.config.settings import Settings

        # Patch Settings class attribute
        monkeypatch.setattr(Settings, "AUTH_FILE", tmp_path / "auth.json")

        assert is_logged_in() is False

    def test_is_logged_in_with_file(self, tmp_path: Path, monkeypatch):
        """is_logged_in should return True when auth file exists."""
        from linux_game_benchmark.config.settings import Settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(steam_id="76561198012345678")
        session.save(auth_file)

        monkeypatch.setattr(Settings, "AUTH_FILE", auth_file)

        assert is_logged_in() is True

    def test_get_current_session_no_file(self, tmp_path: Path, monkeypatch):
        """get_current_session should return None when no auth file."""
        from linux_game_benchmark.config.settings import Settings

        monkeypatch.setattr(Settings, "AUTH_FILE", tmp_path / "auth.json")

        assert get_current_session() is None

    def test_get_current_session_with_file(self, tmp_path: Path, monkeypatch):
        """get_current_session should return session when file exists."""
        from linux_game_benchmark.config.settings import Settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(steam_id="76561198012345678", steam_name="TestUser")
        session.save(auth_file)

        monkeypatch.setattr(Settings, "AUTH_FILE", auth_file)

        loaded = get_current_session()
        assert loaded is not None
        assert loaded.steam_id == "76561198012345678"

    def test_logout_removes_file(self, tmp_path: Path, monkeypatch):
        """logout should remove auth file."""
        from linux_game_benchmark.config.settings import Settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(steam_id="76561198012345678")
        session.save(auth_file)

        monkeypatch.setattr(Settings, "AUTH_FILE", auth_file)

        assert auth_file.exists()
        result = logout()
        assert result is True
        assert not auth_file.exists()

    def test_logout_no_file(self, tmp_path: Path, monkeypatch):
        """logout should return False when not logged in."""
        from linux_game_benchmark.config.settings import Settings

        monkeypatch.setattr(Settings, "AUTH_FILE", tmp_path / "auth.json")

        result = logout()
        assert result is False


class TestSteamIDFormat:
    """Tests for Steam ID format validation."""

    def test_valid_steam_id_format(self):
        """Valid Steam64 IDs should work."""
        valid_ids = [
            "76561198012345678",
            "76561197960287930",  # Minimum valid
            "76561199999999999",  # High number
        ]
        for steam_id in valid_ids:
            session = AuthSession(steam_id=steam_id)
            assert session.steam_id == steam_id

    def test_steam_id_length(self):
        """Steam64 IDs should be 17 digits."""
        session = AuthSession(steam_id="76561198012345678")
        assert len(session.steam_id) == 17
