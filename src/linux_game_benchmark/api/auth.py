"""
Email/Password Authentication for Linux Game Bench.

Handles login, token management and session persistence.
Tokens are stored in ~/.config/lgb/auth.json
"""

import contextlib
import json
import os
import time
import httpx
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

try:  # Linux/macOS only; without it the refresh simply runs unlocked
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

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
        """Save session to file: atomically (a parallel reader never sees half a file) and for the owner only."""
        path = path or settings.get_auth_file()
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

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


@contextlib.contextmanager
def _refresh_lock(timeout: float = 15.0):
    """Let only one lgb process (CLI, GUI) at a time renew the tokens in auth.json.

    Refresh tokens are single-use: if two processes renew at once, the second one is rejected.
    Best effort - if the lock cannot be taken within `timeout`, the refresh runs without it.
    """
    fd = None
    if fcntl is not None:
        auth_file = settings.get_auth_file()
        try:
            fd = os.open(auth_file.with_name(auth_file.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
        except OSError:
            pass
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)  # closing releases the lock


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

    def login(self, email: str, password: str, totp_code: str = None) -> tuple[bool, str]:
        """
        Login with email and password (CLI-specific endpoint).

        Args:
            email: User email address.
            password: User password.
            totp_code: Optional 2FA code (if user enabled 2FA for CLI).

        Returns:
            Tuple of (success, message).
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                payload = {"email": email, "password": password}
                if totp_code:
                    payload["totp_code"] = totp_code

                response = client.post(
                    f"{self.base_url}/auth/cli-login",
                    json=payload,
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
                    data = response.json()
                    detail = data.get("detail", {})
                    if isinstance(detail, dict) and detail.get("code") == "2FA_REQUIRED":
                        return False, "2FA_REQUIRED"
                    return False, detail if isinstance(detail, str) else "Account not verified"
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

    def _adopt_newer_session(self) -> bool:
        """Use the tokens in auth.json if another process (CLI/GUI) renewed them since we loaded ours."""
        disk = AuthSession.load()
        if disk is not None and self._session is not None and disk.refresh_token != self._session.refresh_token:
            self._session = disk
            return True
        return False

    def refresh_tokens(self) -> bool:
        """
        Refresh the access token using refresh token.

        Refresh tokens are single-use, so a token another process already used is not an error:
        the newer tokens are taken from auth.json. The login ends only when the server rejects
        the current refresh token (401). A busy server, rate limit or network error keeps it.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if self._get_session() is None:
            return False

        with _refresh_lock():
            if self._adopt_newer_session() and not self._is_token_expired(self._session.access_token):
                return True  # another process renewed just now

            for _ in range(2):
                session = self._session
                try:
                    with httpx.Client(timeout=10.0) as client:
                        response = client.post(
                            f"{self.base_url}/auth/refresh",
                            json={"refresh_token": session.refresh_token},
                        )
                    status = response.status_code
                    data = response.json() if status == 200 else None
                except Exception:
                    return False

                if status == 200:
                    session.access_token = data["access_token"]
                    session.refresh_token = data["refresh_token"]
                    session.save()
                    self._session = session
                    return True
                if status != 401:
                    return False  # rate limit / server problem: try again later, stay logged in
                if not self._adopt_newer_session():
                    break  # the server really rejected the current tokens

            self.logout()  # session expired or revoked - clear it
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
def login(email: str, password: str, totp_code: str = None) -> tuple[bool, str]:
    """Login with email and password."""
    manager = TokenManager()
    return manager.login(email, password, totp_code)


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
