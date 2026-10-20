"""The Deck recorder: MangoHud logs all the time, the controller chord marks start/stop, the segment is uploaded.

All collaborators are injectable, so the whole flow (chord -> cut -> queue -> upload -> retry) is tested without a Deck.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import game as deck_game
from linux_game_benchmark.deck import queue as deck_queue
from linux_game_benchmark.deck import segments, telemetry, upload
from linux_game_benchmark.deck.chord import ChordTracker, parse_chord
from linux_game_benchmark.deck.detect import DeckInfo
from linux_game_benchmark.deck.session import Event, RecordingSession, Segment


def _default_software(game: Optional[deck_game.GameInfo]) -> dict:
    tools = deck_game.launch_tools(game.app_id) if game else None
    return telemetry.read_software(tools=tools)


@dataclass
class Active:
    log: Path
    log_start: float
    game: Optional[deck_game.GameInfo]
    sampler: Optional[telemetry.Sampler] = None


class DeckService:
    def __init__(
        self,
        config: deck_config.DeckConfig,
        deck: DeckInfo,
        *,
        queue: deck_queue.Queue,
        log_dir: Path,
        work_dir: Path,
        play: Callable[[str], None] = lambda name: None,
        say: Callable[[str], None] = print,
        newest_log: Callable[..., Optional[Path]] = deck_game.newest_log,
        identify: Callable[[Path], Optional[deck_game.GameInfo]] = deck_game.identify,
        cut: Callable[..., segments.Cut] = segments.cut_log,
        wait_flushed: Callable[..., bool] = segments.wait_until_flushed,
        prepare: Callable[..., tuple] = upload.prepare,
        send: Callable[[dict], tuple[bool, str, str]] = upload.send,
        status_file: Optional[Path] = None,
        sampler_factory: Callable[[], telemetry.Sampler] = telemetry.Sampler,
        read_env: Callable[[int], dict] = telemetry.read_process_env,
        read_software: Optional[Callable[[Optional[deck_game.GameInfo]], dict]] = None,
    ):
        self.config = config
        self.deck = deck
        self.queue = queue
        self.log_dir = log_dir
        self.work_dir = work_dir
        self.play, self.say = play, say
        self._newest_log, self._identify, self._cut = newest_log, identify, cut
        self._wait_flushed, self._prepare, self._send = wait_flushed, prepare, send
        self.status_file = status_file
        self._sampler_factory, self._read_env = sampler_factory, read_env
        self._read_software = read_software or _default_software
        self.tracker = ChordTracker(parse_chord(config.chord))
        self.session = RecordingSession(config.min_seconds, config.cancel_window, config.auto_upload, config.record_seconds)
        self._active: Optional[Active] = None
        self._pending_item: Optional[deck_queue.Item] = None
        self._last_housekeeping = 0.0
        self._last_retry = 0.0
        self.last_message = ""

    # ----- input ---------------------------------------------------------------

    def on_key(self, code: int, value: int, now: float) -> None:
        if self.tracker.feed(code, value, now):
            self._guarded(self._on_trigger, now)

    def tick(self, now: float) -> None:
        self._guarded(self._tick, now)

    def _guarded(self, fn, now: float) -> None:
        try:
            fn(now)
        except Exception as exc:                 # the recorder must survive anything a game or a file throws at it
            self._message(f"internal error: {exc}", "error")
            traceback.print_exc()

    # ----- chord ---------------------------------------------------------------

    def _on_trigger(self, now: float) -> None:
        event = self.session.trigger(now)
        if event is None:
            return
        if event.kind == "started":
            self._begin(now)
        elif event.kind == "too_short":
            self._message(f"keep going - a recording needs at least {self.config.min_seconds:.0f} s", "error")
        elif event.kind == "stopped":
            self._finish(event.segment, now)
        elif event.kind == "cancelled":
            if self._pending_item is not None:
                self.queue.update(self._pending_item, status="cancelled")
                self._pending_item = None
            self._message("upload cancelled (the recording stays on the Deck)", "cancel")

    def _begin(self, now: float) -> None:
        log = self._newest_log(self.log_dir)
        start = segments.log_start_from_name(log) if log else None
        if log is None or start is None:
            self.session.reset()
            self._message("no running game found - start a game first", "error")
            return
        self._active = Active(log, start, self._identify(log), self._start_sampler(now))
        name = self._active.game.name if self._active.game else "unknown game"
        limit = f" - stops by itself after {self.config.record_seconds:.0f} s" if self.config.record_seconds else ""
        self._message(f"recording {name}{limit}", "start")

    def _start_sampler(self, now: float) -> Optional[telemetry.Sampler]:
        try:
            sampler = self._sampler_factory()
            sampler.start(now)
            return sampler
        except Exception:                        # telemetry is a bonus, never a reason to lose a recording
            return None

    def _device_state(self, active: "Active", now: float) -> dict:
        if active.sampler is None:
            return {}
        try:
            env = self._read_env(active.game.pid) if active.game and active.game.pid else None
            state = active.sampler.finish(now, env)
        except Exception:
            return {}
        try:
            software = self._read_software(active.game)
        except Exception:                        # the versions are a bonus on top of a bonus
            software = {}
        return {**state, "software": software} if software else state

    def _finish(self, segment: Segment, now: float, auto: bool = False) -> None:
        self._play("stop")                       # at the moment the recording ends, not after the cutting is done
        active = self._active
        self._active = None
        if active is None:
            self.session.reset()
            return
        newest = self._newest_log(self.log_dir)
        if newest is not None and newest != active.log:
            self.session.reset()
            self._message("the game was restarted during the recording - nothing saved", "error")
            return
        self._wait_flushed(active.log, segment.end, active.log_start)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        cut_file = self.work_dir / "cut.csv"
        try:
            cut = self._cut(active.log, segment.start, segment.end, cut_file, log_start=active.log_start)
        except ValueError as exc:
            self.session.reset()
            self._message(f"could not cut the recording: {exc}", "error")
            return
        auto = self.config.auto_upload
        upload_now = auto and self.config.cancel_window <= 0
        meta = {
            "created": segment.end, "seconds": round(cut.duration_seconds, 1), "frames": cut.frames,
            "app_id": active.game.app_id if active.game else None,
            "game_name": active.game.name if active.game else None,
            "status": "pending" if auto else "local",
            "device_state": self._device_state(active, now),
        }
        item = self.queue.add(cut_file, meta)
        game = meta["game_name"] or "unknown game"
        if upload_now:
            self._message(f"saved {game} ({cut.duration_seconds:.0f} s) - uploading", "")
            self.upload_item(item, now)
        elif auto:
            self._pending_item = item
            self._message(f"saved {game} ({cut.duration_seconds:.0f} s) - uploading in "
                          f"{self.config.cancel_window:.0f} s, same chord cancels", "")
        else:
            self._message(f"saved {game} ({cut.duration_seconds:.0f} s) on the Deck", "")

    # ----- time-driven -----------------------------------------------------------

    def _tick(self, now: float) -> None:
        event = self.session.tick(now)
        if event is not None and event.kind == "stopped":
            self._finish(event.segment, now, auto=True)                  # the recording time is up
        elif event is not None and event.kind == "upload_due" and self._pending_item is not None:
            item, self._pending_item = self._pending_item, None
            self.upload_item(item, now)
        if self.config.auto_upload and self.session.phase.value == "idle" and now - self._last_retry >= 30:
            self._last_retry = now
            for item in self.queue.due(now):
                self.upload_item(item, now)
        if now - self._last_housekeeping >= 3600:
            self._last_housekeeping = now
            self.queue.prune()
            deck_queue.prune_logs(self.log_dir, active=self._active.log if self._active else None)
        if self._active and self._active.sampler and self.session.phase.value == "recording":
            try:
                self._active.sampler.sample(now)             # power source, TDP, brightness ... while it runs
            except Exception:
                pass
        self._write_status(now)

    def upload_item(self, item: deck_queue.Item, now: Optional[float] = None) -> bool:
        """Try to upload one queued recording. Returns True when it is online."""
        now = time.time() if now is None else now
        app_id, name = item.meta.get("app_id"), item.meta.get("game_name")
        if not app_id:
            self.queue.failed_attempt(item, "the game could not be identified", retry=False, now=now)
            self._message("not uploaded: the game could not be identified (recording kept)", "error")
            return False
        prepared, reason = self._prepare(item.segment, {"app_id": app_id, "name": name}, self.deck,
                                         device_state=item.meta.get("device_state"))
        if prepared is None:
            self.queue.failed_attempt(item, reason, retry=False, now=now)
            self._message(f"not uploaded: {reason}", "error")
            return False
        ok, info, _ = self._send(prepared.kwargs)
        if ok:
            self.queue.update(item, status="uploaded", url=info, error="", uploaded=now,
                              fps_avg=round(prepared.summary.get("fps_avg", 0), 1))
            self._message(f"uploaded {name}: {prepared.summary.get('fps_avg', 0):.0f} FPS", "done")
            return True
        retry = upload.is_retryable(info)
        self.queue.failed_attempt(item, info, retry=retry, now=now)
        self._message(f"upload failed ({'will retry' if retry else 'giving up'}): {info}", "error")
        return False

    # ----- feedback -----------------------------------------------------------------

    def _play(self, sound: str) -> None:
        if sound and self.config.sound:
            try:
                self.play(sound)
            except Exception:
                pass

    def _message(self, text: str, sound: str) -> None:
        self.last_message = text
        self.say(text)
        self._play(sound)

    def _write_status(self, now: float) -> None:
        if not self.status_file:
            return
        data = {
            "time": now, "phase": self.session.phase.value, "message": self.last_message,
            "chord": self.config.chord, "deck": self.deck.device_class,
            "recording_for": round(now - self.session._start, 1) if self.session.phase.value == "recording" else 0,
        }
        try:
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.status_file.with_name(self.status_file.name + ".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self.status_file)
        except OSError:
            pass


def run_forever(service: DeckService, reader, stop: Optional[Callable[[], bool]] = None,
                clock: Callable[[], float] = time.time) -> None:
    """The service loop: read the pad, feed the chord, let time pass."""
    stop = stop or (lambda: False)
    last_scan = 0.0
    while not stop():
        now = clock()
        if now - last_scan >= 2.0:          # Steam re-creates its virtual pad when a game starts: pick the new one up quickly
            last_scan = now
            reader.rescan()
        for code, value in reader.read(0.25):
            service.on_key(code, value, clock())
        service.tick(clock())
        if not reader.active:
            time.sleep(0.5)
