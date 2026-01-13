"""
Performance Metrics Analyzer.

Analyzes MangoHud CSV logs to calculate:
- FPS metrics (avg, min, max, 1% low, 0.1% low)
- Stutter detection (variance, events, sequences)
- FPS drop detection
- Frame pacing analysis
"""

import csv
import statistics
from pathlib import Path
from typing import Optional


class FrametimeAnalyzer:
    """Analyzes frametime data from MangoHud logs."""

    def __init__(self, log_path: Path):
        """
        Initialize analyzer with a MangoHud CSV log.

        Args:
            log_path: Path to the MangoHud CSV log file.
        """
        self.log_path = Path(log_path)
        self.frametimes: list[float] = []
        self.fps_values: list[float] = []
        self.timestamps: list[float] = []

        # Additional metrics from MangoHud
        self.gpu_temps: list[float] = []
        self.cpu_temps: list[float] = []
        self.gpu_loads: list[float] = []
        self.cpu_loads: list[float] = []
        self.gpu_power: list[float] = []
        self.gpu_clock: list[float] = []
        self.vram_usage: list[float] = []
        self.ram_usage: list[float] = []
        self.resolution: Optional[str] = None

        self._load_data()

    def _load_data(self) -> None:
        """Load and parse MangoHud CSV log."""
        with open(self.log_path, "r") as f:
            lines = f.readlines()

        # Find the FRAME METRICS section (MangoHud format v0.8+)
        data_start = 0
        for i, line in enumerate(lines):
            if "FRAME METRICS" in line or line.startswith("fps,"):
                # Next line is the header if this is the section marker
                if "FRAME METRICS" in line:
                    data_start = i + 1
                else:
                    data_start = i
                break
            # Also try to detect header directly (old format)
            if line.startswith("frametime,") or ",frametime," in line.lower():
                data_start = i
                break

        # Parse CSV from the data section
        from io import StringIO
        csv_data = "".join(lines[data_start:])
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            try:
                # Frametime (preferred) - check various column names
                frametime_key = self._find_key(row, ["frametime", "Frame Time", "frame_time"])
                ft = None
                fps = None

                if frametime_key and row[frametime_key]:
                    ft = float(row[frametime_key])

                # Also get FPS if available
                fps_key = self._find_key(row, ["fps", "FPS"])
                if fps_key and row[fps_key]:
                    fps = float(row[fps_key])

                # Use frametime if available, else calculate from fps
                if ft is not None and ft > 0:
                    # Filter: 0.5ms to 100ms = 10-2000 FPS range (normal gameplay)
                    if 0.5 < ft < 100:
                        self.frametimes.append(ft)
                        self.fps_values.append(1000.0 / ft)
                elif fps is not None and fps > 0:
                    # Filter: 10-2000 FPS range
                    if 10 < fps < 2000:
                        self.fps_values.append(fps)
                        self.frametimes.append(1000.0 / fps)

                # Optional: GPU temp
                gpu_temp_key = self._find_key(row, ["gpu_temp", "GPU Temp"])
                if gpu_temp_key and row[gpu_temp_key]:
                    self.gpu_temps.append(float(row[gpu_temp_key]))

                # Optional: CPU temp
                cpu_temp_key = self._find_key(row, ["cpu_temp", "CPU Temp"])
                if cpu_temp_key and row[cpu_temp_key]:
                    self.cpu_temps.append(float(row[cpu_temp_key]))

                # Optional: GPU load
                gpu_load_key = self._find_key(row, ["gpu_load", "GPU Load"])
                if gpu_load_key and row[gpu_load_key]:
                    val = float(row[gpu_load_key])
                    if val > 0:  # Only add if actually reported
                        self.gpu_loads.append(val)

                # Optional: CPU load
                cpu_load_key = self._find_key(row, ["cpu_load", "CPU Load"])
                if cpu_load_key and row[cpu_load_key]:
                    val = float(row[cpu_load_key])
                    if val > 0:
                        self.cpu_loads.append(val)

                # Optional: GPU power
                gpu_power_key = self._find_key(row, ["gpu_power", "GPU Power"])
                if gpu_power_key and row[gpu_power_key]:
                    val = float(row[gpu_power_key])
                    if val > 0:
                        self.gpu_power.append(val)

                # Optional: GPU clock
                gpu_clock_key = self._find_key(row, ["gpu_core_clock", "GPU Core Clock"])
                if gpu_clock_key and row[gpu_clock_key]:
                    val = float(row[gpu_clock_key])
                    if val > 0:
                        self.gpu_clock.append(val)

                # Optional: VRAM
                vram_key = self._find_key(row, ["vram", "VRAM", "gpu_vram_used"])
                if vram_key and row[vram_key]:
                    self.vram_usage.append(float(row[vram_key]))

                # Optional: Resolution (only need to capture once)
                if self.resolution is None:
                    res_key = self._find_key(row, ["resolution", "Resolution"])
                    if res_key and row[res_key]:
                        self.resolution = row[res_key]

            except (ValueError, KeyError):
                continue

    def _find_key(self, row: dict, candidates: list[str]) -> Optional[str]:
        """Find a matching key from candidates in the row."""
        for key in candidates:
            if key in row:
                return key
        return None

    @property
    def log_system_info(self) -> dict:
        """
        Extract system info from MangoHud log header.

        MangoHud logs include a SYSTEM INFO section with OS, CPU, GPU, etc.
        This is useful for multi-GPU systems to identify which GPU was used.

        Returns:
            Dict with keys: os, cpu, gpu, kernel (None if not found)
        """
        import csv
        from io import StringIO

        info = {"os": None, "cpu": None, "gpu": None, "kernel": None}

        try:
            with open(self.log_path, "r") as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if "SYSTEM INFO" in line:
                    # Next line is header, line after is data
                    if i + 2 < len(lines):
                        header_line = lines[i + 1].strip()
                        data_line = lines[i + 2].strip()

                        # Use proper CSV parsing to handle quoted fields
                        header_reader = csv.reader(StringIO(header_line))
                        data_reader = csv.reader(StringIO(data_line))

                        header = next(header_reader, [])
                        data = next(data_reader, [])

                        # Only parse if field counts match
                        if len(header) == len(data):
                            for h, d in zip(header, data):
                                h = h.strip()
                                if h in ("os", "cpu", "gpu", "kernel"):
                                    info[h] = d.strip()

                            # Validate GPU doesn't look like a CPU
                            gpu = info.get("gpu", "") or ""
                            cpu_keywords = ["ryzen", "intel core", "i5-", "i7-", "i9-", "threadripper", "xeon"]
                            if any(kw in gpu.lower() for kw in cpu_keywords):
                                # GPU field contains CPU name - parsing error, clear it
                                info["gpu"] = None
                    break
        except Exception:
            pass

        return info

    def analyze(self) -> dict:
        """
        Perform full analysis of the frametime data.

        Returns:
            Dictionary with fps, stutter, drops, frame_pacing metrics.
        """
        if not self.frametimes:
            raise ValueError("No frametime data loaded")

        # Calculate FPS metrics first
        fps_metrics = self.calculate_fps_metrics()

        result = {
            "fps": fps_metrics,
            "stutter": self.analyze_stutter(),
            "fps_drops": self.detect_fps_drops(),
            "frame_pacing": self.analyze_frame_pacing(fps_metrics),  # Pass FPS metrics
            "hardware": self.analyze_hardware_usage(),
            "summary": self.generate_summary(),
        }

        # Add resolution if available
        if self.resolution:
            result["resolution"] = self.resolution

        return result

    def calculate_fps_metrics(self) -> dict:
        """Calculate FPS statistics."""
        if not self.frametimes:
            return {}

        # Get gameplay frametimes (excluding transition spikes)
        gameplay_ft = self._get_gameplay_frametimes(threshold_ms=50.0)
        gameplay_fps = [1000.0 / ft for ft in gameplay_ft]

        # Average FPS (from gameplay frametimes)
        avg_frametime = statistics.mean(gameplay_ft)
        avg_fps = 1000.0 / avg_frametime

        # 1% Low and 0.1% Low (integral method, gameplay only)
        low_1 = self._calculate_percentile_low_filtered(gameplay_ft, 1.0)
        low_01 = self._calculate_percentile_low_filtered(gameplay_ft, 0.1)

        return {
            "average": round(avg_fps, 2),
            "minimum": round(min(gameplay_fps), 2),
            "maximum": round(max(gameplay_fps), 2),
            "median": round(statistics.median(gameplay_fps), 2),
            "1_percent_low": round(low_1, 2),
            "0.1_percent_low": round(low_01, 2),
            "std_dev": round(statistics.stdev(gameplay_fps), 2) if len(gameplay_fps) > 1 else 0,
            "frame_count": len(gameplay_ft),
            "duration_seconds": round(sum(gameplay_ft) / 1000.0, 2),
        }

    def _calculate_percentile_low_filtered(self, frametimes: list[float], percentile: float) -> float:
        """Calculate x% low FPS from filtered frametimes."""
        if not frametimes:
            return 0.0

        frametimes_sorted = sorted(frametimes, reverse=True)
        total_time = sum(frametimes)
        target_time = total_time * (percentile / 100.0)

        cumulative = 0.0
        for ft in frametimes_sorted:
            cumulative += ft
            if cumulative >= target_time:
                return 1000.0 / ft

        return 1000.0 / frametimes_sorted[-1]

    def _calculate_percentile_low(self, percentile: float) -> float:
        """
        Calculate x% low FPS using integral method.

        This gives the FPS you stay above for (100-x)% of the time.
        More meaningful than simple percentile of FPS values.
        """
        frametimes_sorted = sorted(self.frametimes, reverse=True)  # Worst first
        total_time = sum(self.frametimes)
        target_time = total_time * (percentile / 100.0)

        cumulative = 0.0
        for ft in frametimes_sorted:
            cumulative += ft
            if cumulative >= target_time:
                return 1000.0 / ft

        return 1000.0 / frametimes_sorted[-1]

    def analyze_stutter(self, threshold_ms: float = 50.0) -> dict:
        """
        Analyze stutter in the frametime data.

        Separates scene transitions (isolated spikes) from real gameplay stutter.

        Args:
            threshold_ms: Frametime threshold for stutter events.

        Returns:
            Dictionary with stutter metrics.
        """
        if not self.frametimes:
            return {}

        mean_ft = statistics.mean(self.frametimes)

        # Detect all high-frametime events and classify them
        transition_events = []
        gameplay_stutter_events = []

        for i, ft in enumerate(self.frametimes):
            if ft > threshold_ms:
                event = {
                    "frame": i,
                    "frametime_ms": round(ft, 2),
                    "severity": round(ft / mean_ft, 2),
                }
                if self._is_transition_spike(i, threshold_ms):
                    event["type"] = "transition"
                    transition_events.append(event)
                else:
                    event["type"] = "stutter"
                    gameplay_stutter_events.append(event)

        # Calculate gameplay stutter index (excluding transition spikes)
        gameplay_frametimes = self._get_gameplay_frametimes(threshold_ms)
        if gameplay_frametimes and len(gameplay_frametimes) > 1:
            gameplay_mean = statistics.mean(gameplay_frametimes)
            gameplay_std = statistics.stdev(gameplay_frametimes)
            gameplay_stutter_index = (gameplay_std / gameplay_mean) * 100 if gameplay_mean > 0 else 0
        else:
            gameplay_stutter_index = 0

        # Full stutter index (for reference)
        std_ft = statistics.stdev(self.frametimes) if len(self.frametimes) > 1 else 0
        full_stutter_index = (std_ft / mean_ft) * 100 if mean_ft > 0 else 0

        # Stutter sequences (consecutive bad frames - these are real stutter)
        sequences = self._detect_stutter_sequences(threshold_ms=33.0)

        # Frame time deltas (sudden changes)
        sudden_changes = self._detect_sudden_changes(delta_threshold=10.0)

        # Combined events list with type markers
        all_events = sorted(
            transition_events + gameplay_stutter_events,
            key=lambda x: x["frame"]
        )

        # Calculate stutter rating based on actual stutter events and sequences
        stutter_rating = self._rate_gameplay_stutter(
            gameplay_stutter_count=len(gameplay_stutter_events),
            sequence_count=len(sequences),
            total_frames=len(self.frametimes),
        )

        return {
            "stutter_index": round(full_stutter_index, 2),
            "gameplay_stutter_index": round(gameplay_stutter_index, 2),
            "stutter_rating": stutter_rating,
            "transition_count": len(transition_events),
            "gameplay_stutter_count": len(gameplay_stutter_events),
            "event_count": len(all_events),
            "events": all_events[:20],
            "sequence_count": len(sequences),
            "sequences": sequences[:10],
            "sudden_change_count": len(sudden_changes),
            "variance": round(std_ft ** 2, 2),
        }

    def _is_transition_spike(self, index: int, threshold_ms: float = 50.0) -> bool:
        """
        Check if a frametime spike is an isolated scene transition.

        A transition spike is:
        - A single large spike (>threshold_ms)
        - Surrounded by normal frames (<20ms) before and after

        Args:
            index: Frame index to check.
            threshold_ms: Minimum frametime to consider as spike.

        Returns:
            True if this looks like a scene transition, not gameplay stutter.
        """
        # Need enough frames before and after to check context
        window = 5
        if index < window or index >= len(self.frametimes) - window:
            return False

        current = self.frametimes[index]
        if current < threshold_ms:
            return False

        # Check frames before (should be normal gameplay)
        before = self.frametimes[index - window:index]
        avg_before = sum(before) / len(before)

        # Check frames after (should be normal gameplay)
        after = self.frametimes[index + 1:index + 1 + window]
        avg_after = sum(after) / len(after)

        # Normal gameplay threshold - typical frame at 60fps is ~16ms
        normal_threshold = 20.0

        # It's a transition if frames around it are normal
        return avg_before < normal_threshold and avg_after < normal_threshold

    def _get_gameplay_frametimes(self, threshold_ms: float = 50.0) -> list[float]:
        """
        Get frametimes excluding isolated transition spikes.

        Args:
            threshold_ms: Threshold for identifying spikes.

        Returns:
            List of frametimes with transition spikes removed.
        """
        result = []
        for i, ft in enumerate(self.frametimes):
            # Include frame if it's below threshold or if it's not a transition
            if ft < threshold_ms or not self._is_transition_spike(i, threshold_ms):
                result.append(ft)
        return result

    def _rate_stutter_index(self, si: float) -> str:
        """Rate stutter index (CV-based, legacy)."""
        if si < 5:
            return "Excellent"
        elif si < 10:
            return "Good"
        elif si < 20:
            return "Moderate"
        else:
            return "Poor"

    def _rate_gameplay_stutter(
        self,
        gameplay_stutter_count: int,
        sequence_count: int,
        total_frames: int,
    ) -> str:
        """
        Rate gameplay stutter based on actual events, not just variance.

        Args:
            gameplay_stutter_count: Number of real stutter events (not transitions).
            sequence_count: Number of consecutive slow frame sequences.
            total_frames: Total frames in the benchmark.

        Returns:
            Rating: "Excellent", "Good", "Moderate", or "Poor".
        """
        if total_frames == 0:
            return "unknown"

        # Calculate stutter events per 1000 frames
        stutter_per_1k = (gameplay_stutter_count / total_frames) * 1000

        # No real stutter events = excellent
        if gameplay_stutter_count == 0 and sequence_count == 0:
            return "Excellent"

        # Very few stutter events = good
        if stutter_per_1k < 0.5 and sequence_count <= 1:
            return "Good"

        # Some stutter events = moderate
        if stutter_per_1k < 2.0 and sequence_count <= 3:
            return "Moderate"

        # Many stutter events = poor
        return "Poor"

    def _detect_stutter_sequences(self, threshold_ms: float = 33.0) -> list[dict]:
        """Detect sequences of consecutive slow frames."""
        sequences = []
        current_seq: list[tuple[int, float]] = []

        for i, ft in enumerate(self.frametimes):
            if ft > threshold_ms:
                current_seq.append((i, ft))
            else:
                if len(current_seq) >= 3:
                    sequences.append({
                        "start_frame": current_seq[0][0],
                        "end_frame": current_seq[-1][0],
                        "length": len(current_seq),
                        "avg_frametime": round(
                            sum(x[1] for x in current_seq) / len(current_seq), 2
                        ),
                        "max_frametime": round(max(x[1] for x in current_seq), 2),
                    })
                current_seq = []

        return sequences

    def _detect_sudden_changes(self, delta_threshold: float = 10.0) -> list[dict]:
        """Detect sudden frametime changes."""
        changes = []
        for i in range(1, len(self.frametimes)):
            delta = abs(self.frametimes[i] - self.frametimes[i - 1])
            if delta > delta_threshold:
                changes.append({
                    "frame": i,
                    "delta_ms": round(delta, 2),
                    "from_ms": round(self.frametimes[i - 1], 2),
                    "to_ms": round(self.frametimes[i], 2),
                })
        return changes

    def detect_fps_drops(
        self,
        drop_threshold_percent: float = 20.0,
        window_size: int = 60,
    ) -> dict:
        """
        Detect FPS drops.

        Args:
            drop_threshold_percent: Percentage below average to count as drop.
            window_size: Window size for rolling average.

        Returns:
            Dictionary with drop detection results.
        """
        if len(self.frametimes) < window_size:
            return {"drop_count": 0, "drops": []}

        # Calculate rolling FPS
        rolling_fps = []
        for i in range(len(self.frametimes) - window_size + 1):
            window = self.frametimes[i : i + window_size]
            avg_ft = sum(window) / len(window)
            rolling_fps.append(1000.0 / avg_ft)

        if not rolling_fps:
            return {"drop_count": 0, "drops": []}

        avg_fps = sum(rolling_fps) / len(rolling_fps)
        threshold_fps = avg_fps * (1 - drop_threshold_percent / 100)

        # Find drops
        drops = []
        in_drop = False
        drop_start = 0

        for i, fps in enumerate(rolling_fps):
            if fps < threshold_fps and not in_drop:
                in_drop = True
                drop_start = i
            elif fps >= threshold_fps and in_drop:
                in_drop = False
                drop_fps = rolling_fps[drop_start:i]
                drops.append({
                    "start_frame": drop_start,
                    "end_frame": i,
                    "duration_frames": i - drop_start,
                    "min_fps": round(min(drop_fps), 2),
                    "avg_fps_during": round(sum(drop_fps) / len(drop_fps), 2),
                    "drop_percent": round((1 - min(drop_fps) / avg_fps) * 100, 1),
                })

        return {
            "drop_count": len(drops),
            "total_drop_duration_frames": sum(d["duration_frames"] for d in drops),
            "drops": drops[:10],  # Limit to first 10
        }

    def analyze_frame_pacing(self, fps_metrics: Optional[dict] = None) -> dict:
        """
        Analyze frame pacing consistency.

        Args:
            fps_metrics: Optional pre-calculated FPS metrics to use for consistency rating.
                        If not provided, will calculate from raw frametimes.
        """
        if len(self.frametimes) < 2:
            return {}

        # Calculate frame-to-frame deltas (using gameplay frametimes if available)
        gameplay_ft = self._get_gameplay_frametimes(threshold_ms=50.0)
        deltas = [
            abs(gameplay_ft[i] - gameplay_ft[i - 1])
            for i in range(1, len(gameplay_ft))
        ]

        avg_frametime = statistics.mean(gameplay_ft)

        # Consistency score (lower is better)
        # Based on how close frametimes are to each other
        consistency_score = statistics.mean(deltas) / avg_frametime * 100

        # Use pre-calculated FPS metrics if provided, otherwise calculate
        if fps_metrics:
            avg_fps = fps_metrics.get('average', 0)
            low_1 = fps_metrics.get('1_percent_low', 0)
            std_fps = fps_metrics.get('std_dev', 0)
            cv = (std_fps / avg_fps * 100) if avg_fps > 0 else 0
        else:
            # Calculate from gameplay frametimes
            gameplay_fps = [1000.0 / ft for ft in gameplay_ft]
            avg_fps = statistics.mean(gameplay_fps)
            std_fps = statistics.stdev(gameplay_fps) if len(gameplay_fps) > 1 else 0
            cv = (std_fps / avg_fps * 100) if avg_fps > 0 else 0
            low_1 = self._calculate_percentile_low_filtered(gameplay_ft, 1.0)

        # Calculate consistency based on multiple factors
        consistency_rating = self._rate_frame_consistency(cv, avg_fps, low_1)

        return {
            "avg_delta_ms": round(statistics.mean(deltas), 2),
            "max_delta_ms": round(max(deltas), 2),
            "consistency_score": round(consistency_score, 2),
            "consistency_rating": consistency_rating,
            "cv_percent": round(cv, 1),
            "fps_stability": round((low_1 / avg_fps * 100), 1) if avg_fps > 0 else 0,
        }

    def _rate_consistency(self, score: float) -> str:
        """Rate frame pacing consistency (legacy method)."""
        if score < 10:
            return "Excellent"
        elif score < 25:
            return "Good"
        elif score < 50:
            return "Moderate"
        else:
            return "Poor"

    def _rate_frame_consistency(self, cv: float, avg_fps: float, low_1_fps: float) -> str:
        """
        Rate overall frame consistency based on multiple factors.

        Uses absolute 1% low FPS thresholds combined with relative variance.
        This ensures high FPS games with large percentage drops but smooth
        absolute performance don't get unfairly penalized.

        Args:
            cv: Coefficient of variation (%)
            avg_fps: Average FPS
            low_1_fps: 1% low FPS

        Returns:
            Rating: "excellent", "good", "moderate", or "poor"
        """
        # Calculate how much FPS drops at 1% low
        fps_drop_percent = ((avg_fps - low_1_fps) / avg_fps * 100) if avg_fps > 0 else 0

        # FPS-Cap Detection: Games locked at common refresh rates get fairer ratings
        # When AVG is very close to a cap AND 1% low is stable, the rating should be better
        common_caps = [30, 60, 120, 144, 165, 240]
        is_likely_capped = any(abs(avg_fps - cap) < 2 for cap in common_caps)

        if is_likely_capped and fps_drop_percent < 15:
            # Capped games with stable 1% low get at least "Good"
            if low_1_fps >= 50:  # ~60 FPS cap with stable lows
                return "Good"
            elif low_1_fps >= 100:  # ~120 FPS cap with stable lows
                return "Good"
            elif low_1_fps >= 25:  # ~30 FPS cap with stable lows
                return "Moderate"

        # High FPS range (1% low >= 120): Drops matter less due to high absolute values
        if low_1_fps >= 120:
            if cv < 15 and fps_drop_percent < 40:
                return "Excellent"
            elif cv < 30 and fps_drop_percent < 60:
                return "Good"
            elif fps_drop_percent < 70:
                return "Moderate"
            else:
                return "Poor"

        # Very smooth range (1% low >= 90): Still very playable
        elif low_1_fps >= 90:
            if cv < 12 and fps_drop_percent < 30:
                return "Excellent"
            elif cv < 25 and fps_drop_percent < 50:
                return "Good"
            elif fps_drop_percent < 65:
                return "Moderate"
            else:
                return "Poor"

        # Smooth range (1% low >= 60): Acceptable for most games
        elif low_1_fps >= 60:
            if cv < 10 and fps_drop_percent < 20:
                return "Excellent"
            elif cv < 20 and fps_drop_percent < 35:
                return "Good"
            elif fps_drop_percent < 45:
                return "Moderate"
            else:
                return "Poor"

        # Playable but stuttery (1% low >= 40): Noticeable but playable
        elif low_1_fps >= 40:
            if cv < 8 and fps_drop_percent < 15:
                return "Good"
            elif cv < 15 and fps_drop_percent < 30:
                return "Moderate"
            else:
                return "Poor"

        # Critical range (1% low < 40): Significantly impacts experience
        else:
            # Below 40 FPS is always poor consistency
            return "Poor"

    def analyze_hardware_usage(self) -> dict:
        """Analyze hardware metrics if available."""
        result = {}

        if self.gpu_temps:
            result["gpu_temp"] = {
                "avg": round(statistics.mean(self.gpu_temps), 1),
                "max": round(max(self.gpu_temps), 1),
            }

        if self.cpu_temps:
            result["cpu_temp"] = {
                "avg": round(statistics.mean(self.cpu_temps), 1),
                "max": round(max(self.cpu_temps), 1),
            }

        if self.gpu_loads:
            result["gpu_load"] = {
                "avg": round(statistics.mean(self.gpu_loads), 1),
                "max": round(max(self.gpu_loads), 1),
            }

        if self.cpu_loads:
            result["cpu_load"] = {
                "avg": round(statistics.mean(self.cpu_loads), 1),
                "max": round(max(self.cpu_loads), 1),
            }

        if self.gpu_power:
            result["gpu_power"] = {
                "avg": round(statistics.mean(self.gpu_power), 1),
                "max": round(max(self.gpu_power), 1),
            }

        if self.gpu_clock:
            result["gpu_clock"] = {
                "avg": round(statistics.mean(self.gpu_clock), 0),
                "max": round(max(self.gpu_clock), 0),
            }

        if self.vram_usage:
            result["vram"] = {
                "avg_mb": round(statistics.mean(self.vram_usage), 0),
                "max_mb": round(max(self.vram_usage), 0),
            }

        # Bottleneck analysis
        result["bottleneck"] = self._analyze_bottleneck()

        return result

    def _analyze_bottleneck(self) -> dict:
        """
        Analyze whether the game is CPU or GPU limited.

        Returns:
            Dictionary with bottleneck analysis.
        """
        avg_fps = statistics.mean(self.fps_values) if self.fps_values else 0
        avg_cpu = statistics.mean(self.cpu_loads) if self.cpu_loads else 0
        avg_gpu = statistics.mean(self.gpu_loads) if self.gpu_loads else 0
        avg_gpu_power = statistics.mean(self.gpu_power) if self.gpu_power else 0

        # Determine bottleneck
        bottleneck = "unknown"
        confidence = "low"
        explanation = ""

        # GPU load available
        if avg_gpu > 0:
            if avg_gpu > 90 and avg_cpu < 70:
                bottleneck = "gpu"
                confidence = "high"
                explanation = f"GPU bei {avg_gpu:.0f}% Auslastung"
            elif avg_cpu > 80 and avg_gpu < 70:
                bottleneck = "cpu"
                confidence = "high"
                explanation = f"CPU bei {avg_cpu:.0f}% Auslastung"
            elif avg_gpu > 70 and avg_cpu > 70:
                bottleneck = "balanced"
                confidence = "medium"
                explanation = f"Beide ca. {avg_gpu:.0f}%/{avg_cpu:.0f}%"
            else:
                bottleneck = "none"
                confidence = "high"
                explanation = "Weder CPU noch GPU ausgelastet"
        # Fallback: Use CPU load + power consumption
        elif avg_cpu > 0:
            if avg_cpu > 80:
                bottleneck = "cpu"
                confidence = "medium"
                explanation = f"CPU bei {avg_cpu:.0f}% (GPU-Load nicht verfügbar)"
            elif avg_cpu < 50 and avg_fps > 100:
                bottleneck = "none"
                confidence = "medium"
                explanation = f"CPU nur bei {avg_cpu:.0f}%, FPS sehr hoch"
            else:
                bottleneck = "unknown"
                confidence = "low"
                explanation = "GPU-Load nicht verfügbar"

        return {
            "type": bottleneck,
            "confidence": confidence,
            "explanation": explanation,
            "cpu_avg": round(avg_cpu, 1) if avg_cpu > 0 else None,
            "gpu_avg": round(avg_gpu, 1) if avg_gpu > 0 else None,
            "gpu_power_avg": round(avg_gpu_power, 1) if avg_gpu_power > 0 else None,
        }

    def generate_summary(self) -> dict:
        """Generate overall summary and rating."""
        fps = self.calculate_fps_metrics()
        stutter = self.analyze_stutter()
        frame_pacing = self.analyze_frame_pacing()

        # Determine overall rating
        issues = []

        # Check FPS
        if fps.get("average", 0) < 30:
            issues.append("very low fps")
        elif fps.get("average", 0) < 60:
            issues.append("low fps")

        # Check 1% low vs average
        if fps.get("1_percent_low", 0) < fps.get("average", 0) * 0.5:
            issues.append("significant fps drops")

        # Check stutter
        stutter_rating = stutter.get("stutter_rating", "")
        if stutter_rating.lower() == "poor":
            issues.append("heavy stutter")
        elif stutter_rating.lower() == "moderate":
            issues.append("noticeable stutter")

        # Determine overall rating
        if not issues:
            overall = "Excellent"
        elif len(issues) == 1 and "noticeable" in issues[0]:
            overall = "Good"
        elif len(issues) <= 2:
            overall = "Acceptable"
        else:
            overall = "Poor"

        return {
            "overall_rating": overall,
            "issues": issues,
            "playability": self._describe_playability(fps.get("average", 0), stutter_rating),
        }

    def _describe_playability(self, avg_fps: float, stutter_rating: str) -> str:
        """Describe playability in human terms."""
        if avg_fps >= 60 and stutter_rating.lower() in ("excellent", "good"):
            return "Smooth gameplay experience"
        elif avg_fps >= 60:
            return "Good FPS but occasional hitches"
        elif avg_fps >= 30 and stutter_rating.lower() in ("excellent", "good"):
            return "Playable, but would benefit from optimization"
        elif avg_fps >= 30:
            return "Playable but not optimal experience"
        else:
            return "Below minimum for comfortable gameplay"


class FPSTargetEvaluator:
    """Evaluates if hardware meets FPS targets."""

    DEFAULT_TARGETS = [60, 120, 144, 165, 240]

    def __init__(self, targets: Optional[list[int]] = None):
        self.targets = targets or self.DEFAULT_TARGETS

    def evaluate(self, metrics: dict) -> dict:
        """
        Evaluate benchmark results against FPS targets.

        Args:
            metrics: Dictionary from FrametimeAnalyzer.analyze()

        Returns:
            Dictionary with target evaluations.
        """
        fps = metrics.get("fps", {})
        avg_fps = fps.get("average", 0)
        fps_1_low = fps.get("1_percent_low", 0)

        stutter = metrics.get("stutter", {})
        stutter_index = stutter.get("stutter_index", 100)

        evaluations = {}
        for target in self.targets:
            evaluations[f"{target}_fps"] = self._evaluate_target(
                target, avg_fps, fps_1_low, stutter_index
            )

        recommended = self._get_recommended_target(evaluations)

        return {
            "targets": evaluations,
            "recommended": recommended,
        }

    def _evaluate_target(
        self,
        target: int,
        avg: float,
        low1: float,
        stutter: float,
    ) -> dict:
        """
        Evaluate a single FPS target.

        Rule: 1% Low must be within 15% of target to recommend.
        """
        min_1_low = target * 0.85  # 15% tolerance

        if low1 >= target:
            rating = "Excellent"
            icon = "OK"
            description = f"1% Low über {target} FPS"
        elif low1 >= min_1_low:
            rating = "Good"
            icon = "OK"
            description = f"1% Low bei {low1:.0f} FPS (>{min_1_low:.0f})"
        else:
            rating = "Not Recommended"
            icon = "X"
            description = f"1% Low zu niedrig ({low1:.0f} < {min_1_low:.0f})"

        return {
            "target_fps": target,
            "rating": rating,
            "icon": icon,
            "description": description,
            "meets_target": rating in ("Excellent", "Good"),
        }

    def _get_recommended_target(self, evaluations: dict) -> dict:
        """Find highest achievable target."""
        for target in sorted(self.targets, reverse=True):
            eval_data = evaluations.get(f"{target}_fps", {})
            if eval_data.get("meets_target"):
                return {
                    "fps": target,
                    "rating": eval_data["rating"],
                }

        return {
            "fps": min(self.targets),
            "rating": "below_minimum",
        }
