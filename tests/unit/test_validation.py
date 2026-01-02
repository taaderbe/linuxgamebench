"""
Tests for benchmark validation module.

Tests the client-side validation that ensures benchmark quality before upload.
"""

import pytest
from linux_game_benchmark.benchmark.validation import (
    BenchmarkValidator,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    validate_benchmark_for_upload,
)


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_initially_valid(self):
        """New ValidationResult should be valid by default."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert len(result.issues) == 0
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error_makes_invalid(self):
        """Adding an ERROR issue should make result invalid."""
        result = ValidationResult(valid=True)
        result.add_issue(ValidationIssue(
            code="TEST",
            message="Test error",
            severity=ValidationSeverity.ERROR,
        ))
        assert result.valid is False
        assert len(result.errors) == 1

    def test_add_warning_stays_valid(self):
        """Adding a WARNING issue should not affect validity."""
        result = ValidationResult(valid=True)
        result.add_issue(ValidationIssue(
            code="TEST",
            message="Test warning",
            severity=ValidationSeverity.WARNING,
        ))
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_add_info_stays_valid(self):
        """Adding an INFO issue should not affect validity."""
        result = ValidationResult(valid=True)
        result.add_issue(ValidationIssue(
            code="TEST",
            message="Test info",
            severity=ValidationSeverity.INFO,
        ))
        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0


class TestBenchmarkValidatorNoData:
    """Tests for validation with empty data."""

    def test_empty_frametimes_fails(self):
        """Empty frametime list should fail validation."""
        validator = BenchmarkValidator()
        result = validator.validate([])
        assert result.valid is False
        assert any(i.code == "NO_DATA" for i in result.errors)


class TestMinimumDuration:
    """Tests for minimum duration validation (>=30 seconds)."""

    def test_duration_too_short_fails(self):
        """Benchmark shorter than 30 seconds should fail."""
        validator = BenchmarkValidator()
        # 1000 frames at 60 FPS = ~16.7 seconds
        frametimes = [16.67] * 1000
        result = validator.validate(frametimes)
        assert result.valid is False
        assert any(i.code == "DURATION_TOO_SHORT" for i in result.errors)

    def test_duration_exactly_30_seconds_passes(self):
        """Benchmark of exactly 30 seconds should pass."""
        validator = BenchmarkValidator()
        # 30 seconds = 30000 ms total, spread over 1000 frames = 30ms each
        frametimes = [30.0] * 1000
        result = validator.validate(frametimes)
        # Should not have duration error (may have other issues)
        assert not any(i.code == "DURATION_TOO_SHORT" for i in result.issues)

    def test_duration_over_30_seconds_passes(self):
        """Benchmark over 30 seconds should pass duration check."""
        validator = BenchmarkValidator()
        # 60 seconds worth at 60 FPS
        frametimes = [16.67] * 3600
        result = validator.validate(frametimes)
        assert not any(i.code == "DURATION_TOO_SHORT" for i in result.issues)


class TestMinimumFrames:
    """Tests for minimum frame count validation (>=1000 frames)."""

    def test_too_few_frames_fails(self):
        """Benchmark with less than 1000 frames should fail."""
        validator = BenchmarkValidator()
        # Only 500 frames, but long enough (50ms each = 25 seconds... too short)
        # Let's make them 70ms each = 35 seconds
        frametimes = [70.0] * 500
        result = validator.validate(frametimes)
        assert result.valid is False
        assert any(i.code == "TOO_FEW_FRAMES" for i in result.errors)

    def test_exactly_1000_frames_passes(self):
        """Benchmark with exactly 1000 frames should pass frame count."""
        validator = BenchmarkValidator()
        # 1000 frames at 30ms each = 30 seconds (exactly minimum)
        frametimes = [30.0] * 1000
        result = validator.validate(frametimes)
        assert not any(i.code == "TOO_FEW_FRAMES" for i in result.issues)

    def test_over_1000_frames_passes(self):
        """Benchmark with over 1000 frames should pass."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes)
        assert not any(i.code == "TOO_FEW_FRAMES" for i in result.issues)


class TestFPSRange:
    """Tests for FPS range validation (1-1000)."""

    def test_normal_fps_no_warning(self):
        """Normal FPS values should not trigger warning."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000  # ~60 FPS
        result = validator.validate(frametimes, fps_avg=60.0, fps_min=45.0, fps_max=75.0)
        assert not any(i.code == "FPS_OUT_OF_RANGE" for i in result.issues)

    def test_very_high_fps_warning(self):
        """FPS over 1000 should trigger warning (but not error)."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, fps_avg=1500.0, fps_max=2000.0)
        assert any(i.code == "FPS_OUT_OF_RANGE" for i in result.warnings)
        # Should still be valid (warning only)
        assert not any(i.code == "FPS_OUT_OF_RANGE" for i in result.errors)

    def test_very_low_fps_warning(self):
        """FPS below 1 should trigger warning."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, fps_avg=0.5)
        assert any(i.code == "FPS_OUT_OF_RANGE" for i in result.warnings)


class TestFrametimeGaps:
    """Tests for loading screen detection (gaps > 5 seconds)."""

    def test_no_gaps_no_info(self):
        """Normal frametimes without gaps should not have loading screen info."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000  # All normal
        result = validator.validate(frametimes)
        assert not any(i.code == "LOADING_SCREENS_DETECTED" for i in result.issues)

    def test_single_loading_screen_detected(self):
        """Single gap > 5 seconds should be detected as loading screen."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 1000  # Normal gameplay
        frametimes.append(6000.0)  # 6 second gap (loading screen)
        frametimes.extend([16.67] * 1000)  # More gameplay

        result = validator.validate(frametimes)
        loading_info = [i for i in result.issues if i.code == "LOADING_SCREENS_DETECTED"]
        assert len(loading_info) == 1
        assert loading_info[0].severity == ValidationSeverity.INFO
        assert loading_info[0].details["gap_count"] == 1

    def test_multiple_loading_screens_detected(self):
        """Multiple gaps should all be detected."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 500
        frametimes.append(7000.0)  # First loading screen
        frametimes.extend([16.67] * 500)
        frametimes.append(8000.0)  # Second loading screen
        frametimes.extend([16.67] * 500)

        result = validator.validate(frametimes)
        loading_info = [i for i in result.issues if i.code == "LOADING_SCREENS_DETECTED"]
        assert len(loading_info) == 1
        assert loading_info[0].details["gap_count"] == 2

    def test_loading_screen_metadata(self):
        """Loading screen info should be in metadata."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 1000
        frametimes.append(10000.0)  # 10 second loading screen
        frametimes.extend([16.67] * 1000)

        result = validator.validate(frametimes)
        assert "loading_screens" in result.metadata
        assert result.metadata["loading_screens"]["count"] == 1
        assert result.metadata["loading_screens"]["total_duration_ms"] == 10000.0


class TestMangoHudVersion:
    """Tests for MangoHud version validation."""

    def test_known_version_no_warning(self):
        """Known MangoHud version should not trigger warning."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, mangohud_version="0.7.2")
        assert not any(i.code == "UNKNOWN_MANGOHUD_VERSION" for i in result.issues)

    def test_version_with_v_prefix(self):
        """Version with 'v' prefix should be normalized."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, mangohud_version="v0.7.2")
        assert not any(i.code == "UNKNOWN_MANGOHUD_VERSION" for i in result.issues)

    def test_unknown_version_warning(self):
        """Unknown MangoHud version should trigger warning."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, mangohud_version="0.5.0")
        assert any(i.code == "UNKNOWN_MANGOHUD_VERSION" for i in result.warnings)

    def test_no_version_no_warning(self):
        """Missing MangoHud version should not cause issues."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000
        result = validator.validate(frametimes, mangohud_version=None)
        assert not any(i.code == "UNKNOWN_MANGOHUD_VERSION" for i in result.issues)


class TestConvenienceFunction:
    """Tests for validate_benchmark_for_upload function."""

    def test_valid_benchmark(self):
        """Valid benchmark should pass all checks."""
        frametimes = [16.67] * 2000  # 60 FPS for ~33 seconds
        fps_metrics = {"average": 60.0, "minimum": 45.0, "maximum": 75.0}

        result = validate_benchmark_for_upload(
            frametimes=frametimes,
            fps_metrics=fps_metrics,
            mangohud_version="0.7.2",
        )

        assert result.valid is True
        assert len(result.errors) == 0

    def test_invalid_benchmark(self):
        """Invalid benchmark should fail."""
        frametimes = [16.67] * 100  # Too short

        result = validate_benchmark_for_upload(frametimes=frametimes)

        assert result.valid is False
        assert len(result.errors) > 0


class TestCombinedValidation:
    """Tests for combined validation scenarios."""

    def test_multiple_errors(self):
        """Benchmark can have multiple errors."""
        validator = BenchmarkValidator()
        # Too short AND too few frames
        frametimes = [16.67] * 100  # ~1.7 seconds, 100 frames

        result = validator.validate(frametimes)

        assert result.valid is False
        assert any(i.code == "DURATION_TOO_SHORT" for i in result.errors)
        assert any(i.code == "TOO_FEW_FRAMES" for i in result.errors)

    def test_valid_with_warnings_and_info(self):
        """Valid benchmark can have warnings and info."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 1000
        frametimes.append(6000.0)  # Loading screen
        frametimes.extend([16.67] * 1000)

        result = validator.validate(
            frametimes,
            fps_avg=1200.0,  # Abnormally high (warning)
            mangohud_version="0.5.0",  # Unknown (warning)
        )

        # Still valid despite warnings and info
        assert result.valid is True
        assert len(result.warnings) >= 1
        assert any(i.code == "LOADING_SCREENS_DETECTED" for i in result.issues)

    def test_metadata_always_present(self):
        """Metadata should always be populated."""
        validator = BenchmarkValidator()
        frametimes = [16.67] * 2000

        result = validator.validate(frametimes)

        assert "frame_count" in result.metadata
        assert "duration_seconds" in result.metadata
        assert result.metadata["frame_count"] == 2000
