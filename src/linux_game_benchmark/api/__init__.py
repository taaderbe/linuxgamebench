"""API module for benchmark uploads."""

from linux_game_benchmark.api.client import (
    BenchmarkAPIClient,
    UploadResult,
    upload_benchmark,
    check_api_status,
)

__all__ = [
    "BenchmarkAPIClient",
    "UploadResult",
    "upload_benchmark",
    "check_api_status",
]
