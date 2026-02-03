"""Hardware name normalization and formatting utilities.

Shared between CLI and GUI to ensure consistent display/storage of
GPU, CPU, kernel, OS, and resolution strings.
"""

import re


def short_gpu(name: str) -> str:
    """Shorten GPU name for consistent storage."""
    if not name:
        return "Unknown"

    # === NVIDIA RTX 50 Series (Blackwell 2025) ===
    if "5090" in name:
        return "RTX 5090"
    if "5080" in name:
        return "RTX 5080"
    if "5070 Ti" in name:
        return "RTX 5070 Ti"
    if "5070" in name:
        return "RTX 5070"
    if "5060 Ti" in name:
        return "RTX 5060 Ti"
    if "5060" in name:
        return "RTX 5060"

    # === NVIDIA RTX 40 Series (Ada Lovelace) ===
    if "4090" in name:
        return "RTX 4090"
    if "4080 Super" in name:
        return "RTX 4080 Super"
    if "4080" in name:
        return "RTX 4080"
    if "4070 Ti Super" in name:
        return "RTX 4070 Ti Super"
    if "4070 Ti" in name:
        return "RTX 4070 Ti"
    if "4070 Super" in name:
        return "RTX 4070 Super"
    if "4070" in name:
        return "RTX 4070"
    if "4060 Ti" in name:
        return "RTX 4060 Ti"
    if "4060" in name:
        return "RTX 4060"

    # === NVIDIA RTX 30 Series (Ampere) ===
    if "3090 Ti" in name:
        return "RTX 3090 Ti"
    if "3090" in name:
        return "RTX 3090"
    if "3080 Ti" in name:
        return "RTX 3080 Ti"
    if "3080" in name:
        return "RTX 3080"
    if "3070 Ti" in name:
        return "RTX 3070 Ti"
    if "3070" in name:
        return "RTX 3070"
    if "3060 Ti" in name:
        return "RTX 3060 Ti"
    if "3060" in name:
        return "RTX 3060"
    if "3050" in name:
        return "RTX 3050"

    # === NVIDIA RTX 20 Series (Turing) ===
    if "2080 Ti" in name:
        return "RTX 2080 Ti"
    if "2080 Super" in name:
        return "RTX 2080 Super"
    if "2080" in name:
        return "RTX 2080"
    if "2070 Super" in name:
        return "RTX 2070 Super"
    if "2070" in name:
        return "RTX 2070"
    if "2060 Super" in name:
        return "RTX 2060 Super"
    if "2060" in name:
        return "RTX 2060"

    # === NVIDIA GTX 16 Series ===
    if "1660 Ti" in name:
        return "GTX 1660 Ti"
    if "1660 Super" in name:
        return "GTX 1660 Super"
    if "1660" in name:
        return "GTX 1660"
    if "1650 Super" in name:
        return "GTX 1650 Super"
    if "1650" in name:
        return "GTX 1650"

    # === NVIDIA GTX 16 Series (budget) ===
    if "1630" in name:
        return "GTX 1630"

    # === NVIDIA GTX 10 Series (Pascal 2016) ===
    if "1080 Ti" in name:
        return "GTX 1080 Ti"
    if "1080" in name:
        return "GTX 1080"
    if "1070 Ti" in name:
        return "GTX 1070 Ti"
    if "1070" in name:
        return "GTX 1070"
    if "1060" in name:
        return "GTX 1060"
    if "1050 Ti" in name:
        return "GTX 1050 Ti"
    if "1050" in name:
        return "GTX 1050"
    if "GT 1030" in name or "GT1030" in name:
        return "GT 1030"

    # === NVIDIA MX Series (Mobile) ===
    if "MX550" in name:
        return "MX550"
    if "MX450" in name:
        return "MX450"
    if "MX350" in name:
        return "MX350"
    if "MX250" in name:
        return "MX250"
    if "MX150" in name:
        return "MX150"
    if "MX130" in name:
        return "MX130"
    if "MX110" in name:
        return "MX110"

    # === NVIDIA GTX 900 Series (Maxwell 2014-2015) ===
    if "980 Ti" in name:
        return "GTX 980 Ti"
    if "980" in name and "GTX" in name:
        return "GTX 980"
    if "970" in name and "GTX" in name:
        return "GTX 970"
    if "960" in name and "GTX" in name:
        return "GTX 960"
    if "950" in name and "GTX" in name:
        return "GTX 950"

    # === AMD RX 9000 Series (RDNA 4 - 2025) ===
    if "9070 XT" in name:
        return "RX 9070 XT"
    if "9070" in name:
        return "RX 9070"
    if "9060 XT" in name:
        return "RX 9060 XT"
    if "9060" in name:
        return "RX 9060"

    # === AMD RX 7000 Series (RDNA 3) ===
    if "7900 XTX" in name:
        return "RX 7900 XTX"
    if "7900 XT" in name and "XTX" not in name:
        return "RX 7900 XT"
    if "7900 GRE" in name:
        return "RX 7900 GRE"
    if "7800 XT" in name:
        return "RX 7800 XT"
    if "7700 XT" in name:
        return "RX 7700 XT"
    if "7600 XT" in name:
        return "RX 7600 XT"
    if "7600" in name and "RX" in name:
        return "RX 7600"

    # === AMD RX 6000 Series (RDNA 2) ===
    if "6950 XT" in name:
        return "RX 6950 XT"
    if "6900 XT" in name:
        return "RX 6900 XT"
    if "6800 XT" in name:
        return "RX 6800 XT"
    if "6800" in name and "RX" in name and "XT" not in name:
        return "RX 6800"
    if "6750 XT" in name:
        return "RX 6750 XT"
    if "6700 XT" in name:
        return "RX 6700 XT"
    if "6700" in name and "RX" in name and "XT" not in name:
        return "RX 6700"
    if "6650 XT" in name:
        return "RX 6650 XT"
    if "6600 XT" in name:
        return "RX 6600 XT"
    if "6600" in name and "RX" in name and "XT" not in name:
        return "RX 6600"
    if "6500 XT" in name:
        return "RX 6500 XT"
    if "6400" in name:
        return "RX 6400"

    # === AMD RX 5000 Series (RDNA 1 - 2019) ===
    if "5700 XT" in name:
        return "RX 5700 XT"
    if "5700" in name and "RX" in name and "XT" not in name:
        return "RX 5700"
    if "5600 XT" in name:
        return "RX 5600 XT"
    if "5600" in name and "RX" in name and "XT" not in name:
        return "RX 5600"
    if "5500 XT" in name:
        return "RX 5500 XT"
    if "5500" in name and "RX" in name and "XT" not in name:
        return "RX 5500"

    # === AMD RX 500 Series (Polaris 2017) ===
    if "RX 590" in name or "RX590" in name:
        return "RX 590"
    if "RX 580" in name or "RX580" in name:
        return "RX 580"
    if "RX 570" in name or "RX570" in name:
        return "RX 570"
    if "RX 560" in name or "RX560" in name:
        return "RX 560"
    if "RX 550" in name or "RX550" in name:
        return "RX 550"

    # === AMD RX 400 Series (Polaris 2016) ===
    if "RX 480" in name or "RX480" in name:
        return "RX 480"
    if "RX 470" in name or "RX470" in name:
        return "RX 470"
    if "RX 460" in name or "RX460" in name:
        return "RX 460"

    # === AMD R9 Fury Series (Fiji 2015) ===
    if "Fury X" in name:
        return "R9 Fury X"
    if "Fury" in name and "Nano" not in name:
        return "R9 Fury"
    if "R9 Nano" in name or "Nano" in name:
        return "R9 Nano"

    # === AMD R9 300 Series (GCN 2015) ===
    if "R9 390X" in name or "390X" in name:
        return "R9 390X"
    if "R9 390" in name or ("390" in name and "X" not in name):
        return "R9 390"
    if "R9 380X" in name or "380X" in name:
        return "R9 380X"
    if "R9 380" in name or ("380" in name and "X" not in name):
        return "R9 380"
    if "R7 370" in name or "370" in name:
        return "R7 370"
    if "R7 360" in name or "360" in name:
        return "R7 360"

    # === Intel Arc B-Series (Battlemage 2024) ===
    if "B580" in name:
        return "Arc B580"
    if "B570" in name:
        return "Arc B570"

    # === Intel Arc A-Series (Alchemist) ===
    if "A770" in name:
        return "Arc A770"
    if "A750" in name:
        return "Arc A750"
    if "A580" in name:
        return "Arc A580"
    if "A380" in name:
        return "Arc A380"
    if "A310" in name:
        return "Arc A310"

    # === Intel Integrated ===
    if "Iris Xe" in name:
        return "Iris Xe"
    if "Iris Plus" in name:
        return "Iris Plus"
    if "UHD" in name and "Intel" in name:
        return "Intel UHD"

    # === AMD APU (integrated) ===
    if "780M" in name:
        return "Radeon 780M"
    if "760M" in name:
        return "Radeon 760M"
    if "680M" in name:
        return "Radeon 680M"
    if "Vega" in name:
        return "Radeon Vega"

    # Fallback
    clean = name.split("(")[0].strip()
    return clean[:30] if len(clean) > 30 else clean


def short_cpu(name: str) -> str:
    """Shorten CPU name for consistent storage."""
    if not name:
        return "Unknown"
    # AMD Ryzen: "AMD Ryzen 7 9800X3D 8-Core Processor" -> "Ryzen 7 9800X3D"
    m = re.search(r'Ryzen\s*(\d)\s*(\d{4}X3D|\d{4}X|\d{4})', name, re.I)
    if m:
        return f"Ryzen {m.group(1)} {m.group(2)}"
    # Intel Core: "Intel Core i7-13700K" -> "i7-13700K"
    m = re.search(r'(i[3579]-\d{4,5}\w*)', name, re.I)
    if m:
        return m.group(1)
    # Intel Core Ultra: "Intel Core Ultra 7 155H" -> "Ultra 7 155H"
    m = re.search(r'Ultra\s*(\d)\s*(\d{3}\w*)', name, re.I)
    if m:
        return f"Ultra {m.group(1)} {m.group(2)}"
    # Fallback: truncate to 30 chars
    return name[:30] if len(name) > 30 else name


def short_kernel(kernel: str) -> str:
    """Normalize kernel version - remove distro suffix."""
    if not kernel:
        return "Unknown"
    # "6.18.3-2-MANJARO" -> "6.18.3-2"
    # "6.18.2-cachyos" -> "6.18.2"
    # "6.8.0-51-generic" -> "6.8.0-51"
    match = re.match(r'^(\d+\.\d+\.\d+(?:-\d+)?)', kernel)
    if match:
        return match.group(1)
    return kernel


def short_os(os_name: str) -> str:
    """Normalize OS name - remove desktop environment suffix."""
    if not os_name:
        return "Unknown"
    # "CachyOS Linux (KDE Plasma)" -> "CachyOS Linux"
    # "Fedora Linux 40 (Workstation Edition)" -> "Fedora Linux 40"
    return re.sub(r'\s*\([^)]+\)\s*$', '', os_name).strip()


def normalize_resolution(res: str) -> str:
    """Normalize resolution to pixel format."""
    if not res:
        return "1920x1080"
    mapping = {
        "HD": "1280x720", "FHD": "1920x1080",
        "WQHD": "2560x1440", "UWQHD": "3440x1440", "UHD": "3840x2160"
    }
    return mapping.get(res.upper(), res)
