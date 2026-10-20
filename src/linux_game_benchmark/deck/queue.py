"""Recordings waiting for (or done with) their upload; survives offline times, standby and restarts."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BACKOFF_SECONDS = (300, 900, 3600, 6 * 3600)       # after the 1st, 2nd, 3rd, later failures


@dataclass
class Item:
    dir: Path
    meta: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.meta.get("id", self.dir.name)

    @property
    def segment(self) -> Path:
        return self.dir / "segment.csv"

    @property
    def status(self) -> str:
        return self.meta.get("status", "")


class Queue:
    def __init__(self, root: Path):
        self.root = Path(root)

    def add(self, segment_csv: Path, meta: dict) -> Item:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(meta.get("created", time.time())))
        directory = self.root / stamp
        n = 1
        while directory.exists():
            n += 1
            directory = self.root / f"{stamp}-{n}"
        directory.mkdir(parents=True)
        shutil.move(str(segment_csv), directory / "segment.csv")
        item = Item(directory, {"id": directory.name, "status": "pending", "attempts": 0, **meta})
        self._write(item)
        return item

    def _write(self, item: Item) -> None:
        tmp = item.dir / "meta.json.tmp"
        tmp.write_text(json.dumps(item.meta, indent=2))
        os.replace(tmp, item.dir / "meta.json")

    def items(self) -> list[Item]:
        found = []
        if not self.root.exists():
            return found
        for directory in sorted(self.root.iterdir()):
            try:
                meta = json.loads((directory / "meta.json").read_text())
            except (OSError, ValueError):
                continue
            found.append(Item(directory, meta))
        return found

    def due(self, now: Optional[float] = None) -> list[Item]:
        """Pending items whose retry time has come."""
        now = time.time() if now is None else now
        return [i for i in self.items() if i.status == "pending" and i.meta.get("next_try", 0) <= now]

    def update(self, item: Item, **changes) -> Item:
        item.meta.update(changes)
        self._write(item)
        return item

    def failed_attempt(self, item: Item, error: str, retry: bool, now: Optional[float] = None) -> Item:
        """Record a failed upload: retry later with backoff, or give up for good."""
        now = time.time() if now is None else now
        attempts = int(item.meta.get("attempts", 0)) + 1
        if not retry:
            return self.update(item, status="failed", error=error, attempts=attempts)
        delay = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
        return self.update(item, status="pending", error=error, attempts=attempts, next_try=now + delay)

    def prune(self, keep_days: float = 30.0, now: Optional[float] = None) -> int:
        """Delete finished items older than keep_days (pending ones stay)."""
        now = time.time() if now is None else now
        removed = 0
        for item in self.items():
            if item.status != "pending" and now - item.meta.get("created", now) > keep_days * 86400:
                shutil.rmtree(item.dir, ignore_errors=True)
                removed += 1
        return removed


def prune_logs(log_dir: Path, keep_days: float = 3.0, max_bytes: int = 600 * 1024 * 1024,
               active: Optional[Path] = None, now: Optional[float] = None) -> int:
    """The flight recorder writes all the time: drop old logs and keep the folder below max_bytes."""
    now = time.time() if now is None else now
    if not log_dir.exists():
        return 0
    every = list(log_dir.glob("*.csv"))
    files = sorted((p for p in every if p != active), key=lambda p: p.stat().st_mtime)
    removed = 0
    total = sum(p.stat().st_size for p in every)           # the running log counts, it is just never deleted
    for path in files:
        old = now - path.stat().st_mtime > keep_days * 86400
        if old or total > max_bytes:
            total -= path.stat().st_size
            path.unlink(missing_ok=True)
            removed += 1
    return removed
