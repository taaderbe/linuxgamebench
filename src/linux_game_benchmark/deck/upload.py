"""From a cut segment to an upload: analyse, validate, build the payload, send, classify the result."""

from __future__ import annotations

import base64
import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from linux_game_benchmark.deck.detect import DeckInfo

DECK_NATIVE_RESOLUTION = "1280x800"
_RETRY_HINTS = ("rate limit", "unreachable", "timed out", "unexpected error", "authentication", "connection")


@dataclass
class Prepared:
    kwargs: dict
    summary: dict            # fps_avg, seconds, frames - for the log line / sound decision


def deck_hardware_names(deck: DeckInfo) -> tuple[str, str]:
    """The Deck is one piece of hardware: name it as such instead of 'AMD Custom GPU 0405'."""
    return (f"Steam Deck {deck.model}".strip(), "Steam Deck APU")


def flatten_system(system_info: dict, deck: DeckInfo, proton: Optional[dict] = None) -> dict:
    from linux_game_benchmark.utils.formatting import short_kernel, short_os
    gpu, cpu = deck_hardware_names(deck)
    gpu_info = system_info.get("gpu", {})
    os_info = system_info.get("os", {})
    flat = {
        "gpu": gpu,
        "cpu": cpu,
        "os": short_os(os_info.get("name", "SteamOS")),
        "kernel": short_kernel(os_info.get("kernel", "")),
        "gpu_driver": gpu_info.get("driver_version"),
        "vulkan": gpu_info.get("vulkan_version"),
        "ram_gb": int(system_info.get("ram", {}).get("total_gb", 0)),
        "scheduler": system_info.get("scheduler"),
        "gpu_device_id": gpu_info.get("device_id"),
        "gpu_lspci_raw": gpu_info.get("lspci_raw"),
        "device_class": deck.device_class,
    }
    if proton:
        flat.update(proton)
    return flat


def flatten_metrics(metrics: dict) -> dict:
    fps = metrics.get("fps", {})
    return {
        "fps_avg": fps.get("average", 0),
        "fps_min": fps.get("minimum", 0),
        "fps_1low": fps.get("1_percent_low", 0),
        "fps_01low": fps.get("0.1_percent_low", 0),
        "stutter_rating": metrics.get("stutter", {}).get("stutter_rating"),
        "consistency_rating": metrics.get("frame_pacing", {}).get("consistency_rating"),
        "duration_seconds": fps.get("duration_seconds", 0),
        "frame_count": fps.get("frame_count", 0),
    }


def compress_log(path: Path) -> Optional[str]:
    try:
        return base64.b64encode(gzip.compress(path.read_bytes())).decode("ascii")
    except OSError:
        return None


def prepare(segment: Path, game: dict, deck: DeckInfo, system_info: Optional[dict] = None,
            device_state: Optional[dict] = None) -> tuple[Optional[Prepared], str]:
    """Analyse + validate a segment. Returns (Prepared, "") or (None, reason)."""
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
    from linux_game_benchmark.benchmark.validation import validate_benchmark_for_upload

    try:
        analyzer = FrametimeAnalyzer(segment)
        metrics = analyzer.analyze()
    except Exception as exc:                        # a broken CSV must not stop the service
        return None, f"cannot analyse the recording: {exc}"
    frametimes = list(getattr(analyzer, "frametimes", []))
    fps = metrics.get("fps", {})
    validation = validate_benchmark_for_upload(
        frametimes, {"average": fps.get("average"), "minimum": fps.get("minimum"), "maximum": fps.get("maximum")})
    errors = [issue.message for issue in validation.errors]
    if errors:
        return None, "; ".join(errors)

    if system_info is None:
        from linux_game_benchmark.system.hardware_info import get_system_info
        system_info = get_system_info()
    kwargs = {
        "steam_app_id": int(game["app_id"]),
        "game_name": game["name"],
        "resolution": getattr(analyzer, "resolution", None) or DECK_NATIVE_RESOLUTION,
        "system_info": flatten_system(system_info, deck),
        "metrics": flatten_metrics(metrics),
        "frametimes": frametimes or None,
        "mangohud_log_compressed": compress_log(segment),
        "comment": None,
        "game_settings": None,
        "device_state": device_state or None,
    }
    return Prepared(kwargs, {
        "fps_avg": fps.get("average", 0), "seconds": fps.get("duration_seconds", 0),
        "frames": fps.get("frame_count", 0),
    }), ""


def is_retryable(error: str) -> bool:
    text = (error or "").lower()
    return any(hint in text for hint in _RETRY_HINTS)


def send(kwargs: dict) -> tuple[bool, str, str]:
    """Upload (anonymous when nobody is paired). Returns (ok, url_or_error, extras_text)."""
    from linux_game_benchmark.api.client import BenchmarkAPIClient
    result = BenchmarkAPIClient().upload_benchmark(**kwargs, require_auth=False)
    if result.success:
        return True, result.url or "", ""
    return False, result.error or "upload failed", ""
