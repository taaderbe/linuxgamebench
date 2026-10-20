"""Chord-driven recording session: start, stop, minimum length, cancel window, upload."""

from linux_game_benchmark.deck.session import Phase, RecordingSession


def test_start_stop_upload_after_the_cancel_window():
    s = RecordingSession(min_seconds=30, cancel_window=10, auto_upload=True)
    assert s.trigger(100.0).kind == "started" and s.phase is Phase.RECORDING
    stopped = s.trigger(160.0)
    assert stopped.kind == "stopped" and stopped.segment.start == 100.0 and stopped.segment.seconds == 60.0
    assert s.phase is Phase.PENDING
    assert s.tick(165.0) is None
    due = s.tick(170.0)
    assert due.kind == "upload_due" and due.segment.end == 160.0
    assert s.phase is Phase.IDLE and s.tick(200.0) is None


def test_a_too_short_press_keeps_recording():
    s = RecordingSession(min_seconds=30)
    s.trigger(0.0)
    event = s.trigger(5.0)
    assert event.kind == "too_short" and s.phase is Phase.RECORDING
    assert s.trigger(45.0).kind == "stopped"              # measured from the original start


def test_the_chord_inside_the_window_cancels_the_upload():
    s = RecordingSession(min_seconds=1, cancel_window=10)
    s.trigger(0.0)
    s.trigger(40.0)
    cancelled = s.trigger(43.0)
    assert cancelled.kind == "cancelled" and cancelled.segment.seconds == 40.0
    assert s.phase is Phase.IDLE and s.tick(100.0) is None
    assert s.trigger(101.0).kind == "started"             # a new recording works again


def test_without_auto_upload_there_is_no_pending_phase():
    s = RecordingSession(min_seconds=1, auto_upload=False)
    s.trigger(0.0)
    assert s.trigger(20.0).kind == "stopped"
    assert s.phase is Phase.IDLE and s.tick(1000.0) is None
