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
