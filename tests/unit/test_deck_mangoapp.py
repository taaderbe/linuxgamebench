"""Steam's overlay program in Game Mode: is it running, and does `mangohudctl set log_session` get the right words."""

import subprocess
from pathlib import Path

from linux_game_benchmark.deck import mangoapp


def fake_proc(tmp_path: Path, **comms: str) -> Path:
    for pid, comm in comms.items():
        entry = tmp_path / pid.lstrip("p")
        entry.mkdir(parents=True)
        (entry / "comm").write_text(comm + "\n")
    (tmp_path / "self").mkdir()                         # not a process number
    return tmp_path


def test_the_overlay_program_is_found_by_its_process_name(tmp_path):
    assert mangoapp.running(fake_proc(tmp_path, p100="bash", p200="mangoapp", p300="steam"))


def test_without_it_the_answer_is_no_even_with_similar_names(tmp_path):
    assert not mangoapp.running(fake_proc(tmp_path, p100="mangohud", p200="mangoapp-x", p300="steam"))
    assert not mangoapp.running(tmp_path / "nowhere")


class Done:
    def __init__(self, returncode=0):
        self.returncode = returncode


def test_the_words_for_start_and_end():
    calls = []
    run = lambda args, **kw: calls.append((args, kw)) or Done()
    assert mangoapp.set_logging(True, run=run, which=lambda name: "/usr/bin/" + name)
    assert mangoapp.set_logging(False, run=run, which=lambda name: "/usr/bin/" + name)
    assert [c[0] for c in calls] == [["/usr/bin/mangohudctl", "set", "log_session", "true"],
                                     ["/usr/bin/mangohudctl", "set", "log_session", "false"]]


def test_the_appimages_library_path_does_not_reach_the_host_tool(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_x/usr/lib")
    seen = {}
    mangoapp.set_logging(True, run=lambda args, **kw: seen.update(kw) or Done(), which=lambda name: "/usr/bin/" + name)
    assert "LD_LIBRARY_PATH" not in seen["env"]


def test_a_missing_tool_a_refusal_and_a_crash_are_all_just_no():
    assert mangoapp.set_logging(True, run=lambda *a, **k: Done(), which=lambda name: None) is False
    assert mangoapp.set_logging(True, run=lambda *a, **k: Done(1), which=lambda name: "/x") is False

    def broken(*a, **k):
        raise subprocess.TimeoutExpired("mangohudctl", 5)
    assert mangoapp.set_logging(True, run=broken, which=lambda name: "/x") is False
    def missing(*a, **k):
        raise FileNotFoundError("mangohudctl")
    assert mangoapp.set_logging(False, run=missing, which=lambda name: "/x") is False


# ----- the log file the overlay program has open -------------------------------------------------------------------------

def fake_proc_with_fds(tmp_path, *processes):
    """A /proc with (comm, [file the process has open, ...]) per process."""
    import os
    for number, (comm, files) in enumerate(processes, start=200):
        entry = tmp_path / str(number)
        (entry / "fd").mkdir(parents=True)
        (entry / "comm").write_text(comm + "\n")
        for fd, target in enumerate(files, start=3):
            os.symlink(target, entry / "fd" / str(fd))
    return tmp_path


def test_the_log_is_found_through_the_files_the_overlay_program_has_open(tmp_path):
    proc = fake_proc_with_fds(tmp_path, ("mangoapp", ["/dev/null", "/home/deck/mangoapp_2026-10-21_16-39-49.csv"]))
    assert mangoapp.open_log(proc=proc) == Path("/home/deck/mangoapp_2026-10-21_16-39-49.csv")


def test_it_does_not_matter_which_folder_the_overlay_program_writes_to(tmp_path):
    proc = fake_proc_with_fds(tmp_path, ("mangoapp", ["/somewhere/else/entirely/mangoapp_2026-10-21_16-39-49.csv"]))
    assert mangoapp.open_log(proc=proc).parent == Path("/somewhere/else/entirely")


def test_a_summary_and_an_old_log_are_not_the_new_one(tmp_path):
    proc = fake_proc_with_fds(tmp_path, ("mangoapp", ["/h/mangoapp_2026-10-21_16-39-49_summary.csv", "/h/mangoapp_2026-10-21_16-00-00.csv"]))
    assert mangoapp.open_log(exclude={"mangoapp_2026-10-21_16-00-00.csv"}, proc=proc) is None
    assert mangoapp.open_log(proc=proc) == Path("/h/mangoapp_2026-10-21_16-00-00.csv")


def test_only_the_overlay_program_counts(tmp_path):
    proc = fake_proc_with_fds(tmp_path, ("firefox", ["/home/deck/Downloads/data.csv"]), ("bash", ["/home/deck/notes.csv"]))
    assert mangoapp.open_log(proc=proc) is None


def test_no_proc_and_no_overlay_program_are_just_none(tmp_path):
    assert mangoapp.open_log(proc=tmp_path / "does-not-exist") is None
    assert mangoapp.open_log(proc=tmp_path) is None
