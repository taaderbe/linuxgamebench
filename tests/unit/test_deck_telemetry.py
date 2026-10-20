"""What the Deck reports about itself: power source, battery, TDP, display, versions - read from a fake /sys tree."""

import json
from pathlib import Path

import pytest

from linux_game_benchmark.deck import telemetry


def put(root: Path, rel: str, text) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text) + "\n")


def build_deck(root: Path, *, ac=False, status="Discharging", pct=80, energy_wh=31.0, power_w=12.5, tdp_w=15, brightness=60):
    """A Steam Deck LCD as sysfs shows it (values in the kernel's units)."""
    put(root, "sys/class/power_supply/ACAD/type", "Mains")
    put(root, "sys/class/power_supply/ACAD/online", int(ac))
    put(root, "sys/class/power_supply/BAT1/type", "Battery")
    put(root, "sys/class/power_supply/BAT1/status", status)
    put(root, "sys/class/power_supply/BAT1/capacity", pct)
    put(root, "sys/class/power_supply/BAT1/energy_now", int(energy_wh * 1e6))
    put(root, "sys/class/power_supply/BAT1/energy_full", int(38.5e6))
    put(root, "sys/class/power_supply/BAT1/energy_full_design", int(40.04e6))
    put(root, "sys/class/power_supply/BAT1/power_now", int(power_w * 1e6))
    put(root, "sys/class/power_supply/BAT1/cycle_count", 142)
    put(root, "sys/class/power_supply/BAT1/temp", 312)
    put(root, "sys/class/power_supply/BAT1/serial_number", "SECRET-SERIAL")
    put(root, "sys/class/drm/card0/device/vendor", "0x1002")
    put(root, "sys/class/drm/card0/device/power_dpm_force_performance_level", "auto")
    put(root, "sys/class/drm/card0/device/mem_info_vram_total", 1024 * 1024 * 1024)
    put(root, "sys/class/drm/card0/device/mem_info_gtt_total", 7168 * 1024 * 1024)
    put(root, "sys/class/drm/card0/device/pp_od_clk_voltage",
        "OD_SCLK:\n0:        200Mhz\n1:       1600Mhz\nOD_RANGE:\nSCLK:     200Mhz       1600Mhz\n")
    put(root, "sys/class/drm/card0-eDP-1/status", "connected")
    put(root, "sys/class/drm/card0-eDP-1/modes", "1280x800\n800x1280")
    put(root, "sys/class/drm/card0-DP-1/status", "disconnected")
    put(root, "sys/class/hwmon/hwmon3/name", "amdgpu")
    put(root, "sys/class/hwmon/hwmon3/power1_cap", int(tdp_w * 1e6))
    put(root, "sys/class/hwmon/hwmon3/power1_cap_min", 3_000_000)
    put(root, "sys/class/hwmon/hwmon3/power1_cap_max", 15_000_000)
    put(root, "sys/class/backlight/amdgpu_bl1/brightness", int(255 * brightness / 100))
    put(root, "sys/class/backlight/amdgpu_bl1/max_brightness", 255)
    put(root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "powersave")
    put(root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq", 3500000)
    put(root, "sys/devices/system/cpu/smt/control", "on")
    put(root, "sys/class/dmi/id/board_name", "Jupiter")
    put(root, "sys/class/dmi/id/bios_version", "F7A0131")
    put(root, "sys/class/dmi/id/product_serial", "SECRET-SERIAL")
    put(root, "etc/os-release", 'NAME="SteamOS"\nVERSION_ID=3.7.8\nBUILD_ID=20250410.1\nVARIANT_ID=steamdeck\n')
    put(root, "proc/sys/kernel/osrelease", "6.5.0-valve22-1-neptune-65")
    put(root, "proc/meminfo", "MemTotal:       15700000 kB\nSwapTotal:       1048576 kB\n")
    put(root, "proc/sys/vm/swappiness", 100)
    put(root, "sys/block/zram0/disksize", 8 * 1024 * 1024 * 1024)
    return root


def test_snapshot_on_battery(tmp_path):
    snap = telemetry.snapshot(build_deck(tmp_path))
    power = snap["power"]
    assert power["ac_online"] is False and power["charge_status"] == "Discharging" and power["battery_pct"] == 80
    assert power["battery_wh"] == 31.0 and power["battery_full_wh"] == 38.5 and power["battery_design_wh"] == 40.04
    assert power["battery_health_pct"] == pytest.approx(96.2, abs=0.1) and power["battery_cycles"] == 142
    assert power["battery_power_w"] == 12.5 and power["battery_temp_c"] == 31.2
    limits = snap["limits"]
    assert limits["tdp_w"] == 15 and limits["tdp_min_w"] == 3 and limits["tdp_max_w"] == 15
    assert limits["gpu_perf_level"] == "auto" and limits["gpu_clock_range_mhz"] == [200, 1600]
    assert limits["gpu_clock_limit_mhz"] == [200, 1600]
    assert limits["cpu_governor"] == "powersave" and limits["cpu_max_mhz"] == 3500 and limits["smt"] is True
    assert snap["display"] == {"brightness_pct": 60, "internal_mode": "1280x800", "external_connected": False}


def test_plugged_in_with_charger_size(tmp_path):
    build_deck(tmp_path, ac=True, status="Charging")
    put(tmp_path, "sys/class/power_supply/ucsi-source-psy-USBC000:001/type", "USB")
    put(tmp_path, "sys/class/power_supply/ucsi-source-psy-USBC000:001/online", 1)
    put(tmp_path, "sys/class/power_supply/ucsi-source-psy-USBC000:001/voltage_max", 20_000_000)
    put(tmp_path, "sys/class/power_supply/ucsi-source-psy-USBC000:001/current_max", 2_250_000)
    power = telemetry.read_power(tmp_path)
    assert power["ac_online"] is True and power["charge_status"] == "Charging" and power["charger_w"] == 45


def test_a_controller_battery_is_not_the_decks_battery(tmp_path):
    build_deck(tmp_path)
    put(tmp_path, "sys/class/power_supply/hid-abc-battery/type", "Battery")
    put(tmp_path, "sys/class/power_supply/hid-abc-battery/scope", "Device")
    put(tmp_path, "sys/class/power_supply/hid-abc-battery/capacity", 5)
    assert telemetry.read_power(tmp_path)["battery_pct"] == 80


def test_charge_based_batteries_are_converted(tmp_path):
    put(tmp_path, "sys/class/power_supply/BAT0/type", "Battery")
    put(tmp_path, "sys/class/power_supply/BAT0/voltage_now", 7_600_000)
    put(tmp_path, "sys/class/power_supply/BAT0/charge_now", 4_000_000)
    put(tmp_path, "sys/class/power_supply/BAT0/charge_full", 5_000_000)
    put(tmp_path, "sys/class/power_supply/BAT0/charge_full_design", 5_200_000)
    put(tmp_path, "sys/class/power_supply/BAT0/current_now", 1_500_000)
    power = telemetry.read_power(tmp_path)
    assert power["battery_wh"] == 30.4 and power["battery_full_wh"] == 38.0 and power["battery_power_w"] == 11.4


def test_external_display_in_the_dock(tmp_path):
    build_deck(tmp_path)
    put(tmp_path, "sys/class/drm/card0-DP-1/status", "connected")
    put(tmp_path, "sys/class/drm/card0-DP-1/modes", "3840x2160\n1920x1080")
    display = telemetry.read_display(tmp_path)
    assert display["external_connected"] is True and display["external_mode"] == "3840x2160"


def test_device_block_and_no_identifiers(tmp_path):
    build_deck(tmp_path)
    device = telemetry.read_device(tmp_path)
    assert device == {"board": "Jupiter", "bios": "F7A0131", "steamos": "3.7.8", "steamos_build": "20250410.1", "steamos_variant": "steamdeck",
                      "kernel": "6.5.0-valve22-1-neptune-65", "ram_gb": 15.0, "swap_gb": 1.0, "vram_mb": 1024, "gtt_mb": 7168,
                      "zram_mb": 8192, "swappiness": 100}
    everything = json.dumps({"snap": telemetry.snapshot(tmp_path), "device": device})
    assert "SECRET-SERIAL" not in everything


def test_a_machine_without_any_of_it_gives_an_empty_answer(tmp_path):
    snap = telemetry.snapshot(tmp_path)
    assert snap["power"] == {"ac_online": False} and snap["limits"] == {} and snap["display"] == {"external_connected": False}
    assert telemetry.read_device(tmp_path) == {}


def test_launch_env_only_keeps_performance_options():
    env = {"PROTON_USE_WINED3D": "1", "DXVK_ASYNC": "1", "WINE_FULLSCREEN_FSR": "1", "RADV_PERFTEST": "gpl",
           "HOME": "/home/deck", "PATH": "/usr/bin", "STEAM_COMPAT_DATA_PATH": "/home/deck/x", "PROTON_LOG_DIR": "/tmp",
           "STEAM_RUNTIME_TOKEN": "abc", "PROTON_SOMETHING_LONG": "x" * 80, "DXVK_STATE_CACHE_PATH": "/home/deck/cache"}
    assert telemetry.read_launch_env(env) == {"DXVK_ASYNC": "1", "PROTON_USE_WINED3D": "1", "RADV_PERFTEST": "gpl", "WINE_FULLSCREEN_FSR": "1"}


def test_process_environment_is_read_from_proc(tmp_path):
    (tmp_path / "proc/4242").mkdir(parents=True)
    (tmp_path / "proc/4242/environ").write_bytes(b"PROTON_NO_ESYNC=1\0HOME=/home/deck\0")
    assert telemetry.read_process_env(4242, tmp_path) == {"PROTON_NO_ESYNC": "1", "HOME": "/home/deck"}
    assert telemetry.read_process_env(1, tmp_path) == {}


class Clock:
    """A reader that walks through prepared snapshots so a whole recording can be replayed."""
    def __init__(self, snaps):
        self.snaps = list(snaps)

    def __call__(self):
        return self.snaps.pop(0) if len(self.snaps) > 1 else self.snaps[0]


def snap(ac=False, pct=80, wh=31.0, draw=12.0, status="Discharging", tdp=15, bright=60):
    return {"power": {"ac_online": ac, "charge_status": status, "battery_pct": pct, "battery_wh": wh, "battery_power_w": draw,
                      "battery_full_wh": 38.5, "battery_design_wh": 40.04, "battery_health_pct": 96.2},
            "limits": {"tdp_w": tdp, "gpu_busy_pct": 99}, "display": {"brightness_pct": bright, "external_connected": False}}


def test_a_minute_on_battery_is_condensed(tmp_path):
    build_deck(tmp_path)
    reader = Clock([snap(), snap(draw=14, pct=79, wh=30.8), snap(draw=10, pct=79, wh=30.6), snap(pct=78, wh=30.4, draw=12)])
    sampler = telemetry.Sampler(tmp_path, reader=reader, interval=2.0)
    sampler.start(100.0)
    sampler.sample(101.0)                                   # too early: skipped
    sampler.sample(102.0)
    sampler.sample(104.0)
    state = sampler.finish(160.0, {"PROTON_USE_WINED3D": "1", "HOME": "/x"})
    power = state["power"]
    assert power["source"] == "battery" and power["battery_pct_start"] == 80 and power["battery_pct_end"] == 78
    assert power["battery_used_pct"] == 2 and power["battery_used_wh"] == 0.6
    assert power["battery_power_avg_w"] == 12.0 and power["battery_power_max_w"] == 14.0
    assert state["limits"] == {"tdp_w": 15} and state["display"]["brightness_pct"] == 60
    assert state["device"]["steamos"] == "3.7.8" and state["launch"] == {"env": {"PROTON_USE_WINED3D": "1"}}
    assert state["v"] == 1


def test_plugged_in_the_whole_time_has_no_battery_use(tmp_path):
    reader = Clock([snap(ac=True, status="Charging", pct=50, wh=19.0, draw=20.0), snap(ac=True, status="Charging", pct=51, wh=19.4, draw=20.0)])
    sampler = telemetry.Sampler(tmp_path, reader=reader)
    sampler.start(0.0)
    power = sampler.finish(60.0)["power"]
    assert power["source"] == "ac" and "battery_used_pct" not in power and "battery_power_avg_w" not in power


def test_unplugging_during_the_run_is_called_mixed(tmp_path):
    reader = Clock([snap(ac=True, status="Charging"), snap(ac=False)])
    sampler = telemetry.Sampler(tmp_path, reader=reader)
    sampler.start(0.0)
    assert sampler.finish(60.0)["power"]["source"] == "mixed"


def test_a_tdp_change_during_the_run_is_noted(tmp_path):
    reader = Clock([snap(tdp=15), snap(tdp=10), snap(tdp=10)])
    sampler = telemetry.Sampler(tmp_path, reader=reader, interval=1.0)
    sampler.start(0.0)
    sampler.sample(2.0)
    limits = sampler.finish(4.0)["limits"]
    assert limits["tdp_w"] == 10 and limits["tdp_w_min"] == 10 and limits["tdp_w_max"] == 15


def test_state_stays_small(tmp_path):
    build_deck(tmp_path)
    sampler = telemetry.Sampler(tmp_path, environ={f"PROTON_OPT{i}": "1" for i in range(100)})
    sampler.start(0.0)
    assert len(json.dumps(sampler.finish(60.0))) < 3000


# ----- the versions of the Deck: storage and screen ----------------------------------------------------------------------

def edid(maker="SDC", product=0x4166, name=b"ATNA40YK20", serial=b"SERIAL123"):
    """A 128-byte EDID with a monitor-name and a (private) serial descriptor."""
    letters = [ord(c) - 64 for c in maker]
    word = (letters[0] << 10) | (letters[1] << 5) | letters[2]
    data = bytearray(128)
    data[:8] = bytes([0, 255, 255, 255, 255, 255, 255, 0])
    data[8], data[9] = word >> 8, word & 255
    data[10], data[11] = product & 255, product >> 8
    for at, tag, text in ((54, 0xFF, serial), (72, 0xFC, name)):
        data[at:at + 5] = bytes([0, 0, 0, tag, 0])
        data[at + 5:at + 18] = (text + b"\n").ljust(13, b" ")[:13]
    return bytes(data)


def disk(root, name, gb, kind=None, model=""):
    sectors = int(gb * 1e9 / 512)
    put(root, f"sys/block/{name}/size", sectors)
    if kind:
        put(root, f"sys/block/{name}/device/type", kind)
    if model:
        put(root, f"sys/block/{name}/device/model", model)
    put(root, f"sys/block/{name}/device/serial", "SECRET-DISK-SERIAL")


@pytest.mark.parametrize("layout, expected", [
    # LCD 64 GB: the eMMC is mmcblk0, a microSD card comes up as mmcblk1
    ({"mmcblk0": (64, "MMC", "BJTD4R"), "mmcblk1": (512, "SD", "")}, {"storage_type": "emmc", "storage_gb": 64}),
    # LCD 256/512 GB and OLED 512 GB / 1 TB: NVMe, the microSD card is mmcblk0
    ({"nvme0n1": (256.06, None, "KINGSTON OM3PDP3256B"), "mmcblk0": (128, "SD", "")}, {"storage_type": "nvme", "storage_gb": 256}),
    ({"nvme0n1": (512.11, None, "Samsung PM991a"), }, {"storage_type": "nvme", "storage_gb": 512}),
    ({"nvme0n1": (1024.2, None, "WD PC SN740"), }, {"storage_type": "nvme", "storage_gb": 1024}),
])
def test_internal_storage_tells_the_versions_apart(tmp_path, layout, expected):
    for name, (gb, kind, model) in layout.items():
        disk(tmp_path, name, gb, kind, model)
    device = telemetry.read_device(tmp_path)
    assert {k: device[k] for k in expected} == expected
    assert "SECRET-DISK-SERIAL" not in str(device)


def test_a_microsd_card_alone_is_not_the_internal_disk(tmp_path):
    disk(tmp_path, "mmcblk0", 128, "SD")
    disk(tmp_path, "mmcblk0boot0", 4, "MMC")
    device = telemetry.read_device(tmp_path)
    assert "storage_type" not in device and "storage_gb" not in device


def test_storage_model_is_kept_short_and_plain(tmp_path):
    disk(tmp_path, "nvme0n1", 512, model="Weird/Model <script>" + "x" * 80)
    model = telemetry.read_device(tmp_path)["storage_model"]
    assert len(model) <= 40 and "<" not in model and ">" not in model


def test_panel_comes_from_the_screens_edid_without_the_serial(tmp_path):
    put(tmp_path, "sys/class/drm/card0-eDP-1/status", "connected")
    (tmp_path / "sys/class/drm/card0-eDP-1/edid").write_bytes(edid("SDC", name=b"ATNA40YK20"))
    device = telemetry.read_device(tmp_path)
    assert device["panel"] == "SDC ATNA40YK20" and "SERIAL123" not in str(device)


def test_panel_without_a_name_falls_back_to_the_product_code(tmp_path):
    (tmp_path / "sys/class/drm/card0-eDP-1").mkdir(parents=True)
    raw = bytearray(edid("BOE", product=0x0B4B))
    raw[72:90] = bytes(18)                                                   # no monitor-name descriptor
    (tmp_path / "sys/class/drm/card0-eDP-1/edid").write_bytes(bytes(raw))
    assert telemetry.read_device(tmp_path)["panel"] == "BOE 0B4B"


def test_external_monitors_and_broken_edids_are_ignored(tmp_path):
    (tmp_path / "sys/class/drm/card0-DP-1").mkdir(parents=True)
    (tmp_path / "sys/class/drm/card0-DP-1/edid").write_bytes(edid("DEL", name=b"U2720Q"))
    (tmp_path / "sys/class/drm/card0-eDP-1").mkdir(parents=True)
    (tmp_path / "sys/class/drm/card0-eDP-1/edid").write_bytes(b"\x00" * 128)
    assert "panel" not in telemetry.read_device(tmp_path)


def test_product_name_is_part_of_the_device(tmp_path):
    build_deck(tmp_path)
    put(tmp_path, "sys/class/dmi/id/product_name", "Galileo")
    assert telemetry.read_device(tmp_path)["product"] == "Galileo"


@pytest.mark.parametrize("reported, shown", [("800x1280", "1280x800"), ("1280x800", "1280x800"), ("1920x1080", "1920x1080")])
def test_the_built_in_screen_is_shown_in_landscape(tmp_path, reported, shown):
    put(tmp_path, "sys/class/drm/card0-eDP-1/status", "connected")
    put(tmp_path, "sys/class/drm/card0-eDP-1/modes", reported + "\n")
    assert telemetry.read_display(tmp_path)["internal_mode"] == shown
