"""How Steam started the game, read from a fake /proc: the Proton build and runtime named on the reaper command line."""

from pathlib import Path

from linux_game_benchmark.deck import game as deck_game


def proc_with(tmp_path: Path, *cmdlines: list) -> Path:
    for i, args in enumerate(cmdlines, start=100):
        entry = tmp_path / str(i)
        entry.mkdir(parents=True)
        (entry / "cmdline").write_bytes(b"\x00".join(a.encode() for a in args) + b"\x00")
    return tmp_path


STEAM = "/home/deck/.local/share/Steam"
PROTON_LAUNCH = [f"{STEAM}/ubuntu12_32/reaper", "SteamLaunch", "AppId=920210", "--",
                 f"{STEAM}/steamapps/common/SteamLinuxRuntime_4/_v2-entry-point", "--verb=waitforexitandrun", "--",
                 f"{STEAM}/steamapps/common/Proton 11.0/proton", "waitforexitandrun", "/run/media/deck/x/game.exe"]
NATIVE_LAUNCH = [f"{STEAM}/ubuntu12_32/reaper", "SteamLaunch", "AppId=1942280", "--",
                 f"{STEAM}/steamapps/common/SteamLinuxRuntime_sniper/_v2-entry-point", "--verb=waitforexitandrun", "--",
                 "/home/deck/games/Brotato/Brotato.x86_64"]


def test_a_proton_launch_names_the_proton_and_runtime_folders(tmp_path):
    proc = proc_with(tmp_path, ["bash"], PROTON_LAUNCH)
    assert deck_game.launch_tools(920210, proc) == {
        "proton_dir": f"{STEAM}/steamapps/common/Proton 11.0",
        "runtime_dir": f"{STEAM}/steamapps/common/SteamLinuxRuntime_4"}


def test_a_native_game_has_a_runtime_but_no_proton(tmp_path):
    proc = proc_with(tmp_path, NATIVE_LAUNCH)
    assert deck_game.launch_tools(1942280, proc) == {"runtime_dir": f"{STEAM}/steamapps/common/SteamLinuxRuntime_sniper"}


def test_a_launch_without_any_tool_is_native_not_unknown(tmp_path):
    proc = proc_with(tmp_path, [f"{STEAM}/ubuntu12_32/reaper", "SteamLaunch", "AppId=7", "--", "/opt/game/run"])
    assert deck_game.launch_tools(7, proc) == {}


def test_a_game_that_was_not_launched_by_steam_is_unknown(tmp_path):
    proc = proc_with(tmp_path, PROTON_LAUNCH)
    assert deck_game.launch_tools(123, proc) is None
    assert deck_game.launch_tools(920210, tmp_path / "nowhere") is None


def test_another_games_launch_is_not_mixed_up(tmp_path):
    proc = proc_with(tmp_path, PROTON_LAUNCH, NATIVE_LAUNCH)
    assert "proton_dir" not in deck_game.launch_tools(1942280, proc)
    assert deck_game.launch_tools(920210, proc)["proton_dir"].endswith("Proton 11.0")


# ----- the game's own process and the log a command started ----------------------------------------------------------------

def process(tmp_path: Path, pid: int, app_id, rss_kb: int) -> None:
    entry = tmp_path / str(pid)
    entry.mkdir(parents=True)
    env = [f"SteamAppId={app_id}"] if app_id else ["HOME=/home/deck"]
    (entry / "environ").write_bytes(b"\x00".join(e.encode() for e in env + ["DISPLAY=:1"]) + b"\x00")
    (entry / "status").write_text(f"Name:\tx\nVmRSS:\t{rss_kb} kB\nThreads:\t4\n")


def test_the_game_is_the_process_of_its_app_that_uses_the_most_memory(tmp_path):
    process(tmp_path, 100, 1942280, 2_000)             # reaper
    process(tmp_path, 101, 1942280, 450_000)           # the game
    process(tmp_path, 102, 1942280, 30_000)            # a helper
    process(tmp_path, 200, 920210, 900_000)            # another app's much bigger process
    process(tmp_path, 300, None, 5_000_000)            # a process of the system
    assert deck_game.game_pid(1942280, tmp_path) == 101
    assert deck_game.game_pid(920210, tmp_path) == 200


def test_an_app_without_processes_has_no_pid(tmp_path):
    process(tmp_path, 100, 920210, 1_000)
    assert deck_game.game_pid(7, tmp_path) is None
    assert deck_game.game_pid(7, tmp_path / "nowhere") is None


def test_a_process_without_a_readable_size_still_counts_as_a_last_resort(tmp_path):
    process(tmp_path, 100, 55, 1_000)
    (tmp_path / "100" / "status").unlink()
    assert deck_game.game_pid(55, tmp_path) == 100


def test_the_log_a_command_started_is_the_one_that_was_not_there_before(tmp_path):
    import os
    old = tmp_path / "mangoapp_2026-10-21_11-00-00.csv"
    old.write_text("x")
    before = deck_game.log_names(tmp_path)
    assert deck_game.new_log(tmp_path, before) is None
    new = tmp_path / "mangoapp_2026-10-21_12-00-00.csv"
    new.write_text("x")
    summary = tmp_path / "mangoapp_2026-10-21_12-00-00_summary.csv"
    summary.write_text("x")
    os.utime(summary, (new.stat().st_mtime + 5, new.stat().st_mtime + 5))
    assert deck_game.new_log(tmp_path, before) == new, "a summary file is never the log"


def test_a_missing_folder_has_no_logs(tmp_path):
    assert deck_game.log_names(tmp_path / "nowhere") == set()
    assert deck_game.new_log(tmp_path / "nowhere", set()) is None
