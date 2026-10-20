"""Cutting one recording out of a MangoHud log that runs for the whole session."""

from datetime import datetime

import pytest

from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
from linux_game_benchmark.deck.segments import cut_log, last_elapsed_ns, log_start_from_name

HEADER = ("os,cpu,gpu,ram,kernel,driver,cpuscheduler\n"
          "SteamOS,AMD Custom APU 0405,AMD Custom GPU 0405,15000000,6.5.0,Mesa 25.1,none\n"
          "fps,frametime,cpu_load,gpu_load,elapsed\n")


def make_log(tmp_path, seconds=120, fps=60, name="game.exe_2026-10-20_18-00-00.csv"):
    """A log with `fps` rows per second, elapsed in ns, started 2026-10-20 18:00:00 local time."""
    rows = []
    step = 1_000_000_000 // fps
    for i in range(seconds * fps):
        rows.append(f"{fps},{1000 / fps:.3f},40.0,90.0,{i * step}\n")
    path = tmp_path / name
    path.write_text(HEADER + "".join(rows))
    return path


T0 = datetime(2026, 10, 20, 18, 0, 0).timestamp()


def test_log_start_comes_from_the_file_name(tmp_path):
    assert log_start_from_name("Elden Ring.exe_2026-10-20_18-00-00.csv") == T0
    assert log_start_from_name("x_2026-10-20_18-00-00_summary.csv") is None     # summaries are not logs
    assert log_start_from_name("nostamp.csv") is None


def test_segment_has_the_rows_between_the_marks_and_is_rebased(tmp_path):
    src = make_log(tmp_path)
    cut = cut_log(src, T0 + 20, T0 + 80, tmp_path / "seg.csv")
    assert cut.duration_seconds == pytest.approx(60, abs=0.1)
    assert 3590 <= cut.frames <= 3610
    lines = (tmp_path / "seg.csv").read_text().splitlines()
    assert lines[:3] == HEADER.splitlines()
    assert lines[3].endswith(",0")                                     # elapsed starts at 0
    assert int(lines[-1].rsplit(",", 1)[1]) == pytest.approx(60e9, abs=2e7)


def test_the_cut_file_is_read_by_the_normal_analyzer(tmp_path):
    src = make_log(tmp_path)
    cut_log(src, T0 + 10, T0 + 70, tmp_path / "seg.csv")
    analyzer = FrametimeAnalyzer(tmp_path / "seg.csv")
    metrics = analyzer.analyze()
    assert metrics["fps"]["average"] == pytest.approx(60, abs=1)
    assert metrics["fps"]["duration_seconds"] == pytest.approx(60, abs=1)
    assert len(analyzer.frametimes) >= 3590


def test_marks_outside_the_log_or_reversed_are_errors(tmp_path):
    src = make_log(tmp_path, seconds=30)
    with pytest.raises(ValueError, match="no frames"):
        cut_log(src, T0 + 500, T0 + 560, tmp_path / "seg.csv")
    with pytest.raises(ValueError, match="after the start"):
        cut_log(src, T0 + 20, T0 + 10, tmp_path / "seg.csv")


def test_explicit_log_start_replaces_the_file_name(tmp_path):
    src = make_log(tmp_path, name="renamed.csv")
    with pytest.raises(ValueError, match="cannot tell"):
        cut_log(src, T0 + 1, T0 + 5, tmp_path / "a.csv")
    assert cut_log(src, T0 + 1, T0 + 5, tmp_path / "a.csv", log_start=T0).frames > 200


def test_a_log_without_elapsed_column_is_refused(tmp_path):
    path = tmp_path / "g_2026-10-20_18-00-00.csv"
    path.write_text("a,b\n1,2\nfps,frametime\n60,16.6\n")
    with pytest.raises(ValueError, match="elapsed"):
        cut_log(path, T0, T0 + 5, tmp_path / "s.csv")


def test_last_elapsed_reads_only_complete_rows(tmp_path):
    src = make_log(tmp_path, seconds=10)
    assert last_elapsed_ns(src) == pytest.approx(10e9, abs=2e7)
    with open(src, "a") as fh:
        fh.write("60,16.6,40.0")                 # half-written row: no elapsed yet
    assert last_elapsed_ns(src) == pytest.approx(10e9, abs=2e7)
    assert last_elapsed_ns(tmp_path / "missing.csv") is None
