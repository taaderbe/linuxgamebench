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
