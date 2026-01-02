"""API module for Steam authentication and benchmark uploads."""

from linux_game_benchmark.api.auth import (
    SteamAuth,
    AuthSession,
    login_with_steam,
    logout,
    get_current_session,
    is_logged_in,
)
from linux_game_benchmark.api.client import (
    BenchmarkAPIClient,
    UploadResult,
    upload_benchmark,
    check_api_status,
)

__all__ = [
    # Auth
    "SteamAuth",
    "AuthSession",
    "login_with_steam",
    "logout",
    "get_current_session",
    "is_logged_in",
    # Client
    "BenchmarkAPIClient",
    "UploadResult",
    "upload_benchmark",
    "check_api_status",
]
