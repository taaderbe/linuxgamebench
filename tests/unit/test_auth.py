"""
Tests for Email/JWT authentication module.

Tests AuthSession serialization, file operations, and utility functions.
Note: Actual API login flow is not tested as it requires network.
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
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"id": 1, "email": "test@example.com", "username": "testuser"},
        )
        assert session.access_token == "test_access_token"
        assert session.refresh_token == "test_refresh_token"
        assert session.user["username"] == "testuser"
        assert session.authenticated_at != ""

    def test_create_session_with_stage(self):
        """Create AuthSession with optional stage."""
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"id": 1, "email": "test@example.com", "username": "testuser"},
            stage="dev",
        )
        assert session.stage == "dev"

    def test_to_dict(self):
        """AuthSession should serialize to dict."""
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"id": 1, "email": "test@example.com", "username": "testuser"},
            stage="prod",
            authenticated_at="2025-01-01T12:00:00",
        )
        data = session.to_dict()

        assert data["access_token"] == "test_access_token"
        assert data["refresh_token"] == "test_refresh_token"
        assert data["user"]["username"] == "testuser"
        assert data["stage"] == "prod"
        assert data["authenticated_at"] == "2025-01-01T12:00:00"

    def test_from_dict(self):
        """AuthSession should deserialize from dict."""
        data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "user": {"id": 1, "email": "test@example.com", "username": "testuser"},
            "stage": "rc",
            "authenticated_at": "2025-01-01T12:00:00",
        }
        session = AuthSession.from_dict(data)

        assert session.access_token == "test_access_token"
        assert session.refresh_token == "test_refresh_token"
        assert session.user["username"] == "testuser"
        assert session.stage == "rc"
        assert session.authenticated_at == "2025-01-01T12:00:00"

    def test_from_dict_minimal(self):
        """AuthSession should handle minimal dict with defaults."""
        data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
        }
        session = AuthSession.from_dict(data)

        assert session.access_token == "test_access_token"
        assert session.refresh_token == "test_refresh_token"
        assert session.user == {}
        assert session.stage == "prod"

    def test_authenticated_at_auto_set(self):
        """authenticated_at should be auto-set if not provided."""
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={},
        )
        # Should be a valid ISO datetime
        datetime.fromisoformat(session.authenticated_at)

    def test_get_username(self):
        """get_username should return username from user dict."""
        session = AuthSession(
            access_token="test",
            refresh_token="test",
            user={"username": "testuser"},
        )
        assert session.get_username() == "testuser"

    def test_get_email(self):
        """get_email should return email from user dict."""
        session = AuthSession(
            access_token="test",
            refresh_token="test",
            user={"email": "test@example.com"},
        )
        assert session.get_email() == "test@example.com"


class TestAuthSessionFileOperations:
    """Tests for AuthSession save/load operations."""

    def test_save_and_load(self, tmp_path: Path):
        """Save and load AuthSession from file."""
        auth_file = tmp_path / "auth.json"

        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"id": 1, "username": "testuser", "email": "test@example.com"},
        )
        session.save(auth_file)

        # Verify file exists
        assert auth_file.exists()

        # Load and verify
        loaded = AuthSession.load(auth_file)
        assert loaded is not None
        assert loaded.access_token == session.access_token
        assert loaded.refresh_token == session.refresh_token
        assert loaded.user["username"] == "testuser"

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
        """Loading JSON without required fields should return None."""
        auth_file = tmp_path / "missing.json"
        auth_file.write_text('{"user": {"username": "test"}}')

        loaded = AuthSession.load(auth_file)
        assert loaded is None

    def test_save_creates_file_content(self, tmp_path: Path):
        """Saved file should contain valid JSON."""
        auth_file = tmp_path / "auth.json"

        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"username": "testuser"},
        )
        session.save(auth_file)

        # Parse and verify
        with open(auth_file) as f:
            data = json.load(f)

        assert data["access_token"] == "test_access_token"
        assert data["refresh_token"] == "test_refresh_token"
        assert data["user"]["username"] == "testuser"


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_is_logged_in_no_file(self, tmp_path: Path, monkeypatch):
        """is_logged_in should return False when no auth file."""
        from linux_game_benchmark.config.settings import settings

        # Patch settings method
        monkeypatch.setattr(settings, "get_auth_file", lambda: tmp_path / "auth.json")

        assert is_logged_in() is False

    def test_is_logged_in_with_file(self, tmp_path: Path, monkeypatch):
        """is_logged_in should return True when auth file exists."""
        from linux_game_benchmark.config.settings import settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"username": "testuser"},
        )
        session.save(auth_file)

        monkeypatch.setattr(settings, "get_auth_file", lambda: auth_file)

        assert is_logged_in() is True

    def test_get_current_session_no_file(self, tmp_path: Path, monkeypatch):
        """get_current_session should return None when no auth file."""
        from linux_game_benchmark.config.settings import settings

        monkeypatch.setattr(settings, "get_auth_file", lambda: tmp_path / "auth.json")

        assert get_current_session() is None

    def test_get_current_session_with_file(self, tmp_path: Path, monkeypatch):
        """get_current_session should return session when file exists."""
        from linux_game_benchmark.config.settings import settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={"username": "testuser"},
        )
        session.save(auth_file)

        monkeypatch.setattr(settings, "get_auth_file", lambda: auth_file)

        loaded = get_current_session()
        assert loaded is not None
        assert loaded.access_token == "test_access_token"

    def test_logout_removes_file(self, tmp_path: Path, monkeypatch):
        """logout should remove auth file."""
        from linux_game_benchmark.config.settings import settings

        auth_file = tmp_path / "auth.json"
        session = AuthSession(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            user={},
        )
        session.save(auth_file)

        monkeypatch.setattr(settings, "get_auth_file", lambda: auth_file)

        assert auth_file.exists()
        success, message = logout()
        assert success is True
        assert not auth_file.exists()

    def test_logout_no_file(self, tmp_path: Path, monkeypatch):
        """logout should return False when not logged in."""
        from linux_game_benchmark.config.settings import settings

        monkeypatch.setattr(settings, "get_auth_file", lambda: tmp_path / "auth.json")

        success, message = logout()
        assert success is False
        assert "Not logged in" in message


class TestTokenFormat:
    """Tests for token handling."""

    def test_access_token_stored(self):
        """Access token should be stored correctly."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        session = AuthSession(
            access_token=token,
            refresh_token="refresh",
            user={},
        )
        assert session.access_token == token

    def test_refresh_token_stored(self):
        """Refresh token should be stored correctly."""
        token = "refresh_token_value_here"
        session = AuthSession(
            access_token="access",
            refresh_token=token,
            user={},
        )
        assert session.refresh_token == token
