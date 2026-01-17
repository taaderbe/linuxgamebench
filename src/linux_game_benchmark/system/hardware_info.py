"""
System Hardware Information.

Gathers GPU, CPU, RAM, OS information for benchmarking context.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

# AMD GPU codename to product name mapping
AMD_GPU_CODENAMES = {
    # RDNA 4
    "GFX1200": "RX 9070 Series",
    "GFX1201": "RX 9060 Series",
    # RDNA 3
    "GFX1100": "RX 7900 Series",
    "GFX1101": "RX 7800 Series",
    "GFX1102": "RX 7600 Series",
    # RDNA 2
    "NAVI21": "RX 6800/6900 Series",
    "NAVI22": "RX 6700 Series",
    "NAVI23": "RX 6600 Series",
    "NAVI24": "RX 6500/6400 Series",
    # RDNA 1
    "NAVI10": "RX 5600/5700 Series",
    "NAVI14": "RX 5500 Series",
    # GCN
    "HAWAII": "R9 290/390 Series",
    "FIJI": "R9 Fury Series",
    "POLARIS10": "RX 480/580 Series",
    "POLARIS11": "RX 460/560 Series",
    "VEGA10": "RX Vega 56/64",
    "VEGA20": "Radeon VII",
}


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


def _is_dgpu(vendor: str, model: str) -> bool:
    """
    Classify GPU as discrete (dGPU) or integrated (iGPU).

    Returns:
        True if discrete GPU, False if integrated GPU.
    """
    model_lower = model.lower()
    vendor_lower = vendor.lower()

    # Intel = always iGPU (no discrete Intel GPUs in gaming laptops)
    if "intel" in vendor_lower:
        # Exception: Intel Arc is discrete
        if "arc" in model_lower:
            return True
        return False

    # NVIDIA = always dGPU
    if "nvidia" in vendor_lower:
        return True

    # AMD: APU vs dGPU
    if "amd" in vendor_lower or "radeon" in model_lower:
        # iGPU patterns (APU integrated graphics)
        igpu_patterns = [
            "raphael", "rembrandt", "cezanne", "renoir", "picasso", "raven",
            "vega 8", "vega 7", "vega 6", "vega 11", "vega 10", "vega 3",
            "780m", "760m", "680m", "660m", "610m",  # RDNA3 APU
            "graphics", "radeon graphics",  # Generic APU naming
        ]
        if any(p in model_lower for p in igpu_patterns):
            return False
        # RX series = always discrete
        if "rx " in model_lower or "rx-" in model_lower:
            return True
        # Default to discrete for AMD Radeon
        return True

    # Unknown vendor - default to discrete
    return True


def detect_all_gpus() -> list[dict]:
    """
    Detect all GPUs in the system with PCI addresses.

    Returns:
        List of GPU dicts with keys:
        - pci_address: PCI address (e.g., "0000:01:00.0")
        - vendor: GPU vendor (NVIDIA, AMD, Intel)
        - model: GPU model name
        - is_dgpu: True if discrete GPU, False if integrated
        - display_name: Human-readable name with (iGPU)/(dGPU) suffix
    """
    gpus = []

    try:
        result = subprocess.run(
            ["lspci", "-D"],
            capture_output=True,
            text=True,
        )

        for line in result.stdout.split("\n"):
            if "VGA" not in line and "3D controller" not in line:
                continue

            # Parse PCI address (first field)
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue

            pci_address = parts[0]
            description = parts[1]

            vendor = "Unknown"
            model = "Unknown"

            if "NVIDIA" in description:
                vendor = "NVIDIA"
                match = re.search(r"NVIDIA.*\[(.+)\]", description)
                if match:
                    model = match.group(1)
                else:
                    model = "NVIDIA GPU"
            elif "AMD" in description or "ATI" in description:
                vendor = "AMD"
                # AMD format: "Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XTX]"
                # We want the part in brackets after [AMD/ATI]
                match = re.search(r"\[AMD/ATI\]\s*([^\[]+)\s*\[([^\]]+)\]", description)
                if match:
                    # Get the model from second brackets (e.g., "Radeon RX 7900 XTX")
                    model = match.group(2).strip()
                else:
                    # Fallback: try to find Radeon pattern
                    match = re.search(r"(Radeon[^]]+)", description)
                    if match:
                        model = match.group(1).strip()
                    else:
                        model = "AMD GPU"
            elif "Intel" in description:
                vendor = "Intel"
                match = re.search(r"Intel Corporation (.+?)(?:\s*\(rev|\s*$)", description)
                if match:
                    model = match.group(1).strip()
                else:
                    model = "Intel GPU"

            is_dgpu = _is_dgpu(vendor, model)
            suffix = "dGPU" if is_dgpu else "iGPU"
            display_name = f"{vendor} {model} ({suffix})"

            gpus.append({
                "pci_address": pci_address,
                "vendor": vendor,
                "model": model,
                "is_dgpu": is_dgpu,
                "display_name": display_name,
            })

    except Exception:
        pass

    return gpus


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
                    # Extract version after "NVIDIA" (e.g., "4.6.0 NVIDIA 550.54.14" -> "550.54.14")
                    match = re.search(r"NVIDIA (\d+\.\d+\.\d+)", version)
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
        # or "AMD Radeon Graphics (RADV GFX1200)" for generic names with codename
        # We want to extract a proper model name
        glx_clean = glxinfo_model.split("(")[0].strip() if glxinfo_model else None

        # Try to extract codename from glxinfo (e.g., "RADV GFX1200" or "RADV HAWAII")
        codename_model = None
        if glxinfo_model:
            codename_match = re.search(r"RADV\s+(\w+)", glxinfo_model, re.IGNORECASE)
            if codename_match:
                codename = codename_match.group(1).upper()
                if codename in AMD_GPU_CODENAMES:
                    codename_model = AMD_GPU_CODENAMES[codename]

        # Prefer specific names over generic "AMD Radeon Graphics"
        if glx_clean and glx_clean != "AMD Radeon Graphics":
            info["model"] = glx_clean
        elif codename_model:
            # Use mapped codename (e.g., GFX1200 -> "RX 9070 Series")
            info["model"] = codename_model
        elif vulkan_model and "AMD" in vulkan_model:
            info["model"] = vulkan_model
        elif lspci_model:
            info["model"] = lspci_model
        elif glx_clean:
            info["model"] = glx_clean
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


def detect_sched_ext() -> Optional[str]:
    """
    Detect active sched-ext scheduler.

    sched-ext (Extensible Scheduler Class) allows custom schedulers like:
    - scx_lavd: Gaming-optimized (Steam Deck, Igalia)
    - scx_rusty: Load balancing, LLC-aware
    - scx_bpfland: General purpose

    Returns:
        Scheduler name (e.g., "scx_lavd") or None if not using sched-ext.
    """
    try:
        path = Path("/sys/kernel/sched_ext/root/ops")
        if path.exists():
            scheduler = path.read_text().strip()
            if scheduler:
                return scheduler
    except Exception:
        pass
    return None


def detect_discrete_gpu_pci() -> Optional[str]:
    """
    Detect discrete GPU PCI address for MangoHud.

    In multi-GPU systems, MangoHud may log the wrong GPU (iGPU instead of dGPU).
    This function returns the PCI address of the first discrete GPU found,
    which can be used with MangoHud's `pci_dev` option.

    Returns:
        PCI address like "0000:03:00.0" or None if no discrete GPU found.
    """
    gpus = detect_all_gpus()

    # Find first discrete GPU
    for gpu in gpus:
        if gpu.get("is_dgpu"):
            return gpu.get("pci_address")

    # No discrete GPU found - return None (MangoHud will use default)
    return None


