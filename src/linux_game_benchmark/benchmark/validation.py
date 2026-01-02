"""
Benchmark Data Validation.

Client-side validation to ensure benchmark quality before upload.
Implements checks for:
- Minimum duration (>=30 seconds)
- Minimum frames (>=1000 frames)
- FPS range (1-1000 FPS)
- Frametime gaps (loading screen detection)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ValidationSeverity(Enum):
    """Severity level for validation issues."""
    ERROR = "error"      # Block upload
    WARNING = "warning"  # Allow upload with notice
    INFO = "info"        # Informational only


@dataclass
class ValidationIssue:
    """A single validation issue."""
    code: str
    message: str
    severity: ValidationSeverity
    details: Optional[dict] = None


@dataclass
class ValidationResult:
    """Result of benchmark validation."""
    valid: bool  # True if no ERROR-level issues
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get all ERROR-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get all WARNING-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add an issue and update validity."""
        self.issues.append(issue)
        if issue.severity == ValidationSeverity.ERROR:
            self.valid = False


class BenchmarkValidator:
    """
    Validates benchmark data before upload.

    Validation rules (from Anti-Fake protection plan):
    - Minimum duration: 30 seconds
    - Minimum frames: 1000 frames
    - FPS range: 1-1000 FPS (warning only)
    - Frametime gaps: >5 seconds marked as loading screens
    """

    # Configuration
    MIN_DURATION_SECONDS = 30
    MIN_FRAME_COUNT = 1000
    MIN_FPS = 1
    MAX_FPS = 1000
    LOADING_SCREEN_GAP_MS = 5000  # 5 seconds in milliseconds

    # Known MangoHud versions (for validation)
    KNOWN_MANGOHUD_VERSIONS = [
        "0.7.0", "0.7.1", "0.7.2", "0.7.3",
        "0.8.0", "0.8.1",
    ]

    def validate(
        self,
        frametimes: list[float],
        fps_avg: Optional[float] = None,
        fps_min: Optional[float] = None,
        fps_max: Optional[float] = None,
        mangohud_version: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate benchmark data.

        Args:
            frametimes: List of frametime values in milliseconds.
            fps_avg: Average FPS (optional, calculated if not provided).
            fps_min: Minimum FPS (optional).
            fps_max: Maximum FPS (optional).
            mangohud_version: MangoHud version string (optional).

        Returns:
            ValidationResult with issues and metadata.
        """
        result = ValidationResult(valid=True)

        # Skip validation if no data
        if not frametimes:
            result.add_issue(ValidationIssue(
                code="NO_DATA",
                message="Keine Frametime-Daten vorhanden",
                severity=ValidationSeverity.ERROR,
            ))
            return result

        # Calculate basic metrics if not provided
        frame_count = len(frametimes)
        duration_ms = sum(frametimes)
        duration_seconds = duration_ms / 1000.0

        if fps_avg is None:
            avg_frametime = duration_ms / frame_count
            fps_avg = 1000.0 / avg_frametime if avg_frametime > 0 else 0

        # Store metadata
        result.metadata = {
            "frame_count": frame_count,
            "duration_seconds": round(duration_seconds, 2),
            "fps_avg": round(fps_avg, 2) if fps_avg else None,
        }

        # Run validation checks
        self._check_minimum_duration(result, duration_seconds)
        self._check_minimum_frames(result, frame_count)
        self._check_fps_range(result, fps_avg, fps_min, fps_max)
        self._check_frametime_gaps(result, frametimes)
        self._check_mangohud_version(result, mangohud_version)

        return result

    def _check_minimum_duration(
        self,
        result: ValidationResult,
        duration_seconds: float,
    ) -> None:
        """Check if benchmark meets minimum duration requirement."""
        if duration_seconds < self.MIN_DURATION_SECONDS:
            result.add_issue(ValidationIssue(
                code="DURATION_TOO_SHORT",
                message=f"Benchmark zu kurz: {duration_seconds:.1f}s (min. {self.MIN_DURATION_SECONDS}s)",
                severity=ValidationSeverity.ERROR,
                details={
                    "actual": duration_seconds,
                    "required": self.MIN_DURATION_SECONDS,
                },
            ))

    def _check_minimum_frames(
        self,
        result: ValidationResult,
        frame_count: int,
    ) -> None:
        """Check if benchmark has minimum number of frames."""
        if frame_count < self.MIN_FRAME_COUNT:
            result.add_issue(ValidationIssue(
                code="TOO_FEW_FRAMES",
                message=f"Zu wenige Frames: {frame_count} (min. {self.MIN_FRAME_COUNT})",
                severity=ValidationSeverity.ERROR,
                details={
                    "actual": frame_count,
                    "required": self.MIN_FRAME_COUNT,
                },
            ))

    def _check_fps_range(
        self,
        result: ValidationResult,
        fps_avg: Optional[float],
        fps_min: Optional[float],
        fps_max: Optional[float],
    ) -> None:
        """Check if FPS values are within expected range."""
        issues = []

        if fps_avg is not None:
            if fps_avg < self.MIN_FPS:
                issues.append(f"AVG FPS zu niedrig: {fps_avg:.1f}")
            elif fps_avg > self.MAX_FPS:
                issues.append(f"AVG FPS ungewöhnlich hoch: {fps_avg:.1f}")

        if fps_min is not None and fps_min < self.MIN_FPS:
            issues.append(f"MIN FPS ungültig: {fps_min:.1f}")

        if fps_max is not None and fps_max > self.MAX_FPS:
            issues.append(f"MAX FPS ungewöhnlich hoch: {fps_max:.1f}")

        if issues:
            result.add_issue(ValidationIssue(
                code="FPS_OUT_OF_RANGE",
                message="; ".join(issues),
                severity=ValidationSeverity.WARNING,  # Warning only, still allow upload
                details={
                    "fps_avg": fps_avg,
                    "fps_min": fps_min,
                    "fps_max": fps_max,
                    "expected_range": f"{self.MIN_FPS}-{self.MAX_FPS}",
                },
            ))

    def _check_frametime_gaps(
        self,
        result: ValidationResult,
        frametimes: list[float],
    ) -> None:
        """
        Detect large gaps in frametimes (loading screens).

        Gaps > 5 seconds are flagged as potential loading screens.
        """
        gaps = []
        for i, ft in enumerate(frametimes):
            if ft > self.LOADING_SCREEN_GAP_MS:
                gaps.append({
                    "frame": i,
                    "duration_ms": round(ft, 2),
                    "duration_s": round(ft / 1000.0, 2),
                })

        if gaps:
            total_gap_time = sum(g["duration_ms"] for g in gaps)
            result.add_issue(ValidationIssue(
                code="LOADING_SCREENS_DETECTED",
                message=f"{len(gaps)} Ladebildschirm(e) erkannt ({total_gap_time/1000:.1f}s gesamt)",
                severity=ValidationSeverity.INFO,
                details={
                    "gap_count": len(gaps),
                    "total_gap_ms": round(total_gap_time, 2),
                    "gaps": gaps[:10],  # Limit to first 10
                },
            ))

            # Store in metadata for server-side use
            result.metadata["loading_screens"] = {
                "count": len(gaps),
                "total_duration_ms": round(total_gap_time, 2),
            }

    def _check_mangohud_version(
        self,
        result: ValidationResult,
        version: Optional[str],
    ) -> None:
        """Check if MangoHud version is known."""
        if version is None:
            return

        # Normalize version (strip 'v' prefix if present)
        normalized = version.lstrip("v").strip()

        if normalized not in self.KNOWN_MANGOHUD_VERSIONS:
            result.add_issue(ValidationIssue(
                code="UNKNOWN_MANGOHUD_VERSION",
                message=f"Unbekannte MangoHud-Version: {version}",
                severity=ValidationSeverity.WARNING,
                details={
                    "version": version,
                    "known_versions": self.KNOWN_MANGOHUD_VERSIONS,
                },
            ))


def validate_benchmark_for_upload(
    frametimes: list[float],
    fps_metrics: Optional[dict] = None,
    mangohud_version: Optional[str] = None,
) -> ValidationResult:
    """
    Convenience function to validate a benchmark before upload.

    Args:
        frametimes: List of frametime values in milliseconds.
        fps_metrics: Optional dict with 'average', 'minimum', 'maximum' keys.
        mangohud_version: Optional MangoHud version string.

    Returns:
        ValidationResult indicating if upload should proceed.
    """
    validator = BenchmarkValidator()

    fps_avg = fps_metrics.get("average") if fps_metrics else None
    fps_min = fps_metrics.get("minimum") if fps_metrics else None
    fps_max = fps_metrics.get("maximum") if fps_metrics else None

    return validator.validate(
        frametimes=frametimes,
        fps_avg=fps_avg,
        fps_min=fps_min,
        fps_max=fps_max,
        mangohud_version=mangohud_version,
    )
