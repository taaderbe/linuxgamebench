"""
CLI interface for Linux Game Benchmark.

Commands:
    lgb scan       - Scan Steam library for installed games
    lgb list       - List installed games
    lgb info       - Show system information
    lgb benchmark  - Run benchmark for a game
    lgb analyze    - Analyze existing MangoHud logs
    lgb report     - Generate report from benchmark results
"""

import re
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Dict, Optional
from pathlib import Path

from linux_game_benchmark import __version__


# Helper functions for normalizing hardware names before upload
def _short_gpu(name: str) -> str:
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


def _short_cpu(name: str) -> str:
    """Shorten CPU name for consistent storage."""
    if not name:
        return "Unknown"
    # AMD Ryzen: "AMD Ryzen 7 9800X3D 8-Core Processor" → "Ryzen 7 9800X3D"
    m = re.search(r'Ryzen\s*(\d)\s*(\d{4}X3D|\d{4}X|\d{4})', name, re.I)
    if m:
        return f"Ryzen {m.group(1)} {m.group(2)}"
    # Intel Core: "Intel Core i7-13700K" → "i7-13700K"
    m = re.search(r'(i[3579]-\d{4,5}\w*)', name, re.I)
    if m:
        return m.group(1)
    # Intel Core Ultra: "Intel Core Ultra 7 155H" → "Ultra 7 155H"
    m = re.search(r'Ultra\s*(\d)\s*(\d{3}\w*)', name, re.I)
    if m:
        return f"Ultra {m.group(1)} {m.group(2)}"
    # Fallback: truncate to 30 chars
    return name[:30] if len(name) > 30 else name


def _short_kernel(kernel: str) -> str:
    """Normalize kernel version - remove distro suffix."""
    if not kernel:
        return "Unknown"
    # "6.18.3-2-MANJARO" → "6.18.3-2"
    # "6.18.2-cachyos" → "6.18.2"
    # "6.8.0-51-generic" → "6.8.0-51"
    match = re.match(r'^(\d+\.\d+\.\d+(?:-\d+)?)', kernel)
    if match:
        return match.group(1)
    return kernel


def _short_os(os_name: str) -> str:
    """Normalize OS name - remove desktop environment suffix."""
    if not os_name:
        return "Unknown"
    # "CachyOS Linux (KDE Plasma)" → "CachyOS Linux"
    # "Fedora Linux 40 (Workstation Edition)" → "Fedora Linux 40"
    return re.sub(r'\s*\([^)]+\)\s*$', '', os_name).strip()


def _normalize_resolution(res: str) -> str:
    """Normalize resolution to pixel format."""
    if not res:
        return "1920x1080"
    mapping = {
        "HD": "1280x720", "FHD": "1920x1080",
        "WQHD": "2560x1440", "UWQHD": "3440x1440", "UHD": "3840x2160"
    }
    return mapping.get(res.upper(), res)


def _select_gpu_for_benchmark(system_info: dict, console: "Console", log_gpu: str = None) -> dict:
    """
    Get GPU info for benchmark upload.

    Server uses MangoHud log GPU as authoritative source, so no user selection needed.
    This function just formats the GPU info from the log or falls back to lspci.

    Args:
        system_info: Current system info dict
        console: Rich console for output
        log_gpu: GPU name from MangoHud log (authoritative source)

    Returns:
        Modified system_info dict with GPU info.
    """
    from linux_game_benchmark.system.hardware_info import detect_all_gpus, get_gpu_info

    # If we have a valid log GPU, use it directly
    if log_gpu and "VGA" not in log_gpu.upper() and "controller" not in log_gpu.lower():
        clean_name = log_gpu.split("(")[0].strip()
        console.print(f"[dim]GPU: {clean_name}[/dim]")

        # Get base GPU info (for driver version etc.)
        gpu_info = get_gpu_info()
        gpu_info["model"] = clean_name

        new_info = system_info.copy()
        new_info["gpu"] = gpu_info
        return new_info

    # Fallback: use lspci detection (prefer dGPU)
    gpus = detect_all_gpus()
    if gpus:
        # Prefer discrete GPU
        selected = next((g for g in gpus if g["is_dgpu"]), gpus[0])
        console.print(f"[dim]GPU: {selected['display_name']}[/dim]")
        return _apply_gpu_selection(system_info, selected, log_gpu)

    # No GPU detected - use existing system_info
    return system_info


def _apply_gpu_selection(system_info: dict, selected_gpu: dict, log_gpu: str = None) -> dict:
    """Apply selected GPU to system_info dict.

    Args:
        system_info: Current system info dict
        selected_gpu: Selected GPU from detect_all_gpus()
        log_gpu: GPU name from MangoHud log (most accurate source)
    """
    # Get detailed GPU info for the selected GPU
    from linux_game_benchmark.system.hardware_info import get_gpu_info

    # Get current GPU info as base (has driver info, etc.)
    gpu_info = get_gpu_info()

    # Prefer MangoHud log GPU name (most accurate - shows actual GPU model)
    # Example: "AMD Radeon RX 7900 XTX (RADV NAVI31)"
    # lspci shows all variants: "Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M"
    if log_gpu and "VGA" not in log_gpu.upper() and "controller" not in log_gpu.lower():
        # Clean up log_gpu: remove driver info in parentheses
        # "AMD Radeon RX 7900 XTX (RADV NAVI31)" → "AMD Radeon RX 7900 XTX"
        clean_log_gpu = log_gpu.split("(")[0].strip()
        if clean_log_gpu:
            gpu_info["model"] = clean_log_gpu
            gpu_info["vendor"] = selected_gpu["vendor"]
    else:
        # Fallback: use detect_all_gpus() model (may have all variants)
        gpu_info["model"] = f"{selected_gpu['vendor']} {selected_gpu['model']}"
        gpu_info["vendor"] = selected_gpu["vendor"]

    # Create new system_info with updated GPU
    new_info = system_info.copy()
    new_info["gpu"] = gpu_info
    return new_info


app = typer.Typer(
    name="lgb",
    help="Linux Game Benchmark - Automated gaming benchmark tool",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"[bold blue]Linux Game Benchmark[/bold blue] v{__version__}")
        raise typer.Exit()


def require_latest_version() -> None:
    """
    Require latest client version for upload commands.

    Checks server version and forces update if outdated.
    Exits if user declines update.
    """
    import subprocess
    from linux_game_benchmark.api.client import check_for_updates

    try:
        new_version = check_for_updates()
        if new_version:
            console.print(
                f"\n[bold red]Update required![/bold red] "
                f"v{new_version} available [dim](current: v{__version__})[/dim]"
            )
            console.print("[dim]Upload requires latest version for data quality.[/dim]\n")

            if typer.confirm("Update now?", default=True):
                console.print("[dim]Updating...[/dim]")
                try:
                    subprocess.run(["pipx", "uninstall", "linux-game-benchmark"], check=True)
                    subprocess.run(["pipx", "install", "git+https://github.com/taaderbe/linuxgamebench.git"], check=True)
                    console.print("[green]Update complete![/green]")
                    console.print("[yellow]Please run the command again.[/yellow]")
                except subprocess.CalledProcessError as e:
                    console.print(f"[red]Update failed: {e}[/red]")
                    console.print("[dim]Try manually: pipx upgrade linux-game-benchmark[/dim]")
                raise typer.Exit(0)
            else:
                console.print("[red]Upload requires latest version. Exiting.[/red]")
                raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception:
        # Can't check version (offline/server down)
        # Continue anyway - upload will fail if server unreachable
        pass


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """
    Linux Game Benchmark - Automated gaming benchmark tool.

    Measures FPS, stutter, frame pacing and more for Steam games.
    """
    # Check for updates
    try:
        from linux_game_benchmark.api.client import check_for_updates
        import subprocess
        new_version = check_for_updates()
        if new_version:
            console.print(
                f"[yellow]Update available: v{new_version}[/yellow] "
                f"[dim](current: v{__version__})[/dim]"
            )
            if typer.confirm("Do you want to update now?", default=True):
                console.print("[dim]Updating...[/dim]")
                subprocess.run(["pipx", "uninstall", "linux-game-benchmark"], check=True)
                subprocess.run(["pipx", "install", "git+https://github.com/taaderbe/linuxgamebench.git"], check=True)
                console.print("[green]Update complete![/green]")
                raise typer.Exit()
            console.print()
    except typer.Exit:
        raise
    except Exception:
        pass  # Silently ignore update check failures


@app.command()
def login(
    email: Optional[str] = typer.Option(
        None,
        "--email",
        "-e",
        help="Email address",
    ),
) -> None:
    """
    Login to Linux Game Bench.

    Authenticate with your email and password.
    Register at https://linuxgamebench.com/register
    """
    from linux_game_benchmark.api.auth import login as auth_login, get_status
    from linux_game_benchmark.config.settings import settings

    # Show current stage
    console.print(f"[dim]Server: {settings.API_BASE_URL}[/dim]\n")

    # Get email if not provided
    if not email:
        email = typer.prompt("Email")

    # Get password (hidden)
    password = typer.prompt("Password", hide_input=True)

    console.print("[dim]Logging in...[/dim]")

    success, message = auth_login(email, password)

    if success:
        console.print(f"[bold green]{message}[/bold green]")
        status = get_status()
        if status.get("user", {}).get("email_verified") is False:
            console.print("[yellow]Note: Your email is not verified yet.[/yellow]")
    else:
        console.print(f"[bold red]{message}[/bold red]")
        raise typer.Exit(1)


@app.command()
def logout() -> None:
    """
    Logout from Linux Game Bench.

    Clears stored authentication tokens.
    """
    from linux_game_benchmark.api.auth import logout as auth_logout

    success, message = auth_logout()

    if success:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[yellow]{message}[/yellow]")


@app.command()
def status() -> None:
    """
    Show current login status.

    Displays authenticated user and server information.
    """
    from linux_game_benchmark.api.auth import get_status
    from linux_game_benchmark.config.settings import settings

    status_info = get_status()

    console.print("[bold]Linux Game Bench Status[/bold]\n")

    # Server info
    stage = status_info.get("stage", "prod")
    stage_color = {"dev": "yellow", "rc": "cyan", "preprod": "blue", "prod": "green"}.get(stage, "white")
    console.print(f"[bold]Stage:[/bold] [{stage_color}]{stage}[/{stage_color}]")
    console.print(f"[bold]Server:[/bold] {status_info.get('api_url')}")

    console.print()

    # Auth status
    if status_info.get("logged_in"):
        # Verify token with server
        from linux_game_benchmark.api.client import verify_auth
        is_valid, msg = verify_auth()

        if is_valid:
            console.print(f"[bold green]Logged in[/bold green] [dim](token valid)[/dim]")
            console.print(f"  [bold]Username:[/bold] {status_info.get('username')}")
            console.print(f"  [bold]Email:[/bold] {status_info.get('email')}")

            user = status_info.get("user", {})
            if user.get("email_verified"):
                console.print(f"  [bold]Verified:[/bold] [green]Yes[/green]")
            else:
                console.print(f"  [bold]Verified:[/bold] [yellow]No[/yellow]")
        else:
            console.print(f"[bold red]Session expired[/bold red]")
            console.print(f"  [dim]{msg}[/dim]")
            console.print(f"\n[yellow]Please login again: lgb login[/yellow]")
    else:
        console.print(f"[yellow]Not logged in[/yellow]")
        console.print(f"\n[dim]Login with: lgb login[/dim]")
        console.print(f"[dim]Register at: https://linuxgamebench.com/register[/dim]")


@app.command()
def config(
    stage: Optional[str] = typer.Option(
        None,
        "--stage",
        "-s",
        help="Set server stage (dev, rc, preprod, prod)",
    ),
) -> None:
    """
    Configure client settings.

    Set the server stage to use for all commands.
    """
    from linux_game_benchmark.config.settings import settings

    if stage:
        if stage not in settings.STAGES:
            console.print(f"[red]Invalid stage: {stage}[/red]")
            console.print(f"[dim]Valid stages: {', '.join(settings.STAGES.keys())}[/dim]")
            raise typer.Exit(1)

        if settings.set_stage(stage):
            stage_color = {"dev": "yellow", "rc": "cyan", "preprod": "blue", "prod": "green"}.get(stage, "white")
            console.print(f"[green]Stage set to:[/green] [{stage_color}]{stage}[/{stage_color}]")
            console.print(f"[dim]Server: {settings.STAGES[stage]}[/dim]")
        else:
            console.print(f"[red]Failed to set stage[/red]")
            raise typer.Exit(1)
    else:
        # Show current config
        console.print("[bold]Current Configuration[/bold]\n")
        stage = settings.CURRENT_STAGE
        stage_color = {"dev": "yellow", "rc": "cyan", "preprod": "blue", "prod": "green"}.get(stage, "white")
        console.print(f"[bold]Stage:[/bold] [{stage_color}]{stage}[/{stage_color}]")
        console.print(f"[bold]Server:[/bold] {settings.API_BASE_URL}")
        console.print(f"\n[dim]Change with: lgb config --stage dev[/dim]")


@app.command()
def settings() -> None:
    """
    Configure default values for benchmark prompts.

    Set default resolution, upload choice, and continue/end behavior.
    """
    from linux_game_benchmark.config.preferences import preferences

    while True:
        console.print("\n[bold]Current Settings[/bold]\n")

        # Show current settings with defaults highlighted
        res = preferences.resolution
        res_name = preferences.get_resolution_name()
        upload = preferences.upload.upper()
        cont = preferences.continue_session.upper()

        console.print(f"  [1] Default Resolution: [bold green]{res_name}[/bold green]")
        console.print(f"  [2] Default Upload:     [bold green]{upload}[/bold green]")
        console.print(f"  [3] Default Continue:   [bold green]{cont}[/bold green]")
        console.print(f"  [4] Reset to defaults")
        console.print(f"  [0] Back")

        try:
            choice = typer.prompt("\nSelect option", default="0").strip()
        except:
            break

        if choice == "0":
            break
        elif choice == "1":
            console.print("\n[bold]Select default resolution:[/bold]")
            console.print("  [1] HD    (1280x720)")
            console.print("  [2] FHD   (1920x1080)")
            console.print("  [3] WQHD  (2560x1440)")
            console.print("  [4] UWQHD (3440x1440)")
            console.print("  [5] UHD   (3840x2160)")
            try:
                new_res = typer.prompt("Resolution [1-5]", default=res).strip()
                if new_res in ("1", "2", "3", "4", "5"):
                    preferences.resolution = new_res
                    console.print(f"[green]Set to: {preferences.get_resolution_name()}[/green]")
            except:
                pass
        elif choice == "2":
            console.print("\n[bold]Default upload choice:[/bold]")
            console.print("  [Y] Yes - upload by default")
            console.print("  [N] No - don't upload by default")
            try:
                new_upload = typer.prompt("Upload [Y/N]", default=upload).strip().lower()
                if new_upload in ("y", "n"):
                    preferences.upload = new_upload
                    console.print(f"[green]Set to: {new_upload.upper()}[/green]")
            except:
                pass
        elif choice == "3":
            console.print("\n[bold]After recording, default to:[/bold]")
            console.print("  [C] Continue - record another benchmark")
            console.print("  [E] End - finish session")
            try:
                new_cont = typer.prompt("Continue [C/E]", default=cont).strip().lower()
                if new_cont in ("c", "e"):
                    preferences.continue_session = new_cont
                    console.print(f"[green]Set to: {new_cont.upper()}[/green]")
            except:
                pass
        elif choice == "4":
            preferences.reset()
            console.print("[green]Reset to defaults[/green]")


@app.command()
def scan(
    steam_path: Optional[Path] = typer.Option(
        None,
        "--steam-path",
        "-s",
        help="Path to Steam installation (auto-detected if not specified)",
    ),
) -> None:
    """
    Scan Steam library for installed games.

    Finds all installed Steam games and caches the information.
    """
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner

    console.print("[bold]Scanning Steam library...[/bold]")

    try:
        scanner = SteamLibraryScanner(steam_path)
        games = scanner.scan()

        console.print(f"\n[green]Found {len(games)} installed games.[/green]")

        # Show games with builtin benchmarks
        builtin = [g for g in games if g.get("has_builtin_benchmark")]
        if builtin:
            console.print(f"[cyan]{len(builtin)} games have builtin benchmarks.[/cyan]")

    except Exception as e:
        console.print(f"[red]Error scanning Steam library: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_games(
    proton_only: bool = typer.Option(
        False,
        "--proton",
        "-p",
        help="Only show Proton/Windows games",
    ),
    native_only: bool = typer.Option(
        False,
        "--native",
        "-n",
        help="Only show native Linux games",
    ),
) -> None:
    """
    List installed Steam games.

    Shows all games found in the Steam library with optional filtering.
    """
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner

    scanner = SteamLibraryScanner()

    try:
        games = scanner.scan()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Run 'lgb scan' first to scan your Steam library.")
        raise typer.Exit(1)

    # Apply filters
    if proton_only:
        games = [g for g in games if g.get("requires_proton")]
    if native_only:
        games = [g for g in games if not g.get("requires_proton")]

    if not games:
        console.print("[yellow]No games found matching the criteria.[/yellow]")
        raise typer.Exit(0)

    # Create table
    table = Table(title="Installed Games")
    table.add_column("App ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="green")

    for game in sorted(games, key=lambda x: x.get("name", "")):
        game_type = "Proton" if game.get("requires_proton") else "Native"
        table.add_row(
            str(game.get("app_id", "?")),
            game.get("name", "Unknown"),
            game_type,
        )

    console.print(table)
    console.print(f"\nTotal: {len(games)} games")


def _check_mangohud_global_config() -> bool:
    """Check if MangoHud is globally enabled."""
    env_dir = Path.home() / ".config" / "environment.d"
    mangohud_conf = env_dir / "mangohud.conf"

    if mangohud_conf.exists():
        content = mangohud_conf.read_text()
        if "MANGOHUD=1" in content:
            return True
    return False


def _enable_mangohud_globally() -> bool:
    """Enable MangoHud globally via environment.d."""
    env_dir = Path.home() / ".config" / "environment.d"
    mangohud_conf = env_dir / "mangohud.conf"

    try:
        env_dir.mkdir(parents=True, exist_ok=True)

        # Append or create
        if mangohud_conf.exists():
            content = mangohud_conf.read_text()
            if "MANGOHUD=1" not in content:
                with open(mangohud_conf, "a") as f:
                    f.write("\nMANGOHUD=1\n")
        else:
            mangohud_conf.write_text("MANGOHUD=1\n")

        return True
    except Exception as e:
        console.print(f"[red]Error enabling MangoHud: {e}[/red]")
        return False


@app.command()
def check() -> None:
    """
    Check system requirements for benchmarking.

    Verifies MangoHud, Steam and other tools are available.
    Automatically enables MangoHud globally if not configured.
    """
    from linux_game_benchmark.mangohud.manager import check_mangohud_installation
    import shutil

    console.print("[bold]Checking system requirements...[/bold]\n")

    all_good = True

    # MangoHud
    mangohud = check_mangohud_installation()
    if mangohud["installed"]:
        console.print(f"[green]MangoHud:[/green] {mangohud.get('version', 'Installed')}")

        # Check if MangoHud is globally enabled
        if _check_mangohud_global_config():
            console.print("[green]MangoHud Global:[/green] Enabled (MANGOHUD=1)")
        else:
            console.print("[yellow]MangoHud Global:[/yellow] Not enabled")
            console.print("  MangoHud needs to be enabled globally for benchmarks to work.")

            if typer.confirm("  Enable MangoHud globally now?", default=True):
                if _enable_mangohud_globally():
                    console.print("[green]  ✓ MangoHud enabled globally![/green]")
                    console.print("[yellow]  → Log out and back in (or reboot) for changes to take effect.[/yellow]")
                else:
                    console.print("[red]  ✗ Failed to enable MangoHud[/red]")
    else:
        console.print("[red]MangoHud:[/red] Not installed")
        console.print("  Install: sudo pacman -S mangohud (Arch) / apt install mangohud (Debian)")
        all_good = False

    # Steam
    steam_path = shutil.which("steam")
    if steam_path:
        console.print(f"[green]Steam:[/green] {steam_path}")
    else:
        console.print("[red]Steam:[/red] Not found in PATH")
        all_good = False

    # Check for required tools
    for tool in ["lspci", "glxinfo", "vulkaninfo"]:
        if shutil.which(tool):
            console.print(f"[green]{tool}:[/green] Available")
        else:
            console.print(f"[yellow]{tool}:[/yellow] Not found (some info may be unavailable)")

    console.print()
    if all_good:
        console.print("[bold green]All required components are installed![/bold green]")
    else:
        console.print("[bold red]Some required components are missing.[/bold red]")
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """
    Show system information.

    Displays GPU, CPU, RAM, OS, drivers and other relevant info.
    """
    from linux_game_benchmark.system.hardware_info import get_system_info

    console.print("[bold]Gathering system information...[/bold]\n")

    try:
        info = get_system_info()
    except Exception as e:
        console.print(f"[red]Error gathering system info: {e}[/red]")
        raise typer.Exit(1)

    # OS Info
    os_panel = Panel(
        f"""[bold]OS:[/bold] {info.get('os', {}).get('name', 'Unknown')}
[bold]Kernel:[/bold] {info.get('os', {}).get('kernel', 'Unknown')}
[bold]Desktop:[/bold] {info.get('os', {}).get('desktop', 'Unknown')}
[bold]Display Server:[/bold] {info.get('os', {}).get('display_server', 'Unknown')}""",
        title="System",
        border_style="blue",
    )
    console.print(os_panel)

    # GPU Info
    gpu = info.get("gpu", {})
    gpu_panel = Panel(
        f"""[bold]Model:[/bold] {gpu.get('model', 'Unknown')}
[bold]VRAM:[/bold] {gpu.get('vram_mb', 0)} MB
[bold]Driver:[/bold] {gpu.get('driver', 'Unknown')} {gpu.get('driver_version', '')}
[bold]Vulkan:[/bold] {gpu.get('vulkan_version', 'Unknown')}""",
        title="GPU",
        border_style="green",
    )
    console.print(gpu_panel)

    # CPU Info
    cpu = info.get("cpu", {})
    cpu_panel = Panel(
        f"""[bold]Model:[/bold] {cpu.get('model', 'Unknown')}
[bold]Cores:[/bold] {cpu.get('cores', 0)} ({cpu.get('threads', 0)} threads)
[bold]Frequency:[/bold] {cpu.get('base_clock_mhz', 0)} MHz (base)""",
        title="CPU",
        border_style="yellow",
    )
    console.print(cpu_panel)

    # RAM Info
    ram = info.get("ram", {})
    console.print(f"\n[bold]RAM:[/bold] {ram.get('total_gb', 0):.1f} GB")

    # Steam/Proton Info
    steam = info.get("steam", {})
    if steam:
        console.print(f"\n[bold]Steam Path:[/bold] {steam.get('path', 'Not found')}")
        protons = steam.get("proton_versions", [])
        if protons:
            console.print(f"[bold]Proton Versions:[/bold] {', '.join(protons[:5])}")


@app.command()
def benchmark(
    game: str = typer.Argument(
        ...,
        help="Game App ID or name to benchmark",
    ),
    show_hud: bool = typer.Option(
        True,
        "--show-hud/--no-hud",
        help="Show MangoHud overlay during benchmark",
    ),
    duration: int = typer.Option(
        300,
        "--duration",
        "-d",
        help="Recording duration in seconds (max 300 = 5 min)",
    ),
    resolution: Optional[str] = typer.Option(
        None, "--resolution", "-r",
        help="Resolution (HD/FHD/WQHD/UWQHD/UHD or 1920x1080 format). Skip interactive prompt.",
    ),
    # Game Settings (all optional)
    preset: Optional[str] = typer.Option(
        None, "--preset",
        help="Graphics preset (low/medium/high/ultra/custom)",
    ),
    raytracing: Optional[str] = typer.Option(
        None, "--raytracing",
        help="Ray tracing (off/low/medium/high/ultra/pathtracing)",
    ),
    upscaling: Optional[str] = typer.Option(
        None, "--upscaling",
        help="Upscaling (none/fsr1/fsr2/fsr3/fsr4/dlss2/dlss3/dlss3.5/dlss4/dlss4.5/xess1/xess2)",
    ),
    upscaling_quality: Optional[str] = typer.Option(
        None, "--upscaling-quality",
        help="Upscaling quality (performance/balanced/quality/ultra-quality)",
    ),
    framegen: Optional[str] = typer.Option(
        None, "--framegen",
        help="Frame generation (off/fsr3-fg/dlss3-fg/afmf/afmf2)",
    ),
    aa: Optional[str] = typer.Option(
        None, "--aa",
        help="Anti-aliasing (none/fxaa/smaa/taa/dlaa)",
    ),
    hdr: Optional[str] = typer.Option(
        None, "--hdr",
        help="HDR (on/off)",
    ),
    vsync: Optional[str] = typer.Option(
        None, "--vsync",
        help="VSync (on/off)",
    ),
    framelimit: Optional[str] = typer.Option(
        None, "--framelimit",
        help="Frame limit (none/30/60/120/144/165/180/240)",
    ),
    cpu_oc: Optional[str] = typer.Option(
        None, "--cpu-oc",
        help="CPU overclock (yes/no)",
    ),
    cpu_oc_info: Optional[str] = typer.Option(
        None, "--cpu-oc-info",
        help="CPU OC details (e.g. '5.0GHz')",
    ),
    gpu_oc: Optional[str] = typer.Option(
        None, "--gpu-oc",
        help="GPU overclock (yes/no)",
    ),
    gpu_oc_info: Optional[str] = typer.Option(
        None, "--gpu-oc-info",
        help="GPU OC details (e.g. '+150core +100mem')",
    ),
) -> None:
    """
    Run benchmark for a game.

    Starts the game and allows multiple benchmark recordings with Shift+F2.
    After each recording, you can choose to continue or end the session.
    """
    # Build game_settings dict from CLI parameters (once, at start)
    game_settings: Dict[str, str] = {}
    if preset:
        game_settings['game_preset'] = preset
    if raytracing:
        game_settings['ray_tracing'] = raytracing
    if upscaling:
        game_settings['upscaling'] = upscaling
    if upscaling_quality:
        game_settings['upscaling_quality'] = upscaling_quality
    if framegen:
        game_settings['frame_generation'] = framegen
    if aa:
        game_settings['anti_aliasing'] = aa
    if hdr:
        game_settings['hdr'] = hdr
    if vsync:
        game_settings['vsync'] = vsync
    if framelimit:
        game_settings['frame_limit'] = framelimit
    if cpu_oc:
        game_settings['cpu_overclock'] = cpu_oc
    if cpu_oc_info:
        game_settings['cpu_overclock_info'] = cpu_oc_info
    if gpu_oc:
        game_settings['gpu_overclock'] = gpu_oc
    if gpu_oc_info:
        game_settings['gpu_overclock_info'] = gpu_oc_info

    # Require latest version for upload functionality
    require_latest_version()

    import time
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
    from linux_game_benchmark.benchmark.game_launcher import GameLauncher
    from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
    from linux_game_benchmark.mangohud.manager import check_mangohud_installation
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage, SystemFingerprint
    from linux_game_benchmark.analysis.report_generator import generate_multi_resolution_report
    from linux_game_benchmark.system.hardware_info import get_system_info, detect_discrete_gpu_pci
    from linux_game_benchmark.steam.launch_options import set_launch_options, restore_launch_options
    from linux_game_benchmark.api import upload_benchmark, check_api_status

    # Check MangoHud
    mangohud_info = check_mangohud_installation()
    if not mangohud_info["installed"]:
        console.print("[red]Error: MangoHud is not installed.[/red]")
        console.print("Install with: sudo pacman -S mangohud (Arch) or apt install mangohud (Debian/Ubuntu)")
        raise typer.Exit(1)

    # Find the game
    scanner = SteamLibraryScanner()
    try:
        games = scanner.scan()
    except Exception as e:
        console.print(f"[red]Error scanning Steam library: {e}[/red]")
        raise typer.Exit(1)

    target_game = None
    try:
        app_id = int(game)
        target_game = scanner.get_game_by_id(app_id)
    except ValueError:
        target_game = scanner.get_game_by_name(game)

    if not target_game:
        console.print(f"[red]Game not found: {game}[/red]")
        console.print("Use 'lgb list' to see installed games.")
        raise typer.Exit(1)

    # Header
    console.print(f"\n[bold cyan]╔══════════════════════════════════════════╗[/bold cyan]")
    console.print(f"[bold cyan]║           BENCHMARK SESSION              ║[/bold cyan]")
    console.print(f"[bold cyan]╚══════════════════════════════════════════╝[/bold cyan]\n")
    console.print(f"[bold]Game:[/bold] {target_game['name']}")
    console.print(f"[bold]App ID:[/bold] {target_game['app_id']}\n")

    console.print("[bold yellow]Controls:[/bold yellow]")
    console.print("  [bold red]Shift+F2[/bold red] → START recording")
    console.print("  [bold red]Shift+F2[/bold red] → STOP recording\n")

    # Setup
    system_info = get_system_info()
    storage = BenchmarkStorage()
    mangohud_manager = MangoHudConfigManager()
    output_dir = Path.home() / "benchmark_results" / "benchmark_session"
    output_dir.mkdir(parents=True, exist_ok=True)

    steam_app_id = target_game["app_id"]

    # Cap duration at 5 min max (server limit)
    MAX_DURATION = 300
    if duration > MAX_DURATION:
        console.print(f"[yellow]Duration capped at {MAX_DURATION}s (5 min max)[/yellow]")
        duration = MAX_DURATION

    # Detect discrete GPU for multi-GPU systems
    gpu_pci = detect_discrete_gpu_pci()
    if gpu_pci:
        # Get GPU name from glxinfo (cleaner than lspci which shows all variants)
        gpu_model = system_info.get("gpu", {}).get("model", "")
        if gpu_model and gpu_model != "Unknown":
            console.print(f"[dim]Detected discrete GPU: {gpu_model}[/dim]")
        else:
            console.print(f"[dim]Detected discrete GPU: {gpu_pci}[/dim]")

    # Configure MangoHud for manual logging with auto-stop
    mangohud_manager.backup_config()
    mangohud_manager.set_benchmark_config(
        output_folder=output_dir,
        show_hud=show_hud,
        manual_logging=True,
        log_duration=duration,  # Auto-stop after duration
        gpu_pci_dev=gpu_pci,
    )

    # Set Steam launch options with pci_dev for multi-GPU systems
    try:
        if gpu_pci:
            # Escape colons for MANGOHUD_CONFIG env var (required format)
            pci_escaped = gpu_pci.replace(":", r"\:")
            launch_opts = f'MANGOHUD=1 MANGOHUD_CONFIG="pci_dev={pci_escaped}" %command%'
        else:
            launch_opts = "MANGOHUD=1 %command%"
        set_launch_options(steam_app_id, launch_opts)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not set launch options: {e}[/yellow]")

    # Check/save fingerprint
    fp = SystemFingerprint.from_system_info(system_info)
    if not storage.check_fingerprint(steam_app_id, fp):
        console.print("[yellow]System config changed - archiving old data[/yellow]")
        storage.archive_old_data(steam_app_id)
    storage.save_fingerprint(steam_app_id, fp, system_info)

    # Register game
    from linux_game_benchmark.games.registry import GameRegistry
    registry = GameRegistry(base_dir=storage.base_dir)
    registry.get_or_create(steam_app_id=steam_app_id, display_name=target_game["name"])

    # Track processed logs and recordings
    processed_logs = set()
    for existing in output_dir.glob("*.csv"):
        if "_summary" not in existing.name:
            processed_logs.add(existing.name)

    recordings = []  # Store all recording data for final upload
    active_recording = None  # Track currently recording file

    def get_new_logs():
        """Find new completed log files."""
        new_logs = []
        for log_file in output_dir.glob("*.csv"):
            if "_summary" not in log_file.name and log_file.name not in processed_logs:
                size1 = log_file.stat().st_size
                time.sleep(0.5)
                size2 = log_file.stat().st_size
                if size1 == size2 and size1 > 1000:
                    new_logs.append(log_file)
        return new_logs

    def get_active_recording():
        """Find actively growing log file (recording in progress)."""
        for log_file in output_dir.glob("*.csv"):
            if "_summary" not in log_file.name and log_file.name not in processed_logs:
                size1 = log_file.stat().st_size
                if size1 > 0:
                    time.sleep(0.3)
                    size2 = log_file.stat().st_size
                    if size2 > size1:  # File is growing = active recording
                        return log_file
        return None

    def monitor_recording(log_path: Path) -> None:
        """Monitor active recording with live timer until complete."""
        from rich.live import Live
        from rich.text import Text
        from linux_game_benchmark.benchmark.validation import BenchmarkValidator

        console.print(f"\n[bold red]● Recording started![/bold red]")
        start_time = time.time()
        last_size = 0
        stable_count = 0
        MIN_DURATION = BenchmarkValidator.MIN_DURATION_SECONDS  # 30
        MAX_DURATION = 300  # 5 minutes max
        max_reached = False

        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while stable_count < 1:  # Exit after first stable check
                elapsed = time.time() - start_time

                # Check max duration
                if elapsed >= MAX_DURATION:
                    max_reached = True
                    break

                # Format timer
                if elapsed < 60:
                    timer_text = f"{int(elapsed)}sec"
                else:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    timer_text = f"{mins}m {secs}sec"

                # Color based on minimum duration
                if elapsed < MIN_DURATION:
                    remaining = int(MIN_DURATION - elapsed)
                    style = "bold red"
                    hint = f" (min {remaining}s)"
                else:
                    style = "bold green"
                    hint = " ✓"

                status = Text()
                status.append("● RECORDING ", style="bold red")
                status.append(timer_text, style=style)
                status.append(hint, style="dim")
                status.append(" - Shift+F2 to stop", style="dim")
                live.update(status)

                # Check if file stopped growing
                try:
                    size = log_path.stat().st_size
                    if size == last_size and size > 0:
                        stable_count += 1
                    else:
                        stable_count = 0
                    last_size = size
                except FileNotFoundError:
                    break
                time.sleep(0.25)  # Fast polling - MangoHud writes every frame

        # Immediate feedback
        elapsed = time.time() - start_time
        if elapsed < 60:
            timer_text = f"{int(elapsed)}sec"
        else:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            timer_text = f"{mins}m {secs}sec"

        if max_reached:
            console.print(f"[bold yellow]■ Recording stopped[/bold yellow] ({timer_text}) [yellow]- 5 min max reached[/yellow]")
        else:
            console.print(f"[bold cyan]■ Recording stopped[/bold cyan] ({timer_text})")

    def process_recording(log_path: Path) -> bool:
        """Process a recording. Returns False if user wants to end session."""
        # Capture sched-ext scheduler NOW while game is still running
        # (scheduler might only be active during gaming)
        from linux_game_benchmark.system.hardware_info import detect_sched_ext
        scheduler = detect_sched_ext()

        console.print(f"\n[bold green]═══ Recording complete! ═══[/bold green]")

        try:
            analyzer = FrametimeAnalyzer(log_path)
            metrics = analyzer.analyze()
            fps = metrics.get("fps", {})
            frame_pacing = metrics.get("frame_pacing", {})
            stutter = metrics.get("stutter", {})

            # Get frametimes for validation and upload
            frametimes = analyzer.frametimes if hasattr(analyzer, 'frametimes') else []

            # === VALIDATION: Check if benchmark data is valid ===
            from linux_game_benchmark.benchmark.validation import BenchmarkValidator
            validator = BenchmarkValidator()
            validation = validator.validate(
                frametimes=frametimes,
                fps_avg=fps.get('average'),
                fps_min=fps.get('minimum'),
                fps_max=fps.get('maximum'),
            )

            # Calculate duration
            duration_sec = fps.get('duration_seconds', 0)
            minutes = int(duration_sec // 60)
            seconds = int(duration_sec % 60)
            frames = fps.get('frame_count', 0)

            console.print(f"\n  [bold]Recorded:[/bold] {minutes}m {seconds}s, {frames} frames")
            console.print(f"  [bold]AVG FPS:[/bold] {fps.get('average', 0):.1f}")
            console.print(f"  [bold]1% Low:[/bold] {fps.get('1_percent_low', 0):.1f}")
            console.print(f"  [bold]0.1% Low:[/bold] {fps.get('0.1_percent_low', 0):.1f}")

            # Show validation status
            can_upload = validation.valid
            if validation.errors:
                console.print(f"\n[bold red]✗ Benchmark invalid - upload blocked:[/bold red]")
                for issue in validation.errors:
                    console.print(f"  [red]• {issue.message}[/red]")
            if validation.warnings:
                for issue in validation.warnings:
                    console.print(f"  [yellow]⚠ {issue.message}[/yellow]")

            # 1. Resolution (CLI param or interactive prompt)
            from linux_game_benchmark.config.preferences import preferences
            default_res = preferences.resolution

            resolution_map = {"1": "1280x720", "2": "1920x1080", "3": "2560x1440", "4": "3440x1440", "5": "3840x2160"}
            resolution_names = {"hd": "1280x720", "fhd": "1920x1080", "wqhd": "2560x1440", "uwqhd": "3440x1440", "uhd": "3840x2160"}

            if resolution:
                # CLI --resolution provided, skip interactive prompt
                res_lower = resolution.lower().strip()
                if res_lower in resolution_names:
                    selected_resolution = resolution_names[res_lower]
                elif res_lower in resolution_map:
                    selected_resolution = resolution_map[res_lower]
                elif "x" in res_lower:
                    # Direct pixel format like 1920x1080
                    selected_resolution = resolution
                else:
                    console.print(f"[yellow]Unknown resolution '{resolution}', using FHD[/yellow]")
                    selected_resolution = "1920x1080"
                console.print(f"\n[dim]Resolution: {selected_resolution}[/dim]")
            else:
                # Interactive prompt
                console.print(f"\n[bold]Which resolution was used?[/bold]")
                for key, label in [("1", "HD    (1280×720)"), ("2", "FHD   (1920×1080)"),
                                   ("3", "WQHD  (2560×1440)"), ("4", "UWQHD (3440×1440)"),
                                   ("5", "UHD   (3840×2160)")]:
                    if key == default_res:
                        console.print(f"  [bold green][{key}] {label}[/bold green]")
                    else:
                        console.print(f"  [{key}] {label}")
                try:
                    res_choice = typer.prompt(f"Resolution [1-5]", default=default_res).strip()
                except:
                    res_choice = default_res
                selected_resolution = resolution_map.get(res_choice, resolution_map.get(default_res, "1920x1080"))

            # 2. Ask for comment
            try:
                comment = typer.prompt("Comment (optional, Enter to skip)", default="").strip()
            except:
                comment = ""

            # 2b. GPU selection for multi-GPU systems (use log GPU as intelligent default)
            log_gpu = analyzer.log_system_info.get("gpu")

            # Validate log GPU - reject generic device types (e.g., "VGA controller")
            invalid_gpu_patterns = ["vga controller", "3d controller", "unknown", "display controller"]
            if log_gpu and any(p in log_gpu.lower() for p in invalid_gpu_patterns):
                console.print(f"[yellow]⚠ MangoHud GPU ungültig: '{log_gpu}' - verwende lspci[/yellow]")
                log_gpu = None  # Fallback to lspci detection

            selected_system_info = _select_gpu_for_benchmark(system_info, console, log_gpu=log_gpu)

            # 3. Save run locally
            stutter_rating = stutter.get("stutter_rating", "Unknown")
            consistency_rating = frame_pacing.get("consistency_rating", "Unknown")
            storage.save_run(
                game_id=steam_app_id,
                resolution=selected_resolution,
                metrics=metrics,
                frametimes=frametimes,
            )
            console.print(f"[dim]Saved locally[/dim]")

            # Store for reference
            recordings.append({
                "metrics": metrics,
                "log_path": log_path,
                "frametimes": frametimes,
                "resolution": selected_resolution,
                "comment": comment,
            })

            # 4. Ask if user wants to upload (only if validation passed)
            if not can_upload:
                console.print(f"\n[dim]Upload skipped due to validation errors.[/dim]")
                upload_choice = "n"
            else:
                default_upload = preferences.upload
                if default_upload == "y":
                    console.print(f"\n[bold]Upload to community database? [[green]Y[/green]/n][/bold]")
                else:
                    console.print(f"\n[bold]Upload to community database? [Y/[green]n[/green]][/bold]")
                try:
                    upload_choice = typer.prompt(f"Upload?", default=default_upload).strip().lower()
                except:
                    upload_choice = default_upload

            if upload_choice in ["y", "yes", "j", "ja", ""] and can_upload:
                # Show login hint if not logged in (upload works without login)
                from linux_game_benchmark.api.auth import get_auth_header
                if not get_auth_header():
                    console.print("[dim]Tip: Login for extra features (track your benchmarks, better compare, edit settings)[/dim]")
                    console.print("[dim]Register: https://linuxgamebench.com/register.html[/dim]")

                # Upload (works with or without login)
                if check_api_status():
                    # Compress MangoHud log for storage
                    import gzip
                    import base64
                    mangohud_log_compressed = None
                    try:
                        with open(log_path, 'rb') as f:
                            raw_log = f.read()
                        mangohud_log_compressed = base64.b64encode(gzip.compress(raw_log)).decode('ascii')
                    except Exception:
                        pass  # Log compression is optional

                    # Note: scheduler was captured at recording stop (game still running)
                    # game_settings already built at function start from CLI parameters

                    # Calculate payload size for user feedback
                    import json as json_module
                    payload_data = {
                        "steam_app_id": steam_app_id,
                        "game_name": target_game["name"],
                        "resolution": _normalize_resolution(selected_resolution),
                        "frametimes": frametimes,
                    }
                    payload_size = len(json_module.dumps(payload_data))
                    if mangohud_log_compressed:
                        payload_size += len(mangohud_log_compressed)
                    size_kb = payload_size / 1024
                    size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

                    # Upload with spinner
                    from rich.status import Status
                    with Status(f"[bold green]Uploading {size_str}...[/bold green]", console=console) as status:
                        result = upload_benchmark(
                            steam_app_id=steam_app_id,
                            game_name=target_game["name"],
                            resolution=_normalize_resolution(selected_resolution),
                            system_info={
                                "gpu": _short_gpu(selected_system_info.get("gpu", {}).get("model")),
                                "cpu": _short_cpu(selected_system_info.get("cpu", {}).get("model")),
                                "os": _short_os(selected_system_info.get("os", {}).get("name", "Linux")),
                                "kernel": _short_kernel(selected_system_info.get("os", {}).get("kernel")),
                                "gpu_driver": selected_system_info.get("gpu", {}).get("driver_version"),
                                "vulkan": selected_system_info.get("gpu", {}).get("vulkan_version"),
                                "ram_gb": int(selected_system_info.get("ram", {}).get("total_gb", 0)),
                                "scheduler": scheduler,
                            },
                            metrics={
                                "fps_avg": fps.get('average', 0),
                                "fps_min": fps.get('minimum', 0),
                                "fps_1low": fps.get('1_percent_low', 0),
                                "fps_01low": fps.get('0.1_percent_low', 0),
                                "stutter_rating": stutter_rating,
                                "consistency_rating": consistency_rating,
                                "duration_seconds": fps.get('duration_seconds', 0),
                                "frame_count": fps.get('frame_count', 0),
                            },
                            frametimes=frametimes,
                            mangohud_log_compressed=mangohud_log_compressed,
                            comment=comment if comment else None,
                            game_settings=game_settings if game_settings else None,
                        )
                    if result.success:
                        console.print(f"[bold green]✓ Uploaded![/bold green]")
                        if result.url:
                            console.print(f"  {result.url}")
                    else:
                        # Check if auth error - offer to login and retry
                        auth_errors = ["session expired", "authentication", "login again", "401"]
                        is_auth_error = any(e in (result.error or "").lower() for e in auth_errors)

                        if is_auth_error:
                            console.print(f"[yellow]Session expired or not logged in.[/yellow]")
                            from linux_game_benchmark.api.auth import login as auth_login

                            # Login retry loop
                            logged_in = False
                            upload_anonymous = False
                            while True:
                                login_choice = typer.prompt("Try login? [Y/n]", default="y").strip().lower()
                                if login_choice not in ["y", "yes", "j", "ja", ""]:
                                    # User declined login - upload anonymously
                                    from linux_game_benchmark.api.auth import logout as auth_logout
                                    auth_logout()  # Clear expired token
                                    upload_anonymous = True
                                    break
                                # Prompt for credentials
                                email = typer.prompt("Email")
                                password = typer.prompt("Password", hide_input=True)
                                console.print("[dim]Logging in...[/dim]")
                                success, msg = auth_login(email, password)
                                if success:
                                    console.print(f"[green]{msg}[/green]")
                                    logged_in = True
                                    break
                                # Login failed - ask to retry
                                console.print(f"[yellow]{msg}[/yellow]")

                            if logged_in or upload_anonymous:
                                # Retry upload after successful login or anonymously
                                if upload_anonymous:
                                    console.print("[dim]Uploading anonymously...[/dim]")
                                else:
                                    console.print("[dim]Retrying upload...[/dim]")
                                result = upload_benchmark(
                                    steam_app_id=steam_app_id,
                                    game_name=target_game["name"],
                                    resolution=_normalize_resolution(selected_resolution),
                                    system_info={
                                        "gpu": _short_gpu(selected_system_info.get("gpu", {}).get("model")),
                                        "cpu": _short_cpu(selected_system_info.get("cpu", {}).get("model")),
                                        "os": _short_os(selected_system_info.get("os", {}).get("name", "Linux")),
                                        "kernel": _short_kernel(selected_system_info.get("os", {}).get("kernel")),
                                        "gpu_driver": selected_system_info.get("gpu", {}).get("driver_version"),
                                        "vulkan": selected_system_info.get("gpu", {}).get("vulkan_version"),
                                        "ram_gb": int(selected_system_info.get("ram", {}).get("total_gb", 0)),
                                        "scheduler": scheduler,
                                    },
                                    metrics={
                                        "fps_avg": fps.get('average', 0),
                                        "fps_min": fps.get('minimum', 0),
                                        "fps_1low": fps.get('1_percent_low', 0),
                                        "fps_01low": fps.get('0.1_percent_low', 0),
                                        "stutter_rating": stutter_rating,
                                        "consistency_rating": consistency_rating,
                                        "duration_seconds": fps.get('duration_seconds', 0),
                                        "frame_count": fps.get('frame_count', 0),
                                    },
                                    frametimes=frametimes,
                                    mangohud_log_compressed=mangohud_log_compressed,
                                    comment=comment if comment else None,
                                    game_settings=game_settings if game_settings else None,
                                )
                                if result.success:
                                    if upload_anonymous:
                                        console.print(f"[bold green]✓ Uploaded anonymously![/bold green]")
                                    else:
                                        console.print(f"[bold green]✓ Uploaded![/bold green]")
                                    if result.url:
                                        console.print(f"  {result.url}")
                                else:
                                    console.print(f"[red]Upload failed: {result.error}[/red]")
                        else:
                            console.print(f"[red]Upload failed: {result.error}[/red]")
                else:
                    console.print("[red]Server unreachable. Please try again later.[/red]")
            else:
                console.print("[dim]Not uploaded.[/dim]")

        except Exception as e:
            console.print(f"[red]Analysis error: {e}[/red]")
            return True  # Continue session

        # 5. Ask to continue or end
        default_cont = preferences.continue_session
        if default_cont == "c":
            console.print(f"\n[bold][[green]C[/green]]ontinue / [E]nd[/bold]")
        else:
            console.print(f"\n[bold][C]ontinue / [[green]E[/green]]nd[/bold]")
        try:
            continue_choice = typer.prompt(f"Choice", default=default_cont).strip().lower()
        except:
            return default_cont == "c"

        if continue_choice in ["e", "end", "q", "quit"]:
            return False  # End session

        console.print(f"\n[bold yellow]Waiting for next recording ([bold red]Shift+F2[/bold red])...[/bold yellow]")
        return True  # Continue session

    # Launch game
    console.print("[bold]Starting game...[/bold]")
    launcher = GameLauncher()

    try:
        success = launcher.launch(
            app_id=steam_app_id,
        )

        if not success:
            console.print("[red]Failed to launch game[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Game launch initiated![/green]")
        console.print(f"\n[bold yellow]Once the game is running, press [bold red]Shift+F2[/bold red] to start recording[/bold yellow]")
        console.print(f"[dim]Red dot in overlay = recording. Press Shift+F2 again to stop.[/dim]")
        console.print(f"[dim]Press [bold cyan]Shift+F3[/bold cyan] to toggle HUD visibility.[/dim]\n")

        # Monitor for recordings (no PID check - user ends session manually)
        session_active = True
        while session_active:
            # First check for active recording (file growing)
            active = get_active_recording()
            if active and active.name not in processed_logs:
                monitor_recording(active)  # Shows live timer until complete

            # Then check for completed recordings
            new_logs = get_new_logs()
            for log_path in new_logs:
                processed_logs.add(log_path.name)
                session_active = process_recording(log_path)
                if not session_active:
                    break

            time.sleep(0.5)

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
    finally:
        mangohud_manager.restore_config()
        try:
            restore_launch_options(steam_app_id)
        except:
            pass

    # End of session summary
    if not recordings:
        console.print("\n[yellow]No recordings captured.[/yellow]")
    else:
        console.print(f"\n[bold cyan]═══ Session ended: {len(recordings)} recording(s) processed ═══[/bold cyan]")

        # Generate report
        all_resolutions = storage.get_all_resolutions(steam_app_id)
        if all_resolutions:
            resolution_data = {res: storage.aggregate_runs(runs) for res, runs in all_resolutions.items()}
            report_path = storage.get_report_path(steam_app_id)
            generate_multi_resolution_report(
                game_name=target_game["name"],
                app_id=steam_app_id,
                system_info=system_info,
                resolution_data=resolution_data,
                output_path=report_path,
                runs_data=all_resolutions,
            )
            console.print(f"[bold]Report:[/bold] {report_path}")


@app.command()
def analyze(
    log_file: Path = typer.Argument(
        ...,
        help="Path to MangoHud log file (CSV)",
        exists=True,
    ),
    target_fps: int = typer.Option(
        60,
        "--target",
        "-t",
        help="Target FPS for evaluation",
    ),
) -> None:
    """
    Analyze an existing MangoHud log file.

    Calculates FPS metrics, detects stutter, and evaluates frame pacing.
    """
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer

    console.print(f"[bold]Analyzing: {log_file}[/bold]\n")

    try:
        analyzer = FrametimeAnalyzer(log_file)
        results = analyzer.analyze()

        # Display results
        fps = results.get("fps", {})
        console.print("[bold cyan]FPS Metrics[/bold cyan]")
        console.print(f"  Average:    {fps.get('average', 0):.1f}")
        console.print(f"  Minimum:    {fps.get('minimum', 0):.1f}")
        console.print(f"  Maximum:    {fps.get('maximum', 0):.1f}")
        console.print(f"  1% Low:     {fps.get('1_percent_low', 0):.1f}")
        console.print(f"  0.1% Low:   {fps.get('0.1_percent_low', 0):.1f}")

        stutter = results.get("stutter", {})
        frame_pacing = results.get("frame_pacing", {})

        console.print(f"\n[bold cyan]Performance Quality[/bold cyan]")

        # Stutter events
        rating = stutter.get('stutter_rating', 'unknown')
        rating_color = {'excellent': 'green', 'good': 'green', 'moderate': 'yellow', 'poor': 'red'}.get(rating, 'white')
        console.print(f"  Stutter:       [{rating_color}]{rating}[/{rating_color}] ({stutter.get('gameplay_stutter_count', 0)} events)")

        # Frame consistency
        if frame_pacing:
            cons_rating = frame_pacing.get('consistency_rating', 'unknown')
            cons_color = {'excellent': 'green', 'good': 'green', 'moderate': 'yellow', 'poor': 'red'}.get(cons_rating, 'white')
            cv = frame_pacing.get('cv_percent', 0)
            console.print(f"  Consistency:   [{cons_color}]{cons_rating}[/{cons_color}] (CV: {cv:.1f}%)")

    except Exception as e:
        console.print(f"[red]Error analyzing log: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def report(
    input_dir: Path = typer.Argument(
        ...,
        help="Directory containing benchmark results",
        exists=True,
    ),
    format: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Output format (html, json, csv)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path",
    ),
) -> None:
    """
    Generate a report from benchmark results.

    Creates a detailed report with charts and analysis.
    """
    console.print(f"[bold]Generating {format.upper()} report...[/bold]")

    # TODO: Implement report generation
    console.print("[yellow]Report generation not yet implemented.[/yellow]")



if __name__ == "__main__":
    app()
