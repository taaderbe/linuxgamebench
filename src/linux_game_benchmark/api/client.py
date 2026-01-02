"""
API Client for Linux Game Bench.

Handles benchmark uploads and API communication.
"""

import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any

from linux_game_benchmark.api.auth import get_current_session, is_logged_in
from linux_game_benchmark.config.settings import settings


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
        """Get request headers including Steam ID if logged in."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"LinuxGameBench/{settings.CLIENT_VERSION}",
        }

        session = get_current_session()
        if session:
            headers["X-Steam-ID"] = session.steam_id

        return headers

    def upload_benchmark(
        self,
        steam_app_id: int,
        game_name: str,
        resolution: str,
        system_info: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> UploadResult:
        """
        Upload a benchmark result to the server.

        Args:
            steam_app_id: Steam App ID of the game.
            game_name: Display name of the game.
            resolution: Resolution used (e.g., "2560x1440").
            system_info: System information dict with gpu, cpu, os, etc.
            metrics: Performance metrics dict with fps_avg, fps_1low, etc.

        Returns:
            UploadResult with success status and URL if successful.
        """
        if not is_logged_in():
            return UploadResult(
                success=False,
                error="Nicht eingeloggt. Bitte zuerst 'lgb login' ausführen."
            )

        session = get_current_session()

        payload = {
            "steam_app_id": steam_app_id,
            "game_name": game_name,
            "resolution": resolution,
            "system": {
                "gpu": system_info.get("gpu", "Unknown"),
                "cpu": system_info.get("cpu", "Unknown"),
                "os": system_info.get("os", "Linux"),
                "kernel": system_info.get("kernel"),
                "mesa": system_info.get("mesa"),
                "vulkan": system_info.get("vulkan"),
                "ram_gb": system_info.get("ram_gb"),
            },
            "metrics": {
                "fps_avg": metrics.get("average", metrics.get("fps_avg", 0)),
                "fps_min": metrics.get("minimum", metrics.get("fps_min")),
                "fps_1low": metrics.get("fps_1_low", metrics.get("fps_1low")),
                "fps_01low": metrics.get("fps_0.1_low", metrics.get("fps_01low")),
                "stutter_rating": metrics.get("stutter_rating"),
                "consistency_rating": metrics.get("consistency_rating"),
            },
            "submitter": {
                "steam_id": session.steam_id,
                "steam_name": session.steam_name,
            },
            "client_version": settings.CLIENT_VERSION,
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
                        error="Authentifizierung fehlgeschlagen. Bitte erneut einloggen."
                    )
                elif response.status_code == 429:
                    return UploadResult(
                        success=False,
                        error="Rate Limit erreicht. Bitte später erneut versuchen."
                    )
                else:
                    error_detail = response.json().get("detail", response.text)
                    return UploadResult(
                        success=False,
                        error=f"Upload fehlgeschlagen ({response.status_code}): {error_detail}"
                    )

        except httpx.ConnectError:
            return UploadResult(
                success=False,
                error=f"Verbindung zu {self.base_url} fehlgeschlagen. Server nicht erreichbar."
            )
        except httpx.TimeoutException:
            return UploadResult(
                success=False,
                error="Timeout beim Upload. Bitte erneut versuchen."
            )
        except Exception as e:
            return UploadResult(
                success=False,
                error=f"Unerwarteter Fehler: {e}"
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


# Convenience functions
def upload_benchmark(
    steam_app_id: int,
    game_name: str,
    resolution: str,
    system_info: Dict[str, Any],
    metrics: Dict[str, Any],
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
    )


def check_api_status() -> bool:
    """Check if the API is reachable."""
    client = BenchmarkAPIClient()
    return client.health_check()
