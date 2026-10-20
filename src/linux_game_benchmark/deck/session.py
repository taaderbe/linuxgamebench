"""Recording session driven by the chord: start -> stop -> (cancel window) -> upload.

Pure state machine with injected time, so every path is testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Phase(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PENDING = "pending"          # stopped, the cancel window is still open


@dataclass(frozen=True)
class Segment:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Event:
    kind: str                    # started | stopped | too_short | cancelled | upload_due
    segment: Optional[Segment] = None


class RecordingSession:
    def __init__(self, min_seconds: float = 30.0, cancel_window: float = 10.0, auto_upload: bool = True):
        self.min_seconds = min_seconds
        self.cancel_window = cancel_window
        self.auto_upload = auto_upload
        self.phase = Phase.IDLE
        self._start = 0.0
        self._segment: Optional[Segment] = None
        self._upload_at = 0.0

    def trigger(self, now: float) -> Optional[Event]:
        """The chord was pressed."""
        if self.phase is Phase.IDLE:
            self.phase = Phase.RECORDING
            self._start = now
            return Event("started")
        if self.phase is Phase.RECORDING:
            if now - self._start < self.min_seconds:
                return Event("too_short", Segment(self._start, now))       # keep recording
            self._segment = Segment(self._start, now)
            if self.auto_upload:
                self.phase = Phase.PENDING
                self._upload_at = now + self.cancel_window
            else:
                self.phase = Phase.IDLE
            return Event("stopped", self._segment)
        # PENDING: the same chord cancels the upload
        segment, self._segment = self._segment, None
        self.phase = Phase.IDLE
        return Event("cancelled", segment)

    def reset(self) -> None:
        """Forget a recording that could not be started (e.g. no game running)."""
        self.phase = Phase.IDLE
        self._segment = None

    def tick(self, now: float) -> Optional[Event]:
        """Call regularly; returns upload_due once the cancel window has passed."""
        if self.phase is Phase.PENDING and now >= self._upload_at:
            segment, self._segment = self._segment, None
            self.phase = Phase.IDLE
            return Event("upload_due", segment)
        return None
