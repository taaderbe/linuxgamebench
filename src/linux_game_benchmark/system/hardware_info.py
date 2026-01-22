"""
System Hardware Information.

Gathers GPU, CPU, RAM, OS information for benchmarking context.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

# PCI Device ID to GPU model mapping (vendor:device -> model name)
# Format: "vendor:device" (lowercase hex)
GPU_DEVICE_IDS = {
    # AMD RDNA 4
    "1002:7480": "RX 9070 XT",
    "1002:7481": "RX 9070",
    # AMD RDNA 3
    "1002:744c": "RX 7900 XTX",
    "1002:7448": "RX 7900 XT",
    "1002:745e": "RX 7900 GRE",
    "1002:7470": "RX 7800 XT",
    "1002:7471": "RX 7700 XT",
    "1002:7480": "RX 7600 XT",
    "1002:7489": "RX 7600",
    # AMD RDNA 2
    "1002:73bf": "RX 6900 XT",
    "1002:73af": "RX 6800 XT",
    "1002:73a5": "RX 6800",
    "1002:73df": "RX 6700 XT",
    "1002:73ff": "RX 6600 XT",
    "1002:73e3": "RX 6600",
    # NVIDIA RTX 50 Series
    "10de:2684": "RTX 5090",
    "10de:2685": "RTX 5080",
    "10de:2704": "RTX 5070 Ti",
    "10de:2705": "RTX 5070",
    # NVIDIA RTX 40 Series
    "10de:2684": "RTX 4090",
    "10de:2702": "RTX 4080 SUPER",
    "10de:2704": "RTX 4080",
    "10de:2782": "RTX 4070 Ti SUPER",
    "10de:2783": "RTX 4070 Ti",
    "10de:2786": "RTX 4070 SUPER",
    "10de:2786": "RTX 4070",
    "10de:2860": "RTX 4060 Ti",
    "10de:2882": "RTX 4060",
    # NVIDIA RTX 30 Series
    "10de:2204": "RTX 3090",
    "10de:2206": "RTX 3080",
    "10de:2484": "RTX 3070",
    "10de:2503": "RTX 3060",
}

# AMD GPU codename to product name mapping
AMD_GPU_CODENAMES = {
    # RDNA 4
    "GFX1200": "RX 9070",
    "GFX1201": "RX 9060",
    # RDNA 3
    "GFX1100": "RX 7900",
    "GFX1101": "RX 7800",
    "GFX1102": "RX 7600",
    # RDNA 2
    "NAVI21": "RX 6800/6900",
    "NAVI22": "RX 6700",
    "NAVI23": "RX 6600",
    "NAVI24": "RX 6500/6400",
    # RDNA 1
    "NAVI10": "RX 5600/5700",
    "NAVI14": "RX 5500",
    # GCN
    "HAWAII": "R9 290/390",
    "FIJI": "R9 Fury",
    "POLARIS10": "RX 480/580",
    "POLARIS11": "RX 460/560",
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
    """Get GPU information.

    Priority for GPU model detection:
    1. vulkaninfo deviceName (most accurate, exact marketing name)
    2. device_id + VRAM disambiguation (for shared device IDs like Navi 31)
    3. lspci model name (fallback)

    Always stores lspci_raw and device_id for debugging.
    """
    info = {
        "model": "Unknown",
        "vendor": "Unknown",
        "vram_mb": 0,
        "driver": "Unknown",
        "driver_version": "",
        "vulkan_version": "",
        "device_id": "",
        "lspci_raw": "",
    }

    lspci_model = None
    vulkan_model = None

    # === Step 1: Gather raw data from all sources ===

    # Get VRAM from sysfs first (needed for disambiguation)
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

    # Try lspci -nn for device ID and raw line (always needed for debugging)
    try:
        result = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "VGA" in line or "3D controller" in line:
                # Skip integrated graphics if we already found a discrete GPU
                if info["lspci_raw"]:
                    # Intel iGPU
                    if "Intel" in line:
                        continue
                    # AMD iGPU (Ryzen APU integrated graphics)
                    # Codenames: Granite Ridge, Raphael, Phoenix, Hawk Point, Rembrandt, Cezanne, etc.
                    amd_igpu_patterns = ["Granite Ridge", "Raphael", "Phoenix", "Hawk Point",
                                         "Rembrandt", "Cezanne", "Renoir", "Picasso", "Raven"]
                    if any(igpu in line for igpu in amd_igpu_patterns):
                        continue

                # Store raw lspci line for debugging
                info["lspci_raw"] = line.strip()

                # Extract PCI device ID (e.g., "[10de:2484]" -> "10de:2484")
                device_id_match = re.search(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\](?:\s*\(rev|\s*$)", line)
                if device_id_match:
                    info["device_id"] = device_id_match.group(1).lower()

                # Detect vendor
                if "NVIDIA" in line:
                    info["vendor"] = "NVIDIA"
                    match = re.search(r"NVIDIA.*\[(.+?)\]", line)
                    if match:
                        lspci_model = match.group(1)
                elif "AMD" in line or "ATI" in line:
                    info["vendor"] = "AMD"
                    match = re.search(r"\]:\s*.*?\[(.+?)\]", line)
                    if match:
                        lspci_model = match.group(1).strip()
                elif "Intel" in line:
                    info["vendor"] = "Intel"
                    match = re.search(r"Intel Corporation (.+?)(?:\s*\[|\s*\(rev|\s*$)", line)
                    if match:
                        lspci_model = match.group(1).strip()
    except Exception:
        pass

    # Get Vulkan device name (PRIMARY SOURCE for GPU model)
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
                    raw_name = match.group(1).strip()
                    # Clean up the name - remove driver suffix like "(RADV NAVI31)" or "(RADV RAPHAEL_MENDOCINO)"
                    # Keep the marketing name part
                    clean_name = re.sub(r"\s*\(RADV\s+\w+\)\s*$", "", raw_name)
                    clean_name = re.sub(r"\s*\(TU\d+\)\s*$", "", clean_name)  # NVIDIA Turing
                    clean_name = re.sub(r"\s*\(GA\d+\)\s*$", "", clean_name)  # NVIDIA Ampere
                    clean_name = re.sub(r"\s*\(AD\d+\)\s*$", "", clean_name)  # NVIDIA Ada

                    # Skip CPU/APU entries (like "AMD Ryzen 7 9800X3D...")
                    if "Ryzen" not in clean_name and "Core" not in clean_name and "Processor" not in clean_name:
                        vulkan_model = clean_name.strip()
                        break  # Use first discrete GPU
            if "apiVersion" in line:
                match = re.search(r"= (\d+\.\d+\.\d+)", line)
                if match:
                    info["vulkan_version"] = match.group(1)
    except Exception:
        pass

    # Get driver info from glxinfo
    try:
        result = subprocess.run(
            ["glxinfo", "-B"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "OpenGL version" in line or "OpenGL core profile version" in line:
                version = line.split(":")[-1].strip()
                if "Mesa" in version:
                    info["driver"] = "Mesa"
                    match = re.search(r"Mesa (\d+\.\d+\.\d+)", version)
                    if match:
                        info["driver_version"] = match.group(1)
                elif "NVIDIA" in version:
                    info["driver"] = "NVIDIA"
                    match = re.search(r"NVIDIA (\d+\.\d+\.\d+)", version)
                    if match:
                        info["driver_version"] = match.group(1)
    except Exception:
        pass

    # NVIDIA driver fallback detection (if glxinfo failed or nvidia-smi not in PATH)
    if info["vendor"] == "NVIDIA" and not info["driver_version"]:
        info["driver"] = "NVIDIA"

        # Method 1: nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                info["driver_version"] = result.stdout.strip()
        except Exception:
            pass

        # Method 2: /proc/driver/nvidia/version
        if not info["driver_version"]:
            try:
                nvidia_proc = Path("/proc/driver/nvidia/version")
                if nvidia_proc.exists():
                    content = nvidia_proc.read_text()
                    match = re.search(r"Kernel Module\s+(\d+\.\d+\.\d+)", content)
                    if match:
                        info["driver_version"] = match.group(1)
            except Exception:
                pass

        # Method 3: /sys/module/nvidia/version
        if not info["driver_version"]:
            try:
                nvidia_sys = Path("/sys/module/nvidia/version")
                if nvidia_sys.exists():
                    info["driver_version"] = nvidia_sys.read_text().strip()
            except Exception:
                pass

        # Method 4: modinfo nvidia
        if not info["driver_version"]:
            try:
                result = subprocess.run(
                    ["modinfo", "nvidia"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    match = re.search(r"^version:\s+(\d+\.\d+\.\d+)", result.stdout, re.MULTILINE)
                    if match:
                        info["driver_version"] = match.group(1)
            except Exception:
                pass

    # AMD/Mesa driver fallback detection (if glxinfo failed to get version)
    if info["vendor"] == "AMD" and not info["driver_version"]:
        info["driver"] = "Mesa"

        # Use vulkaninfo to get Mesa version
        try:
            result = subprocess.run(
                ["vulkaninfo", "--summary"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                # Look for driverInfo which contains "Mesa X.Y.Z-..."
                if "driverInfo" in line:
                    match = re.search(r"Mesa (\d+\.\d+\.\d+)", line)
                    if match:
                        info["driver_version"] = match.group(1)
                        break
                # Fallback: driverVersion field (just the version number)
                elif "driverVersion" in line and not info["driver_version"]:
                    match = re.search(r"=\s*(\d+\.\d+\.\d+)", line)
                    if match:
                        info["driver_version"] = match.group(1)
        except Exception:
            pass

    # === Step 2: Determine GPU model with priority ===

    # Priority 1: vulkaninfo deviceName (most accurate)
    if vulkan_model:
        info["model"] = vulkan_model
        return info

    # Priority 2: device_id + VRAM disambiguation (for shared device IDs)
    if info["device_id"]:
        device_id = info["device_id"]
        vram_gb = info["vram_mb"] / 1024 if info["vram_mb"] > 0 else 0

        # AMD Navi 31 variants (shared device ID 1002:744c)
        if device_id == "1002:744c":
            if vram_gb >= 23:  # 24GB
                info["model"] = "AMD Radeon RX 7900 XTX"
            elif vram_gb >= 19:  # 20GB
                info["model"] = "AMD Radeon RX 7900 XT"
            elif vram_gb >= 15:  # 16GB
                info["model"] = "AMD Radeon RX 7900 GRE"
            else:
                info["model"] = "AMD Radeon RX 7900"  # Unknown variant
            return info

        # AMD Navi 32 variants (RX 7800 XT / 7700 XT)
        if device_id == "1002:7480":
            if vram_gb >= 15:  # 16GB
                info["model"] = "AMD Radeon RX 7800 XT"
            else:  # 12GB
                info["model"] = "AMD Radeon RX 7700 XT"
            return info

        # Direct device ID mapping for unique IDs
        if device_id in GPU_DEVICE_IDS:
            info["model"] = GPU_DEVICE_IDS[device_id]
            return info

    # Priority 3: lspci model name (fallback)
    if lspci_model:
        if info["vendor"] == "Intel":
            info["model"] = f"Intel {lspci_model}"
        else:
            info["model"] = lspci_model
        return info

    # Fallback: try to get VRAM from glxinfo if still 0
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

    # Find Steam path (native or Flatpak)
    candidates = [
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "root",
        Path.home() / ".local" / "share" / "Steam",
        # Flatpak Steam
        Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",
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


