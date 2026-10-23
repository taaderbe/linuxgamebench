"""Everything the Deck can tell about itself while a game runs: power source, battery, TDP, display, clocks, versions.

MangoHud already logs the per-frame sensors (temperatures, fan, battery %, battery watts, clocks); what it cannot
say is *how the Deck was set up*: plugged in or on battery, which TDP limit Steam applied, how bright the screen was,
whether a dock with an external display was connected, which SteamOS/BIOS this is. That is read from sysfs/procfs
(no root needed), once when the recording starts, every few seconds while it runs and once more at the end.

Everything is best effort: a missing file is simply left out. Nothing that identifies the device (serial numbers,
MAC addresses, account names) is read. `root` lets the tests point the readers at a fake /sys tree.
"""

from __future__ import annotations

import os
import re
import struct
import threading
import time
from pathlib import Path
from typing import Callable, Optional

SAMPLE_INTERVAL = 2.0
SENSOR_INTERVAL = 1.0           # the GPU / temperature sensors are read more often: they move faster than the battery
MAX_SERIES_POINTS = 120         # a sensor series is condensed to at most this many points (a 10 minute recording stays small)
SCHEMA_VERSION = 1

# launch options that change performance and are safe to publish (never values of secrets / paths)
ENV_PREFIXES = ("PROTON_", "DXVK_", "VKD3D_", "RADV_", "MESA_", "WINE_FULLSCREEN_FSR", "ENABLE_GAMESCOPE_WSI",
                "SteamDeck", "STEAM_DECK", "MANGOHUD_", "GAMEMODE")
ENV_BLOCK = ("PROTON_LOG_DIR", "PROTON_CRASH_REPORT_DIR", "PROTON_COMPAT_DATA_PATH", "STEAM_COMPAT_DATA_PATH")


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(errors="replace").strip()
    except (OSError, ValueError):
        return None


def _number(path: Path) -> Optional[float]:
    text = _read(path)
    if text is None:
        return None
    try:
        return float(text.split()[0])
    except (ValueError, IndexError):
        return None


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    return None if value is None else round(value, digits)


def _drop_empty(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None and v != {} and v != ""}


# ----- power supplies ---------------------------------------------------------------------------------------------------

def _supplies(root: Path) -> list[tuple[str, Path, str]]:
    base = root / "sys/class/power_supply"
    out = []
    try:
        names = sorted(p.name for p in base.iterdir())
    except OSError:
        return out
    for name in names:
        kind = (_read(base / name / "type") or "").lower()
        out.append((name, base / name, kind))
    return out


def read_power(root: Path) -> dict:
    """Plugged in or not, charger size, battery level / energy / power draw / health."""
    battery: Optional[Path] = None
    mains_online = False
    charger_w: Optional[float] = None
    for name, path, kind in _supplies(root):
        if kind == "battery" and battery is None and (_read(path / "scope") or "").lower() != "device":
            battery = path
        elif kind in ("mains", "usb", "usb_c", "usb_pd", "usb_pd_drp"):
            if _number(path / "online"):
                mains_online = True
                volts, amps = _number(path / "voltage_max") or _number(path / "voltage_now"), _number(path / "current_max")
                if volts and amps and (charger_w is None or volts * amps / 1e12 > charger_w):
                    charger_w = volts * amps / 1e12          # µV * µA -> W
    out: dict = {"ac_online": mains_online}
    if charger_w:
        out["charger_w"] = _round(charger_w, 0)
    if battery is None:
        return out
    status = _read(battery / "status")
    capacity = _number(battery / "capacity")
    energy_now, energy_full, energy_design = (_number(battery / n) for n in ("energy_now", "energy_full", "energy_full_design"))
    if energy_now is None:                                     # some drivers report charge (µAh) instead of energy (µWh)
        volts = _number(battery / "voltage_now")
        charge = [_number(battery / n) for n in ("charge_now", "charge_full", "charge_full_design")]
        if volts and all(c is not None for c in charge):
            energy_now, energy_full, energy_design = (c * volts / 1e6 for c in charge)
    power = _number(battery / "power_now")
    if power is None:
        volts, amps = _number(battery / "voltage_now"), _number(battery / "current_now")
        power = volts * amps / 1e6 if volts and amps else None
    out.update({
        "charge_status": status,
        "battery_pct": capacity,
        "battery_wh": _round(energy_now / 1e6, 2) if energy_now else None,
        "battery_full_wh": _round(energy_full / 1e6, 2) if energy_full else None,
        "battery_design_wh": _round(energy_design / 1e6, 2) if energy_design else None,
        "battery_health_pct": _round(energy_full / energy_design * 100, 1) if energy_full and energy_design else None,
        "battery_cycles": _number(battery / "cycle_count"),
        "battery_temp_c": _round((_number(battery / "temp") or 0) / 10, 1) if _number(battery / "temp") else _battery_temp(root),
        "battery_power_w": _round(abs(power) / 1e6, 2) if power is not None else None,
    })
    return _drop_empty(out)


# ----- limits (TDP, GPU clock, CPU governor) --------------------------------------------------------------------------------

def _gpu_device(root: Path) -> Optional[Path]:
    base = root / "sys/class/drm"
    try:
        cards = sorted(p for p in base.iterdir() if re.fullmatch(r"card\d+", p.name))
    except OSError:
        return None
    for card in cards:
        if (_read(card / "device/vendor") or "").lower() == "0x1002":
            return card / "device"
    return None


def _hwmon(root: Path, name: str) -> Optional[Path]:
    base = root / "sys/class/hwmon"
    try:
        for entry in sorted(base.iterdir()):
            if _read(entry / "name") == name:
                return entry
    except OSError:
        pass
    return None


def _od_range(text: Optional[str], section: str) -> Optional[list[int]]:
    """OD_RANGE lines like 'SCLK:     200Mhz       1600Mhz' -> [200, 1600]."""
    if not text:
        return None
    match = re.search(rf"{section}:\s*(\d+)\s*Mhz\s+(\d+)\s*Mhz", text, re.I)
    return [int(match.group(1)), int(match.group(2))] if match else None


def read_limits(root: Path) -> dict:
    """The TDP Steam applied, GPU clock limits, CPU governor - what makes two runs of the same game different."""
    out: dict = {}
    gpu = _gpu_device(root)
    hw = _hwmon(root, "amdgpu")
    if hw is not None:
        cap, cap_min, cap_max = (_number(hw / n) for n in ("power1_cap", "power1_cap_min", "power1_cap_max"))
        out["tdp_w"] = _round(cap / 1e6, 1) if cap else None
        out["tdp_min_w"] = _round(cap_min / 1e6, 1) if cap_min else None
        out["tdp_max_w"] = _round(cap_max / 1e6, 1) if cap_max else None
        boost = _number(hw / "power2_cap")
        out["tdp_boost_w"] = _round(boost / 1e6, 1) if boost else None
    if gpu is not None:
        out["gpu_perf_level"] = _read(gpu / "power_dpm_force_performance_level")
        od = _read(gpu / "pp_od_clk_voltage")
        limits = _od_range(od, "SCLK")
        current = re.search(r"OD_SCLK:\s*0:\s*(\d+)\s*Mhz\s*1:\s*(\d+)\s*Mhz", od or "", re.I)
        if current:
            out["gpu_clock_limit_mhz"] = [int(current.group(1)), int(current.group(2))]
        if limits:
            out["gpu_clock_range_mhz"] = limits
        out["gpu_busy_pct"] = _number(gpu / "gpu_busy_percent")
    cpu0 = root / "sys/devices/system/cpu/cpu0/cpufreq"
    out["cpu_governor"] = _read(cpu0 / "scaling_governor")
    out["cpu_epp"] = _read(cpu0 / "energy_performance_preference")
    top = _number(cpu0 / "scaling_max_freq")
    out["cpu_max_mhz"] = round(top / 1000) if top else None
    smt = _read(root / "sys/devices/system/cpu/smt/control")
    out["smt"] = None if smt is None else smt == "on"
    return _drop_empty(out)


# ----- sensors MangoHud's log lacks in Game Mode -----------------------------------------------------------------------------

def _fan_rpm(root: Path) -> Optional[float]:
    base = root / "sys/class/hwmon"
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return None
    for entry in entries:
        rpm = _number(entry / "fan1_input")
        if rpm is not None:
            return rpm
    return None


def _hwmon_label(root: Path, label: str) -> Optional[Path]:
    """The input file next to a hwmon label, e.g. 'Battery Temp' -> .../temp1_input."""
    base = root / "sys/class/hwmon"
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            labels = sorted(entry.glob("*_label"))
        except OSError:
            continue
        for path in labels:
            if _read(path) == label:
                return path.with_name(path.name[:-len("_label")] + "_input")
    return None


def _battery_temp(root: Path) -> Optional[float]:
    path = _hwmon_label(root, "Battery Temp")                  # steamdeck_hwmon (the battery's own supply has no temp file)
    value = _number(path) if path else None
    return _round(value / 1000, 1) if value is not None and 0 < value < 100_000 else None


# The APU's own metrics table (amdgpu gpu_metrics, format 2 = APUs such as the Deck's): the SMU refreshes it by itself and
# averages over a few milliseconds - unlike gpu_busy_percent, a momentary 0 / 100 reading. Layout from the kernel's
# gpu_metrics_v2_x (the same for 2.0 to 2.4 up to the throttle status; indep_throttle_status from 2.2 on). 0xFFFF = no value.
_NA16 = 0xFFFF
POWER_THROTTLE_BITS = tuple(range(0, 8)) + tuple(range(16, 24))   # PPT / SPL / fast and slow PPT, current (TDC / EDC) limits
THERMAL_THROTTLE_BITS = tuple(range(32, 48)) + (56, 57)          # temperature limits, VR hot, PROCHOT


def parse_gpu_metrics(data: bytes) -> dict:
    """gpu_metrics v2.x -> {gpu_load_pct, gpu_clock_mhz, cpu_power_w, gpu_power_w, cpu_temp_c, cpu_clock_mhz, throttle}.
    {} for another format or a short table. throttle: 0 = free, 1 = at a power limit, 2 = thermal, 3 = both."""
    if len(data) < 120 or data[2] != 2:
        return {}
    ok = lambda v: v != _NA16
    out: dict = {}
    temps = [t for t in struct.unpack_from("<8H", data, 8) if ok(t)]
    gfx_activity = struct.unpack_from("<H", data, 28)[0]
    _socket, cpu_mw, _soc, gfx_mw = struct.unpack_from("<4H", data, 40)
    avg_gfxclk = struct.unpack_from("<H", data, 64)[0]
    core_clocks = [c for c in struct.unpack_from("<8H", data, 88) if ok(c) and c > 0]
    if ok(gfx_activity) and gfx_activity <= 100:
        out["gpu_load_pct"] = float(gfx_activity)
    if ok(avg_gfxclk) and avg_gfxclk > 0:
        out["gpu_clock_mhz"] = avg_gfxclk
    if ok(cpu_mw):
        out["cpu_power_w"] = _round(cpu_mw / 1000, 2)
    if ok(gfx_mw):
        out["gpu_power_w"] = _round(gfx_mw / 1000, 2)
    if temps:
        out["cpu_temp_c"] = _round(max(temps) / 100, 1)        # centi-°C, the hottest core
    if core_clocks:
        out["cpu_clock_mhz"] = round(sum(core_clocks) / len(core_clocks))
    if data[3] >= 2 and len(data) >= 128:
        flags = struct.unpack_from("<Q", data, 120)[0]
        power = any(flags >> b & 1 for b in POWER_THROTTLE_BITS)
        thermal = any(flags >> b & 1 for b in THERMAL_THROTTLE_BITS)
        out["throttle"] = int(power) + 2 * int(thermal)
    return out


def read_sensors(root: Path) -> dict:
    """One momentary reading of what Steam's overlay program does not log in Game Mode (it records frames, CPU and memory
    only): GPU load and clock, the APU's temperature and power, the fan; from the APU's metrics table also the power split
    into CPU and GPU, the CPU temperature and clock and whether the chip held itself back. Plain sysfs, no root needed."""
    out: dict = {}
    gpu = _gpu_device(root)
    metrics: dict = {}
    if gpu is not None:
        try:
            metrics = parse_gpu_metrics((gpu / "gpu_metrics").read_bytes())
        except (OSError, struct.error):
            metrics = {}
        out["gpu_load_pct"] = metrics.get("gpu_load_pct", _number(gpu / "gpu_busy_percent"))
        if "gpu_load_pct" in metrics:
            out["gpu_load_source"] = "metrics"
    hw = _hwmon(root, "amdgpu")
    if hw is not None:
        clock, temp, power = (_number(hw / n) for n in ("freq1_input", "temp1_input", "power1_average"))
        out["gpu_clock_mhz"] = None if clock is None else round(clock / 1e6)             # Hz
        out["apu_temp_c"] = None if temp is None else _round(temp / 1000, 1)             # m°C: the die temperature the GPU reports
        out["apu_power_w"] = None if power is None else _round(power / 1e6, 1)           # µW: the same reading the TDP limit caps
    if "gpu_clock_mhz" in metrics:
        out["gpu_clock_mhz"] = metrics["gpu_clock_mhz"]                                  # averaged, not the momentary clock
    for key in ("cpu_power_w", "gpu_power_w", "cpu_temp_c", "cpu_clock_mhz", "throttle"):
        if key in metrics:
            out[key] = metrics[key]
    out["fan_rpm"] = _fan_rpm(root)
    return {k: v for k, v in out.items() if v is not None}


class GpuBusy:
    """GPU load and clock as the mean of quick readings (10 a second) since the previous take().

    gpu_busy_percent is a momentary 0 / 100 reading, and the "average" in gpu_metrics only covers the time since anyone
    last read the table - Steam's overlay program reads it too, so a reading right after it covers a few milliseconds
    (seen on the real Deck: 65 % one second, 0 or 100 % the next). Our own quick readings do not depend on anyone else."""

    IDLE_STOP = 10.0                    # nobody took a reading for this long (a recording dropped without finish): the thread ends

    def __init__(self, root: str | Path = "/", interval: float = 0.1, clock: Callable[[], float] = time.monotonic):
        self.root = Path(root)
        self.interval = interval
        self.clock = clock
        self.last_take = clock()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.loads: list[float] = []
        self.clocks: list[float] = []
        gpu, hw = _gpu_device(self.root), _hwmon(self.root, "amdgpu")
        self.busy_file = gpu / "gpu_busy_percent" if gpu is not None else None
        self.clock_file = hw / "freq1_input" if hw is not None else None

    def poll(self) -> None:
        """One quick reading (the thread calls this; tests call it directly)."""
        load = _number(self.busy_file) if self.busy_file else None
        clock = _number(self.clock_file) if self.clock_file else None
        with self.lock:
            if load is not None:
                self.loads.append(load)
            if clock is not None:
                self.clocks.append(clock / 1e6)

    def take(self) -> dict:
        with self.lock:
            loads, clocks, self.loads, self.clocks = self.loads, self.clocks, [], []
            self.last_take = self.clock()
        out: dict = {}
        if len(loads) >= 3:                                    # too few readings say no more than the momentary one
            out["gpu_load_pct"] = _round(sum(loads) / len(loads), 1)
            out["gpu_load_source"] = "sampled"
        if len(clocks) >= 3:
            out["gpu_clock_mhz"] = round(sum(clocks) / len(clocks))
        return out

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval):
            if self.clock() - self.last_take > self.IDLE_STOP:
                break
            try:
                self.poll()
            except Exception:                                  # a sensor that goes away ends nothing
                pass

    def start(self) -> None:
        if self.busy_file is None or self.thread is not None:
            return
        self.last_take = self.clock()
        self.thread = threading.Thread(target=self._run, name="lgb-gpu-busy", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None


def read_memory(root: Path) -> dict:
    """RAM in use (total minus available, GB) and what the GPU holds: its carve-out plus system memory it mapped (MB)."""
    info: dict = {}
    for line in (_read(root / "proc/meminfo") or "").splitlines():
        name, _, rest = line.partition(":")
        try:
            info[name.strip()] = float(rest.split()[0])
        except (ValueError, IndexError):
            continue
    out: dict = {}
    if "MemTotal" in info and "MemAvailable" in info:
        out["ram_used_gb"] = _round((info["MemTotal"] - info["MemAvailable"]) / 1024 / 1024, 2)
    gpu = _gpu_device(root)
    if gpu is not None:
        vram, gtt = _number(gpu / "mem_info_vram_used"), _number(gpu / "mem_info_gtt_used")
        if vram is not None or gtt is not None:
            out["gpu_mem_mb"] = round(((vram or 0) + (gtt or 0)) / 1024 / 1024)
    return out


def read_battery_now(root: Path) -> dict:
    """What the whole Deck draws from the battery right now (only while discharging - plugged in it is the charge current)
    and the battery's temperature."""
    out: dict = {}
    for _, path, kind in _supplies(root):
        if kind != "battery" or (_read(path / "scope") or "").lower() == "device":
            continue
        if (_read(path / "status") or "").lower() == "discharging":
            power = _number(path / "power_now")
            if power is None:
                volts, amps = _number(path / "voltage_now"), _number(path / "current_now")
                power = volts * amps / 1e6 if volts and amps else None
            if power is not None:
                out["battery_power_w"] = _round(abs(power) / 1e6, 2)
        break
    temp = _battery_temp(root)
    if temp is not None:
        out["battery_temp_c"] = temp
    return out


_WHOLE_DISK = re.compile(r"^(nvme\d+n\d+|mmcblk\d+|sd[a-z]+|vd[a-z]+)$")


def _psi_total(path: Path) -> Optional[float]:
    """/proc/pressure/<x>: the 'some' line's total= (µs some task waited, since boot)."""
    match = re.search(r"^some .*\btotal=(\d+)", _read(path) or "", re.M)
    return float(match.group(1)) if match else None


def _disk_sectors_read(root: Path) -> Optional[float]:
    """Sectors read from all whole disks (internal SSD, microSD card), from /proc/diskstats."""
    total, found = 0.0, False
    for line in (_read(root / "proc/diskstats") or "").splitlines():
        parts = line.split()
        if len(parts) > 5 and _WHOLE_DISK.match(parts[2]):
            try:
                total += float(parts[5])
                found = True
            except ValueError:
                continue
    return total if found else None


class IoLoad:
    """Since the previous reading: the share of time some task waited for the disk / for memory (pressure stall
    information) and how much was read from the disks - a loading or shader-building hitch shows up here. The first
    reading only sets the start point."""

    def __init__(self, root: str | Path = "/", clock: Callable[[], float] = time.monotonic):
        self.root = Path(root)
        self.clock = clock
        self.previous: Optional[tuple] = None

    def read(self) -> dict:
        now = (self.clock(), _psi_total(self.root / "proc/pressure/io"), _psi_total(self.root / "proc/pressure/memory"),
               _disk_sectors_read(self.root))
        before, self.previous = self.previous, now
        if before is None or now[0] <= before[0]:
            return {}
        seconds = now[0] - before[0]
        out: dict = {}
        for index, key in ((1, "io_stall_pct"), (2, "mem_stall_pct")):
            if now[index] is not None and before[index] is not None:
                out[key] = _round(min(max((now[index] - before[index]) / (seconds * 1e6) * 100, 0.0), 100.0), 1)
        if now[3] is not None and before[3] is not None:
            mb = max(now[3] - before[3], 0.0) * 512 / 1e6
            out["disk_read_mb"] = _round(mb, 2)
            out["disk_read_mbs"] = _round(mb / seconds, 1)
        return out


def shader_cache_mb(app_id: Optional[int], home: Optional[Path] = None, max_files: int = 50_000) -> Optional[float]:
    """The size of a game's shader cache (all Steam libraries, internal and microSD) in MB; None when there is none."""
    if not app_id:
        return None
    steam = (home or Path.home()) / ".local/share/Steam"
    libraries = [steam]
    for match in re.finditer(r'"path"\s+"([^"]+)"', _read(steam / "steamapps/libraryfolders.vdf") or ""):
        if Path(match.group(1)) not in libraries:
            libraries.append(Path(match.group(1)))
    total, seen, found = 0, 0, False
    for library in libraries:
        folder = library / "steamapps/shadercache" / str(int(app_id))
        if not folder.is_dir():
            continue
        found = True
        for dirpath, _, files in os.walk(folder):
            for name in files:
                seen += 1
                if seen > max_files:
                    return _round(total / 1e6, 1)
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
    return _round(total / 1e6, 1) if found else None


def _cpu_times(root: Path) -> dict:
    """{"cpu": (busy, total), "cpu0": (busy, total), ...} in jiffies since boot, from /proc/stat."""
    out: dict = {}
    for line in (_read(root / "proc/stat") or "").splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("cpu") or len(parts) < 5:
            continue
        try:
            values = [int(v) for v in parts[1:9]]              # user nice system idle iowait irq softirq steal (guest is inside user)
        except ValueError:
            continue
        total = sum(values)
        out[parts[0]] = (total - values[3] - (values[4] if len(values) > 4 else 0), total)
    return out


class CpuLoad:
    """CPU load since the previous reading: the whole CPU, every core and the busiest core (a game held back by one thread
    shows a busy core while the average stays low). The first reading only sets the start point."""

    def __init__(self, root: str | Path = "/"):
        self.root = Path(root)
        self.previous: dict = {}

    def read(self) -> dict:
        now = _cpu_times(self.root)
        before, self.previous = self.previous, now

        def pct(name: str) -> Optional[float]:
            if name not in now or name not in before:
                return None
            busy, total = now[name][0] - before[name][0], now[name][1] - before[name][1]
            return None if total <= 0 else _round(min(max(100.0 * busy / total, 0.0), 100.0), 1)

        cores = [pct(name) for name in sorted((n for n in now if n != "cpu"), key=lambda n: int(n[3:]) if n[3:].isdigit() else 999)]
        out: dict = {}
        whole = pct("cpu")
        if whole is not None:
            out["cpu_load_pct"] = whole
        if cores and all(c is not None for c in cores):
            out["cpu_cores_pct"] = cores
            out["cpu_core_max_pct"] = max(cores)
        return out


# (reading key, label of the summary values, unit suffix)
SENSOR_STATS = (("gpu_load_pct", "gpu_load", "pct"), ("gpu_clock_mhz", "gpu_clock", "mhz"), ("apu_temp_c", "apu_temp", "c"),
                ("apu_power_w", "apu_power", "w"), ("fan_rpm", "fan", "rpm"),
                ("cpu_load_pct", "cpu_load", "pct"), ("cpu_core_max_pct", "cpu_core_max", "pct"),
                ("gpu_power_w", "gpu_power", "w"), ("cpu_power_w", "cpu_power", "w"), ("cpu_temp_c", "cpu_temp", "c"),
                ("cpu_clock_mhz", "cpu_clock", "mhz"), ("ram_used_gb", "ram_used", "gb"), ("gpu_mem_mb", "gpu_mem", "mb"),
                ("battery_temp_c", "battery_temp", "c"), ("io_stall_pct", "io_stall", "pct"), ("mem_stall_pct", "mem_stall", "pct"),
                ("disk_read_mbs", "disk_read", "mbs"))
# the readings that also go up as a series (the others only as mean / peak: the CPU clock is in the overlay's log already,
# battery temperature and memory stalls move too little to draw)
SERIES_KEYS = ("gpu_load_pct", "gpu_clock_mhz", "apu_temp_c", "apu_power_w", "fan_rpm", "cpu_load_pct", "cpu_core_max_pct",
               "gpu_power_w", "cpu_power_w", "cpu_temp_c", "ram_used_gb", "gpu_mem_mb", "battery_power_w",
               "io_stall_pct", "disk_read_mbs", "throttle")
MAX_CORES = 64                  # per-core values are kept for at most this many cores


def _condense(values: list[float], points: int = MAX_SERIES_POINTS) -> list[float]:
    """At most `points` values, each the mean of a run of neighbours (the shape of the recording is kept)."""
    if len(values) <= points:
        return [round(v, 1) for v in values]
    size = len(values) / points
    return [round(sum(chunk) / len(chunk), 1) for chunk in (values[int(i * size):max(int((i + 1) * size), int(i * size) + 1)] for i in range(points))]


# ----- display ------------------------------------------------------------------------------------------------------------

def _landscape(mode: Optional[str]) -> Optional[str]:
    """The Deck's panel is built upright and the kernel reports 800x1280; people know it as 1280x800."""
    match = re.fullmatch(r"(\d+)x(\d+)", mode or "")
    if match and int(match.group(1)) < int(match.group(2)):
        return f"{match.group(2)}x{match.group(1)}"
    return mode


def read_display(root: Path) -> dict:
    out: dict = {}
    bl_base = root / "sys/class/backlight"
    try:
        for entry in sorted(bl_base.iterdir()):
            now, top = _number(entry / "brightness"), _number(entry / "max_brightness")
            if now is not None and top:
                out["brightness_pct"] = round(now / top * 100)
                break
    except OSError:
        pass
    drm = root / "sys/class/drm"
    external = []
    try:
        for entry in sorted(drm.iterdir()):
            match = re.fullmatch(r"card\d+-(.+)", entry.name)
            if not match or _read(entry / "status") != "connected":
                continue
            mode = (_read(entry / "modes") or "").splitlines()
            mode = mode[0] if mode else None
            if match.group(1).lower().startswith("edp"):
                out["internal_mode"] = _landscape(mode)
            else:
                external.append(mode or match.group(1))
    except OSError:
        pass
    out["external_connected"] = bool(external)
    if external:
        out["external_mode"] = external[0]
    return _drop_empty(out) | {"external_connected": bool(external)}


# ----- the device itself (does not change during a recording) ---------------------------------------------------------------

def _os_release(root: Path) -> dict:
    out = {}
    for line in (_read(root / "etc/os-release") or "").splitlines():
        key, _, value = line.partition("=")
        out[key] = value.strip().strip('"')
    return out


def _internal_storage(root: Path) -> dict:
    """The Deck's own disk, which tells the versions apart: 64 GB eMMC, 256/512 GB NVMe (LCD), 512 GB/1 TB NVMe (OLED).

    The microSD card also shows up as mmcblk*, but its `device/type` says SD; only a `MMC` one is the internal eMMC.
    Only size, kind and model name are read - never a serial number."""
    base = root / "sys/block"
    try:
        names = sorted(p.name for p in base.iterdir())
    except OSError:
        return {}
    for name in names:
        if name.startswith("nvme"):
            kind = "nvme"
        elif name.startswith("mmcblk") and not re.search(r"(boot\d|rpmb)$", name) and (_read(base / name / "device/type") or "").upper() == "MMC":
            kind = "emmc"
        else:
            continue
        sectors = _number(base / name / "size")
        if not sectors:
            continue
        model = _read(base / name / "device/model") or _read(base / name / "device/name") or ""
        return _drop_empty({"storage_type": kind, "storage_gb": round(sectors * 512 / 1e9),
                            "storage_model": re.sub(r"[^A-Za-z0-9 .,:+()_/\-]", "", model).strip()[:40] or None})
    return {}


def _panel_name(root: Path) -> Optional[str]:
    """Maker and model of the built-in screen from its EDID (OLED Decks ship with panels from different makers)."""
    try:
        entries = sorted((root / "sys/class/drm").iterdir())
    except OSError:
        return None
    for entry in entries:
        if not re.fullmatch(r"card\d+-eDP-\d+", entry.name):
            continue
        try:
            edid = (entry / "edid").read_bytes()
        except OSError:
            continue
        if len(edid) < 128 or edid[:8] != bytes([0, 255, 255, 255, 255, 255, 255, 0]):
            continue
        word = (edid[8] << 8) | edid[9]
        maker = "".join(chr(64 + ((word >> shift) & 31)) for shift in (10, 5, 0))
        if not maker.isalpha():
            continue
        name = ""
        for at in (54, 72, 90, 108):
            block = edid[at:at + 18]
            if block[:3] == b"\0\0\0" and block[3] == 0xFC:                 # 0xFC = monitor name; 0xFF (serial) is never read
                name = re.sub(r"[^A-Za-z0-9 .+\-]", "", block[5:].split(b"\n")[0].decode("ascii", "ignore")).strip()
                break
        return f"{maker} {name}" if name else f"{maker} {edid[10] | (edid[11] << 8):04X}"
    return None


def read_device(root: Path) -> dict:
    osr = _os_release(root)
    meminfo = _read(root / "proc/meminfo") or ""

    def kb(label: str) -> Optional[float]:
        match = re.search(rf"^{label}:\s+(\d+)\s*kB", meminfo, re.M)
        return int(match.group(1)) / 1024 / 1024 if match else None

    gpu = _gpu_device(root)
    vram, gtt = (_number(gpu / n) if gpu is not None else None for n in ("mem_info_vram_total", "mem_info_gtt_total"))
    zram = _number(root / "sys/block/zram0/disksize")
    out = {
        "product": _read(root / "sys/class/dmi/id/product_name"),
        "board": _read(root / "sys/class/dmi/id/board_name"),
        "bios": _read(root / "sys/class/dmi/id/bios_version"),
        "steamos": osr.get("VERSION_ID"),
        "steamos_build": osr.get("BUILD_ID"),
        "steamos_variant": osr.get("VARIANT_ID"),
        "kernel": _read(root / "proc/sys/kernel/osrelease"),
        "ram_gb": _round(kb("MemTotal"), 1),
        "swap_gb": _round(kb("SwapTotal"), 1),
        "vram_mb": round(vram / 1024 / 1024) if vram else None,
        "gtt_mb": round(gtt / 1024 / 1024) if gtt else None,
        "zram_mb": round(zram / 1024 / 1024) if zram else None,
        "swappiness": _number(root / "proc/sys/vm/swappiness"),
        "panel": _panel_name(root),
        **_internal_storage(root),
    }
    return _drop_empty(out)


def read_launch_env(environ: Optional[dict] = None) -> dict:
    """Only the launch options that change performance (PROTON_*, DXVK_*, ...); never anything else."""
    environ = os.environ if environ is None else environ
    picked = {}
    for key, value in sorted(environ.items()):
        if key in ENV_BLOCK or not key.startswith(ENV_PREFIXES):
            continue
        value = str(value)
        if len(value) <= 48 and "/" not in value and "\n" not in value:
            picked[key] = value
        if len(picked) >= 24:
            break
    return picked


# ----- software versions: Proton build, runtime, Steam client, drivers ---------------------------------------------------

# the packages whose version changes how a game runs (SteamOS keeps its package database under /usr/lib/holo)
SOFTWARE_PACKAGES = {"mesa": "mesa", "vulkan_driver": "vulkan-radeon", "gamescope": "gamescope", "steam_package": "steam-jupiter-stable"}
PACMAN_DBS = ("usr/lib/holo/pacmandb/local", "var/lib/pacman/local")
_PKG_DIR = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)-(?P<release>[^-]+)$")
_UNSAFE = re.compile(r"[^A-Za-z0-9 .,:+()_\-]")


def _safe(text: Optional[str], limit: int = 48) -> Optional[str]:
    """A version or tool name that is fine to publish: plain characters only, never a path."""
    if not text:
        return None
    cleaned = _UNSAFE.sub("", text.strip()).strip()
    return cleaned[:limit] or None


def _installed_packages(root: Path) -> dict:
    wanted = set(SOFTWARE_PACKAGES.values())
    for rel in PACMAN_DBS:
        try:
            names = [entry.name for entry in (root / rel).iterdir()]
        except OSError:
            continue
        found = {}
        for entry in names:
            match = _PKG_DIR.match(entry)
            if match and match["name"] in wanted:
                found[match["name"]] = match["version"]
        if found:
            return found
    return {}


def _tool_build(tool_dir: Path) -> Optional[str]:
    """Proton writes '<timestamp> <build name>' into its `version` file; the build name is what people quote."""
    text = _read(tool_dir / "version")
    if not text:
        return None
    parts = text.split()
    if len(parts) < 2:                                       # a bare timestamp (custom builds) says nothing
        return None
    return _safe(parts[-1])


def _runtime_version(runtime_dir: Path) -> Optional[str]:
    text = _read(runtime_dir / "VERSIONS.txt") or ""
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "depot":
            return fields[1]
    return None


def _steam_client(home: Path) -> dict:
    """The Steam client build and update channel, from the package manifest Steam keeps in its own folder."""
    for base in (home / ".local/share/Steam/package", home / ".steam/steam/package"):
        try:
            manifests = sorted(base.glob("steam_client_*.manifest"))
        except OSError:
            continue
        for path in manifests:
            match = re.search(r'"version"\s+"(\d+)"', _read(path) or "")
            if match:
                channel = re.sub(r"^steam_client_|_ubuntu12\.manifest$", "", path.name)
                return {"steam_client": match.group(1), "steam_channel": _safe(channel)}
    return {}


def read_software(root: str | Path = "/", home: Optional[Path] = None, tools: Optional[dict] = None) -> dict:
    """What the game ran on, above the hardware: Proton build and Steam Linux Runtime (from how Steam launched the game),
    the Steam client, Mesa / Vulkan driver / gamescope. `tools` is game.launch_tools(): None when unknown, {} for a
    native Linux game, {"proton_dir", "runtime_dir"} for a Proton game. Names only - never a path."""
    root = Path(root)
    home = home or (Path.home() if str(root) == "/" else root / "home/deck")
    out: dict = {}
    if tools is not None:
        proton = tools.get("proton_dir")
        if proton:
            proton = Path(proton)
            out["compat"] = "proton"
            out["proton"] = _safe(proton.name)
            out["proton_build"] = _tool_build(proton)
            out["proton_source"] = "custom" if "compatibilitytools.d" in proton.parts else "steam"
        else:
            out["compat"] = "native"
        runtime = tools.get("runtime_dir")
        if runtime:
            runtime = Path(runtime)
            version = _runtime_version(runtime)
            out["runtime"] = _safe(f"{runtime.name} {version}" if version else runtime.name)
    out.update(_steam_client(home))
    packages = _installed_packages(root)
    for key, package in SOFTWARE_PACKAGES.items():
        if package in packages:
            out[key] = _safe(packages[package])
    return _drop_empty(out)


def snapshot(root: str | Path = "/") -> dict:
    """One reading of everything that can change during a run."""
    root = Path(root)
    return {"power": read_power(root), "limits": read_limits(root), "display": read_display(root)}


# ----- a recording's worth of readings -------------------------------------------------------------------------------------

class Sampler:
    """Reads the volatile state every few seconds while a recording runs and condenses it into one `device_state`."""

    def __init__(self, root: str | Path = "/", environ: Optional[dict] = None,
                 reader: Optional[Callable[[], dict]] = None, interval: float = SAMPLE_INTERVAL,
                 sensor_reader: Optional[Callable[[], dict]] = None, sensor_interval: float = SENSOR_INTERVAL, gpu_busy: bool = True):
        self.root = Path(root)
        self.reader = reader or (lambda: snapshot(self.root))
        self.cpu = CpuLoad(self.root)
        self.io = IoLoad(self.root)
        self.gpu: Optional[GpuBusy] = GpuBusy(self.root) if sensor_reader is None and gpu_busy else None
        self.sensor_reader = sensor_reader or (lambda: {**read_sensors(self.root), **read_memory(self.root), **read_battery_now(self.root),
                                                        **self.cpu.read(), **self.io.read(), **(self.gpu.take() if self.gpu else {})})
        self.interval = interval
        self.sensor_interval = sensor_interval
        self.environ = environ
        self.samples: list[tuple[float, dict]] = []
        self.sensor_samples: list[tuple[float, dict]] = []
        self.first: dict = {}
        self.last_at = -1e18
        self.last_sensor_at = -1e18
        self.started = 0.0

    def start(self, now: float) -> None:
        self.started = now
        if self.gpu is not None:
            self.gpu.start()
        self.first = self.reader()
        self.samples = [(now, self.first)]
        self.last_at = now
        self.sensor_samples = []
        self.last_sensor_at = -1e18
        self._sense(now)

    def sample(self, now: float) -> None:
        if now - self.last_at >= self.interval:
            self.last_at = now
            self.samples.append((now, self.reader()))
        if now - self.last_sensor_at >= self.sensor_interval:
            self._sense(now)

    def _sense(self, now: float) -> None:
        self.last_sensor_at = now
        try:
            reading = self.sensor_reader()
        except Exception:                           # a sensor that cannot be read is simply missing from the run
            return
        if isinstance(reading, dict) and reading:
            self.sensor_samples.append((now, reading))

    def finish(self, now: float, game_env: Optional[dict] = None) -> dict:
        last = self.reader()
        self.samples.append((now, last))
        self._sense(now)
        if self.gpu is not None:
            self.gpu.stop()
        return self.summary(game_env, last)

    # -- condensing --

    def _series(self, section: str, key: str) -> list[float]:
        return [s[section][key] for _, s in self.samples if isinstance(s.get(section, {}).get(key), (int, float))]

    def sensors(self) -> dict:
        """Mean / peak of every sensor and a condensed series of each (what the site draws as GPU load and clock)."""
        out: dict = {}
        series: dict = {}
        longest = 0
        def values_of(key: str) -> list:
            return [r[key] for _, r in self.sensor_samples if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]

        for key, label, unit in SENSOR_STATS:
            values = values_of(key)
            if values:
                out[f"{label}_avg_{unit}"] = _round(sum(values) / len(values), 1)
                out[f"{label}_max_{unit}"] = _round(max(values), 1)
        for key in SERIES_KEYS:
            values = values_of(key)
            if values:
                series[key] = _condense(values)
                longest = max(longest, len(series[key]))
        if not series:
            return {}
        throttle = [int(v) for v in values_of("throttle")]
        if throttle:                                # share of the readings the chip held itself back (power limit / heat)
            out["throttle_power_pct"] = _round(100 * sum(1 for v in throttle if v & 1) / len(throttle), 1)
            out["throttle_thermal_pct"] = _round(100 * sum(1 for v in throttle if v & 2) / len(throttle), 1)
        read_mb = values_of("disk_read_mb")
        if read_mb:
            out["disk_read_total_mb"] = _round(sum(read_mb), 1)
        if values_of("gpu_load_pct"):
            sources = {r.get("gpu_load_source") for _, r in self.sensor_samples}
            out["gpu_load_source"] = "sampled" if "sampled" in sources else "metrics" if "metrics" in sources else "busy"
        cores = [r["cpu_cores_pct"] for _, r in self.sensor_samples if isinstance(r.get("cpu_cores_pct"), list) and r["cpu_cores_pct"]]
        width = len(cores[-1]) if cores else 0
        cores = [c for c in cores if len(c) == width][:] if 0 < width <= MAX_CORES else []
        if cores:                                   # per core: mean and peak over the recording (same core count in every reading)
            out["cpu_cores_avg_pct"] = [_round(sum(c[i] for c in cores) / len(cores), 1) for i in range(width)]
            out["cpu_cores_max_pct"] = [_round(max(c[i] for c in cores), 1) for i in range(width)]
        times = [t for t, _ in self.sensor_samples]
        span = times[-1] - times[0]
        out["samples"] = len(self.sensor_samples)
        out["step_s"] = _round(span / (longest - 1), 1) if longest > 1 and span > 0 else None
        out["series"] = series
        return _drop_empty(out)

    def summary(self, game_env: Optional[dict] = None, last: Optional[dict] = None) -> dict:
        first = self.first or {}
        last = last or (self.samples[-1][1] if self.samples else {})
        p0, p1 = first.get("power", {}), last.get("power", {})
        online = [bool(s.get("power", {}).get("ac_online")) for _, s in self.samples if "power" in s]
        if not online:
            source = None
        elif all(online):
            source = "ac"
        elif not any(online):
            source = "battery"
        else:
            source = "mixed"
        draw = self._series("power", "battery_power_w")
        discharging = [s["power"]["battery_power_w"] for _, s in self.samples
                       if str(s.get("power", {}).get("charge_status", "")).lower() == "discharging"
                       and isinstance(s.get("power", {}).get("battery_power_w"), (int, float))]
        used_pct = (p0["battery_pct"] - p1["battery_pct"]) if "battery_pct" in p0 and "battery_pct" in p1 else None
        used_wh = (p0["battery_wh"] - p1["battery_wh"]) if "battery_wh" in p0 and "battery_wh" in p1 else None
        power = {
            "source": source,
            "ac_online_start": p0.get("ac_online"), "ac_online_end": p1.get("ac_online"),
            "charge_status_start": p0.get("charge_status"), "charge_status_end": p1.get("charge_status"),
            "charger_w": p1.get("charger_w") or p0.get("charger_w"),
            "battery_pct_start": p0.get("battery_pct"), "battery_pct_end": p1.get("battery_pct"),
            "battery_used_pct": _round(used_pct, 1) if source == "battery" else None,
            "battery_wh_start": p0.get("battery_wh"), "battery_wh_end": p1.get("battery_wh"),
            "battery_used_wh": _round(used_wh, 2) if source == "battery" and used_wh is not None else None,
            "battery_power_avg_w": _round(sum(discharging) / len(discharging), 1) if discharging else None,
            "battery_power_max_w": _round(max(draw), 1) if draw else None,
            "battery_full_wh": p1.get("battery_full_wh") or p0.get("battery_full_wh"),
            "battery_design_wh": p1.get("battery_design_wh") or p0.get("battery_design_wh"),
            "battery_health_pct": p1.get("battery_health_pct") or p0.get("battery_health_pct"),
            "battery_cycles": p1.get("battery_cycles") or p0.get("battery_cycles"),
            "battery_temp_c": p1.get("battery_temp_c") or p0.get("battery_temp_c"),
        }
        limits = dict(last.get("limits") or first.get("limits") or {})
        tdp = self._series("limits", "tdp_w")
        if tdp and min(tdp) != max(tdp):
            limits["tdp_w_min"], limits["tdp_w_max"] = min(tdp), max(tdp)       # the user changed it during the run
        limits.pop("gpu_busy_pct", None)                                       # a momentary value, MangoHud logs the real one
        display = dict(last.get("display") or first.get("display") or {})
        brightness = self._series("display", "brightness_pct")
        if brightness:
            display["brightness_pct"] = round(sum(brightness) / len(brightness))
        state = {
            "v": SCHEMA_VERSION,
            "power": _drop_empty(power),
            "limits": limits,
            "display": display,
            "device": read_device(self.root),
            "sensors": self.sensors(),
        }
        env = read_launch_env(game_env if game_env is not None else self.environ)
        if env:
            state["launch"] = {"env": env}
        return _drop_empty(state)


def read_process_env(pid: int, root: str | Path = "/") -> dict:
    """The environment of the game's process (launch options live there). {} when unreadable."""
    try:
        raw = (Path(root) / f"proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out = {}
    for item in raw.split(b"\0"):
        key, sep, value = item.decode("utf-8", "replace").partition("=")
        if sep:
            out[key] = value
    return out
