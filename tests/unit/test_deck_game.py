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



# ----- shortcuts (games added to Steam that are no Steam app) ----------------------------------------------------------------

import struct
import zlib

import pytest


def vdf_map(entries: dict) -> bytes:
    out = b""
    for key, value in entries.items():
        if isinstance(value, dict):
            out += b"\x00" + key.encode() + b"\x00" + vdf_map(value)
        elif isinstance(value, int):
            out += b"\x02" + key.encode() + b"\x00" + struct.pack("<I", value)
        else:
            out += b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"
    return out + b"\x08"


def write_shortcuts(home: Path, account: str, entries: list, mtime: float = None) -> Path:
    path = home / ".local/share/Steam/userdata" / account / "config/shortcuts.vdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(vdf_map({"shortcuts": {str(i): e for i, e in enumerate(entries)}}))
    if mtime is not None:
        import os
        os.utime(path, (mtime, mtime))
    return path


RIDE = {"appid": 2933456376, "AppName": "Ride 2", "Exe": '"/usr/bin/flatpak" run net.rpcs3.RPCS3 --no-gui "/run/media/x/Ride/EBOOT.BIN"', "LaunchOptions": ""}
ZELDA = {"appid": 2502734983, "AppName": "The Legend of Zelda: Breath of the Wild", "Exe": '"/home/deck/Applications/eden/eden.sh"',
         "LaunchOptions": '-f -g "/run/media/x/Roms/Switch/Zelda BotW.nsp"'}


def test_the_binary_list_is_read():
    data = vdf_map({"shortcuts": {"0": {"appid": 7, "AppName": "X", "tags": {"0": "favorite"}}}})
    assert deck_game.read_binary_vdf(data) == {"shortcuts": {"0": {"appid": 7, "AppName": "X", "tags": {"0": "favorite"}}}}


@pytest.mark.parametrize("data", [b"", b"\x01key\x00no end", b"\x09odd\x00", b"\x02n\x00\x01"])
def test_a_broken_list_is_an_error_not_a_crash(data):
    with pytest.raises(ValueError):
        deck_game.read_binary_vdf(data)


def test_shortcuts_of_every_account_are_found(tmp_path):
    write_shortcuts(tmp_path, "111", [RIDE])
    write_shortcuts(tmp_path, "222", [ZELDA])
    found = deck_game.shortcuts(tmp_path)
    assert found[2933456376] == {"name": "Ride 2", "launcher": "RPCS3"}
    assert found[2502734983] == {"name": "The Legend of Zelda: Breath of the Wild", "launcher": "eden"}


def test_the_newest_list_wins_for_the_same_id(tmp_path):
    write_shortcuts(tmp_path, "111", [{**RIDE, "AppName": "Ride 2 old"}], mtime=1000)
    write_shortcuts(tmp_path, "222", [RIDE], mtime=2000)
    assert deck_game.shortcuts(tmp_path)[2933456376]["name"] == "Ride 2"


def test_a_list_without_ids_and_with_small_keys_still_works(tmp_path):
    write_shortcuts(tmp_path, "111", [{"appname": "Old Game", "exe": '"/opt/old/run.sh"'}])
    expected = zlib.crc32(b'"/opt/old/run.sh"Old Game') | 0x80000000
    assert deck_game.shortcuts(tmp_path) == {expected: {"name": "Old Game", "launcher": "run"}}


def test_a_broken_list_does_not_hide_the_others(tmp_path):
    write_shortcuts(tmp_path, "111", [RIDE])
    bad = tmp_path / ".local/share/Steam/userdata/222/config/shortcuts.vdf"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\x00shortcuts\x00\x00")
    assert 2933456376 in deck_game.shortcuts(tmp_path)


def test_only_shortcut_ids_are_looked_up(tmp_path):
    write_shortcuts(tmp_path, "111", [{**RIDE, "appid": 1245620}])             # a Steam app id is never a shortcut
    assert deck_game.shortcut(1245620, tmp_path) is None
    assert deck_game.is_shortcut(2933456376) and not deck_game.is_shortcut(1245620) and not deck_game.is_shortcut(None)


@pytest.mark.parametrize("entry, expected", [
    ({"Exe": '"/usr/bin/flatpak" run net.rpcs3.RPCS3 --no-gui "/x/EBOOT.BIN"'}, "RPCS3"),
    ({"Exe": '"/usr/bin/flatpak"', "LaunchOptions": '"run" "--branch=stable" "--command=prismlauncher" "org.prismlauncher.PrismLauncher" -l x'}, "PrismLauncher"),
    ({"Exe": '"/usr/bin/flatpak"', "FlatpakAppID": "org.libretro.RetroArch", "LaunchOptions": "run org.libretro.RetroArch"}, "RetroArch"),
    ({"Exe": '"/home/deck/Applications/eden/eden.sh"', "LaunchOptions": '-f -g "/x.nsp"'}, "eden"),
    ({"Exe": '"/home/deck/Documents/WS_latest.x86_64"'}, "WS_latest"),
    ({"Exe": '"/home/deck/Downloads/ChromieCraft/Wow.exe"'}, "Wow"),
    ({"Exe": '"/usr/bin/flatpak"', "LaunchOptions": 'run com.heroicgameslauncher.hgl --no-gui --no-sandbox "heroic://launch/gog/1423049311"'}, "Heroic (GOG)"),
    ({"Exe": '"/usr/bin/flatpak"', "LaunchOptions": 'run com.heroicgameslauncher.hgl --no-gui "heroic://launch/legendary/Fortnite"'}, "Heroic (Epic)"),
    ({"Exe": "heroic", "LaunchOptions": '"heroic://launch?appName=abc&runner=nile"'}, "Heroic (Amazon)"),
    ({"Exe": '"/usr/bin/flatpak" run com.heroicgameslauncher.hgl'}, "Heroic"),
    ({"Exe": '"/opt/odd name/with\'quote"'}, "withquote"),
    ({"Exe": ""}, None),
])
def test_the_launcher_is_a_short_name_never_a_path(entry, expected):
    assert deck_game.shortcut_launcher(entry) == expected


def test_identify_names_a_running_shortcut_from_the_list(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_shortcuts(home, "111", [RIDE])
    monkeypatch.setenv("HOME", str(home))
    proc = proc_with(tmp_path / "proc", [f"{STEAM}/ubuntu12_32/reaper", "SteamLaunch", "AppId=2933456376", "--", "/usr/bin/flatpak"])
    info = deck_game.identify(tmp_path / "none.csv", proc)
    assert (info.app_id, info.name, info.launcher, info.non_steam) == (2933456376, "Ride 2", "RPCS3", True)


def test_a_shortcut_missing_from_every_list_is_still_non_steam(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    proc = proc_with(tmp_path / "proc", [f"{STEAM}/ubuntu12_32/reaper", "SteamLaunch", "AppId=3000000000", "--", "/x"])
    info = deck_game.identify(tmp_path / "none.csv", proc)
    assert info.name == "Non-Steam game" and info.non_steam and info.launcher is None


@pytest.mark.parametrize("name, launcher, itself", [
    ("Eden", "eden", True), ("Heroic", "Heroic", True), ("Heroic Games Launcher", "Heroic", True), ("Google Chrome", "Chrome", True),
    ("RetroArch", "RetroArch", True), ("RPCS3", "RPCS3", True),
    ("Ride 2", "RPCS3", False), ("The Legend of Zelda: Breath of the Wild", "eden", False), ("Cyberpunk 2077", "Heroic (GOG)", False),
    ("D2R", "D2R", False), ("Wow.exe", "Wow", False), ("Minecraft", "PrismLauncher", False), ("Anything", None, False),
])
def test_a_shortcut_to_a_launcher_itself_is_told_apart_from_a_game(name, launcher, itself):
    assert deck_game.is_frontend_itself(name, launcher) is itself
