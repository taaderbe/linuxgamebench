"""
Steam OpenID Authentication.

Implements Steam login flow:
1. Start local HTTP server for callback
2. Open browser to Steam OpenID login
3. Receive callback with Steam ID
4. Save session to ~/.config/lgb/auth.json
"""

import json
import re
import socket
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, parse_qs, urlparse

from linux_game_benchmark.config.settings import settings


@dataclass
class AuthSession:
    """Authenticated Steam session."""
    steam_id: str
    steam_name: Optional[str] = None
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
            steam_id=data["steam_id"],
            steam_name=data.get("steam_name"),
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


class SteamOpenIDHandler(BaseHTTPRequestHandler):
    """HTTP handler for Steam OpenID callback."""

    steam_id: Optional[str] = None
    error: Optional[str] = None

    def log_message(self, format, *args):
        """Suppress HTTP server logging."""
        pass

    def do_GET(self):
        """Handle GET request from Steam OpenID callback."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Check for OpenID response
        if "openid.claimed_id" in params:
            claimed_id = params["openid.claimed_id"][0]
            # Extract Steam ID from claimed_id
            # Format: https://steamcommunity.com/openid/id/76561198...
            match = re.search(r"/id/(\d+)$", claimed_id)
            if match:
                SteamOpenIDHandler.steam_id = match.group(1)
                self._send_success_page()
            else:
                SteamOpenIDHandler.error = "Invalid Steam ID format"
                self._send_error_page("Ungültiges Steam ID Format")
        elif "openid.mode" in params and params["openid.mode"][0] == "cancel":
            SteamOpenIDHandler.error = "Login cancelled"
            self._send_error_page("Login abgebrochen")
        else:
            SteamOpenIDHandler.error = "Invalid response"
            self._send_error_page("Ungültige Antwort von Steam")

    def _send_success_page(self):
        """Send success HTML page."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Login erfolgreich</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 50px; background: #1b2838; color: #fff; }
        .success { color: #66c0f4; font-size: 24px; }
        .info { color: #8f98a0; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="success">Login erfolgreich!</div>
    <div class="info">Du kannst dieses Fenster jetzt schließen.</div>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_error_page(self, message: str):
        """Send error HTML page."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Login fehlgeschlagen</title>
    <style>
        body {{ font-family: sans-serif; text-align: center; padding: 50px; background: #1b2838; color: #fff; }}
        .error {{ color: #ff6b6b; font-size: 24px; }}
        .info {{ color: #8f98a0; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="error">Login fehlgeschlagen</div>
    <div class="info">{message}</div>
</body>
</html>"""
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


class SteamAuth:
    """Steam OpenID authentication handler."""

    def __init__(self):
        self.callback_url: Optional[str] = None
        self.server: Optional[HTTPServer] = None

    def _find_free_port(self) -> int:
        """Find a free port in the configured range."""
        for port in range(*settings.CALLBACK_PORT_RANGE):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((settings.CALLBACK_HOST, port))
                sock.close()
                return port
            except OSError:
                continue
        raise RuntimeError("Kein freier Port gefunden")

    def _build_openid_url(self, callback_url: str) -> str:
        """Build Steam OpenID login URL."""
        params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": callback_url,
            "openid.realm": callback_url,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
        return f"{settings.STEAM_OPENID_URL}?{urlencode(params)}"

    def login(self, timeout: int = 120) -> Optional[AuthSession]:
        """
        Start Steam OpenID login flow.

        Args:
            timeout: Timeout in seconds to wait for callback.

        Returns:
            AuthSession if successful, None if cancelled/failed.
        """
        # Reset handler state
        SteamOpenIDHandler.steam_id = None
        SteamOpenIDHandler.error = None

        # Find free port and start server
        port = self._find_free_port()
        self.callback_url = f"http://{settings.CALLBACK_HOST}:{port}/callback"

        self.server = HTTPServer(
            (settings.CALLBACK_HOST, port),
            SteamOpenIDHandler,
        )
        self.server.timeout = timeout

        # Build login URL and open browser
        login_url = self._build_openid_url(self.callback_url)

        print(f"Öffne Steam Login im Browser...")
        print(f"Falls der Browser nicht öffnet, besuche:")
        print(f"  {login_url[:80]}...")

        webbrowser.open(login_url)

        # Wait for callback
        print("\nWarte auf Steam Login...")
        try:
            self.server.handle_request()
        except Exception as e:
            print(f"Fehler beim Warten auf Callback: {e}")
            return None
        finally:
            self.server.server_close()

        # Check result
        if SteamOpenIDHandler.steam_id:
            session = AuthSession(
                steam_id=SteamOpenIDHandler.steam_id,
            )
            session.save()
            return session
        else:
            if SteamOpenIDHandler.error:
                print(f"Login fehlgeschlagen: {SteamOpenIDHandler.error}")
            return None


def login_with_steam(timeout: int = 120) -> Optional[AuthSession]:
    """
    Convenience function to login with Steam.

    Args:
        timeout: Timeout in seconds.

    Returns:
        AuthSession if successful, None otherwise.
    """
    auth = SteamAuth()
    return auth.login(timeout=timeout)


def logout() -> bool:
    """
    Logout by removing auth file.

    Returns:
        True if successfully logged out, False if wasn't logged in.
    """
    auth_file = settings.get_auth_file()
    if auth_file.exists():
        auth_file.unlink()
        return True
    return False


def get_current_session() -> Optional[AuthSession]:
    """
    Get current auth session if logged in.

    Returns:
        AuthSession if logged in, None otherwise.
    """
    return AuthSession.load()


def is_logged_in() -> bool:
    """Check if user is logged in."""
    return get_current_session() is not None
