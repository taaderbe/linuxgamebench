"""
System Hardware Information.

Gathers GPU, CPU, RAM, OS information for benchmarking context.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


def get_system_info() -> dict:
    """
    Gather comprehensive system information.

    Returns:
        Dictionary with os, gpu, cpu, ram, steam info.
    """
    return {
        "os": get_os_info(),
        "gpu": get_gpu_info(),
        "cpu": get_cpu_info(),
        "ram": get_ram_info(),
        "steam": get_steam_info(),
    }


def get_os_info() -> dict:
    """Get OS and kernel information."""
    info = {
        "name": "Unknown",
        "kernel": "Unknown",
        "desktop": "Unknown",
        "display_server": "Unknown",
    }

    # Kernel version
    try:
        info["kernel"] = subprocess.run(
            ["uname", "-r"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        pass

    # OS name from /etc/os-release
    try:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            content = os_release.read_text()
            name_match = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', content, re.MULTILINE)
            if name_match:
                info["name"] = name_match.group(1)
    except Exception:
        pass

    # Desktop environment
    info["desktop"] = os.environ.get(
        "XDG_CURRENT_DESKTOP",
        os.environ.get("DESKTOP_SESSION", "Unknown"),
    )

    # Display server
    if os.environ.get("WAYLAND_DISPLAY"):
        info["display_server"] = "wayland"
    elif os.environ.get("DISPLAY"):
        info["display_server"] = "x11"

    return info


def get_gpu_info() -> dict:
    """Get GPU information."""
    info = {
        "model": "Unknown",
        "vendor": "Unknown",
        "vram_mb": 0,
        "driver": "Unknown",
        "driver_version": "",
        "vulkan_version": "",
    }

    lspci_model = None
    vulkan_model = None

    # Try lspci for GPU model (most reliable for identifying the chip)
    try:
        result = subprocess.run(
            ["lspci", "-v"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "VGA" in line or "3D controller" in line:
                # Extract model name
                if "NVIDIA" in line:
                    info["vendor"] = "NVIDIA"
                    match = re.search(r"NVIDIA.*\[(.+)\]", line)
                    if match:
                        lspci_model = match.group(1)
                elif "AMD" in line or "ATI" in line:
                    info["vendor"] = "AMD"
                    match = re.search(r"(Radeon[^]]+|AMD[^]]+)", line)
                    if match:
                        lspci_model = match.group(1).strip()
                elif "Intel" in line:
                    info["vendor"] = "Intel"
                    # Intel: capture full description including brackets
                    # e.g. "TigerLake-LP GT2 [Iris Xe Graphics]"
                    match = re.search(r"Intel Corporation (.+?)(?:\s*\(rev|\s*$)", line)
                    if match:
                        lspci_model = match.group(1).strip()
                break
    except Exception:
        pass

    # Get Vulkan device name (often has good Intel naming)
    try:
        result = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "deviceName" in line:
                match = re.search(r"=\s*(.+)", line)
                if match:
                    vulkan_model = match.group(1).strip()
            if "apiVersion" in line:
                match = re.search(r"= (\d+\.\d+\.\d+)", line)
                if match:
                    info["vulkan_version"] = match.group(1)
    except Exception:
        pass

    # Get driver info from glxinfo
    glxinfo_model = None
    try:
        result = subprocess.run(
            ["glxinfo", "-B"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "OpenGL renderer" in line:
                glxinfo_model = line.split(":")[-1].strip()
            if "OpenGL version" in line:
                version = line.split(":")[-1].strip()
                if "Mesa" in version:
                    info["driver"] = "Mesa"
                    match = re.search(r"Mesa (\d+\.\d+\.\d+)", version)
                    if match:
                        info["driver_version"] = match.group(1)
                elif "NVIDIA" in version:
                    info["driver"] = "NVIDIA"
                    match = re.search(r"(\d+\.\d+)", version)
                    if match:
                        info["driver_version"] = match.group(1)
    except Exception:
        pass

    # Choose best model name based on vendor
    if info["vendor"] == "Intel":
        # For Intel: prefer vulkaninfo > lspci > glxinfo
        # vulkaninfo gives clean names like "Intel(R) Iris(R) Xe Graphics (TGL GT2)"
        # lspci gives "TigerLake-LP GT2 [Iris Xe Graphics]"
        # glxinfo sometimes only gives "Mesa Intel(R) Graphics"
        if vulkan_model and "Intel" in vulkan_model:
            info["model"] = vulkan_model
        elif lspci_model:
            info["model"] = f"Intel {lspci_model}"
        elif glxinfo_model:
            info["model"] = glxinfo_model
    elif info["vendor"] == "AMD":
        # For AMD: glxinfo gives full info but includes driver details in parentheses
        # e.g. "AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 21.1.6, DRM 3.64, 6.18.2-3-cachyos)"
        # We want just "AMD Radeon RX 7900 XTX"
        if glxinfo_model:
            info["model"] = glxinfo_model.split("(")[0].strip()
        elif lspci_model:
            info["model"] = lspci_model
    elif info["vendor"] == "NVIDIA":
        # For NVIDIA: lspci is usually clean
        if lspci_model:
            info["model"] = lspci_model
        elif glxinfo_model:
            info["model"] = glxinfo_model
    else:
        # Fallback
        info["model"] = glxinfo_model or lspci_model or vulkan_model or "Unknown"

    # Try to get VRAM from sysfs (AMD) - check all cards and find the largest
    try:
        max_vram = 0
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for card_dir in drm_path.glob("card[0-9]"):
                vram_path = card_dir / "device" / "mem_info_vram_total"
                if vram_path.exists():
                    try:
                        vram_bytes = int(vram_path.read_text().strip())
                        if vram_bytes > max_vram:
                            max_vram = vram_bytes
                    except (ValueError, IOError):
                        pass
            if max_vram > 0:
                info["vram_mb"] = max_vram // (1024 * 1024)
    except Exception:
        pass

    # Fallback: try to get VRAM from glxinfo
    if info["vram_mb"] == 0:
        try:
            result = subprocess.run(
                ["glxinfo"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if "Video memory" in line or "Dedicated video memory" in line:
                    match = re.search(r"(\d+)\s*MB", line, re.IGNORECASE)
                    if match:
                        info["vram_mb"] = int(match.group(1))
                        break
        except Exception:
            pass

    return info


def get_cpu_info() -> dict:
    """Get CPU information."""
    info = {
        "model": "Unknown",
        "vendor": "Unknown",
        "cores": 0,
        "threads": 0,
        "base_clock_mhz": 0,
    }

    # Parse /proc/cpuinfo
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()

        # Model name
        model_match = re.search(r"model name\s+:\s+(.+)", cpuinfo)
        if model_match:
            info["model"] = model_match.group(1).strip()

        # Vendor
        vendor_match = re.search(r"vendor_id\s+:\s+(.+)", cpuinfo)
        if vendor_match:
            vendor_id = vendor_match.group(1).strip()
            if "AMD" in vendor_id:
                info["vendor"] = "AMD"
            elif "Intel" in vendor_id:
                info["vendor"] = "Intel"

        # Count physical cores and threads
        physical_ids = set()
        core_ids = set()
        processor_count = 0

        for line in cpuinfo.split("\n"):
            if line.startswith("processor"):
                processor_count += 1
            elif "physical id" in line:
                physical_ids.add(line.split(":")[-1].strip())
            elif "core id" in line:
                core_ids.add(line.split(":")[-1].strip())

        info["threads"] = processor_count
        # Cores = unique core ids per physical package
        info["cores"] = len(core_ids) * max(len(physical_ids), 1)

        # Base clock from /sys
        try:
            freq_path = Path(
                "/sys/devices/system/cpu/cpu0/cpufreq/base_frequency"
            )
            if freq_path.exists():
                freq_khz = int(freq_path.read_text().strip())
                info["base_clock_mhz"] = freq_khz // 1000
            else:
                # Fallback to max freq
                freq_path = Path(
                    "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
                )
                if freq_path.exists():
                    freq_khz = int(freq_path.read_text().strip())
                    info["base_clock_mhz"] = freq_khz // 1000
        except Exception:
            pass

    except Exception:
        pass

    return info


def get_ram_info() -> dict:
    """Get RAM information."""
    info = {
        "total_gb": 0,
        "total_mb": 0,
    }

    try:
        meminfo = Path("/proc/meminfo").read_text()
        total_match = re.search(r"MemTotal:\s+(\d+)\s+kB", meminfo)
        if total_match:
            total_kb = int(total_match.group(1))
            info["total_mb"] = total_kb // 1024
            info["total_gb"] = total_kb / (1024 * 1024)
    except Exception:
        pass

    return info


def get_steam_info() -> dict:
    """Get Steam installation info."""
    info = {
        "path": None,
        "proton_versions": [],
    }

    # Find Steam path
    candidates = [
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "root",
        Path.home() / ".local" / "share" / "Steam",
    ]

    for path in candidates:
        if path.exists() and (path / "steamapps").exists():
            info["path"] = str(path)
            break

    if not info["path"]:
        return info

    steam_path = Path(info["path"])

    # Get Proton versions
    proton_names = []

    # Official Proton
    common_dir = steam_path / "steamapps" / "common"
    if common_dir.exists():
        for folder in common_dir.glob("Proton*"):
            if folder.is_dir():
                proton_names.append(folder.name)

    # Custom Proton
    compat_dir = steam_path / "compatibilitytools.d"
    if compat_dir.exists():
        for folder in compat_dir.iterdir():
            if folder.is_dir():
                proton_names.append(folder.name)

    info["proton_versions"] = sorted(proton_names)

    return info


def get_cpu_governor() -> str:
    """Get current CPU governor."""
    try:
        path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        if path.exists():
            return path.read_text().strip()
    except Exception:
        pass
    return "unknown"


def get_amd_gpu_power_profile() -> Optional[str]:
    """Get AMD GPU power profile (if AMD GPU)."""
    try:
        path = Path("/sys/class/drm/card0/device/power_dpm_force_performance_level")
        if path.exists():
            return path.read_text().strip()
    except Exception:
        pass
    return None


def is_compositor_running() -> bool:
    """Check if a compositor is running (for X11)."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "kwin_x11|kwin_wayland|mutter|picom|compton"],
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_gamemode_active() -> bool:
    """Check if Feral GameMode is active."""
    try:
        result = subprocess.run(
            ["gamemoded", "-s"],
            capture_output=True,
            text=True,
        )
        return "active" in result.stdout.lower()
    except Exception:
        return False
