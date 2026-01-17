"""
API Client for Linux Game Bench.

Handles benchmark uploads and API communication.
"""

import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

from linux_game_benchmark.config.settings import settings


def _parse_version(version: str) -> Tuple[int, ...]:
    """Parse version string to tuple for comparison. E.g., '0.1.14' -> (0, 1, 14)"""
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _is_newer_version(server_version: str, client_version: str) -> bool:
    """Check if server version is newer than client version."""
    return _parse_version(server_version) > _parse_version(client_version)


@dataclass
class UploadResult:
    """Result of a benchmark upload."""
    success: bool
    benchmark_id: Optional[int] = None
    url: Optional[str] = None
    error: Optional[str] = None


class BenchmarkAPIClient:
    """Client for Linux Game Bench API."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0):
        """
        Initialize API client.

        Args:
            base_url: API base URL. Defaults to settings.API_BASE_URL.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url or settings.API_BASE_URL
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including auth if logged in."""
        from linux_game_benchmark.api.auth import get_auth_header

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"LinuxGameBench/{settings.CLIENT_VERSION}",
        }

        # Add auth header if logged in
        auth_header = get_auth_header()
        if auth_header:
            headers.update(auth_header)

        return headers

    def verify_auth(self) -> tuple[bool, Optional[str]]:
        """
        Verify if current auth token is valid.

        Returns:
            Tuple of (is_valid, username or error message)
        """
        from linux_game_benchmark.api.auth import get_auth_header, is_logged_in

        if not is_logged_in():
            return False, "Not logged in"

        auth_header = get_auth_header()
        if not auth_header:
            return False, "No auth token"

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{self.base_url}/auth/me",
                    headers=auth_header,
                )
                if response.status_code == 200:
                    data = response.json()
                    return True, data.get("username", "Unknown")
                elif response.status_code == 401:
                    return False, "Session expired - please login again"
                else:
                    return False, f"Auth check failed ({response.status_code})"
        except Exception as e:
            return False, f"Could not verify auth: {e}"

    def upload_benchmark(
        self,
        steam_app_id: int,
        game_name: str,
        resolution: str,
        system_info: Dict[str, Any],
        metrics: Dict[str, Any],
        frametimes: Optional[list] = None,
        mangohud_log_compressed: Optional[str] = None,
        comment: Optional[str] = None,
        game_settings: Optional[Dict[str, str]] = None,
        require_auth: bool = True,
    ) -> UploadResult:
        """
        Upload a benchmark result to the server.

        Args:
            steam_app_id: Steam App ID of the game.
            game_name: Display name of the game.
            resolution: Resolution used (e.g., "2560x1440").
            system_info: System information dict with gpu, cpu, os, etc.
            metrics: Performance metrics dict with fps_avg, fps_1low, etc.
            require_auth: If True, verify auth before upload. Default True.

        Returns:
            UploadResult with success status and URL if successful.
        """
        # Verify authentication before upload
        if require_auth:
            from linux_game_benchmark.api.auth import is_logged_in
            if is_logged_in():
                is_valid, msg = self.verify_auth()
                if not is_valid:
                    return UploadResult(
                        success=False,
                        error=f"Authentication invalid: {msg}. Run 'lgb login' to login again."
                    )

        payload = {
            "steam_app_id": steam_app_id,
            "game_name": game_name,
            "resolution": resolution,
            "system": {
                "gpu": system_info.get("gpu", "Unknown"),
                "cpu": system_info.get("cpu", "Unknown"),
                "os": system_info.get("os", "Linux"),
                "kernel": system_info.get("kernel"),
                "gpu_driver": system_info.get("gpu_driver"),
                "vulkan": system_info.get("vulkan"),
                "ram_gb": system_info.get("ram_gb"),
                "scheduler": system_info.get("scheduler"),
                "gpu_device_id": system_info.get("gpu_device_id"),
                "gpu_lspci_raw": system_info.get("gpu_lspci_raw"),
            },
            "metrics": {
                "fps_avg": metrics.get("fps_avg") or metrics.get("average", 0),
                "fps_min": metrics.get("fps_min") or metrics.get("minimum", 0),
                "fps_1low": metrics.get("fps_1low") or metrics.get("1_percent_low", 0),
                "fps_01low": metrics.get("fps_01low") or metrics.get("0.1_percent_low", 0),
                "stutter_rating": metrics.get("stutter_rating"),
                "consistency_rating": metrics.get("consistency_rating"),
                "duration_seconds": metrics.get("duration_seconds", 0),
                "frame_count": metrics.get("frame_count", 0),
            },
            "client_version": settings.CLIENT_VERSION,
            "frametimes": frametimes,
            "mangohud_log_compressed": mangohud_log_compressed,
            "comment": comment,
            "game_settings": game_settings,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/benchmark",
                    json=payload,
                    headers=self._get_headers(),
                )

                if response.status_code == 200 or response.status_code == 201:
                    data = response.json()
                    return UploadResult(
                        success=True,
                        benchmark_id=data.get("id"),
                        url=data.get("url"),
                    )
                elif response.status_code == 401:
                    return UploadResult(
                        success=False,
                        error="Authentication failed. Please login again."
                    )
                elif response.status_code == 429:
                    return UploadResult(
                        success=False,
                        error="Rate limit reached. Please try again later."
                    )
                else:
                    error_detail = response.json().get("detail", response.text)
                    return UploadResult(
                        success=False,
                        error=f"Upload failed ({response.status_code}): {error_detail}"
                    )

        except httpx.ConnectError:
            return UploadResult(
                success=False,
                error=f"Connection to {self.base_url} failed. Server unreachable."
            )
        except httpx.TimeoutException:
            return UploadResult(
                success=False,
                error="Upload timed out. Please try again."
            )
        except Exception as e:
            return UploadResult(
                success=False,
                error=f"Unexpected error: {e}"
            )

    def get_game_benchmarks(self, steam_app_id: int) -> Dict[str, Any]:
        """
        Get all benchmarks for a specific game.

        Args:
            steam_app_id: Steam App ID of the game.

        Returns:
            Dict with benchmarks list and count.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/game/{steam_app_id}/benchmarks",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": response.text, "count": 0, "benchmarks": []}

        except Exception as e:
            return {"error": str(e), "count": 0, "benchmarks": []}

    def health_check(self) -> bool:
        """
        Check if the API is reachable.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                # Use base URL without /api/v1 for health check
                base = self.base_url.replace("/api/v1", "")
                response = client.get(f"{base}/health")
                return response.status_code == 200
        except Exception:
            return False

    def check_for_updates(self) -> Optional[str]:
        """
        Check if a newer client version is available.

        Returns:
            New version string if available, None otherwise.
        """
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self.base_url}/version")
                if response.status_code == 200:
                    latest = response.json().get("version")
                    if latest and _is_newer_version(latest, settings.CLIENT_VERSION):
                        return latest
        except Exception:
            pass  # Silently fail - don't block user
        return None


# Convenience functions
def upload_benchmark(
    steam_app_id: int,
    game_name: str,
    resolution: str,
    system_info: Dict[str, Any],
    metrics: Dict[str, Any],
    frametimes: Optional[list] = None,
    mangohud_log_compressed: Optional[str] = None,
    comment: Optional[str] = None,
    game_settings: Optional[Dict[str, str]] = None,
) -> UploadResult:
    """
    Upload a benchmark result.

    Convenience function that creates a client and uploads.
    """
    client = BenchmarkAPIClient()
    return client.upload_benchmark(
        steam_app_id=steam_app_id,
        game_name=game_name,
        resolution=resolution,
        system_info=system_info,
        metrics=metrics,
        frametimes=frametimes,
        mangohud_log_compressed=mangohud_log_compressed,
        comment=comment,
        game_settings=game_settings,
    )


def check_api_status() -> bool:
    """Check if the API is reachable."""
    client = BenchmarkAPIClient()
    return client.health_check()


def check_for_updates() -> Optional[str]:
    """Check if a newer client version is available."""
    client = BenchmarkAPIClient()
    return client.check_for_updates()


def verify_auth() -> tuple[bool, Optional[str]]:
    """
    Verify if current auth token is valid.

    Returns:
        Tuple of (is_valid, username or error message)
    """
    client = BenchmarkAPIClient()
    return client.verify_auth()
