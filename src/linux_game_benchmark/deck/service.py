"""The Deck recorder: the controller chord starts a recording, the performance log of that minute is cut and uploaded.

Game Mode: Steam's overlay program (mangoapp) sees every game - OpenGL, Vulkan, Proton - and writes a log only on command
(`mangohudctl set log_session`): the chord starts one log file, the end of the recording closes it. Nothing is logged in
between. Desktop Mode has no overlay program: there MangoHud's Vulkan layer inside the game logs all the time and the
recording is cut out of that log.

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
from linux_game_benchmark.deck import gamescope, segments, telemetry, upload
from linux_game_benchmark.deck import mangoapp as deck_mangoapp
from linux_game_benchmark.deck.chord import ChordTracker, parse_chord
from linux_game_benchmark.deck.detect import DeckInfo
from linux_game_benchmark.deck.session import Event, RecordingSession, Segment


def _default_software(game: Optional[deck_game.GameInfo]) -> dict:
    tools = deck_game.launch_tools(game.app_id) if game else None
    return telemetry.read_software(tools=tools)


def _default_display(game: Optional[deck_game.GameInfo]) -> dict:
    return gamescope.probe(game.pid, game.app_id) if game else {}


DISPLAY_PROBE_INTERVAL = 20.0            # seconds between looks at the game's window while a recording runs
FOCUS_POLL_INTERVAL = 2.0                # seconds between looks at what is in front (overlay recordings only)
FOCUS_LOSS_LIMIT = 5.0                   # the overlay program logs what is in front: more than this away from the game spoils the minute
LOG_WAIT_SECONDS = 3.0                   # how long the overlay program may take to open the log file it was told to start
STOP_RETRY_SECONDS = 5.0                 # a log that could not be ended is ended again this often


@dataclass
class Active:
    log: Path
    log_start: float
    game: Optional[deck_game.GameInfo]
    sampler: Optional[telemetry.Sampler] = None
    looks: Optional[list] = None             # what Gamescope said about the game's window, one entry per look
    last_look: float = 0.0
    on_demand: bool = False                  # a log the overlay program wrote for this recording only (Game Mode)
    last_focus: float = 0.0                  # overlay recordings: when the front app was last looked at
    away: float = 0.0                        # ... how long something else than the game was in front so far
    away_since: Optional[float] = None


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
        read_display: Optional[Callable[[Optional[deck_game.GameInfo]], dict]] = None,
        mangoapp_log_dir: Optional[Path] = None,
        running_games: Callable[[], set] = deck_game.running_steam_games,
        overlay_running: Callable[[], bool] = deck_mangoapp.running,
        overlay_log: Callable[[bool], bool] = deck_mangoapp.set_logging,
        focused_app: Callable[[], Optional[int]] = gamescope.focused_app,
        describe: Callable[[int], deck_game.GameInfo] = deck_game.describe,
        wait_closed: Callable[..., bool] = segments.wait_until_closed,
        overlay_wait: float = LOG_WAIT_SECONDS,
    ):
        self.config = config
        self.deck = deck
        self.queue = queue
        self.log_dir = log_dir
        self.mangoapp_log_dir = mangoapp_log_dir
        self._running_games, self._overlay_running, self._overlay_log = running_games, overlay_running, overlay_log
        self._focused_app, self._describe, self._wait_closed, self._overlay_wait = focused_app, describe, wait_closed, overlay_wait
        self._overlay_on = False                 # the overlay program is logging because this service told it to
        self._overlay_stop_try = 0.0
        self.work_dir = work_dir
        self.play, self.say = play, say
        self._newest_log, self._identify, self._cut = newest_log, identify, cut
        self._wait_flushed, self._prepare, self._send = wait_flushed, prepare, send
        self.status_file = status_file
        self._sampler_factory, self._read_env = sampler_factory, read_env
        self._read_software = read_software or _default_software
        self._read_display = read_display or _default_display
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

    def _games_now(self) -> set:
        try:
            return set(self._running_games())
        except Exception:
            return set()

    def _overlay_mode(self) -> bool:
        """Game Mode: Steam's overlay program runs and sees every game."""
        try:
            return self.mangoapp_log_dir is not None and bool(self._overlay_running())
        except Exception:
            return False

    def _begin(self, now: float) -> None:
        if self._overlay_mode():
            self._begin_overlay(now)
            return
        # Desktop Mode: the MangoHud layer inside a Vulkan game logs all the time, the recording is cut out of that log
        log = self._newest_log(self.log_dir)
        start = segments.log_start_from_name(log) if log else None
        if log is None or start is None:
            self.session.reset()
            if self._games_now():
                # a game runs, but nothing writes performance data for it: say why, a beep alone leaves the player guessing
                self._message("no performance data for this game - OpenGL games can only be recorded in Game Mode "
                              "(after a new install, restart Steam first)", "error")
            else:
                self._message("no running game found - start a game first", "error")
            return
        self._active = Active(log, start, self._identify(log), self._start_sampler(now), looks=[])
        self._announce(self._active, now)

    def _begin_overlay(self, now: float) -> None:
        """Game Mode: tell Steam's overlay program to start a log of its own for this recording."""
        games = self._games_now()
        front = self._front_app()
        if len(games) > 1 and front in games:
            games = {front}                                  # two games run: the one in front is the one being played
        if not games:
            self._refuse("no running game found - start a game first")
            return
        if len(games) > 1:
            self._refuse("could not tell which game is running - close the other ones")
            return
        app_id = next(iter(games))
        if front is not None and front != app_id:
            # the overlay program logs what is in front: with Steam's menu or a notification there it would log that
            self._refuse("the game is not in front (Steam's menu is open?) - go back into the game and press again")
            return
        game = self._describe(app_id)
        before = deck_game.log_names(self.mangoapp_log_dir)
        if not self._start_overlay_log():
            self._refuse("could not start the log (mangohudctl did not answer) - run 'lgb deck setup' once")
            return
        log = self._wait_for_new_log(before)
        if log is None:
            self._stop_overlay_log()
            self._refuse("Steam's overlay program did not start a log - run 'lgb deck setup' once and try again")
            return
        self._active = Active(log, now, game, self._start_sampler(now), looks=[], on_demand=True, last_focus=now)
        self._announce(self._active, now)

    def _refuse(self, text: str) -> None:
        self.session.reset()
        self._message(text, "error")

    def _announce(self, active: "Active", now: float) -> None:
        self._look(active, now)
        name = active.game.name if active.game else "unknown game"
        limit = f" - stops by itself after {self.config.record_seconds:.0f} s" if self.config.record_seconds else ""
        self._message(f"recording {name}{limit}", "start")

    def _front_app(self) -> Optional[int]:
        try:
            return self._focused_app()
        except Exception:
            return None

    # ----- the overlay program's log, started and ended on command -----------------------------------------------------

    def _start_overlay_log(self) -> bool:
        try:
            ok = bool(self._overlay_log(True))
        except Exception:
            ok = False
        if ok:
            self._overlay_on = True
        return ok

    def _stop_overlay_log(self) -> bool:
        """End the log the service started. A log that cannot be ended stays marked, so the loop tries again."""
        if not self._overlay_on:
            return True
        try:
            ok = bool(self._overlay_log(False))
        except Exception:
            ok = False
        if ok:
            self._overlay_on = False
        return ok

    def _wait_for_new_log(self, before: set) -> Optional[Path]:
        deadline = time.monotonic() + self._overlay_wait
        while True:
            found = deck_game.new_log(self.mangoapp_log_dir, before)
            if found is not None or time.monotonic() >= deadline:
                return found
            time.sleep(0.1)

    def _watch_front(self, active: "Active", now: float) -> None:
        """Count the seconds something else than the game was in front (the overlay log would hold those frames)."""
        active.last_focus = now
        front = self._front_app()
        away = front is not None and active.game is not None and front != active.game.app_id
        if away and active.away_since is None:
            active.away_since = now
        elif not away and active.away_since is not None:
            active.away += now - active.away_since
            active.away_since = None

    def _overlay_problem(self, active: "Active", now: float) -> Optional[str]:
        """Why the minute from the overlay program cannot be used, or None."""
        if active.game is not None and active.game.app_id not in self._games_now():
            # the overlay log goes on after the game ends (Steam's menu): those frames are not the game
            return "the game was closed during the recording - nothing saved"
        self._watch_front(active, now)
        away = active.away + (now - active.away_since if active.away_since is not None else 0.0)
        if away > FOCUS_LOSS_LIMIT:
            return f"the game was not in front for {away:.0f} s during the recording (Steam's menu?) - nothing saved"
        return None

    def recover(self) -> None:
        """At service start: a log a previous run left open (crash, kill) would run - and show its red dot - for ever."""
        if self._overlay_mode():
            try:
                self._overlay_log(False)
            except Exception:
                pass

    def close(self) -> None:
        """At service stop: never leave a log running."""
        self._stop_overlay_log()

    def _look(self, active: "Active", now: float) -> None:
        """Ask Gamescope what the game renders at and which limits Steam applied (a bonus: never a reason to lose a recording)."""
        active.last_look = now
        try:
            seen = self._read_display(active.game)
        except Exception:
            return
        if seen and active.looks is not None:
            active.looks.append(seen)

    def _start_sampler(self, now: float) -> Optional[telemetry.Sampler]:
        try:
            sampler = self._sampler_factory()
            sampler.start(now)
            return sampler
        except Exception:                        # telemetry is a bonus, never a reason to lose a recording
            return None

    def _device_state(self, active: "Active", now: float) -> dict:
        state: dict = {}
        if active.sampler is not None:
            try:
                env = self._read_env(active.game.pid) if active.game and active.game.pid else None
                state = active.sampler.finish(now, env)
            except Exception:
                state = {}
        self._look(active, now)
        seen = gamescope.condense(active.looks or [])
        if seen:
            state = {**state, "display": {**state.get("display", {}), **seen}}
        if not state:
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
            self._stop_overlay_log()
            return
        if active.on_demand:
            self._stop_overlay_log()             # ends the log file: from here on nothing more is written to it
            problem = self._overlay_problem(active, now)
            if problem:
                self.session.reset()
                self._message(problem, "error")
                return
            self._wait_closed(active.log)
        else:
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
            deck_queue.prune_logs(self.log_dir, active=self._active.log if self._active and not self._active.on_demand else None)
            if self.mangoapp_log_dir is not None:
                deck_queue.prune_logs(self.mangoapp_log_dir, active=self._active.log if self._active and self._active.on_demand else None)
        if self._active and self._active.sampler and self.session.phase.value == "recording":
            try:
                self._active.sampler.sample(now)             # power source, TDP, brightness ... while it runs
            except Exception:
                pass
        if self._active and self.session.phase.value == "recording" and now - self._active.last_look >= DISPLAY_PROBE_INTERVAL:
            self._look(self._active, now)
        if self._active and self._active.on_demand and self.session.phase.value == "recording" \
                and now - self._active.last_focus >= FOCUS_POLL_INTERVAL:
            self._watch_front(self._active, now)
        if self._overlay_on and (self._active is None or self.session.phase.value != "recording") \
                and now - self._overlay_stop_try >= STOP_RETRY_SECONDS:
            self._overlay_stop_try = now                         # nothing is recording any more, yet the log runs: end it
            self._stop_overlay_log()
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
