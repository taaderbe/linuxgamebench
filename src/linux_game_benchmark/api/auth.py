"""
Email/Password Authentication for Linux Game Bench.

Handles login, token management and session persistence.
Tokens are stored in ~/.config/lgb/auth.json
"""

import json
import httpx
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from linux_game_benchmark.config.settings import settings


@dataclass
class UserInfo:
    """Authenticated user information."""
    id: int
    email: str
    username: str
    email_verified: bool = False


@dataclass
class AuthSession:
    """Authenticated session with tokens and user info."""
    access_token: str
    refresh_token: str
    user: Dict[str, Any]
    stage: str = "prod"
    authenticated_at: str = ""

    def __post_init__(self):
        if not self.authenticated_at:
            self.authenticated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AuthSession":
        """Create from dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            user=data.get("user", {}),
            stage=data.get("stage", "prod"),
            authenticated_at=data.get("authenticated_at", ""),
        )

    def save(self, path: Optional[Path] = None) -> None:
        """Save session to file."""
        path = path or settings.get_auth_file()
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Optional["AuthSession"]:
        """Load session from file if exists."""
        path = path or settings.get_auth_file()
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def get_username(self) -> str:
        """Get username from user info."""
        return self.user.get("username", "Unknown")

    def get_email(self) -> str:
        """Get email from user info."""
        return self.user.get("email", "Unknown")


class TokenManager:
    """Manages authentication tokens and API communication."""

    def __init__(self, base_url: Optional[str] = None):
        """Initialize token manager.

        Args:
            base_url: API base URL. Defaults to settings.API_BASE_URL.
        """
        self.base_url = base_url or settings.API_BASE_URL
        self._session: Optional[AuthSession] = None

    def _get_session(self) -> Optional[AuthSession]:
        """Get current session, loading from file if needed."""
        if self._session is None:
            self._session = AuthSession.load()
        return self._session

    def login(self, email: str, password: str) -> tuple[bool, str]:
        """
        Login with email and password.

        Args:
            email: User email address.
            password: User password.

        Returns:
            Tuple of (success, message).
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.base_url}/auth/login",
                    json={"email": email, "password": password},
                )

                if response.status_code == 200:
                    data = response.json()
                    self._session = AuthSession(
                        access_token=data["access_token"],
                        refresh_token=data["refresh_token"],
                        user=data.get("user", {}),
                        stage=settings.CURRENT_STAGE,
                    )
                    self._session.save()
                    return True, f"Logged in as {self._session.get_username()}"
                elif response.status_code == 401:
                    detail = response.json().get("detail", "Invalid credentials")
                    return False, detail
                elif response.status_code == 403:
                    detail = response.json().get("detail", "Account not verified")
                    return False, detail
                else:
                    detail = response.json().get("detail", "Login failed")
                    return False, f"Login failed: {detail}"

        except httpx.ConnectError:
            return False, f"Cannot connect to server ({self.base_url})"
        except httpx.TimeoutException:
            return False, "Connection timed out"
        except Exception as e:
            return False, f"Login error: {e}"

    def logout(self) -> tuple[bool, str]:
        """
        Logout and clear stored tokens.

        Returns:
            Tuple of (success, message).
        """
        session = self._get_session()

        if session is None:
            return False, "Not logged in"

        # Try to invalidate token on server (optional, don't fail if server unreachable)
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{self.base_url}/auth/logout",
                    headers={"Authorization": f"Bearer {session.access_token}"},
                )
        except Exception:
            pass  # Server logout is best-effort

        # Clear local session
        auth_file = settings.get_auth_file()
        if auth_file.exists():
            auth_file.unlink()
        self._session = None

        return True, "Logged out successfully"

    def refresh_tokens(self) -> bool:
        """
        Refresh the access token using refresh token.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        session = self._get_session()
        if session is None:
            return False

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.base_url}/auth/refresh",
                    json={"refresh_token": session.refresh_token},
                )

                if response.status_code == 200:
                    data = response.json()
                    session.access_token = data["access_token"]
                    session.refresh_token = data["refresh_token"]
                    session.save()
                    self._session = session
                    return True
                else:
                    # Refresh failed - clear invalid session
                    self.logout()
                    return False

        except Exception:
            return False

    def _is_token_expired(self, token: str) -> bool:
        """Check if JWT token is expired (with 60s buffer)."""
        try:
            import base64
            # JWT is header.payload.signature - decode payload
            payload_b64 = token.split(".")[1]
            # Add padding if needed
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp", 0)
            # Check if expired (with 60 second buffer)
            return datetime.now().timestamp() > (exp - 60)
        except Exception:
            return True  # Assume expired if we can't decode

    def get_access_token(self) -> Optional[str]:
        """
        Get current access token, refreshing if needed.

        Returns:
            Access token string or None if not logged in.
        """
        session = self._get_session()
        if session is None:
            return None

        # Check if token is expired and refresh if needed
        if self._is_token_expired(session.access_token):
            if not self.refresh_tokens():
                return None  # Refresh failed, not logged in
            session = self._get_session()
            if session is None:
                return None

        return session.access_token

    def get_auth_header(self) -> Optional[Dict[str, str]]:
        """
        Get Authorization header for API requests.

        Returns:
            Dict with Authorization header or None if not logged in.
        """
        token = self.get_access_token()
        if token is None:
            return None
        return {"Authorization": f"Bearer {token}"}

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """
        Get current user info from stored session.

        Returns:
            User info dict or None if not logged in.
        """
        session = self._get_session()
        if session is None:
            return None
        return session.user

    def get_status(self) -> Dict[str, Any]:
        """
        Get current authentication status.

        Returns:
            Dict with login status, user info, and stage.
        """
        session = self._get_session()
        if session is None:
            return {
                "logged_in": False,
                "stage": settings.CURRENT_STAGE,
                "api_url": self.base_url,
            }

        return {
            "logged_in": True,
            "user": session.user,
            "username": session.get_username(),
            "email": session.get_email(),
            "stage": settings.CURRENT_STAGE,  # Always use current config, not login-time stage
            "api_url": self.base_url,
            "authenticated_at": session.authenticated_at,
        }


# Convenience functions
def login(email: str, password: str) -> tuple[bool, str]:
    """Login with email and password."""
    manager = TokenManager()
    return manager.login(email, password)


def logout() -> tuple[bool, str]:
    """Logout and clear tokens."""
    manager = TokenManager()
    return manager.logout()


def get_current_session() -> Optional[AuthSession]:
    """Get current auth session if logged in."""
    return AuthSession.load()


def is_logged_in() -> bool:
    """Check if user is logged in."""
    return get_current_session() is not None


def get_auth_header() -> Optional[Dict[str, str]]:
    """Get Authorization header for API requests."""
    manager = TokenManager()
    return manager.get_auth_header()


def get_status() -> Dict[str, Any]:
    """Get current authentication status."""
    manager = TokenManager()
    return manager.get_status()
