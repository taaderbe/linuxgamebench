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
from pathlib import Path
from typing import Callable, Optional

SAMPLE_INTERVAL = 2.0
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
        "battery_temp_c": _round((_number(battery / "temp") or 0) / 10, 1) if _number(battery / "temp") else None,
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


# ----- display ------------------------------------------------------------------------------------------------------------

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
                out["internal_mode"] = mode
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


def snapshot(root: str | Path = "/") -> dict:
    """One reading of everything that can change during a run."""
    root = Path(root)
    return {"power": read_power(root), "limits": read_limits(root), "display": read_display(root)}


# ----- a recording's worth of readings -------------------------------------------------------------------------------------

class Sampler:
    """Reads the volatile state every few seconds while a recording runs and condenses it into one `device_state`."""

    def __init__(self, root: str | Path = "/", environ: Optional[dict] = None,
                 reader: Optional[Callable[[], dict]] = None, interval: float = SAMPLE_INTERVAL):
        self.root = Path(root)
        self.reader = reader or (lambda: snapshot(self.root))
        self.interval = interval
        self.environ = environ
        self.samples: list[tuple[float, dict]] = []
        self.first: dict = {}
        self.last_at = -1e18
        self.started = 0.0

    def start(self, now: float) -> None:
        self.started = now
        self.first = self.reader()
        self.samples = [(now, self.first)]
        self.last_at = now

    def sample(self, now: float) -> None:
        if now - self.last_at >= self.interval:
            self.last_at = now
            self.samples.append((now, self.reader()))

    def finish(self, now: float, game_env: Optional[dict] = None) -> dict:
        last = self.reader()
        self.samples.append((now, last))
        return self.summary(game_env, last)

    # -- condensing --

    def _series(self, section: str, key: str) -> list[float]:
        return [s[section][key] for _, s in self.samples if isinstance(s.get(section, {}).get(key), (int, float))]

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
