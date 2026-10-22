"""Cut one recording out of a MangoHud log.

Desktop Mode: MangoHud logs all the time ("flight recorder") and the controller chord only sets two time marks. Game Mode: the
log was started with the chord, so it begins at the first mark. Either way the segment between the marks is written to its own
CSV in the format the benchmark pipeline already reads (system lines, header, rows; elapsed rebased to 0).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_STAMP = re.compile(r"_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.csv$")
NS = 1_000_000_000


def log_start_from_name(path: Path | str) -> Optional[float]:
    """MangoHud names its logs <process>_YYYY-MM-DD_HH-MM-SS.csv (local time) -> epoch seconds."""
    match = _STAMP.search(Path(path).name)
    if not match:
        return None
    year, month, day, hour, minute, second = (int(x) for x in match.groups())
    return datetime(year, month, day, hour, minute, second).timestamp()


# No frame for longer than this inside a recording: the game paused or hung (Vampire Survivors stops drawing while Steam's
# menu is open, and the log simply has no rows for that time). Real logs on the Deck: at most 0.07 s between two frames.
GAP_LIMIT_SECONDS = 2.0
# At the start and the end a little more is allowed: the first frame comes up to 0.5 s after the command, and in Desktop Mode
# the log's start time comes from its file name (whole seconds).
EDGE_LIMIT_SECONDS = GAP_LIMIT_SECONDS + 1.0


@dataclass(frozen=True)
class Cut:
    frames: int
    duration_seconds: float
    longest_gap_seconds: float = 0.0     # between two frames inside the segment
    head_seconds: float = 0.0            # from the start mark to the first frame
    tail_seconds: float = 0.0            # from the last frame to the end mark

    def hole_seconds(self) -> Optional[float]:
        """The longest stretch without frames, if it is too long for a usable recording - else None."""
        if self.longest_gap_seconds > GAP_LIMIT_SECONDS or max(self.head_seconds, self.tail_seconds) > EDGE_LIMIT_SECONDS:
            return max(self.longest_gap_seconds, self.head_seconds, self.tail_seconds)
        return None


def _split(line: str) -> list[str]:
    return line.rstrip("\n").split(",")


def last_elapsed_ns(path: Path | str) -> Optional[int]:
    """Elapsed time of the last complete row (reads the tail only) - tells how far MangoHud has flushed."""
    path = Path(path)
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - 4096))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    for line in reversed(lines[-3:]):
        last = line.rsplit(",", 1)[-1].strip()
        if last.isdigit():
            return int(last)
    return None


def cut_log(src: Path | str, start_epoch: float, end_epoch: float, dst: Path | str,
            log_start: Optional[float] = None) -> Cut:
    """Write the rows between the two wall-clock marks to dst. Raises ValueError when nothing matches."""
    src, dst = Path(src), Path(dst)
    if end_epoch <= start_epoch:
        raise ValueError("the end mark must be after the start mark")
    if log_start is None:
        log_start = log_start_from_name(src)
    if log_start is None:
        raise ValueError(f"cannot tell when {src.name} started (no timestamp in the file name)")
    start_ns = int((start_epoch - log_start) * NS)
    end_ns = int((end_epoch - log_start) * NS)

    head: list[str] = []
    rows: list[str] = []
    elapsed_col = -1
    first_ns: Optional[int] = None
    last_ns = 0
    longest_gap = 0
    with open(src, "r", errors="replace") as fh:
        for line in fh:
            if elapsed_col < 0:
                head.append(line)
                if line.startswith("fps,"):
                    cols = _split(line)
                    if "elapsed" not in cols:
                        raise ValueError("the log has no 'elapsed' column")
                    elapsed_col = cols.index("elapsed")
                continue
            parts = _split(line)
            if len(parts) <= elapsed_col or not parts[elapsed_col].strip().isdigit():
                continue
            ns = int(parts[elapsed_col])
            if ns < start_ns:
                continue
            if ns > end_ns:
                break
            if first_ns is None:
                first_ns = ns
            else:
                longest_gap = max(longest_gap, ns - last_ns)
            last_ns = ns
            parts[elapsed_col] = str(ns - first_ns)
            rows.append(",".join(parts) + "\n")
    if elapsed_col < 0:
        raise ValueError("no MangoHud header ('fps,...') found in the log")
    if not rows:
        raise ValueError("no frames between the marks")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(head) + "".join(rows))
    return Cut(frames=len(rows), duration_seconds=(last_ns - (first_ns or 0)) / NS, longest_gap_seconds=longest_gap / NS,
               head_seconds=max(0, (first_ns or 0) - max(start_ns, 0)) / NS, tail_seconds=max(0, end_ns - last_ns) / NS)


def wait_until_closed(src: Path | str, timeout: float = 3.0, poll: float = 0.1) -> bool:
    """A log that was ended on command: MangoHud writes the `_summary.csv` next to it when it closes the file. Wait for that
    (or for the file to stop growing) before reading it."""
    src = Path(src)
    summary = src.with_name(src.stem + "_summary.csv")
    deadline = time.monotonic() + timeout
    last, steady = -1, 0
    while time.monotonic() < deadline:
        if summary.exists():
            return True
        try:
            size = src.stat().st_size
        except OSError:
            return False
        steady = steady + 1 if size == last else 0
        if steady >= 3:
            return True
        last = size
        time.sleep(poll)
    return False


def wait_until_flushed(src: Path | str, end_epoch: float, log_start: float,
                       timeout: float = 10.0, poll: float = 0.5) -> bool:
    """MangoHud buffers its output: wait until the file reaches the end mark (or timeout)."""
    target = int((end_epoch - log_start) * NS)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        last = last_elapsed_ns(src)
        if last is not None and last >= target:
            return True
        time.sleep(poll)
    return False
