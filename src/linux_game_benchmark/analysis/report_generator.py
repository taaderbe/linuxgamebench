"""
HTML Report Generator for benchmark results.
Supports multiple resolutions and MULTIPLE SYSTEMS on one page.

Features:
- Tabs for switching between different systems (OS configurations)
- All benchmark data from all systems is displayed
- No data is ever archived or deleted
- Overview page with all games and benchmarks
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# Steam App IDs for header images
STEAM_APP_IDS = {
    "7 Days to Die": 251570,
    "Cities Skylines": 255710,
    "Cyberpunk 2077": 1091500,
    "Path of Exile": 238960,
    "Path of Exile 2": 2694490,
    "Rise of the Tomb Raider": 391220,
    "Shadow of the Tomb Raider": 750920,
    "Metro Exodus": 412020,
    "Factorio": 427520,
}

RESOLUTION_ORDER = ["1920x1080", "2560x1440", "3840x2160"]
RESOLUTION_NAMES = {
    "1920x1080": "FHD",
    "2560x1440": "WQHD",
    "3840x2160": "UHD",
}


def shorten_gpu_name(gpu_full: str) -> str:
    """
    Shorten GPU name for display while keeping it identifiable.
    Supports GPUs from 2015-2025 (NVIDIA, AMD, Intel).
    """
    import re

    if not gpu_full:
        return "Unknown"

    # Clean up common prefixes
    name = gpu_full.replace("Mesa ", "").strip()

    # ===================
    # NVIDIA GPUs (2014-2025)
    # ===================
    if "NVIDIA" in name or "GeForce" in name or "RTX" in name or "GTX" in name:
        # Remove prefixes
        name = name.replace("NVIDIA ", "").replace("GeForce ", "")

        # RTX 5000 Series (2025)
        match = re.search(r'(RTX\s*50\d{2}(?:\s*Ti|\s*SUPER)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RTX 4000 Series (2022-2024)
        match = re.search(r'(RTX\s*40\d{2}(?:\s*Ti|\s*SUPER)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RTX 3000 Series (2020-2022)
        match = re.search(r'(RTX\s*30\d{2}(?:\s*Ti)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RTX 2000 Series (2018-2020)
        match = re.search(r'(RTX\s*20\d{2}(?:\s*Ti|\s*SUPER)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # GTX 1600 Series (2019-2020)
        match = re.search(r'(GTX\s*16\d{2}(?:\s*Ti|\s*SUPER)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # GTX 1000 Series (2016-2018)
        match = re.search(r'(GTX\s*10\d{2}(?:\s*Ti)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # GTX 900 Series (2014-2016)
        match = re.search(r'(GTX\s*9\d{2}(?:\s*Ti)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # GTX 700/600 Series (older)
        match = re.search(r'(GTX\s*[67]\d{2}(?:\s*Ti)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # Fallback for NVIDIA
        if "(" in name:
            return name.split("(")[0].strip()
        return name.strip()

    # ===================
    # AMD GPUs (2015-2025)
    # ===================
    if "AMD" in name or "Radeon" in name or "RX" in name:
        # RX 8000 Series (2025)
        match = re.search(r'(RX\s*8\d{3}(?:\s*XT(?:X)?)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX 7000 Series (2022-2024)
        match = re.search(r'(RX\s*7\d{3}(?:\s*XT(?:X)?)?(?:\s*GRE)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX 6000 Series (2020-2022)
        match = re.search(r'(RX\s*6\d{3}(?:\s*XT(?:S)?)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX 5000 Series (2019-2020)
        match = re.search(r'(RX\s*5\d{3}(?:\s*XT)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX Vega (2017-2019)
        match = re.search(r'((?:RX\s*)?Vega\s*(?:56|64|VII)?)', name, re.IGNORECASE)
        if match:
            result = match.group(1).strip()
            if not result.upper().startswith("VEGA"):
                return result
            return "Vega " + result.split()[-1] if len(result.split()) > 1 else "Vega"

        # RX 500 Series (2017-2019)
        match = re.search(r'(RX\s*5[89]0(?:X)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX 500 Series (lower)
        match = re.search(r'(RX\s*5[67]0(?:X)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # RX 400 Series (2016-2017)
        match = re.search(r'(RX\s*4[678]0(?:X)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # R9/R7 Series (2013-2016)
        match = re.search(r'(R[79]\s*\d{3}(?:X)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # R9 Fury/Nano
        if "Fury" in name:
            if "Nano" in name:
                return "R9 Fury Nano"
            elif "X" in name:
                return "R9 Fury X"
            return "R9 Fury"

        # Generic RX pattern fallback
        match = re.search(r'(RX\s*\d+(?:\s*\w+)?)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("  ", " ")

        # Fallback for AMD
        if "(" in name:
            return name.split("(")[0].strip().replace("AMD ", "").replace("Radeon ", "")
        return name.replace("AMD ", "").replace("Radeon ", "").strip()

    # ===================
    # Intel GPUs (2015-2025)
    # ===================
    if "Intel" in name:
        # Remove common Intel prefixes
        name = name.replace("Intel(R) ", "").replace("Intel ", "")
        name = name.replace("(R)", "").replace("(TM)", "")

        # Intel Arc (2022-2025)
        match = re.search(r'(Arc\s*[AB]\d{3}[M]?)', name, re.IGNORECASE)
        if match:
            return "Arc " + match.group(1).split()[-1].upper()

        # Intel Iris Xe (2020-2024) - with generation info
        if "Iris" in name and "Xe" in name:
            # Try to get generation like TGL, ADL, RPL
            match = re.search(r'\((\w{3})\s*GT\d?\)', name)
            if match:
                gen = match.group(1).upper()
                return f"Iris Xe ({gen})"
            return "Iris Xe"

        # Intel Iris Plus (2016-2020)
        if "Iris Plus" in name or "Iris(R) Plus" in name:
            match = re.search(r'Iris(?:\(R\))?\s*Plus(?:\s*Graphics)?\s*(\d+)?', name)
            if match and match.group(1):
                return f"Iris Plus {match.group(1)}"
            return "Iris Plus"

        # Intel Iris Pro (2013-2015)
        if "Iris Pro" in name:
            match = re.search(r'Iris Pro(?:\s*Graphics)?\s*(\d+)?', name)
            if match and match.group(1):
                return f"Iris Pro {match.group(1)}"
            return "Iris Pro"

        # Intel Iris (generic)
        if "Iris" in name:
            match = re.search(r'Iris(?:\s*Graphics)?\s*(\d+)?', name)
            if match and match.group(1):
                return f"Iris {match.group(1)}"
            return "Iris"

        # Intel UHD Graphics (2018-2024)
        match = re.search(r'UHD(?:\s*Graphics)?\s*(\d+)?', name)
        if match:
            if match.group(1):
                return f"UHD {match.group(1)}"
            return "UHD Graphics"

        # Intel HD Graphics (2010-2020)
        match = re.search(r'HD(?:\s*Graphics)?\s*(\d+)?', name)
        if match:
            if match.group(1):
                return f"HD {match.group(1)}"
            return "HD Graphics"

        # Fallback for Intel
        name = name.replace(" Graphics", "").strip()
        return name if name else "Intel Graphics"

    # Fallback
    if "(" in gpu_full:
        return gpu_full.split("(")[0].strip()
    return gpu_full


def shorten_cpu_name(cpu_full: str) -> str:
    """
    Shorten CPU name for display while keeping it identifiable.
    Supports CPUs from 2015-2025 (Intel, AMD).
    """
    import re

    if not cpu_full:
        return "Unknown"

    # Clean up
    name = cpu_full.strip()

    # ===================
    # AMD CPUs (2017-2025)
    # ===================
    if "AMD" in name or "Ryzen" in name or "Threadripper" in name or "EPYC" in name:
        # Threadripper (2017-2024)
        match = re.search(r'Threadripper(?:\s*PRO)?\s*(\d{4}\w*)', name, re.IGNORECASE)
        if match:
            if "PRO" in name.upper():
                return f"TR PRO {match.group(1)}"
            return f"TR {match.group(1)}"

        # Ryzen 9000 Series (2024-2025)
        match = re.search(r'Ryzen\s*(\d)\s*(9[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 8000 Series (2024)
        match = re.search(r'Ryzen\s*(\d)\s*(8[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 7000 Series (2022-2024)
        match = re.search(r'Ryzen\s*(\d)\s*(7[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 6000 Series (2022 - mobile)
        match = re.search(r'Ryzen\s*(\d)\s*(6[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 5000 Series (2020-2022)
        match = re.search(r'Ryzen\s*(\d)\s*(5[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 4000 Series (2020 - APUs)
        match = re.search(r'Ryzen\s*(\d)\s*(4[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 3000 Series (2019-2020)
        match = re.search(r'Ryzen\s*(\d)\s*(3[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 2000 Series (2018-2019)
        match = re.search(r'Ryzen\s*(\d)\s*(2[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Ryzen 1000 Series (2017-2018)
        match = re.search(r'Ryzen\s*(\d)\s*(1[0-9]{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ryzen {match.group(1)} {match.group(2)}"

        # Generic Ryzen pattern
        match = re.search(r'(Ryzen\s*\d\s*\w+)', name, re.IGNORECASE)
        if match:
            result = match.group(1)
            # Clean up extra stuff
            result = re.sub(r'\s*\d+-Core.*', '', result)
            result = re.sub(r'\s*with.*', '', result, flags=re.IGNORECASE)
            return result.strip()

        # AMD FX Series (2011-2017)
        match = re.search(r'(FX-\d{4}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        # AMD A-Series APUs (2011-2018)
        match = re.search(r'(A\d{1,2}-\d{4}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        # AMD Athlon (2018-2020)
        match = re.search(r'Athlon\s*(\w*\s*\d+\w*)', name, re.IGNORECASE)
        if match:
            return f"Athlon {match.group(1).strip()}"

        # Fallback for AMD
        name = name.replace("AMD ", "")
        name = re.sub(r'\s*\d+-Core\s*Processor', '', name)
        name = re.sub(r'\s*with\s+Radeon.*', '', name, flags=re.IGNORECASE)
        return name.strip()

    # ===================
    # Intel CPUs (2015-2025)
    # ===================
    if "Intel" in name:
        # Clean up Intel prefixes
        name = name.replace("Intel(R) ", "").replace("Intel ", "")
        name = name.replace("Core(TM) ", "Core ").replace("(R)", "").replace("(TM)", "")

        # Core Ultra (2024-2025)
        match = re.search(r'Core\s*Ultra\s*(\d)\s*(\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ultra {match.group(1)} {match.group(2)}"

        # Alternative Core Ultra pattern
        match = re.search(r'Ultra\s*(\d)\s*(\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return f"Ultra {match.group(1)} {match.group(2)}"

        # 14th Gen (2023-2024) - i3/i5/i7/i9-14xxx
        match = re.search(r'(i[3579]-14\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 13th Gen (2022-2023) - i3/i5/i7/i9-13xxx
        match = re.search(r'(i[3579]-13\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 12th Gen (2021-2022) - i3/i5/i7/i9-12xxx
        match = re.search(r'(i[3579]-12\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 11th Gen (2021) - i3/i5/i7/i9-11xxx
        match = re.search(r'(i[3579]-11\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 10th Gen (2020) - i3/i5/i7/i9-10xxx
        match = re.search(r'(i[3579]-10\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 9th Gen (2018-2019) - i3/i5/i7/i9-9xxx
        match = re.search(r'(i[3579]-9\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 8th Gen (2017-2018) - i3/i5/i7-8xxx
        match = re.search(r'(i[357]-8\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 7th Gen (2017) - i3/i5/i7-7xxx
        match = re.search(r'(i[357]-7\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 6th Gen (2015-2016) - i3/i5/i7-6xxx
        match = re.search(r'(i[357]-6\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # 5th Gen and older (2015) - i3/i5/i7-5xxx, 4xxx, 3xxx, 2xxx
        match = re.search(r'(i[357]-[2345]\d{3}\w*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Mobile CPUs with U/H/HK/HX suffix (11th Gen mobile like i5-1135G7)
        match = re.search(r'(i[3579]-1[0-4]\d{2}[A-Z]\d*)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Intel Xeon
        match = re.search(r'Xeon\s*(\w*\s*[\w-]+)', name, re.IGNORECASE)
        if match:
            return f"Xeon {match.group(1).strip()}"

        # Intel Pentium (2015-2022)
        match = re.search(r'Pentium\s*(\w*\s*\w+)', name, re.IGNORECASE)
        if match:
            return f"Pentium {match.group(1).strip()}"

        # Intel Celeron
        match = re.search(r'Celeron\s*(\w*\s*\w+)', name, re.IGNORECASE)
        if match:
            return f"Celeron {match.group(1).strip()}"

        # Intel N-Series (2023+)
        match = re.search(r'(N\d{3})', name)
        if match:
            return f"Intel {match.group(1)}"

        # Fallback - try to extract i-series pattern
        match = re.search(r'(i[3579]-\w+)', name)
        if match:
            return match.group(1)

        # Remove frequency and clean up
        name = re.sub(r'\s*@\s*[\d.]+\s*GHz', '', name)
        name = re.sub(r'^\d+th Gen\s*', '', name)
        name = re.sub(r'\s*CPU\s*', ' ', name)
        return name.strip()

    # Fallback
    return cpu_full


def generate_multi_resolution_report(
    game_name: str,
    app_id: int,
    system_info: dict,
    resolution_data: dict[str, dict],  # resolution -> aggregated metrics
    output_path: Path,
    runs_data: Optional[dict[str, list[dict]]] = None,  # resolution -> list of runs
) -> Path:
    """
    Generate an HTML report with multiple resolutions.

    Args:
        game_name: Name of the game
        app_id: Steam App ID
        system_info: System information dictionary
        resolution_data: Dict mapping resolution to aggregated metrics
        output_path: Where to save the report

    Returns:
        Path to the generated report
    """
    # Get system info
    gpu_info = system_info.get("gpu", {})
    cpu_info = system_info.get("cpu", {})
    os_info = system_info.get("os", {})

    gpu_name = shorten_gpu_name(gpu_info.get("model", "Unknown GPU"))

    cpu_name = cpu_info.get("model", "Unknown CPU")
    if "9800X3D" in cpu_name:
        cpu_name = "Ryzen 7 9800X3D"
    elif "Ryzen" in cpu_name:
        cpu_name = cpu_name.replace("AMD ", "").split(" 8-Core")[0]

    ram_gb = system_info.get("ram", {}).get("total_gb", 0)
    os_name = os_info.get("name", "Linux")
    kernel = os_info.get("kernel", "").split("-")[0]
    mesa = gpu_info.get("driver_version", "")
    vulkan = gpu_info.get("vulkan_version", "")

    date_str = datetime.now().strftime("%d.%m.%Y")

    # Prepare runs data for charts
    runs_data = runs_data or {}

    # Generate resolution cards
    resolution_cards = ""
    for resolution in RESOLUTION_ORDER:
        if resolution not in resolution_data:
            continue

        metrics = resolution_data[resolution]
        fps = metrics.get("fps", {})
        stutter = metrics.get("stutter", {})
        hw = metrics.get("hardware", {})

        res_name = RESOLUTION_NAMES.get(resolution, resolution)
        res_display = resolution.replace("x", "×")
        run_count = fps.get("run_count", 1)

        # Calculate target recommendation
        low1 = fps.get("1_percent_low", 0)
        recommended_hz = 60
        for target in [165, 144, 120, 60]:
            if low1 >= target * 0.85:
                recommended_hz = target
                break

        # Stutter rating
        stutter_rating = stutter.get("stutter_rating", "unknown")
        gameplay_stutter = stutter.get("gameplay_stutter_count", 0)

        # Frame pacing/consistency rating
        frame_pacing = metrics.get("frame_pacing", {})
        consistency_rating = frame_pacing.get("consistency_rating", "unknown")

        # Check if we have detailed run data for this resolution
        has_details = resolution in runs_data and any(
            run.get('frametimes') for run in runs_data[resolution]
        )

        details_button = ""
        if has_details:
            details_button = f'''
                <button class="details-btn" onclick="toggleDetails('{resolution}')">
                    📊 Runs anzeigen
                </button>'''

        resolution_cards += f'''
        <div class="resolution-card" id="card-{resolution}">
            <div class="res-header">
                <span class="res-name">{res_name}</span>
                <span class="res-detail">{res_display}</span>
                <span class="run-count">{run_count} Run{'s' if run_count > 1 else ''}</span>
                {details_button}
            </div>
            <div class="res-stats">
                <div class="stat-main">
                    <span class="stat-value">{fps.get('average', 0):.0f}</span>
                    <span class="stat-label">AVG FPS</span>
                </div>
                <div class="stat">
                    <span class="stat-value">{fps.get('1_percent_low', 0):.0f}</span>
                    <span class="stat-label">1% Low</span>
                </div>
                <div class="stat">
                    <span class="stat-value">{fps.get('0.1_percent_low', 0):.0f}</span>
                    <span class="stat-label">0.1% Low</span>
                </div>
                <div class="stat">
                    <span class="stat-value stutter-{stutter_rating}">{stutter_rating.capitalize()}</span>
                    <span class="stat-label">Stutter</span>
                </div>
                <div class="stat">
                    <span class="stat-value consistency-{consistency_rating}">{consistency_rating.capitalize()}</span>
                    <span class="stat-label">Consistency</span>
                </div>
                <div class="stat">
                    <span class="stat-value recommend">{recommended_hz} Hz</span>
                    <span class="stat-label">Recommended</span>
                </div>
            </div>
            <div class="chart-container" id="details-{resolution}" style="display: none;">
                <div class="chart-controls">
                    <label>Select run:</label>
                    <select id="run-select-{resolution}" onchange="updateChart('{resolution}')">
                    </select>
                </div>
                <canvas id="chart-{resolution}"></canvas>
            </div>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Benchmark - {game_name}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --card-alt: #2d2f5a;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 40px 20px;
        }}

        .container {{ max-width: 1100px; margin: 0 auto; }}

        header {{ text-align: center; margin-bottom: 40px; }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 8px; }}
        header .info {{ color: var(--text-muted); font-size: 1rem; }}

        /* Resolution Cards */
        .resolution-grid {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 30px;
        }}

        .resolution-card {{
            background: var(--card);
            border-radius: 20px;
            padding: 25px 30px;
        }}

        .res-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        .res-name {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--blue);
        }}

        .res-detail {{
            font-size: 1rem;
            color: var(--text-muted);
        }}

        .run-count {{
            margin-left: auto;
            background: rgba(255,255,255,0.1);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .res-stats {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}

        .stat {{
            text-align: center;
            min-width: 80px;
        }}

        .stat-main {{
            text-align: center;
            min-width: 100px;
            padding-right: 20px;
            border-right: 1px solid rgba(255,255,255,0.1);
            margin-right: 10px;
        }}

        .stat-main .stat-value {{
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--green);
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            display: block;
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 5px;
            display: block;
        }}

        .stutter-excellent, .stutter-good, .consistency-excellent, .consistency-good {{ color: var(--green); }}
        .stutter-moderate, .consistency-moderate {{ color: var(--yellow); }}
        .stutter-poor, .consistency-poor {{ color: var(--red); }}

        .recommend {{ color: var(--blue); }}

        /* System Card */
        .system-card {{
            background: var(--card);
            border-radius: 20px;
            padding: 25px 30px;
        }}

        .system-card h2 {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 18px;
        }}

        .sys-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px 30px;
        }}

        .sys-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.95rem;
        }}

        .sys-item .lbl {{ color: var(--text-muted); }}
        .sys-item .val {{ font-weight: 600; }}

        /* Chart Details */
        .details-btn {{
            margin-left: auto;
            background: var(--blue);
            color: var(--bg);
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .details-btn:hover {{
            background: #6DD5FA;
            transform: translateY(-2px);
        }}

        .chart-container {{
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}

        .chart-controls {{
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 20px;
        }}

        .chart-controls label {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .chart-controls select {{
            background: var(--card-alt);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9rem;
            cursor: pointer;
        }}

        .chart-controls select:hover {{
            border-color: var(--blue);
        }}

        canvas {{
            max-height: 400px;
        }}

        footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        @media (max-width: 700px) {{
            .res-stats {{
                gap: 20px;
            }}
            .stat-main {{
                border-right: none;
                margin-right: 0;
                padding-right: 0;
                width: 100%;
                margin-bottom: 10px;
            }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        // Store charts and data
        const charts = {{}};
        const runsData = {json.dumps(runs_data)};

        function toggleDetails(resolution) {{
            const details = document.getElementById('details-' + resolution);
            const btn = event.target;

            if (details.style.display === 'none') {{
                details.style.display = 'block';
                btn.textContent = '📊 Runs verbergen';

                // Initialize chart if not done yet
                if (!charts[resolution]) {{
                    initChart(resolution);
                }}
            }} else {{
                details.style.display = 'none';
                btn.textContent = '📊 Runs anzeigen';
            }}
        }}

        function initChart(resolution) {{
            const runs = runsData[resolution] || [];
            const select = document.getElementById('run-select-' + resolution);

            // Create array with original indices and sort by timestamp (newest first)
            const sortedRuns = runs.map((run, idx) => ({{ run, originalIdx: idx }}))
                .sort((a, b) => new Date(b.run.timestamp) - new Date(a.run.timestamp));

            // Populate select options
            select.innerHTML = '';
            sortedRuns.forEach((item, sortedIdx) => {{
                const run = item.run;
                const option = document.createElement('option');
                option.value = item.originalIdx;
                const timestamp = new Date(run.timestamp).toLocaleString('de-DE');
                const avgFps = run.metrics?.fps?.average || 0;
                option.textContent = `${{avgFps.toFixed(0)}} FPS avg (${{timestamp}})`;
                // Select the newest run (first in sorted list)
                if (sortedIdx === 0) {{
                    option.selected = true;
                }}
                select.appendChild(option);
            }});

            // Create chart
            updateChart(resolution);
        }}

        function updateChart(resolution) {{
            const select = document.getElementById('run-select-' + resolution);
            const runIndex = parseInt(select.value);
            const runs = runsData[resolution] || [];
            const run = runs[runIndex];

            if (!run || !run.frametimes) return;

            const ctx = document.getElementById('chart-' + resolution);

            // Destroy existing chart
            if (charts[resolution]) {{
                charts[resolution].destroy();
            }}

            // Convert frametimes to FPS
            const frametimes = run.frametimes;
            const fps = frametimes.map(ft => 1000.0 / ft);
            const labels = frametimes.map((_, i) => (i * 10 / 60).toFixed(1)); // Time in seconds (sampled every 10 frames)

            // Create new chart
            charts[resolution] = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'FPS',
                        data: fps,
                        borderColor: '#4fc3f7',
                        backgroundColor: 'rgba(79, 195, 247, 0.1)',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0,
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: false
                        }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false,
                            callbacks: {{
                                title: function(context) {{
                                    return 'Zeit: ' + context[0].label + 's';
                                }},
                                label: function(context) {{
                                    return 'FPS: ' + context.parsed.y.toFixed(1);
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: 'Zeit (Sekunden)',
                                color: '#a0a0a0'
                            }},
                            ticks: {{
                                color: '#a0a0a0',
                                maxTicksLimit: 10
                            }},
                            grid: {{
                                color: 'rgba(255, 255, 255, 0.1)'
                            }}
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: 'FPS',
                                color: '#a0a0a0'
                            }},
                            ticks: {{
                                color: '#a0a0a0'
                            }},
                            grid: {{
                                color: 'rgba(255, 255, 255, 0.1)'
                            }}
                        }}
                    }}
                }}
            }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <header>
            <img src="https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"
                 alt="{game_name}"
                 style="width: 100%; max-width: 460px; border-radius: 12px; margin-bottom: 20px;"
                 onerror="this.style.display='none'">
            <h1>{game_name}</h1>
            <p class="info">{date_str} &bull; {len(resolution_data)} Resolution{'s' if len(resolution_data) > 1 else ''}</p>
        </header>

        <div class="resolution-grid">
{resolution_cards}
        </div>

        <div class="system-card">
            <h2>System</h2>
            <div class="sys-grid">
                <div class="sys-item">
                    <span class="lbl">GPU</span>
                    <span class="val">{gpu_name}</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">CPU</span>
                    <span class="val">{cpu_name}</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">RAM</span>
                    <span class="val">{ram_gb:.0f} GB</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">OS</span>
                    <span class="val">{os_name}</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">Mesa</span>
                    <span class="val">{mesa}</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">Vulkan</span>
                    <span class="val">{vulkan}</span>
                </div>
                <div class="sys-item">
                    <span class="lbl">Kernel</span>
                    <span class="val">{kernel}</span>
                </div>
            </div>
        </div>

        <footer>
            Linux Game Benchmark &bull; MangoHud v0.8.2
        </footer>
    </div>
</body>
</html>
'''

    output_path.write_text(html)
    return output_path


def generate_filterable_report(
    game_name: str,
    app_id: Optional[int],
    systems_data: dict[str, dict],
    output_path: Path,
) -> Path:
    """
    Generate an HTML report with filter dropdowns for GPU, Kernel, OS, Mesa.

    Features:
    - Filter dropdowns for each attribute
    - All benchmarks shown as cards
    - Compare mode for side-by-side comparison
    """
    date_str = datetime.now().strftime("%d.%m.%Y")

    # Collect all unique values for filters and build benchmark cards data
    all_gpus = set()
    all_kernels = set()
    all_oses = set()
    all_mesas = set()
    all_resolutions = set()

    benchmarks = []  # List of all benchmark entries

    for system_id, data in systems_data.items():
        system_info = data.get("system_info", {}) or {}
        resolutions = data.get("resolutions", {})

        gpu_info = system_info.get("gpu", {})
        os_info = system_info.get("os", {})

        # Extract values
        gpu = shorten_gpu_name(gpu_info.get("model", "Unknown"))

        os_name = os_info.get("name", system_id.split("_")[0] if "_" in system_id else "Unknown")
        kernel_full = os_info.get("kernel", "Unknown")
        kernel = kernel_full.split("-")[0] if kernel_full else "Unknown"
        mesa = gpu_info.get("driver_version", "Unknown")

        all_gpus.add(gpu)
        all_kernels.add(kernel)
        all_oses.add(os_name)
        all_mesas.add(mesa)

        # Process each resolution
        for resolution, runs in resolutions.items():
            res_name = RESOLUTION_NAMES.get(resolution, resolution)
            all_resolutions.add(res_name)

            # Aggregate runs
            fps_keys = ["average", "1_percent_low", "0.1_percent_low"]
            fps_sums = {key: 0.0 for key in fps_keys}
            for run in runs:
                fps = run.get("metrics", {}).get("fps", {})
                for key in fps_keys:
                    fps_sums[key] += fps.get(key, 0)
            n = len(runs)
            fps_avg = {key: fps_sums[key] / n for key in fps_keys}

            last_metrics = runs[-1].get("metrics", {}) if runs else {}
            stutter = last_metrics.get("stutter", {})
            stutter_rating = stutter.get("stutter_rating", "unknown")

            # Calculate recommended Hz
            low1 = fps_avg.get("1_percent_low", 0)
            recommended_hz = 60
            for target in [165, 144, 120, 60]:
                if low1 >= target * 0.85:
                    recommended_hz = target
                    break

            benchmarks.append({
                "id": f"{system_id}_{resolution}",
                "system_id": system_id,
                "resolution": res_name,
                "resolution_raw": resolution,
                "os": os_name,
                "kernel": kernel,
                "gpu": gpu,
                "mesa": mesa,
                "avg_fps": round(fps_avg.get("average", 0), 1),
                "low1": round(fps_avg.get("1_percent_low", 0), 1),
                "low01": round(fps_avg.get("0.1_percent_low", 0), 1),
                "stutter": stutter_rating,
                "recommended_hz": recommended_hz,
                "run_count": n,
                "runs": runs,
            })

    # Sort benchmarks by resolution (UHD first), then by FPS
    res_order = {"UHD": 0, "WQHD": 1, "FHD": 2}
    benchmarks.sort(key=lambda x: (res_order.get(x["resolution"], 99), -x["avg_fps"]))

    app_id_safe = app_id if app_id else 0

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Benchmark - {game_name}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --card-hover: #2d2f5a;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
            --purple: #b388ff;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 30px 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}

        header {{ text-align: center; margin-bottom: 25px; }}
        header h1 {{ font-size: 2.2rem; margin-bottom: 5px; }}
        header .info {{ color: var(--text-muted); }}

        /* Filter Bar */
        .filter-bar {{
            background: var(--card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 25px;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            align-items: center;
        }}
        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}
        .filter-group label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .filter-group select {{
            background: var(--bg);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
            min-width: 140px;
        }}
        .filter-group select:hover {{
            border-color: var(--blue);
        }}
        .reset-btn {{
            background: transparent;
            color: var(--text-muted);
            border: 1px solid var(--text-muted);
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            margin-left: auto;
            transition: all 0.2s;
        }}
        .reset-btn:hover {{
            color: var(--text);
            border-color: var(--text);
        }}
        .compare-btn {{
            background: var(--purple);
            color: var(--bg);
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.2s;
        }}
        .compare-btn:hover {{
            opacity: 0.9;
        }}
        .compare-btn.active {{
            background: var(--green);
        }}

        /* Results count */
        .results-info {{
            color: var(--text-muted);
            margin-bottom: 15px;
            font-size: 0.9rem;
        }}

        /* Benchmark Cards */
        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }}
        .benchmark-card {{
            background: var(--card);
            border-radius: 16px;
            padding: 20px;
            transition: all 0.2s;
            border: 2px solid transparent;
            cursor: default;
        }}
        .benchmark-card:hover {{
            background: var(--card-hover);
        }}
        .benchmark-card.selected {{
            border-color: var(--purple);
        }}
        .benchmark-card.hidden {{
            display: none;
        }}
        .card-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .res-badge {{
            background: var(--blue);
            color: var(--bg);
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.9rem;
        }}
        .card-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            flex: 1;
        }}
        .tag {{
            background: rgba(255,255,255,0.1);
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .card-stats {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            text-align: center;
        }}
        .stat {{
            padding: 10px 5px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
        }}
        .stat-value {{
            font-size: 1.4rem;
            font-weight: 700;
            display: block;
        }}
        .stat-value.fps {{ color: var(--green); }}
        .stat-label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-top: 3px;
            display: block;
        }}
        .stutter-excellent, .stutter-good {{ color: var(--green); }}
        .stutter-moderate {{ color: var(--yellow); }}
        .stutter-poor {{ color: var(--red); }}
        .stutter-unknown {{ color: var(--text-muted); }}

        /* Compare Modal */
        .compare-modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .compare-modal.show {{
            display: flex;
        }}
        .compare-content {{
            background: var(--bg);
            border-radius: 20px;
            padding: 30px;
            max-width: 900px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
        }}
        .compare-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }}
        .compare-header h2 {{ font-size: 1.5rem; }}
        .close-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.5rem;
            cursor: pointer;
        }}
        .compare-grid {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 20px;
            align-items: start;
        }}
        .compare-card {{
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
        }}
        .compare-card h3 {{
            color: var(--blue);
            margin-bottom: 15px;
            font-size: 1.1rem;
        }}
        .compare-card .detail {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .compare-card .detail .lbl {{ color: var(--text-muted); }}
        .compare-card .detail .val {{ font-weight: 600; }}
        .compare-diff {{
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding-top: 40px;
        }}
        .diff-item {{
            text-align: center;
            padding: 8px;
        }}
        .diff-value {{
            font-weight: 700;
            font-size: 1.1rem;
        }}
        .diff-value.positive {{ color: var(--green); }}
        .diff-value.negative {{ color: var(--red); }}
        .diff-value.neutral {{ color: var(--text-muted); }}

        footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
            font-size: 0.85rem;
        }}

        @media (max-width: 700px) {{
            .filter-bar {{ flex-direction: column; align-items: stretch; }}
            .reset-btn, .compare-btn {{ margin-left: 0; width: 100%; }}
            .cards-grid {{ grid-template-columns: 1fr; }}
            .card-stats {{ grid-template-columns: repeat(2, 1fr); }}
            .compare-grid {{ grid-template-columns: 1fr; }}
            .compare-diff {{ flex-direction: row; padding-top: 0; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <img src="https://steamcdn-a.akamaihd.net/steam/apps/{app_id_safe}/header.jpg"
                 alt="{game_name}"
                 style="width: 100%; max-width: 400px; border-radius: 12px; margin-bottom: 15px;"
                 onerror="this.style.display='none'">
            <h1>{game_name}</h1>
            <p class="info">{date_str}</p>
        </header>

        <div class="filter-bar">
            <div class="filter-group">
                <label>Resolution</label>
                <select id="filter-res" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{r}">{r}</option>' for r in sorted(all_resolutions, key=lambda x: res_order.get(x, 99)))}
                </select>
            </div>
            <div class="filter-group">
                <label>CPU</label>
                <select id="filter-cpu" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{c}">{c}</option>' for c in sorted(all_cpus))}
                </select>
            </div>
            <div class="filter-group">
                <label>GPU</label>
                <select id="filter-gpu" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{g}">{g}</option>' for g in sorted(all_gpus))}
                </select>
            </div>
            <div class="filter-group">
                <label>OS</label>
                <select id="filter-os" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{o}">{o}</option>' for o in sorted(all_oses))}
                </select>
            </div>
            <div class="filter-group">
                <label>Kernel</label>
                <select id="filter-kernel" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{k}">{k}</option>' for k in sorted(all_kernels))}
                </select>
            </div>
            <div class="filter-group">
                <label>Mesa</label>
                <select id="filter-mesa" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{m}">{m}</option>' for m in sorted(all_mesas))}
                </select>
            </div>
            <button class="reset-btn" onclick="resetFilters()">Reset</button>
            <button class="compare-btn" id="compare-btn" onclick="toggleCompareMode()">Compare</button>
        </div>

        <div class="results-info">
            <span id="results-count">{len(benchmarks)}</span> results
        </div>

        <div class="cards-grid" id="cards-grid">
'''

    # Generate benchmark cards
    for b in benchmarks:
        html += f'''
            <div class="benchmark-card"
                 data-res="{b['resolution']}"
                 data-gpu="{b['gpu']}"
                 data-os="{b['os']}"
                 data-kernel="{b['kernel']}"
                 data-mesa="{b['mesa']}"
                 data-id="{b['id']}"
                 data-avg="{b['avg_fps']}"
                 data-low1="{b['low1']}"
                 data-low01="{b['low01']}"
                 onclick="toggleSelect(this)">
                <div class="card-header">
                    <span class="res-badge">{b['resolution']}</span>
                    <div class="card-tags">
                        <span class="tag">{b['os']}</span>
                        <span class="tag">{b['kernel']}</span>
                        <span class="tag">{b['gpu']}</span>
                    </div>
                </div>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-value fps">{b['avg_fps']:.0f}</span>
                        <span class="stat-label">AVG FPS</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">{b['low1']:.0f}</span>
                        <span class="stat-label">1% Low</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">{b['low01']:.0f}</span>
                        <span class="stat-label">0.1% Low</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value stutter-{b['stutter']}">{b['stutter'].capitalize()}</span>
                        <span class="stat-label">Stutter</span>
                    </div>
                </div>
            </div>
'''

    html += '''
        </div>

        <!-- Compare Modal -->
        <div class="compare-modal" id="compare-modal">
            <div class="compare-content">
                <div class="compare-header">
                    <h2>Comparison</h2>
                    <button class="close-btn" onclick="closeCompare()">&times;</button>
                </div>
                <div class="compare-grid" id="compare-grid">
                    <!-- Filled by JS -->
                </div>
            </div>
        </div>

        <footer>
            Linux Game Benchmark &bull; Filter & Compare
        </footer>
    </div>

    <script>
        let compareMode = false;
        let selectedCards = [];

        function applyFilters() {
            const res = document.getElementById('filter-res').value;
            const gpu = document.getElementById('filter-gpu').value;
            const os = document.getElementById('filter-os').value;
            const kernel = document.getElementById('filter-kernel').value;
            const mesa = document.getElementById('filter-mesa').value;

            let visibleCount = 0;
            document.querySelectorAll('.benchmark-card').forEach(card => {
                const matchRes = !res || card.dataset.res === res;
                const matchGpu = !gpu || card.dataset.gpu === gpu;
                const matchOs = !os || card.dataset.os === os;
                const matchKernel = !kernel || card.dataset.kernel === kernel;
                const matchMesa = !mesa || card.dataset.mesa === mesa;

                if (matchRes && matchGpu && matchOs && matchKernel && matchMesa) {
                    card.classList.remove('hidden');
                    visibleCount++;
                } else {
                    card.classList.add('hidden');
                }
            });

            document.getElementById('results-count').textContent = visibleCount;
        }

        function resetFilters() {
            document.getElementById('filter-res').value = '';
            document.getElementById('filter-gpu').value = '';
            document.getElementById('filter-os').value = '';
            document.getElementById('filter-kernel').value = '';
            document.getElementById('filter-mesa').value = '';
            applyFilters();
        }

        function toggleCompareMode() {
            compareMode = !compareMode;
            const btn = document.getElementById('compare-btn');

            if (compareMode) {
                btn.classList.add('active');
                btn.textContent = 'Select (0/2)';
                selectedCards = [];
                document.querySelectorAll('.benchmark-card').forEach(c => c.classList.remove('selected'));
            } else {
                btn.classList.remove('active');
                btn.textContent = 'Compare';
                selectedCards = [];
                document.querySelectorAll('.benchmark-card').forEach(c => c.classList.remove('selected'));
            }
        }

        function toggleSelect(card) {
            if (!compareMode) return;

            const id = card.dataset.id;
            const idx = selectedCards.findIndex(c => c.id === id);

            if (idx >= 0) {
                selectedCards.splice(idx, 1);
                card.classList.remove('selected');
            } else if (selectedCards.length < 2) {
                selectedCards.push({
                    id: id,
                    res: card.dataset.res,
                    gpu: card.dataset.gpu,
                    os: card.dataset.os,
                    kernel: card.dataset.kernel,
                    mesa: card.dataset.mesa,
                    avg: parseFloat(card.dataset.avg),
                    low1: parseFloat(card.dataset.low1),
                    low01: parseFloat(card.dataset.low01),
                });
                card.classList.add('selected');
            }

            document.getElementById('compare-btn').textContent = `Select (${selectedCards.length}/2)`;

            if (selectedCards.length === 2) {
                showCompare();
            }
        }

        function showCompare() {
            const a = selectedCards[0];
            const b = selectedCards[1];

            const diffAvg = b.avg - a.avg;
            const diffLow1 = b.low1 - a.low1;
            const diffLow01 = b.low01 - a.low01;

            const formatDiff = (val) => {
                if (val > 0) return `<span class="diff-value positive">+${val.toFixed(0)}</span>`;
                if (val < 0) return `<span class="diff-value negative">${val.toFixed(0)}</span>`;
                return `<span class="diff-value neutral">0</span>`;
            };

            document.getElementById('compare-grid').innerHTML = `
                <div class="compare-card">
                    <h3>${a.res} - ${a.os}</h3>
                    <div class="detail"><span class="lbl">GPU</span><span class="val">${a.gpu}</span></div>
                    <div class="detail"><span class="lbl">Kernel</span><span class="val">${a.kernel}</span></div>
                    <div class="detail"><span class="lbl">Mesa</span><span class="val">${a.mesa}</span></div>
                    <div class="detail"><span class="lbl">AVG FPS</span><span class="val" style="color: var(--green)">${a.avg.toFixed(0)}</span></div>
                    <div class="detail"><span class="lbl">1% Low</span><span class="val">${a.low1.toFixed(0)}</span></div>
                    <div class="detail"><span class="lbl">0.1% Low</span><span class="val">${a.low01.toFixed(0)}</span></div>
                </div>
                <div class="compare-diff">
                    <div class="diff-item">
                        <div class="diff-label" style="font-size: 0.7rem; color: var(--text-muted);">AVG</div>
                        ${formatDiff(diffAvg)}
                    </div>
                    <div class="diff-item">
                        <div class="diff-label" style="font-size: 0.7rem; color: var(--text-muted);">1%</div>
                        ${formatDiff(diffLow1)}
                    </div>
                    <div class="diff-item">
                        <div class="diff-label" style="font-size: 0.7rem; color: var(--text-muted);">0.1%</div>
                        ${formatDiff(diffLow01)}
                    </div>
                </div>
                <div class="compare-card">
                    <h3>${b.res} - ${b.os}</h3>
                    <div class="detail"><span class="lbl">GPU</span><span class="val">${b.gpu}</span></div>
                    <div class="detail"><span class="lbl">Kernel</span><span class="val">${b.kernel}</span></div>
                    <div class="detail"><span class="lbl">Mesa</span><span class="val">${b.mesa}</span></div>
                    <div class="detail"><span class="lbl">AVG FPS</span><span class="val" style="color: var(--green)">${b.avg.toFixed(0)}</span></div>
                    <div class="detail"><span class="lbl">1% Low</span><span class="val">${b.low1.toFixed(0)}</span></div>
                    <div class="detail"><span class="lbl">0.1% Low</span><span class="val">${b.low01.toFixed(0)}</span></div>
                </div>
            `;

            document.getElementById('compare-modal').classList.add('show');
        }

        function closeCompare() {
            document.getElementById('compare-modal').classList.remove('show');
            toggleCompareMode();
        }

        // Close modal on outside click
        document.getElementById('compare-modal').addEventListener('click', function(e) {
            if (e.target === this) closeCompare();
        });
    </script>
</body>
</html>
'''

    output_path.write_text(html)
    return output_path


def generate_multi_system_report(
    game_name: str,
    app_id: Optional[int],
    systems_data: dict[str, dict],  # system_id -> {"system_info": {...}, "resolutions": {...}}
    output_path: Path,
) -> Path:
    """
    Generate an HTML report with multiple systems (OS configurations).

    Args:
        game_name: Name of the game
        app_id: Steam App ID (optional)
        systems_data: Dict mapping system_id to system data
        output_path: Where to save the report

    Returns:
        Path to the generated report
    """
    date_str = datetime.now().strftime("%d.%m.%Y")

    # Generate system tabs
    system_tabs = ""
    system_contents = ""

    for idx, (system_id, data) in enumerate(sorted(systems_data.items())):
        system_info = data.get("system_info", {})
        fingerprint = data.get("fingerprint", {})
        resolutions = data.get("resolutions", {})

        # Extract system name from system_id (e.g., "CachyOS_abc123" -> "CachyOS")
        os_name = system_id.split("_")[0] if "_" in system_id else system_id
        if os_name == "legacy":
            os_name = system_info.get("os", {}).get("name", "Legacy")

        # Get detailed info
        gpu_info = system_info.get("gpu", {}) if system_info else {}
        cpu_info = system_info.get("cpu", {}) if system_info else {}
        os_info = system_info.get("os", {}) if system_info else {}

        gpu_name = shorten_gpu_name(gpu_info.get("model", "Unknown GPU"))

        cpu_name = cpu_info.get("model", "Unknown CPU")
        if "9800X3D" in cpu_name:
            cpu_name = "Ryzen 7 9800X3D"
        elif "Ryzen" in cpu_name:
            cpu_name = cpu_name.replace("AMD ", "").split(" 8-Core")[0]

        ram_gb = system_info.get("ram", {}).get("total_gb", 0) if system_info else 0
        kernel = os_info.get("kernel", "").split("-")[0] if os_info else ""
        mesa = gpu_info.get("driver_version", "")
        vulkan = gpu_info.get("vulkan_version", "")

        active_class = "active" if idx == 0 else ""

        # Create tab button
        system_tabs += f'''
            <button class="system-tab {active_class}" onclick="showSystem('{system_id}')" data-system="{system_id}">
                {os_name}
            </button>'''

        # Create resolution cards for this system
        resolution_cards = ""
        for resolution in RESOLUTION_ORDER:
            if resolution not in resolutions:
                continue

            runs = resolutions[resolution]
            # Aggregate runs
            fps_keys = ["average", "minimum", "maximum", "1_percent_low", "0.1_percent_low"]
            fps_sums = {key: 0.0 for key in fps_keys}
            for run in runs:
                fps = run.get("metrics", {}).get("fps", {})
                for key in fps_keys:
                    fps_sums[key] += fps.get(key, 0)
            n = len(runs)
            fps = {key: fps_sums[key] / n for key in fps_keys}
            fps["run_count"] = n

            # Get stutter from last run
            last_metrics = runs[-1].get("metrics", {}) if runs else {}
            stutter = last_metrics.get("stutter", {})
            frame_pacing = last_metrics.get("frame_pacing", {})

            res_name = RESOLUTION_NAMES.get(resolution, resolution)
            res_display = resolution.replace("x", "×")
            run_count = n

            # Calculate target recommendation
            low1 = fps.get("1_percent_low", 0)
            recommended_hz = 60
            for target in [165, 144, 120, 60]:
                if low1 >= target * 0.85:
                    recommended_hz = target
                    break

            stutter_rating = stutter.get("stutter_rating", "unknown")
            consistency_rating = frame_pacing.get("consistency_rating", "unknown")

            # Check for frametimes
            has_details = any(run.get('frametimes') for run in runs)
            details_button = ""
            if has_details:
                details_button = f'''
                    <button class="details-btn" onclick="toggleDetails('{system_id}_{resolution}')">
                        📊 Runs anzeigen
                    </button>'''

            resolution_cards += f'''
            <div class="resolution-card">
                <div class="res-header">
                    <span class="res-name">{res_name}</span>
                    <span class="res-detail">{res_display}</span>
                    <span class="run-count">{run_count} Run{'s' if run_count > 1 else ''}</span>
                    {details_button}
                </div>
                <div class="res-stats">
                    <div class="stat-main">
                        <span class="stat-value">{fps.get('average', 0):.0f}</span>
                        <span class="stat-label">AVG FPS</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">{fps.get('1_percent_low', 0):.0f}</span>
                        <span class="stat-label">1% Low</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">{fps.get('0.1_percent_low', 0):.0f}</span>
                        <span class="stat-label">0.1% Low</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value stutter-{stutter_rating}">{stutter_rating.capitalize()}</span>
                        <span class="stat-label">Stutter</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value consistency-{consistency_rating}">{consistency_rating.capitalize()}</span>
                        <span class="stat-label">Consistency</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value recommend">{recommended_hz} Hz</span>
                        <span class="stat-label">Recommended</span>
                    </div>
                </div>
                <div class="chart-container" id="details-{system_id}_{resolution}" style="display: none;">
                    <div class="chart-controls">
                        <label>Select run:</label>
                        <select id="run-select-{system_id}_{resolution}" onchange="updateChart('{system_id}_{resolution}')">
                        </select>
                    </div>
                    <canvas id="chart-{system_id}_{resolution}"></canvas>
                </div>
            </div>'''

        # Create system content
        display_style = "block" if idx == 0 else "none"
        system_contents += f'''
        <div class="system-content" id="system-{system_id}" style="display: {display_style};">
            <div class="resolution-grid">
                {resolution_cards}
            </div>

            <div class="system-card">
                <h2>System: {os_name}</h2>
                <div class="sys-grid">
                    <div class="sys-item">
                        <span class="lbl">GPU</span>
                        <span class="val">{gpu_name}</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">CPU</span>
                        <span class="val">{cpu_name}</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">RAM</span>
                        <span class="val">{ram_gb:.0f} GB</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">OS</span>
                        <span class="val">{os_name}</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">Mesa</span>
                        <span class="val">{mesa}</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">Vulkan</span>
                        <span class="val">{vulkan}</span>
                    </div>
                    <div class="sys-item">
                        <span class="lbl">Kernel</span>
                        <span class="val">{kernel}</span>
                    </div>
                </div>
            </div>
        </div>'''

    # Prepare runs data for JavaScript
    all_runs_data = {}
    for system_id, data in systems_data.items():
        for resolution, runs in data.get("resolutions", {}).items():
            key = f"{system_id}_{resolution}"
            all_runs_data[key] = runs

    app_id_safe = app_id if app_id else 0

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Benchmark - {game_name}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --card-alt: #2d2f5a;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 40px 20px;
        }}

        .container {{ max-width: 1100px; margin: 0 auto; }}

        header {{ text-align: center; margin-bottom: 30px; }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 8px; }}
        header .info {{ color: var(--text-muted); font-size: 1rem; }}

        /* System Tabs */
        .system-tabs {{
            display: flex;
            gap: 10px;
            margin-bottom: 25px;
            flex-wrap: wrap;
            justify-content: center;
        }}

        .system-tab {{
            background: var(--card);
            border: 2px solid transparent;
            color: var(--text-muted);
            padding: 12px 24px;
            border-radius: 12px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .system-tab:hover {{
            background: var(--card-alt);
            color: var(--text);
        }}

        .system-tab.active {{
            background: var(--blue);
            color: var(--bg);
            border-color: var(--blue);
        }}

        /* Resolution Cards */
        .resolution-grid {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 30px;
        }}

        .resolution-card {{
            background: var(--card);
            border-radius: 20px;
            padding: 25px 30px;
        }}

        .res-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        .res-name {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--blue);
        }}

        .res-detail {{
            font-size: 1rem;
            color: var(--text-muted);
        }}

        .run-count {{
            margin-left: auto;
            background: rgba(255,255,255,0.1);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .res-stats {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}

        .stat {{
            text-align: center;
            min-width: 80px;
        }}

        .stat-main {{
            text-align: center;
            min-width: 100px;
            padding-right: 20px;
            border-right: 1px solid rgba(255,255,255,0.1);
            margin-right: 10px;
        }}

        .stat-main .stat-value {{
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--green);
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            display: block;
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 5px;
            display: block;
        }}

        .stutter-excellent, .stutter-good, .consistency-excellent, .consistency-good {{ color: var(--green); }}
        .stutter-moderate, .consistency-moderate {{ color: var(--yellow); }}
        .stutter-poor, .consistency-poor {{ color: var(--red); }}
        .stutter-unknown, .consistency-unknown {{ color: var(--text-muted); }}

        .recommend {{ color: var(--blue); }}

        /* System Card */
        .system-card {{
            background: var(--card);
            border-radius: 20px;
            padding: 25px 30px;
        }}

        .system-card h2 {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 18px;
        }}

        .sys-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px 30px;
        }}

        .sys-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.95rem;
        }}

        .sys-item .lbl {{ color: var(--text-muted); }}
        .sys-item .val {{ font-weight: 600; }}

        /* Chart Details */
        .details-btn {{
            background: var(--blue);
            color: var(--bg);
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .details-btn:hover {{
            background: #6DD5FA;
            transform: translateY(-2px);
        }}

        .chart-container {{
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}

        .chart-controls {{
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 20px;
        }}

        .chart-controls label {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .chart-controls select {{
            background: var(--card-alt);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9rem;
            cursor: pointer;
        }}

        .filter-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .filter-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .filter-item label {{
            font-size: 0.9em;
            color: var(--text-muted);
            white-space: nowrap;
        }}

        .filter-item select {{
            padding: 6px 10px;
            border: 1px solid rgba(255,255,255,0.2);
            background: var(--card-alt);
            color: var(--text);
            border-radius: 6px;
            min-width: 100px;
            font-size: 0.9em;
        }}

        .filter-item select option {{
            background: var(--card-alt);
            color: var(--text);
        }}

        .run-selection-row {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}

        .run-select-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .run-select-item label {{
            font-weight: bold;
            min-width: 70px;
        }}

        .run-select-item select {{
            flex: 1;
            min-width: 300px;
        }}

        canvas {{
            max-height: 400px;
        }}

        footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        @media (max-width: 700px) {{
            .res-stats {{
                gap: 20px;
            }}
            .stat-main {{
                border-right: none;
                margin-right: 0;
                padding-right: 0;
                width: 100%;
                margin-bottom: 10px;
            }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        const charts = {{}};
        const runsData = {json.dumps(all_runs_data)};

        function showSystem(systemId) {{
            // Hide all system contents
            document.querySelectorAll('.system-content').forEach(el => {{
                el.style.display = 'none';
            }});

            // Deactivate all tabs
            document.querySelectorAll('.system-tab').forEach(el => {{
                el.classList.remove('active');
            }});

            // Show selected system
            document.getElementById('system-' + systemId).style.display = 'block';

            // Activate selected tab
            document.querySelector('[data-system="' + systemId + '"]').classList.add('active');
        }}

        function toggleDetails(key) {{
            const details = document.getElementById('details-' + key);
            const btn = event.target;

            if (details.style.display === 'none') {{
                details.style.display = 'block';
                btn.textContent = '📊 Runs verbergen';
                if (!charts[key]) {{
                    initChart(key);
                }}
            }} else {{
                details.style.display = 'none';
                btn.textContent = '📊 Runs anzeigen';
            }}
        }}

        function initChart(key) {{
            const runs = runsData[key] || [];
            const select = document.getElementById('run-select-' + key);

            // Create array with original indices and sort by timestamp (newest first)
            const sortedRuns = runs.map((run, idx) => ({{ run, originalIdx: idx }}))
                .sort((a, b) => new Date(b.run.timestamp) - new Date(a.run.timestamp));

            select.innerHTML = '';
            sortedRuns.forEach((item, sortedIdx) => {{
                const run = item.run;
                const option = document.createElement('option');
                option.value = item.originalIdx;
                const timestamp = new Date(run.timestamp).toLocaleString('de-DE');
                const avgFps = run.metrics?.fps?.average || 0;
                option.textContent = `${{avgFps.toFixed(0)}} FPS avg (${{timestamp}})`;
                // Select the newest run (first in sorted list)
                if (sortedIdx === 0) {{
                    option.selected = true;
                }}
                select.appendChild(option);
            }});

            updateChart(key);
        }}

        function updateChart(key) {{
            const select = document.getElementById('run-select-' + key);
            const runIndex = parseInt(select.value);
            const runs = runsData[key] || [];
            const run = runs[runIndex];

            if (!run || !run.frametimes) return;

            const ctx = document.getElementById('chart-' + key);

            if (charts[key]) {{
                charts[key].destroy();
            }}

            const frametimes = run.frametimes;
            const fps = frametimes.map(ft => 1000.0 / ft);
            const labels = frametimes.map((_, i) => (i * 10 / 60).toFixed(1));

            charts[key] = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'FPS',
                        data: fps,
                        borderColor: '#4fc3f7',
                        backgroundColor: 'rgba(79, 195, 247, 0.1)',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0,
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false,
                            callbacks: {{
                                title: ctx => 'Zeit: ' + ctx[0].label + 's',
                                label: ctx => 'FPS: ' + ctx.parsed.y.toFixed(1)
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{ display: true, text: 'Time (Seconds)', color: '#a0a0a0' }},
                            ticks: {{ color: '#a0a0a0', maxTicksLimit: 10 }},
                            grid: {{ color: 'rgba(255,255,255,0.1)' }}
                        }},
                        y: {{
                            title: {{ display: true, text: 'FPS', color: '#a0a0a0' }},
                            ticks: {{ color: '#a0a0a0' }},
                            grid: {{ color: 'rgba(255,255,255,0.1)' }}
                        }}
                    }}
                }}
            }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <header>
            <img src="https://steamcdn-a.akamaihd.net/steam/apps/{app_id_safe}/header.jpg"
                 alt="{game_name}"
                 style="width: 100%; max-width: 460px; border-radius: 12px; margin-bottom: 20px;"
                 onerror="this.style.display='none'">
            <h1>{game_name}</h1>
            <p class="info">{date_str} &bull; {len(systems_data)} System{'s' if len(systems_data) > 1 else ''}</p>
        </header>

        <div class="system-tabs">
            {system_tabs}
        </div>

        {system_contents}

        <footer>
            Linux Game Benchmark &bull; Multi-System Report
        </footer>
    </div>
</body>
</html>
'''

    output_path.write_text(html)
    return output_path


def generate_single_resolution_report(
    game_name: str,
    app_id: int,
    system_id: str,
    resolution: str,
    runs: list[dict],
    system_info: dict,
    output_path: Path,
    all_game_runs: list[dict] = None,
) -> Path:
    """
    Generate a detailed HTML report for a single resolution/system combination.

    Args:
        game_name: Name of the game
        app_id: Steam App ID
        system_id: System identifier (e.g., "CachyOS_c21b11a6")
        resolution: Resolution string (e.g., "FHD", "WQHD", "UHD")
        runs: List of run dictionaries for this resolution
        system_info: System information dictionary
        output_path: Where to save the report

    Returns:
        Path to the generated report
    """
    from datetime import datetime
    import json

    # Get system info
    gpu_info = system_info.get("gpu", {})
    cpu_info = system_info.get("cpu", {})
    os_info = system_info.get("os", {})

    gpu_name = shorten_gpu_name(gpu_info.get("model", "Unknown GPU"))

    cpu_name = cpu_info.get("model", "Unknown CPU")
    if "9800X3D" in cpu_name:
        cpu_name = "Ryzen 7 9800X3D"
    elif "Ryzen" in cpu_name:
        cpu_name = cpu_name.replace("AMD ", "").split(" 8-Core")[0]

    ram_gb = system_info.get("ram", {}).get("total_gb", 0)
    os_name = os_info.get("name", "Linux")
    kernel = os_info.get("kernel", "").split("-")[0]
    mesa = gpu_info.get("driver_version", "")

    date_str = datetime.now().strftime("%d.%m.%Y")

    # Aggregate metrics from all runs
    if not runs:
        return output_path

    fps_keys = ["average", "1_percent_low", "0.1_percent_low"]
    fps_sums = {key: 0.0 for key in fps_keys}
    for run in runs:
        fps = run.get("metrics", {}).get("fps", {})
        for key in fps_keys:
            fps_sums[key] += fps.get(key, 0)

    n = len(runs)
    fps_avg = {key: fps_sums[key] / n for key in fps_keys}

    # Get ratings from last run
    last_metrics = runs[-1].get("metrics", {}) if runs else {}
    stutter = last_metrics.get("stutter", {})
    stutter_rating = stutter.get("stutter_rating", "unknown")
    frame_pacing = last_metrics.get("frame_pacing", {})
    consistency_rating = frame_pacing.get("consistency_rating", "unknown")

    # Calculate target recommendation
    low1 = fps_avg.get("1_percent_low", 0)
    recommended_hz = 60
    for target in [240, 165, 144, 120, 60]:
        if low1 >= target * 0.85:
            recommended_hz = target
            break

    # Resolution display
    res_name = resolution
    res_display = {
        "FHD": "1920×1080",
        "WQHD": "2560×1440",
        "UHD": "3840×2160"
    }.get(resolution, resolution)

    # Runs table
    runs_table_rows = ""
    for idx, run in enumerate(runs, 1):
        run_fps = run.get("metrics", {}).get("fps", {})
        run_stutter = run.get("metrics", {}).get("stutter", {})
        run_consistency = run.get("metrics", {}).get("frame_pacing", {})
        timestamp = datetime.fromisoformat(run.get("timestamp", "")).strftime("%d.%m.%Y %H:%M")

        runs_table_rows += f'''
            <tr onclick="showRunChart({idx - 1})" style="cursor: pointer;">
                <td>{idx}</td>
                <td>{timestamp}</td>
                <td class="fps">{run_fps.get("average", 0):.1f}</td>
                <td>{run_fps.get("1_percent_low", 0):.1f}</td>
                <td>{run_fps.get("0.1_percent_low", 0):.1f}</td>
                <td class="stutter-{run_stutter.get("stutter_rating", "unknown")}">{run_stutter.get("stutter_rating", "unknown").capitalize()}</td>
                <td class="stutter-{run_consistency.get("consistency_rating", "unknown")}">{run_consistency.get("consistency_rating", "unknown").capitalize()}</td>
            </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{game_name} - {resolution} Benchmark</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 40px 20px;
        }}

        .container {{ max-width: 1100px; margin: 0 auto; }}

        header {{ text-align: center; margin-bottom: 40px; }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 8px; }}
        header .info {{ color: var(--text-muted); font-size: 1rem; }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-box {{
            background: var(--card);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
        }}

        .stat-box .value {{ font-size: 2rem; font-weight: bold; margin-bottom: 5px; }}
        .stat-box .label {{ color: var(--text-muted); font-size: 0.9rem; }}

        .fps {{ color: var(--blue); }}
        .recommend {{ color: var(--green); }}
        .stutter-low {{ color: var(--green); }}
        .stutter-medium {{ color: var(--yellow); }}
        .stutter-high {{ color: var(--red); }}
        .stutter-unknown {{ color: var(--text-muted); }}

        table {{
            width: 100%;
            background: var(--card);
            border-radius: 15px;
            overflow: hidden;
            margin-bottom: 30px;
        }}

        th, td {{ padding: 15px; text-align: left; }}
        th {{ background: rgba(255, 255, 255, 0.05); font-weight: 600; }}
        tr:hover {{ background: rgba(255, 255, 255, 0.03); }}

        .chart-section {{ background: var(--card); padding: 25px; border-radius: 15px; margin-bottom: 30px; }}
        .chart-section h3 {{ margin-bottom: 15px; }}
        .chart-container {{ height: 400px; }}

        .system-info {{
            background: var(--card);
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 30px;
        }}

        .system-info .row {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
        .system-info .label {{ color: var(--text-muted); }}

        .comparison-table {{
            width: 100%;
            background: var(--card);
            border-radius: 15px;
            overflow: hidden;
            margin-top: 20px;
        }}

        .comparison-table th, .comparison-table td {{
            padding: 12px 15px;
            text-align: left;
        }}

        .comparison-table th {{
            background: rgba(255, 255, 255, 0.05);
            font-weight: 600;
        }}

        .comparison-table tr:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}

        .diff-positive {{
            color: var(--green);
        }}

        .diff-negative {{
            color: var(--red);
        }}

        .diff-neutral {{
            color: var(--text-muted);
        }}

        footer {{ text-align: center; color: var(--text-muted); margin-top: 50px; }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 10px;">
                <!-- Back button -->
                <a href="../index.html" style="
                    color: var(--blue);
                    text-decoration: none;
                    font-size: 0.9rem;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 1px solid rgba(79, 195, 247, 0.3);
                    transition: all 0.2s;
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    white-space: nowrap;
                " onmouseover="this.style.borderColor='rgba(79, 195, 247, 0.8)'; this.style.backgroundColor='rgba(79, 195, 247, 0.1)';"
                   onmouseout="this.style.borderColor='rgba(79, 195, 247, 0.3)'; this.style.backgroundColor='transparent';">
                    ← Overview
                </a>

                <!-- Game info (centered) -->
                <div style="display: flex; align-items: center; justify-content: center; gap: 20px; flex: 1;">
                    <img src="https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/capsule_sm_120.jpg"
                         style="height: 60px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);"
                         onerror="this.style.display='none'">
                    <h1 style="margin: 0;">{game_name}</h1>
                </div>

                <!-- Empty spacer for balance -->
                <div style="width: 80px;"></div>
            </div>
            <div class="info">{res_name} ({res_display}) &bull; {os_name} &bull; {date_str}</div>
        </header>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="value fps">{fps_avg.get("average", 0):.0f}</div>
                <div class="label">AVG FPS</div>
            </div>
            <div class="stat-box">
                <div class="value">{fps_avg.get("1_percent_low", 0):.0f}</div>
                <div class="label">1% Low</div>
            </div>
            <div class="stat-box">
                <div class="value">{fps_avg.get("0.1_percent_low", 0):.0f}</div>
                <div class="label">0.1% Low</div>
            </div>
            <div class="stat-box">
                <div class="value">
                    <span class="tooltip-wrapper stutter-{stutter_rating}">
                        {stutter_rating.capitalize()}
                        <span class="tooltip-text">
                            <strong>Stutter (Gameplay Hitches)</strong>
                            Measures real gameplay hitches and freezes, filters out loading screens.
                            <ul>
                                <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> &lt;0.5 stutter events per 1000 frames</li>
                                <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> &lt;2.0 events per 1000 frames</li>
                                <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> ≥2.0 events or &gt;3 sequences</li>
                            </ul>
                            Lower values = better gaming experience
                        </span>
                    </span>
                </div>
                <div class="label">Stutter</div>
            </div>
            <div class="stat-box">
                <div class="value">
                    <span class="tooltip-wrapper stutter-{consistency_rating}">
                        {consistency_rating.capitalize()}
                        <span class="tooltip-text">
                            <strong>Consistency (Frame-Pacing)</strong>
                            Measures frame-to-frame stability. Combines frametime variance (CV%) and FPS stability (1% Low vs Average).
                            <ul>
                                <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> Low variance, stable frametimes</li>
                                <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> Noticeable variance, but playable</li>
                                <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> High variance, uneven gameplay feel</li>
                            </ul>
                            Rating is FPS-dependent: stricter criteria at 120+ FPS than at 60 FPS
                        </span>
                    </span>
                </div>
                <div class="label">Consistency</div>
            </div>
            <div class="stat-box">
                <div class="value recommend">{recommended_hz} Hz</div>
                <div class="label">Recommended</div>
            </div>
        </div>

        <div class="system-info">
            <h3 style="margin-bottom: 15px;">System Information</h3>
            <div class="row"><span class="label">GPU:</span><span>{gpu_name}</span></div>
            <div class="row"><span class="label">CPU:</span><span>{cpu_name}</span></div>
            <div class="row"><span class="label">RAM:</span><span>{ram_gb:.0f} GB</span></div>
            <div class="row"><span class="label">OS:</span><span>{os_name}</span></div>
            <div class="row"><span class="label">Kernel:</span><span>{kernel}</span></div>
            <div class="row"><span class="label">Mesa:</span><span>{mesa}</span></div>
        </div>

        <div class="chart-section">
            <h3>FPS Timeline</h3>
            <div class="run-selector" style="margin-bottom: 15px; display: flex; align-items: center; gap: 15px;">
                <label>Run 1:</label>
                <select id="run-select-primary" onchange="updateComparisonChart()">
                    <!-- Populated by JS -->
                </select>
                <label>Compare with:</label>
                <select id="run-select-compare" onchange="updateComparisonChart()">
                    <option value="">No comparison</option>
                    <!-- Populated by JS -->
                </select>
            </div>
            <div class="chart-container">
                <canvas id="chart"></canvas>
            </div>
        </div>

        <div id="comparison-stats" style="display: none;">
            <h3 style="margin: 30px 0 15px 0;">Comparison Table</h3>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Run 1</th>
                        <th>Run 2</th>
                        <th>Difference</th>
                    </tr>
                </thead>
                <tbody id="comparison-body">
                    <!-- Populated by JS -->
                </tbody>
            </table>
        </div>

        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Date</th>
                    <th>AVG FPS</th>
                    <th>1% Low</th>
                    <th>0.1% Low</th>
                    <th>Stutter</th>
                    <th>Consistency</th>
                </tr>
            </thead>
            <tbody>
                {runs_table_rows}
            </tbody>
        </table>

        <footer>
            Linux Game Benchmark &bull; {game_name} @ {resolution}
        </footer>
    </div>

    <script>
        const runsData = {json.dumps(runs)};
        const allGameRuns = {json.dumps(all_game_runs or [])};
        let currentChart = null;
        let selectedPrimaryRun = 0;
        let selectedCompareRun = null;

        // Initialize select dropdowns
        function initializeRunSelectors() {{
            const primarySelect = document.getElementById('run-select-primary');
            const compareSelect = document.getElementById('run-select-compare');

            if (!primarySelect || !compareSelect) return;

            primarySelect.innerHTML = '';
            compareSelect.innerHTML = '<option value="">No comparison</option>';

            // Populate primary select with current resolution's runs
            runsData.forEach((run, idx) => {{
                const timestamp = new Date(run.timestamp).toLocaleString('en-US');
                const avgFps = run.metrics?.fps?.average || 0;
                const label = `Run ${{idx + 1}} - ${{avgFps.toFixed(0)}} FPS (${{timestamp}})`;

                const opt1 = document.createElement('option');
                opt1.value = `local:${{idx}}`;
                opt1.textContent = label;
                primarySelect.appendChild(opt1);
            }});

            // Populate compare select with ALL runs from the game
            if (allGameRuns && allGameRuns.length > 0) {{
                allGameRuns.forEach((runData, idx) => {{
                    const run = runData.run;
                    const timestamp = new Date(run.timestamp).toLocaleString('en-US');
                    const avgFps = run.metrics?.fps?.average || 0;
                    const label = `${{runData.resolution}} @ ${{runData.os}} - ${{avgFps.toFixed(0)}} FPS (${{timestamp}})`;

                    const opt2 = document.createElement('option');
                    opt2.value = `game:${{idx}}`;
                    opt2.textContent = label;
                    compareSelect.appendChild(opt2);
                }});
            }}

            updateComparisonChart();
        }}

        function updateComparisonChart() {{
            const primarySelect = document.getElementById('run-select-primary');
            const compareSelect = document.getElementById('run-select-compare');

            if (!primarySelect || !compareSelect) return;

            const primaryValue = primarySelect.value;
            const compareValue = compareSelect.value;

            // Parse primary run
            const primaryIndex = primaryValue.startsWith('local:') ? parseInt(primaryValue.split(':')[1]) : 0;
            selectedPrimaryRun = primaryIndex;

            const run1 = runsData[primaryIndex];
            if (!run1 || !run1.frametimes) return;

            const ctx = document.getElementById('chart');
            if (currentChart) {{
                currentChart.destroy();
            }}

            // Build datasets
            const datasets = [];

            // Primary run (blue)
            const frametimes1 = run1.frametimes;
            const fps1 = frametimes1.map(ft => 1000.0 / ft);
            const labels = frametimes1.map((_, i) => (i * 10 / 60).toFixed(1));

            datasets.push({{
                label: `Run ${{primaryIndex + 1}}`,
                data: fps1,
                borderColor: '#4fc3f7',
                backgroundColor: 'rgba(79, 195, 247, 0.1)',
                borderWidth: 2,
                tension: 0.1,
                pointRadius: 0,
                fill: compareValue === ''
            }});

            // Comparison run (orange) - from game-wide data
            if (compareValue !== '' && allGameRuns && allGameRuns.length > 0) {{
                const compareIndex = parseInt(compareValue.split(':')[1]);
                selectedCompareRun = compareIndex;
                const runData = allGameRuns[compareIndex];
                const run2 = runData.run;

                if (run2 && run2.frametimes) {{
                    const frametimes2 = run2.frametimes;
                    const fps2 = frametimes2.map(ft => 1000.0 / ft);

                    datasets.push({{
                        label: `${{runData.resolution}} @ ${{runData.os}}`,
                        data: fps2,
                        borderColor: '#ff9800',
                        backgroundColor: 'rgba(255, 152, 0, 0.1)',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0,
                        fill: false
                    }});
                }}
            }} else {{
                selectedCompareRun = null;
            }}

            currentChart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: datasets
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: compareValue !== '',
                            labels: {{ color: '#eaeaea' }}
                        }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false,
                            callbacks: {{
                                title: function(context) {{
                                    return 'Zeit: ' + context[0].label + 's';
                                }},
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + ' FPS';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            grid: {{ color: 'rgba(255,255,255,0.1)' }},
                            ticks: {{ color: '#a0a0a0' }},
                            title: {{
                                display: true,
                                text: 'Zeit (Sekunden)',
                                color: '#a0a0a0'
                            }}
                        }},
                        y: {{
                            grid: {{ color: 'rgba(255,255,255,0.1)' }},
                            ticks: {{ color: '#a0a0a0' }},
                            title: {{
                                display: true,
                                text: 'FPS',
                                color: '#a0a0a0'
                            }}
                        }}
                    }}
                }}
            }});

            // Update comparison table
            updateComparisonTable();
        }}

        function updateComparisonTable() {{
            const comparisonStats = document.getElementById('comparison-stats');
            const comparisonBody = document.getElementById('comparison-body');

            if (!comparisonStats || !comparisonBody) return;

            if (selectedCompareRun === null) {{
                comparisonStats.style.display = 'none';
                return;
            }}

            comparisonStats.style.display = 'block';

            const run1 = runsData[selectedPrimaryRun];
            const run2 = runsData[selectedCompareRun];

            const metrics1 = run1.metrics || {{}};
            const metrics2 = run2.metrics || {{}};

            const fps1 = metrics1.fps || {{}};
            const fps2 = metrics2.fps || {{}};

            const rows = [
                {{
                    label: 'AVG FPS',
                    val1: fps1.average || 0,
                    val2: fps2.average || 0,
                    unit: ' FPS',
                    higherBetter: true
                }},
                {{
                    label: '1% Low',
                    val1: fps1['1_percent_low'] || 0,
                    val2: fps2['1_percent_low'] || 0,
                    unit: ' FPS',
                    higherBetter: true
                }},
                {{
                    label: '0.1% Low',
                    val1: fps1['0.1_percent_low'] || 0,
                    val2: fps2['0.1_percent_low'] || 0,
                    unit: ' FPS',
                    higherBetter: true
                }}
            ];

            let html = '';
            rows.forEach(row => {{
                const diff = row.val2 - row.val1;
                const diffPercent = row.val1 !== 0 ? ((diff / row.val1) * 100) : 0;

                let diffClass = 'diff-neutral';
                let diffSymbol = '';

                if (Math.abs(diffPercent) >= 0.5) {{
                    if ((diff > 0 && row.higherBetter) || (diff < 0 && !row.higherBetter)) {{
                        diffClass = 'diff-positive';
                        diffSymbol = '+';
                    }} else {{
                        diffClass = 'diff-negative';
                    }}
                }}

                html += `
                    <tr>
                        <td><strong>${{row.label}}</strong></td>
                        <td>${{row.val1.toFixed(1)}}${{row.unit}}</td>
                        <td>${{row.val2.toFixed(1)}}${{row.unit}}</td>
                        <td class="${{diffClass}}">
                            ${{diffSymbol}}${{diff.toFixed(1)}}${{row.unit}}
                            (${{diffSymbol}}${{diffPercent.toFixed(1)}}%)
                        </td>
                    </tr>
                `;
            }});

            comparisonBody.innerHTML = html;
        }}

        // Initialize on load
        if (runsData.length > 0) {{
            initializeRunSelectors();
        }}
    </script>
</body>
</html>
'''

    output_path.write_text(html)
    return output_path


def generate_overview_report(
    all_games_data: dict[str, dict],  # game_name -> systems_data
    output_path: Path,
) -> Path:
    """
    Generate an overview HTML page showing all games and all benchmarks.

    Args:
        all_games_data: Dict mapping game_name to systems_data
        output_path: Where to save the report

    Returns:
        Path to the generated report
    """
    date_str = datetime.now().strftime("%d.%m.%Y")

    # Collect all unique values for filters
    all_games = set()
    all_cpus = set()
    all_gpus = set()
    all_kernels = set()
    all_oses = set()
    all_mesas = set()
    all_resolutions = set()

    benchmarks = []

    for game_name, systems_data in all_games_data.items():
        all_games.add(game_name)
        app_id = STEAM_APP_IDS.get(game_name, 0)

        # Collect ALL runs for this game across all systems/resolutions
        all_runs_for_game = []
        for sys_id, sys_data in systems_data.items():
            sys_info = sys_data.get("system_info", {})
            for res, res_runs in sys_data.get("resolutions", {}).items():
                res_name = RESOLUTION_NAMES.get(res, res)
                all_resolutions.add(res_name)  # Add ALL resolutions to filter, not just latest
                os_name = sys_info.get('os', {}).get('name', sys_id.split("_")[0] if "_" in sys_id else "Unknown")
                gpu_info = sys_info.get("gpu", {})
                cpu_info = sys_info.get("cpu", {})
                gpu = shorten_gpu_name(gpu_info.get("model", "Unknown"))
                cpu = shorten_cpu_name(cpu_info.get("model", "Unknown"))

                # Collect ALL runs with their system context
                for run in res_runs:
                    all_runs_for_game.append({
                        'run': run,
                        'system_id': sys_id,
                        'system_info': sys_info,
                        'resolution_name': res_name,
                        'os': os_name,
                        'cpu': cpu,
                        'gpu': gpu
                    })

        # Skip if no runs found for this game
        if not all_runs_for_game:
            continue

        # Find the LATEST run (highest timestamp)
        latest_run_data = max(
            all_runs_for_game,
            key=lambda rd: rd['run'].get('timestamp', '')
        )

        latest_run = latest_run_data['run']
        latest_system_info = latest_run_data['system_info']
        latest_system_id = latest_run_data['system_id']
        latest_resolution = latest_run_data['resolution_name']

        # Extract metrics from the latest run
        metrics = latest_run.get("metrics", {})
        fps = metrics.get("fps", {})
        stutter = metrics.get("stutter", {})
        frame_pacing = metrics.get("frame_pacing", {})

        # Extract system info
        gpu_info = latest_system_info.get("gpu", {})
        cpu_info = latest_system_info.get("cpu", {})
        os_info = latest_system_info.get("os", {})

        gpu = shorten_gpu_name(gpu_info.get("model", "Unknown"))
        cpu = shorten_cpu_name(cpu_info.get("model", "Unknown"))

        os_name = os_info.get("name", latest_system_id.split("_")[0] if "_" in latest_system_id else "Unknown")
        kernel_full = os_info.get("kernel", "Unknown")
        kernel = kernel_full.split("-")[0] if kernel_full else "Unknown"
        mesa = gpu_info.get("driver_version", "Unknown")

        # Add to filter sets
        all_resolutions.add(latest_resolution)
        all_cpus.add(cpu)
        all_gpus.add(gpu)
        all_kernels.add(kernel)
        all_oses.add(os_name)
        all_mesas.add(mesa)

        # Create ONE benchmark entry per game with data from latest run
        benchmarks.append({
            "game": game_name,
            "app_id": app_id,
            "system_id": latest_system_id,
            "resolution": latest_resolution,
            "os": os_name,
            "kernel": kernel,
            "cpu": cpu,
            "gpu": gpu,
            "mesa": mesa,
            "avg_fps": round(fps.get("average", 0), 1),
            "low1": round(fps.get("1_percent_low", 0), 1),
            "low01": round(fps.get("0.1_percent_low", 0), 1),
            "stutter": stutter.get("stutter_rating", "unknown"),
            "consistency": frame_pacing.get("consistency_rating", "unknown"),
            "run_count": len(all_runs_for_game),  # Total runs across all systems/resolutions
            "runs": all_runs_for_game,  # All runs WITH system context for dropdowns
        })

    # Sort by game name
    benchmarks.sort(key=lambda x: x["game"])

    # Define resolution order for sorting
    res_order = {"UHD": 0, "WQHD": 1, "FHD": 2}

    # Build game-wide runs collection for comparison
    all_game_runs = {}  # game_name -> list of all runs with metadata
    for game_name in sorted(set(b['game'] for b in benchmarks)):
        game_runs = []
        seen_timestamps = set()  # Track unique runs by timestamp

        for b in benchmarks:
            if b['game'] == game_name:
                # b['runs'] now contains all_runs_for_game with full context
                for run_data in b['runs']:
                    # Deduplicate by timestamp
                    timestamp = run_data['run'].get('timestamp', '')
                    if timestamp in seen_timestamps:
                        continue
                    seen_timestamps.add(timestamp)

                    # Extract system info from the run's context
                    system_info = run_data['system_info']
                    gpu_info = system_info.get("gpu", {})
                    cpu_info = system_info.get("cpu", {})
                    os_info = system_info.get("os", {})

                    gpu = shorten_gpu_name(gpu_info.get("model", "Unknown"))
                    cpu = shorten_cpu_name(cpu_info.get("model", "Unknown"))

                    os_name = os_info.get("name", run_data['system_id'].split("_")[0] if "_" in run_data['system_id'] else "Unknown")
                    kernel_full = os_info.get("kernel", "Unknown")
                    kernel = kernel_full.split("-")[0] if kernel_full else "Unknown"
                    mesa = gpu_info.get("driver_version", "Unknown")

                    game_runs.append({
                        'run': run_data['run'],
                        'system_id': run_data['system_id'],
                        'resolution': run_data['resolution_name'],
                        'os': os_name,
                        'cpu': cpu,
                        'gpu': gpu,
                        'kernel': kernel,
                        'mesa': mesa
                    })
        all_game_runs[game_name] = game_runs

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Linux Game Benchmark - Overview</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --card-alt: #2d2f5a;
            --card-hover: #2d2f5a;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
            --purple: #b388ff;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 30px 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(90deg, var(--blue), var(--purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        header .subtitle {{ color: var(--text-muted); font-size: 1.1rem; }}

        /* Filter Bar */
        .filter-bar {{
            background: var(--card);
            border-radius: 16px;
            padding: 20px;
            margin-top: 30px;
            margin-bottom: 25px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: flex-end;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }}
        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}
        .filter-group label {{
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .filter-group select {{
            background: var(--bg);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.9rem;
            cursor: pointer;
            min-width: 130px;
        }}
        .filter-group select:hover {{ border-color: var(--blue); }}
        .reset-btn {{
            background: transparent;
            color: var(--text-muted);
            border: 1px solid var(--text-muted);
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            margin-left: auto;
        }}
        .reset-btn:hover {{ color: var(--text); border-color: var(--text); }}

        /* Active Filter Tags */
        .active-filters {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 20px;
            min-height: 28px;
        }}
        .filter-tag {{
            background: var(--blue);
            color: var(--bg);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-weight: 500;
        }}
        .filter-tag .remove {{
            cursor: pointer;
            opacity: 0.7;
            font-size: 1rem;
            line-height: 1;
        }}
        .filter-tag .remove:hover {{
            opacity: 1;
        }}

        /* Detail Panel Filters */
        .filter-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .filter-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .filter-item label {{
            font-size: 0.9em;
            color: var(--text-muted);
            white-space: nowrap;
        }}

        .filter-item select {{
            padding: 6px 10px;
            border: 1px solid rgba(255,255,255,0.2);
            background: var(--card-alt);
            color: var(--text);
            border-radius: 6px;
            min-width: 100px;
            font-size: 0.9em;
        }}

        .filter-item select option {{
            background: var(--card-alt);
            color: var(--text);
        }}

        .run-selection-row {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}

        .run-select-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .run-select-item label {{
            font-weight: bold;
            min-width: 70px;
        }}

        .run-select-item select {{
            flex: 1;
            min-width: 300px;
        }}

        /* General select styling for dark theme */
        select {{
            background: var(--card-alt);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
        }}

        select option {{
            background: var(--card-alt);
            color: var(--text);
        }}

        /* Stats Bar */
        .stats-bar {{
            display: flex;
            gap: 30px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }}
        .stat-box {{
            background: var(--card);
            padding: 15px 25px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }}
        .stat-box .number {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--blue);
        }}
        .stat-box .label {{
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}

        /* Game sections */
        .game-section {{
            margin-bottom: 30px;
        }}
        .game-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
            padding: 15px;
            background: var(--card);
            border-radius: 12px;
        }}
        .game-header img {{
            height: 45px;
            border-radius: 6px;
        }}
        .game-header h2 {{
            font-size: 1.3rem;
            flex: 1;
        }}
        .game-header a {{
            color: var(--blue);
            text-decoration: none;
            font-size: 0.9rem;
            padding: 8px 16px;
            border: 1px solid var(--blue);
            border-radius: 8px;
        }}
        .game-header a:hover {{
            background: var(--blue);
            color: var(--bg);
        }}

        /* Table Wrapper for responsive scrolling */
        .table-wrapper {{
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }}

        /* Benchmark table */
        .benchmark-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card);
            border-radius: 12px;
            overflow: hidden;
            min-width: 800px;
        }}
        .benchmark-table th {{
            background: rgba(0,0,0,0.3);
            padding: 12px 15px;
            text-align: left;
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            cursor: pointer;
            user-select: none;
            position: relative;
            padding-right: 25px;
        }}
        .benchmark-table th:hover {{
            background: rgba(0,0,0,0.4);
        }}
        .sort-arrow {{
            position: absolute;
            right: 8px;
            opacity: 0.3;
            font-size: 0.9rem;
        }}
        .sort-arrow::after {{
            content: '⇅';
        }}
        .sort-arrow.asc::after {{
            content: '↑';
            opacity: 1;
        }}
        .sort-arrow.desc::after {{
            content: '↓';
            opacity: 1;
        }}
        .benchmark-table th:hover .sort-arrow {{
            opacity: 0.7;
        }}
        .tooltip-wrapper {{
            position: relative;
            display: inline-block;
            cursor: help;
        }}
        .tooltip-wrapper .tooltip-text {{
            visibility: hidden;
            width: 320px;
            background-color: var(--card-alt);
            color: var(--text);
            text-align: left;
            border-radius: 8px;
            padding: 12px;
            position: absolute;
            z-index: 1000;
            top: 125%;
            left: 50%;
            margin-left: -160px;
            opacity: 0;
            transition: opacity 0.3s;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            font-size: 0.85rem;
            line-height: 1.4;
            text-transform: none;
            letter-spacing: normal;
        }}
        .tooltip-wrapper .tooltip-text::after {{
            content: "";
            position: absolute;
            bottom: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: transparent transparent var(--card-alt) transparent;
        }}
        .tooltip-wrapper:hover .tooltip-text {{
            visibility: visible;
            opacity: 1;
        }}
        .tooltip-text strong {{
            color: var(--blue);
            display: block;
            margin-bottom: 6px;
        }}
        .tooltip-text ul {{
            margin: 8px 0 8px 18px;
            padding: 0;
        }}
        .tooltip-text li {{
            margin: 4px 0;
        }}
        .benchmark-table td {{
            padding: 12px 15px;
            border-top: 1px solid rgba(255,255,255,0.05);
        }}
        .benchmark-table tr.data-row:hover {{
            background: var(--card-hover);
            transform: scale(1.005);
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            transition: all 0.15s ease;
        }}
        .benchmark-table tr.data-row {{
            transition: all 0.15s ease;
        }}
        .benchmark-table tr.data-row.expanded {{
            background: var(--card);
            border-left: 3px solid var(--blue);
        }}
        .benchmark-table tr.hidden {{
            display: none;
        }}
        .benchmark-table tr.data-row {{
            cursor: pointer;
        }}
        .benchmark-table tr.data-row:hover td:first-child span {{
            color: var(--blue);
        }}
        .detail-row {{
            display: none;
        }}
        .detail-row.show {{
            display: table-row;
        }}
        .detail-row td {{
            padding: 0;
            background: rgba(0,0,0,0.2);
        }}
        .detail-content {{
            padding: 20px;
            position: relative;
        }}
        .close-details {{
            position: absolute;
            top: 15px;
            right: 20px;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 4px;
            transition: all 0.2s;
            z-index: 10;
        }}
        .close-details:hover {{
            color: var(--red);
            background: rgba(255,82,82,0.1);
        }}
        .detail-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .detail-header h3 {{
            color: var(--blue);
            font-size: 1.1rem;
        }}
        .detail-stats {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }}
        .detail-stat {{
            text-align: center;
            min-width: 120px;
            flex: 0 1 auto;
        }}
        .detail-stat .value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--green);
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .detail-stat .label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        /* Hover-Effekt nur für Stutter und Consistency */
        .detail-stat-hoverable {{
            padding: 10px;
            border-radius: 8px;
            cursor: help;
            transition: background 0.2s ease;
        }}
        .detail-stat-hoverable:hover {{
            background: #3c3c64;
        }}
        .chart-section {{
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
            padding: 20px;
        }}
        .chart-section h4 {{
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 15px;
        }}
        .run-selector {{
            margin-bottom: 15px;
        }}
        .run-selector select {{
            background: var(--card);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.2);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.9rem;
        }}
        .chart-container {{
            height: 250px;
        }}
        .res-badge {{
            background: var(--blue);
            color: var(--bg);
            padding: 4px 10px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
        }}
        .tag {{
            background: rgba(255,255,255,0.1);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-right: 5px;
        }}
        .fps {{ color: var(--green); font-weight: 700; font-size: 1.1rem; }}
        .stutter-excellent, .stutter-good {{ color: var(--green); }}
        .stutter-moderate {{ color: var(--yellow); }}
        .stutter-poor {{ color: var(--red); }}
        .stutter-unknown {{ color: var(--text-muted); }}

        /* Comparison Table */
        .comparison-table {{
            width: 100%;
            background: var(--card);
            border-radius: 12px;
            overflow: hidden;
            margin-top: 15px;
            font-size: 0.9rem;
        }}

        .comparison-table th,
        .comparison-table td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .comparison-table th {{
            background: rgba(255, 255, 255, 0.05);
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .comparison-table tr:last-child td {{
            border-bottom: none;
        }}

        .comparison-table tr:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}

        .diff-positive {{ color: var(--green); font-weight: 600; }}
        .diff-negative {{ color: var(--red); font-weight: 600; }}
        .diff-neutral {{ color: var(--text-muted); }}

        footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
            font-size: 0.85rem;
        }}

        @media (max-width: 900px) {{
            .filter-bar {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            }}
            .reset-btn {{ margin-left: 0; width: 100%; margin-top: 10px; grid-column: 1 / -1; }}
            .benchmark-table {{ font-size: 0.85rem; }}
            .benchmark-table th, .benchmark-table td {{ padding: 10px 8px; }}
            .stats-bar {{ justify-content: center; }}
        }}

        @media (max-width: 600px) {{
            .filter-bar {{
                grid-template-columns: 1fr 1fr;
            }}
            .stats-bar {{
                flex-direction: column;
                align-items: center;
            }}
            .stat-box {{
                width: 100%;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Linux Game Benchmark</h1>
            <p class="subtitle">All benchmarks at a glance &bull; {date_str}</p>
        </header>

        <div class="filter-bar">
            <div class="filter-group">
                <label>Game</label>
                <select id="filter-game" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{g}">{g}</option>' for g in sorted(all_games))}
                </select>
            </div>
            <div class="filter-group">
                <label>Resolution</label>
                <select id="filter-res" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{r}">{r}</option>' for r in sorted(all_resolutions, key=lambda x: res_order.get(x, 99)))}
                </select>
            </div>
            <div class="filter-group">
                <label>CPU</label>
                <select id="filter-cpu" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{c}">{c}</option>' for c in sorted(all_cpus))}
                </select>
            </div>
            <div class="filter-group">
                <label>GPU</label>
                <select id="filter-gpu" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{g}">{g}</option>' for g in sorted(all_gpus))}
                </select>
            </div>
            <div class="filter-group">
                <label>OS</label>
                <select id="filter-os" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{o}">{o}</option>' for o in sorted(all_oses))}
                </select>
            </div>
            <div class="filter-group">
                <label>Kernel</label>
                <select id="filter-kernel" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{k}">{k}</option>' for k in sorted(all_kernels))}
                </select>
            </div>
            <div class="filter-group">
                <label>Mesa</label>
                <select id="filter-mesa" onchange="applyFilters()">
                    <option value="">All</option>
                    {"".join(f'<option value="{m}">{m}</option>' for m in sorted(all_mesas))}
                </select>
            </div>
            <button class="reset-btn" onclick="resetFilters()">Reset</button>
        </div>

        <div class="active-filters" id="active-filters"></div>

        <div class="stats-bar">
            <div class="stat-box">
                <div class="number">{len(all_games)}</div>
                <div class="label">Games</div>
            </div>
            <div class="stat-box">
                <div class="number" id="visible-count">{len(benchmarks)}</div>
                <div class="label">Benchmarks</div>
            </div>
            <div class="stat-box">
                <div class="number">{len(all_oses)}</div>
                <div class="label">Systems</div>
            </div>
        </div>

        <div class="table-wrapper">
        <table class="benchmark-table">
            <thead>
                <tr>
                    <th onclick="sortTable(0, 'text')">Game <span class="sort-arrow"></span></th>
                    <th onclick="sortTable(1, 'number')">
                        <span class="tooltip-wrapper">
                            AVG FPS
                            <span class="tooltip-text">
                                <strong>Average FPS (Frames Per Second)</strong>
                                The arithmetic mean of all frame rates during the benchmark.
                                <ul>
                                    <li><span style="color: var(--green)">●</span> Higher is better</li>
                                    <li>Shows overall performance level</li>
                                    <li>Compare with your monitor's refresh rate</li>
                                </ul>
                            </span>
                        </span>
                        <span class="sort-arrow"></span>
                    </th>
                    <th onclick="sortTable(2, 'number')">
                        <span class="tooltip-wrapper">
                            1% Low
                            <span class="tooltip-text">
                                <strong>1% Low FPS</strong>
                                The average of the lowest 1% of frame rates. Shows performance during demanding scenes.
                                <ul>
                                    <li>Better indicator of "felt" smoothness than AVG</li>
                                    <li>Low values indicate micro-stuttering</li>
                                    <li>Should ideally be close to AVG FPS</li>
                                </ul>
                            </span>
                        </span>
                        <span class="sort-arrow"></span>
                    </th>
                    <th onclick="sortTable(3, 'number')">
                        <span class="tooltip-wrapper">
                            0.1% Low
                            <span class="tooltip-text">
                                <strong>0.1% Low FPS</strong>
                                The average of the lowest 0.1% of frame rates. Shows worst-case performance.
                                <ul>
                                    <li>Indicates severe frame drops/hitches</li>
                                    <li>Very low values = noticeable stuttering</li>
                                    <li>Important for competitive gaming</li>
                                </ul>
                            </span>
                        </span>
                        <span class="sort-arrow"></span>
                    </th>
                    <th onclick="sortTable(4, 'text')">
                        <span class="tooltip-wrapper">
                            Stutter
                            <span class="tooltip-text">
                                <strong>Stutter (Gameplay Hitches)</strong>
                                Measures actual gameplay hitches and freezes, filtering out loading screens.
                                <ul>
                                    <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> &lt;0.5 stutter events per 1000 frames</li>
                                    <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> &lt;2.0 events per 1000 frames</li>
                                    <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> ≥2.0 events or &gt;3 sequences</li>
                                </ul>
                                Lower values = better gaming experience
                            </span>
                        </span>
                        <span class="sort-arrow"></span>
                    </th>
                    <th onclick="sortTable(5, 'text')">
                        <span class="tooltip-wrapper">
                            Consistency
                            <span class="tooltip-text">
                                <strong>Consistency (Frame-Pacing)</strong>
                                Measures frame-to-frame stability. Combines frametime variance (CV%) and FPS stability (1% Low vs Average).
                                <ul>
                                    <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> Low variance, stable frametimes</li>
                                    <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> Noticeable variance, but playable</li>
                                    <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> High variance, uneven gameplay feel</li>
                                </ul>
                                Rating is FPS-dependent: Stricter criteria at 120+ FPS than at 60 FPS
                            </span>
                        </span>
                        <span class="sort-arrow"></span>
                    </th>
                    <th onclick="sortTable(6, 'number')">Runs <span class="sort-arrow"></span></th>
                </tr>
            </thead>
            <tbody id="benchmark-body">
'''

    # Prepare runs data for JavaScript
    all_runs_data = {}

    for idx, b in enumerate(benchmarks):
        game_folder = b['game'].replace(" ", "_")
        row_id = f"row_{idx}"

        # Store runs data for JS
        all_runs_data[row_id] = b['runs']

        html += f'''
                <tr class="data-row" data-game="{b['game']}" data-res="{b['resolution']}" data-cpu="{b['cpu']}" data-gpu="{b['gpu']}" data-os="{b['os']}" data-kernel="{b['kernel']}" data-mesa="{b['mesa']}" onclick="toggleDetail('{row_id}')">
                    <td>
                        <img src="https://steamcdn-a.akamaihd.net/steam/apps/{b['app_id']}/capsule_sm_120.jpg"
                             style="height: 30px; border-radius: 4px; vertical-align: middle; margin-right: 10px;"
                             onerror="this.style.display='none'">
                        <span style="border-bottom: 1px dashed var(--text-muted);">{b['game']}</span>
                    </td>
                    <td class="fps">{b['avg_fps']:.0f}</td>
                    <td>{b['low1']:.0f}</td>
                    <td>{b['low01']:.0f}</td>
                    <td class="stutter-{b['stutter']}">{b['stutter'].capitalize()}</td>
                    <td class="stutter-{b['consistency']}">{b['consistency'].capitalize()}</td>
                    <td>{b['run_count']}</td>
                </tr>
                <tr class="detail-row" id="detail-{row_id}">
                    <td colspan="7">
                        <div class="detail-content">
                            <button class="close-details" onclick="closeDetail('{row_id}')" title="Close">✕</button>
                            <div class="detail-header">
                                <h3>{b['game']} - {b['resolution']} @ {b['os']}</h3>
                            </div>
                            <div class="detail-stats">
                                <div class="detail-stat">
                                    <div class="value" id="stat-avg-{row_id}">{b['avg_fps']:.0f}</div>
                                    <div class="label">AVG FPS</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-low1-{row_id}" style="color: var(--text);">{b['low1']:.0f}</div>
                                    <div class="label">1% Low</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-low01-{row_id}" style="color: var(--text);">{b['low01']:.0f}</div>
                                    <div class="label">0.1% Low</div>
                                </div>
                                <div class="detail-stat detail-stat-hoverable">
                                    <div class="value">
                                        <span id="stat-stutter-{row_id}" class="tooltip-wrapper stutter-{b['stutter']}">
                                            {b['stutter'].capitalize()}
                                            <span class="tooltip-text">
                                                <strong>Stutter (Gameplay Hitches)</strong>
                                                Measures actual gameplay hitches and freezes, filtering out loading screens.
                                                <ul>
                                                    <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> &lt;0.5 stutter events per 1000 frames</li>
                                                    <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> &lt;2.0 events per 1000 frames</li>
                                                    <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> ≥2.0 events or &gt;3 sequences</li>
                                                </ul>
                                                Lower values = better gaming experience
                                            </span>
                                        </span>
                                    </div>
                                    <div class="label">Stutter</div>
                                </div>
                                <div class="detail-stat detail-stat-hoverable">
                                    <div class="value">
                                        <span id="stat-consistency-{row_id}" class="tooltip-wrapper stutter-{b['consistency']}">
                                            {b['consistency'].capitalize()}
                                            <span class="tooltip-text">
                                                <strong>Consistency (Frame-Pacing)</strong>
                                                Measures frame-to-frame stability. Combines frametime variance (CV%) and FPS stability (1% Low vs Average).
                                                <ul>
                                                    <li><span style="color: var(--green)">●</span> <strong>Excellent/Good:</strong> Low variance, stable frametimes</li>
                                                    <li><span style="color: var(--yellow)">●</span> <strong>Moderate:</strong> Noticeable variance, but playable</li>
                                                    <li><span style="color: var(--red)">●</span> <strong>Poor:</strong> High variance, uneven gameplay feel</li>
                                                </ul>
                                                Rating is FPS-dependent: Stricter criteria at 120+ FPS than at 60 FPS
                                            </span>
                                        </span>
                                    </div>
                                    <div class="label">Consistency</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-gpu-{row_id}" style="color: var(--text);">{b['gpu']}</div>
                                    <div class="label">GPU</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-mesa-{row_id}" style="color: var(--text);">{b['mesa']}</div>
                                    <div class="label">Mesa</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-os-{row_id}" style="color: var(--text);">{b['os']}</div>
                                    <div class="label">OS</div>
                                </div>
                                <div class="detail-stat">
                                    <div class="value" id="stat-res-{row_id}" style="color: var(--text);">{b['resolution']}</div>
                                    <div class="label">Resolution</div>
                                </div>
                            </div>
                            <div class="chart-section">
                                <h4>FPS Timeline</h4>
                                <div class="run-selector">
                                    <!-- Filter Section -->
                                    <div class="filter-row">
                                        <div class="filter-item">
                                            <label>Resolution:</label>
                                            <select id="filter-res-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                        <div class="filter-item">
                                            <label>CPU:</label>
                                            <select id="filter-cpu-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                        <div class="filter-item">
                                            <label>GPU:</label>
                                            <select id="filter-gpu-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                        <div class="filter-item">
                                            <label>OS:</label>
                                            <select id="filter-os-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                        <div class="filter-item">
                                            <label>Kernel:</label>
                                            <select id="filter-kernel-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                        <div class="filter-item">
                                            <label>Mesa:</label>
                                            <select id="filter-mesa-{row_id}" onchange="applyDetailFilters('{row_id}')">
                                                <option value="">All</option>
                                            </select>
                                        </div>
                                    </div>

                                    <!-- Run Selection -->
                                    <div class="run-selection-row">
                                        <div class="run-select-item">
                                            <label>Main:</label>
                                            <select id="select-{row_id}" onchange="updateChart('{row_id}')"></select>
                                        </div>
                                        <div class="run-select-item">
                                            <label>Compare:</label>
                                            <select id="compare-{row_id}" onchange="updateChart('{row_id}')">
                                                <option value="">No comparison</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                <div class="filter-row" style="margin-bottom: 10px;">
                                    <div class="filter-item">
                                        <label>FPS Reference:</label>
                                        <select id="fps-reference-{row_id}" onchange="updateChart('{row_id}')" style="background: #2d2f5a !important; color: #e0e0e0 !important;">
                                            <option value="" style="background: #2d2f5a; color: #e0e0e0;">None</option>
                                            <option value="60" style="background: #2d2f5a; color: #e0e0e0;">60 FPS</option>
                                            <option value="120" style="background: #2d2f5a; color: #e0e0e0;">120 FPS</option>
                                            <option value="144" style="background: #2d2f5a; color: #e0e0e0;">144 FPS</option>
                                            <option value="180" style="background: #2d2f5a; color: #e0e0e0;">180 FPS</option>
                                            <option value="240" style="background: #2d2f5a; color: #e0e0e0;">240 FPS</option>
                                            <option value="360" style="background: #2d2f5a; color: #e0e0e0;">360 FPS</option>
                                        </select>
                                    </div>
                                    <span id="fps-percentage-{row_id}" style="color: var(--text-muted); font-size: 0.9em; font-weight: bold; min-width: 120px;"></span>
                                </div>
                                <div class="chart-container">
                                    <canvas id="chart-{row_id}"></canvas>
                                </div>

                                <!-- Comparison Metrics Table -->
                                <div id="comparison-stats-{row_id}" style="display: none; margin-top: 20px;">
                                    <h4 style="margin-bottom: 10px;">Comparison Values</h4>
                                    <table class="comparison-table">
                                        <thead>
                                            <tr>
                                                <th>Metric</th>
                                                <th>Run 1</th>
                                                <th>Run 2</th>
                                                <th>Difference</th>
                                            </tr>
                                        </thead>
                                        <tbody id="comparison-body-{row_id}">
                                            <!-- Populated by JS -->
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
'''

    html += f'''
            </tbody>
        </table>
        </div>

        <footer>
            Linux Game Benchmark &bull; All Benchmarks Overview
        </footer>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        const runsData = {json.dumps(all_runs_data)};
        const allGameRuns = {json.dumps(all_game_runs)};
        const charts = {{}};

        function applyFilters() {{
            const game = document.getElementById('filter-game').value;
            const res = document.getElementById('filter-res').value;
            const cpu = document.getElementById('filter-cpu').value;
            const gpu = document.getElementById('filter-gpu').value;
            const os = document.getElementById('filter-os').value;
            const kernel = document.getElementById('filter-kernel').value;
            const mesa = document.getElementById('filter-mesa').value;

            let visibleCount = 0;
            document.querySelectorAll('#benchmark-body tr.data-row').forEach(row => {{
                const matchGame = !game || row.dataset.game === game;
                const matchRes = !res || row.dataset.res === res;
                const matchCpu = !cpu || row.dataset.cpu === cpu;
                const matchGpu = !gpu || row.dataset.gpu === gpu;
                const matchOs = !os || row.dataset.os === os;
                const matchKernel = !kernel || row.dataset.kernel === kernel;
                const matchMesa = !mesa || row.dataset.mesa === mesa;

                const detailRow = document.getElementById('detail-' + row.id.replace('row_', 'row_'));
                const rowId = row.getAttribute('onclick').match(/'([^']+)'/)[1];
                const detailEl = document.getElementById('detail-' + rowId);

                if (matchGame && matchRes && matchCpu && matchGpu && matchOs && matchKernel && matchMesa) {{
                    row.classList.remove('hidden');
                    visibleCount++;
                }} else {{
                    row.classList.add('hidden');
                    if (detailEl) detailEl.classList.remove('show');
                }}
            }});

            document.getElementById('visible-count').textContent = visibleCount;
            updateFilterTags();
        }}

        function updateFilterTags() {{
            const container = document.getElementById('active-filters');
            container.innerHTML = '';

            const filters = [
                {{ id: 'filter-game', label: 'Game' }},
                {{ id: 'filter-res', label: 'Resolution' }},
                {{ id: 'filter-cpu', label: 'CPU' }},
                {{ id: 'filter-gpu', label: 'GPU' }},
                {{ id: 'filter-os', label: 'OS' }},
                {{ id: 'filter-kernel', label: 'Kernel' }},
                {{ id: 'filter-mesa', label: 'Mesa' }}
            ];

            filters.forEach(filter => {{
                const select = document.getElementById(filter.id);
                if (select && select.value) {{
                    const tag = document.createElement('span');
                    tag.className = 'filter-tag';
                    tag.innerHTML = `${{filter.label}}: ${{select.value}} <span class="remove" onclick="clearFilter('${{filter.id}}')">×</span>`;
                    container.appendChild(tag);
                }}
            }});
        }}

        function clearFilter(filterId) {{
            document.getElementById(filterId).value = '';
            applyFilters();
        }}

        function resetFilters() {{
            document.getElementById('filter-game').value = '';
            document.getElementById('filter-res').value = '';
            document.getElementById('filter-cpu').value = '';
            document.getElementById('filter-gpu').value = '';
            document.getElementById('filter-os').value = '';
            document.getElementById('filter-kernel').value = '';
            document.getElementById('filter-mesa').value = '';
            applyFilters();
        }}

        function toggleDetail(rowId) {{
            const detailRow = document.getElementById('detail-' + rowId);
            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);

            // Close all other detail rows and remove expanded class
            document.querySelectorAll('.detail-row.show').forEach(row => {{
                if (row.id !== 'detail-' + rowId) {{
                    row.classList.remove('show');
                }}
            }});
            document.querySelectorAll('tr.data-row.expanded').forEach(row => {{
                if (!row.getAttribute('onclick').includes(rowId)) {{
                    row.classList.remove('expanded');
                }}
            }});

            // Toggle this one
            detailRow.classList.toggle('show');
            if (dataRow) {{
                dataRow.classList.toggle('expanded');
            }}

            // Initialize chart if opening
            if (detailRow.classList.contains('show') && !charts[rowId]) {{
                initChart(rowId);
            }}
        }}

        function closeDetail(rowId) {{
            const detailRow = document.getElementById('detail-' + rowId);
            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);

            detailRow.classList.remove('show');
            if (dataRow) {{
                dataRow.classList.remove('expanded');
            }}
        }}

        function initChart(rowId) {{
            const select = document.getElementById('select-' + rowId);
            const compareSelect = document.getElementById('compare-' + rowId);

            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);
            const gameName = dataRow ? dataRow.dataset.game : null;

            if (!gameName || !allGameRuns[gameName]) return;

            const gameRuns = allGameRuns[gameName];

            select.innerHTML = '';
            if (compareSelect) {{
                compareSelect.innerHTML = '<option value="">No comparison</option>';
            }}

            // Find the LATEST run (highest timestamp) - this matches what's shown in the overview
            let matchingRunIndex = 0;
            let latestTimestamp = '';

            gameRuns.forEach((runData, idx) => {{
                const ts = runData.run.timestamp || '';
                if (ts > latestTimestamp) {{
                    latestTimestamp = ts;
                    matchingRunIndex = idx;
                }}
            }});

            // Sort runs by resolution (UHD first) then by timestamp (newest first)
            const resOrder = {{
                'UHD': 0, '3840x2160': 0,
                'WQHD': 1, '2560x1440': 1,
                'FHD': 2, '1920x1080': 2
            }};
            const sortedGameRuns = gameRuns.map((runData, idx) => ({{ runData, originalIdx: idx }}))
                .sort((a, b) => {{
                    const resA = resOrder[a.runData.resolution] ?? 99;
                    const resB = resOrder[b.runData.resolution] ?? 99;
                    if (resA !== resB) return resA - resB;
                    return new Date(b.runData.run.timestamp) - new Date(a.runData.run.timestamp);
                }});

            // Populate BOTH dropdowns with ALL game runs (sorted by date, newest first)
            sortedGameRuns.forEach((item) => {{
                const runData = item.runData;
                const idx = item.originalIdx;
                const run = runData.run;
                const timestamp = new Date(run.timestamp).toLocaleString('de-DE');
                const avgFps = run.metrics?.fps?.average || 0;
                const label = `${{runData.resolution}} @ ${{runData.os}} - ${{avgFps.toFixed(0)}} FPS (${{timestamp}})`;

                // Add to primary select
                const option1 = document.createElement('option');
                option1.value = `game:${{idx}}`;
                option1.textContent = label;
                if (idx === matchingRunIndex) {{
                    option1.selected = true;
                }}
                select.appendChild(option1);

                // Add to comparison select
                if (compareSelect) {{
                    const option2 = document.createElement('option');
                    option2.value = `game:${{idx}}`;
                    option2.textContent = label;
                    compareSelect.appendChild(option2);
                }}
            }});

            // Populate filter dropdowns with unique values
            const uniqueResolutions = new Set();
            const uniqueCpus = new Set();
            const uniqueGpus = new Set();
            const uniqueOses = new Set();
            const uniqueKernels = new Set();
            const uniqueMesas = new Set();

            gameRuns.forEach(runData => {{
                uniqueResolutions.add(runData.resolution);
                uniqueCpus.add(runData.cpu);
                uniqueGpus.add(runData.gpu);
                uniqueOses.add(runData.os);
                uniqueKernels.add(runData.kernel);
                uniqueMesas.add(runData.mesa);
            }});

            // Populate Resolution filter
            const filterRes = document.getElementById(`filter-res-${{rowId}}`);
            if (filterRes) {{
                Array.from(uniqueResolutions).sort((a, b) => {{
                    const order = {{
                        'UHD': 0, '3840x2160': 0,
                        'WQHD': 1, '2560x1440': 1,
                        'FHD': 2, '1920x1080': 2
                    }};
                    return (order[a] ?? 99) - (order[b] ?? 99);
                }}).forEach(res => {{
                    const option = document.createElement('option');
                    option.value = res;
                    option.textContent = res;
                    filterRes.appendChild(option);
                }});
            }}

            // Populate CPU filter
            const filterCpu = document.getElementById(`filter-cpu-${{rowId}}`);
            if (filterCpu) {{
                Array.from(uniqueCpus).sort().forEach(cpu => {{
                    const option = document.createElement('option');
                    option.value = cpu;
                    option.textContent = cpu;
                    filterCpu.appendChild(option);
                }});
            }}

            // Populate GPU filter
            const filterGpu = document.getElementById(`filter-gpu-${{rowId}}`);
            if (filterGpu) {{
                Array.from(uniqueGpus).sort().forEach(gpu => {{
                    const option = document.createElement('option');
                    option.value = gpu;
                    option.textContent = gpu;
                    filterGpu.appendChild(option);
                }});
            }}

            // Populate OS filter
            const filterOs = document.getElementById(`filter-os-${{rowId}}`);
            if (filterOs) {{
                Array.from(uniqueOses).sort().forEach(os => {{
                    const option = document.createElement('option');
                    option.value = os;
                    option.textContent = os;
                    filterOs.appendChild(option);
                }});
            }}

            // Populate Kernel filter
            const filterKernel = document.getElementById(`filter-kernel-${{rowId}}`);
            if (filterKernel) {{
                Array.from(uniqueKernels).sort().reverse().forEach(kernel => {{
                    const option = document.createElement('option');
                    option.value = kernel;
                    option.textContent = kernel;
                    filterKernel.appendChild(option);
                }});
            }}

            // Populate Mesa filter
            const filterMesa = document.getElementById(`filter-mesa-${{rowId}}`);
            if (filterMesa) {{
                Array.from(uniqueMesas).sort().reverse().forEach(mesa => {{
                    const option = document.createElement('option');
                    option.value = mesa;
                    option.textContent = mesa;
                    filterMesa.appendChild(option);
                }});
            }}

            updateChart(rowId);
        }}

        function applyDetailFilters(rowId) {{
            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);
            const gameName = dataRow ? dataRow.dataset.game : null;

            if (!gameName || !allGameRuns[gameName]) return;

            const gameRuns = allGameRuns[gameName];

            // Get filter values
            const filterRes = document.getElementById(`filter-res-${{rowId}}`).value;
            const filterCpu = document.getElementById(`filter-cpu-${{rowId}}`).value;
            const filterGpu = document.getElementById(`filter-gpu-${{rowId}}`).value;
            const filterOs = document.getElementById(`filter-os-${{rowId}}`).value;
            const filterKernel = document.getElementById(`filter-kernel-${{rowId}}`).value;
            const filterMesa = document.getElementById(`filter-mesa-${{rowId}}`).value;

            // Filter runs based on selected criteria
            const filteredRuns = gameRuns.filter(runData => {{
                if (filterRes && runData.resolution !== filterRes) return false;
                if (filterCpu && runData.cpu !== filterCpu) return false;
                if (filterGpu && runData.gpu !== filterGpu) return false;
                if (filterOs && runData.os !== filterOs) return false;
                if (filterKernel && runData.kernel !== filterKernel) return false;
                if (filterMesa && runData.mesa !== filterMesa) return false;
                return true;
            }});

            // Repopulate Main and Compare dropdowns with filtered runs
            const select = document.getElementById(`select-${{rowId}}`);
            const compareSelect = document.getElementById(`compare-${{rowId}}`);

            // Clear existing options
            select.innerHTML = '';
            compareSelect.innerHTML = '<option value="">No comparison</option>';

            // Sort filtered runs by resolution (UHD first) then by timestamp (newest first)
            const resOrder = {{
                'UHD': 0, '3840x2160': 0,
                'WQHD': 1, '2560x1440': 1,
                'FHD': 2, '1920x1080': 2
            }};
            const sortedFilteredRuns = filteredRuns
                .map(runData => ({{ runData, originalIdx: gameRuns.indexOf(runData) }}))
                .sort((a, b) => {{
                    const resA = resOrder[a.runData.resolution] ?? 99;
                    const resB = resOrder[b.runData.resolution] ?? 99;
                    if (resA !== resB) return resA - resB;
                    return new Date(b.runData.run.timestamp) - new Date(a.runData.run.timestamp);
                }});

            // Find the newest run's original index for pre-selection
            const newestOriginalIdx = sortedFilteredRuns.length > 0 ? sortedFilteredRuns[0].originalIdx : 0;

            // Populate with sorted filtered runs
            sortedFilteredRuns.forEach((item, idx) => {{
                const runData = item.runData;
                const originalIdx = item.originalIdx;

                const run = runData.run;
                const timestamp = new Date(run.timestamp).toLocaleString('de-DE');
                const avgFps = run.metrics?.fps?.average || 0;
                const label = `${{runData.resolution}} @ ${{runData.os}} - ${{avgFps.toFixed(0)}} FPS (${{timestamp}})`;

                // Add to Main select
                const option1 = document.createElement('option');
                option1.value = `game:${{originalIdx}}`;
                option1.textContent = label;
                if (idx === 0) {{
                    option1.selected = true;  // Pre-select newest filtered run
                }}
                select.appendChild(option1);

                // Add to Compare select
                const option2 = document.createElement('option');
                option2.value = `game:${{originalIdx}}`;
                option2.textContent = label;
                compareSelect.appendChild(option2);
            }});

            // Update chart with new selection
            updateChart(rowId);
        }}

        function updateChart(rowId) {{
            const select = document.getElementById('select-' + rowId);
            const compareSelect = document.getElementById('compare-' + rowId);

            if (!select) return;

            const runValue = select.value;
            const compareValue = compareSelect && compareSelect.value !== '' ? compareSelect.value : null;

            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);
            const gameName = dataRow ? dataRow.dataset.game : null;

            if (!gameName || !allGameRuns[gameName]) return;

            const gameRuns = allGameRuns[gameName];

            // Parse primary run FROM allGameRuns
            const runIndex = parseInt(runValue.split(':')[1]);
            const runData1 = gameRuns[runIndex];
            const run1 = runData1.run;

            if (!run1 || !run1.frametimes || run1.frametimes.length === 0) {{
                const ctx = document.getElementById('chart-' + rowId);
                if (ctx) {{
                    ctx.parentElement.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 40px;">No frametime data available</p>';
                }}
                return;
            }}

            const ctx = document.getElementById('chart-' + rowId);
            if (!ctx) return;

            if (charts[rowId]) {{
                charts[rowId].destroy();
            }}

            // Build datasets
            const datasets = [];

            // Primary run
            const frametimes1 = run1.frametimes;
            const fps1 = frametimes1.map(ft => 1000.0 / ft);
            const labels = frametimes1.map((_, i) => (i * 10 / 60).toFixed(1));

            datasets.push({{
                label: `${{runData1.resolution}} @ ${{runData1.os}}`,
                data: fps1,
                borderColor: '#4fc3f7',
                backgroundColor: 'rgba(79, 195, 247, 0.1)',
                borderWidth: 2,
                tension: 0.1,
                pointRadius: 0,
                fill: compareValue === null
            }});

            // Comparison run (from game-wide data)
            if (compareValue !== null && gameName && allGameRuns[gameName]) {{
                const gameRuns = allGameRuns[gameName];
                const compareIndex = parseInt(compareValue.split(':')[1]);
                const runData = gameRuns[compareIndex];
                const run2 = runData.run;

                if (run2 && run2.frametimes) {{
                    const frametimes2 = run2.frametimes;
                    const fps2 = frametimes2.map(ft => 1000.0 / ft);

                    datasets.push({{
                        label: `${{runData.resolution}} @ ${{runData.os}}`,
                        data: fps2,
                        borderColor: '#ff9800',
                        backgroundColor: 'rgba(255, 152, 0, 0.1)',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0,
                        fill: false
                    }});
                }}
            }}

            // Add FPS reference line if one is selected
            const fpsReferenceSelect = document.getElementById('fps-reference-' + rowId);
            if (fpsReferenceSelect && fpsReferenceSelect.value) {{
                const numPoints = labels.length;
                const selectedFps = parseInt(fpsReferenceSelect.value);

                // Define colors for different FPS levels
                const fpsColors = {{
                    60: '#ffc107',   // Yellow
                    120: '#b388ff',  // Purple
                    144: '#4fc3f7',  // Cyan
                    180: '#ff6b9d',  // Pink
                    240: '#00d26a',  // Green
                    360: '#ff9800'   // Orange
                }};

                datasets.push({{
                    label: selectedFps + ' FPS',
                    data: new Array(numPoints).fill(selectedFps),
                    borderColor: fpsColors[selectedFps] || '#ffffff',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false,
                    tension: 0
                }});

                // Calculate percentage of time at or above selected FPS
                const mainDataset = datasets[0];  // First dataset is always the main run
                if (mainDataset && mainDataset.data) {{
                    const framesAbove = mainDataset.data.filter(fps => fps >= selectedFps).length;
                    const totalFrames = mainDataset.data.length;
                    const percentage = totalFrames > 0 ? (framesAbove / totalFrames * 100).toFixed(1) : 0;

                    const percentageSpan = document.getElementById('fps-percentage-' + rowId);
                    if (percentageSpan) {{
                        percentageSpan.textContent = `(≥ ${{selectedFps}} FPS: ${{percentage}}%)`;
                        percentageSpan.style.color = fpsColors[selectedFps] || '#ffffff';
                        percentageSpan.style.fontWeight = 'bold';
                    }}
                }}
            }} else {{
                // Clear percentage display if no FPS reference selected
                const percentageSpan = document.getElementById('fps-percentage-' + rowId);
                if (percentageSpan) {{
                    percentageSpan.textContent = '';
                }}
            }}

            charts[rowId] = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: datasets
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: compareValue !== null || (fpsReferenceSelect && fpsReferenceSelect.value),
                            labels: {{
                                color: '#eaeaea',
                                padding: 10,
                                boxWidth: 40,
                                font: {{ size: 12 }},
                                usePointStyle: false
                            }}
                        }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false,
                            callbacks: {{
                                title: ctx => 'Zeit: ' + ctx[0].label + 's',
                                label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + ' FPS'
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            grid: {{ color: 'rgba(255,255,255,0.1)' }},
                            ticks: {{ color: '#a0a0a0', maxTicksLimit: 10 }},
                            title: {{ display: true, text: 'Time (Seconds)', color: '#a0a0a0' }}
                        }},
                        y: {{
                            grid: {{ color: 'rgba(255,255,255,0.1)' }},
                            ticks: {{ color: '#a0a0a0' }},
                            title: {{ display: true, text: 'FPS', color: '#a0a0a0' }}
                        }}
                    }}
                }}
            }});

            // Update comparison metrics table
            updateComparisonMetrics(rowId);

            // Update stats display with selected run's metrics
            const fps = run1.metrics?.fps || {{}};
            const stutterData = run1.metrics?.stutter || {{}};
            const framePacing = run1.metrics?.frame_pacing || {{}};

            // Update FPS values
            const avgEl = document.getElementById('stat-avg-' + rowId);
            const low1El = document.getElementById('stat-low1-' + rowId);
            const low01El = document.getElementById('stat-low01-' + rowId);

            if (avgEl) avgEl.textContent = (fps.average || 0).toFixed(0);
            if (low1El) low1El.textContent = (fps['1_percent_low'] || 0).toFixed(0);
            if (low01El) low01El.textContent = (fps['0.1_percent_low'] || 0).toFixed(0);

            // Update Stutter - preserve tooltip, update text and class
            const stutterEl = document.getElementById('stat-stutter-' + rowId);
            if (stutterEl) {{
                const stutterRating = stutterData.stutter_rating || 'unknown';
                // Update the class for color
                stutterEl.className = 'tooltip-wrapper stutter-' + stutterRating;
                // Update the text (first text node before tooltip)
                const textNode = stutterEl.firstChild;
                if (textNode && textNode.nodeType === Node.TEXT_NODE) {{
                    textNode.textContent = stutterRating.charAt(0).toUpperCase() + stutterRating.slice(1);
                }}
            }}

            // Update Consistency - preserve tooltip, update text and class
            const consistencyEl = document.getElementById('stat-consistency-' + rowId);
            if (consistencyEl) {{
                const consistencyRating = framePacing.consistency_rating || 'unknown';
                // Update the class for color
                consistencyEl.className = 'tooltip-wrapper stutter-' + consistencyRating;
                // Update the text (first text node before tooltip)
                const textNode = consistencyEl.firstChild;
                if (textNode && textNode.nodeType === Node.TEXT_NODE) {{
                    textNode.textContent = consistencyRating.charAt(0).toUpperCase() + consistencyRating.slice(1);
                }}
            }}

            // Update system info (GPU, Mesa, OS, Resolution)
            const gpuEl = document.getElementById('stat-gpu-' + rowId);
            const mesaEl = document.getElementById('stat-mesa-' + rowId);
            const osEl = document.getElementById('stat-os-' + rowId);
            const resEl = document.getElementById('stat-res-' + rowId);

            if (gpuEl) gpuEl.textContent = runData1.gpu || 'Unknown';
            if (mesaEl) mesaEl.textContent = runData1.mesa || 'Unknown';
            if (osEl) osEl.textContent = runData1.os || 'Unknown';
            if (resEl) resEl.textContent = runData1.resolution || 'Unknown';

            // Update header title
            const headerEl = document.querySelector(`#detail-${{rowId}} .detail-header h3`);
            if (headerEl) {{
                headerEl.textContent = `${{gameName}} - ${{runData1.resolution}} @ ${{runData1.os}}`;
            }}
        }}

        function updateComparisonMetrics(rowId) {{
            const compareSelect = document.getElementById('compare-' + rowId);
            const compareValue = compareSelect && compareSelect.value !== '' ? compareSelect.value : null;

            const statsDiv = document.getElementById('comparison-stats-' + rowId);
            const tbody = document.getElementById('comparison-body-' + rowId);

            // Hide if no comparison
            if (compareValue === null) {{
                statsDiv.style.display = 'none';
                return;
            }}

            // Show comparison stats
            statsDiv.style.display = 'block';

            const dataRow = document.querySelector(`tr.data-row[onclick*="${{rowId}}"]`);
            const gameName = dataRow ? dataRow.dataset.game : null;

            if (!gameName || !allGameRuns[gameName]) return;

            const gameRuns = allGameRuns[gameName];

            // Parse indices FROM allGameRuns (beide!)
            const selectEl = document.getElementById('select-' + rowId);
            const runValue = selectEl.value;
            const runIndex = parseInt(runValue.split(':')[1]);
            const run1 = gameRuns[runIndex].run;

            const compareIndex = parseInt(compareValue.split(':')[1]);
            const run2 = gameRuns[compareIndex].run;

            if (!run1 || !run2 || !run1.metrics || !run2.metrics) {{
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No metrics available</td></tr>';
                return;
            }}

            // Extract metrics
            const fps1 = run1.metrics.fps || {{}};
            const fps2 = run2.metrics.fps || {{}};

            const metrics = [
                {{
                    name: 'AVG FPS',
                    val1: fps1.average || 0,
                    val2: fps2.average || 0,
                    higherIsBetter: true
                }},
                {{
                    name: '1% Low',
                    val1: fps1['1_percent_low'] || 0,
                    val2: fps2['1_percent_low'] || 0,
                    higherIsBetter: true
                }},
                {{
                    name: '0.1% Low',
                    val1: fps1['0.1_percent_low'] || 0,
                    val2: fps2['0.1_percent_low'] || 0,
                    higherIsBetter: true
                }}
            ];

            // Build table rows
            let html = '';
            metrics.forEach(metric => {{
                const diff = metric.val2 - metric.val1;
                const diffPercent = metric.val1 !== 0 ? (diff / metric.val1) * 100 : 0;

                let diffClass = 'diff-neutral';
                let diffText = '—';

                if (Math.abs(diffPercent) >= 0.5) {{
                    const isPositive = metric.higherIsBetter ? diff > 0 : diff < 0;
                    diffClass = isPositive ? 'diff-positive' : 'diff-negative';
                    const sign = diff > 0 ? '+' : '';
                    diffText = `${{sign}}${{diff.toFixed(1)}} (${{sign}}${{diffPercent.toFixed(1)}}%)`;
                }}

                html += `
                    <tr>
                        <td>${{metric.name}}</td>
                        <td>${{metric.val1.toFixed(1)}}</td>
                        <td>${{metric.val2.toFixed(1)}}</td>
                        <td class="${{diffClass}}">${{diffText}}</td>
                    </tr>
                `;
            }});

            tbody.innerHTML = html;
        }}

        // Table sorting
        let currentSort = {{ column: -1, ascending: true }};

        function sortTable(columnIndex, type) {{
            const table = document.getElementById('benchmark-body');
            const rows = Array.from(table.querySelectorAll('tr.data-row'));

            // Determine sort direction
            if (currentSort.column === columnIndex) {{
                currentSort.ascending = !currentSort.ascending;
            }} else {{
                currentSort.column = columnIndex;
                currentSort.ascending = true;
            }}

            // Sort rows
            rows.sort((a, b) => {{
                let aVal = a.cells[columnIndex].textContent.trim();
                let bVal = b.cells[columnIndex].textContent.trim();

                // Extract numeric value if type is number
                if (type === 'number') {{
                    aVal = parseFloat(aVal) || 0;
                    bVal = parseFloat(bVal) || 0;
                }} else {{
                    // For text, case-insensitive comparison
                    aVal = aVal.toLowerCase();
                    bVal = bVal.toLowerCase();
                }}

                let comparison = 0;
                if (aVal < bVal) comparison = -1;
                if (aVal > bVal) comparison = 1;

                return currentSort.ascending ? comparison : -comparison;
            }});

            // Clear and re-append rows (maintains detail rows association)
            rows.forEach(row => {{
                const rowId = row.getAttribute('onclick').match(/'([^']+)'/)[1];
                const detailRow = document.getElementById('detail-' + rowId);

                table.appendChild(row);
                if (detailRow) {{
                    table.appendChild(detailRow);
                }}
            }});

            // Update sort arrow indicators
            document.querySelectorAll('th .sort-arrow').forEach((arrow, idx) => {{
                arrow.className = 'sort-arrow';
                if (idx === columnIndex) {{
                    arrow.className = currentSort.ascending ? 'sort-arrow asc' : 'sort-arrow desc';
                }}
            }});
        }}
    </script>
</body>
</html>
'''

    output_path.write_text(html)
    return output_path
