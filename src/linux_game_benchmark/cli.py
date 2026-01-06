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
from typing import Optional
from pathlib import Path

from linux_game_benchmark import __version__


# Helper functions for normalizing hardware names before upload
def _short_gpu(name: str) -> str:
    """Shorten GPU name for consistent storage."""
    if not name:
        return "Unknown"
    # AMD RX 7000/6000 series: "AMD Radeon RX 7900 XTX" → "RX 7900 XTX"
    m = re.search(r'RX\s*(\d{4}\s*XT[Xi]?)', name, re.I)
    if m:
        return "RX " + m.group(1).replace('  ', ' ')
    m = re.search(r'RX\s*(\d{3,4})', name, re.I)
    if m:
        return "RX " + m.group(1)
    # NVIDIA: "NVIDIA GeForce RTX 4090" → "RTX 4090"
    m = re.search(r'(RTX|GTX)\s*(\d{3,4}(\s*Ti)?(\s*Super)?)', name, re.I)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    # Intel Arc: "Intel Arc A770" → "Arc A770"
    m = re.search(r'Arc\s*(A\d{3,4})', name, re.I)
    if m:
        return "Arc " + m.group(1)
    # Intel integrated: "Intel Iris Xe Graphics" → keep short
    m = re.search(r'(Iris\s+\w+)', name, re.I)
    if m:
        return m.group(1)
    # Fallback: truncate to 30 chars
    return name[:30] if len(name) > 30 else name


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


def _normalize_resolution(res: str) -> str:
    """Normalize resolution to pixel format."""
    if not res:
        return "1920x1080"
    mapping = {
        "HD": "1280x720", "FHD": "1920x1080",
        "WQHD": "2560x1440", "UWQHD": "3440x1440", "UHD": "3840x2160"
    }
    return mapping.get(res.upper(), res)


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

    Verifies MangoHud, Steam, Gamescope and other tools are available.
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

    # Gamescope (optional)
    gamescope_path = shutil.which("gamescope")
    if gamescope_path:
        console.print(f"[green]Gamescope:[/green] {gamescope_path}")
    else:
        console.print("[yellow]Gamescope:[/yellow] Not installed (optional)")

    # GameMode (optional)
    gamemode_path = shutil.which("gamemoderun")
    if gamemode_path:
        console.print(f"[green]GameMode:[/green] {gamemode_path}")
    else:
        console.print("[yellow]GameMode:[/yellow] Not installed (optional)")

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
        0,
        "--duration",
        "-d",
        help="Recording duration in seconds (0 = manual stop with Shift+F2)",
    ),
) -> None:
    """
    Run benchmark for a game.

    Starts the game and allows multiple benchmark recordings with Shift+F2.
    After each recording, you can choose to continue or end the session.
    """
    import time
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
    from linux_game_benchmark.benchmark.game_launcher import GameLauncher
    from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
    from linux_game_benchmark.mangohud.manager import check_mangohud_installation
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage, SystemFingerprint
    from linux_game_benchmark.analysis.report_generator import generate_multi_resolution_report
    from linux_game_benchmark.system.hardware_info import get_system_info
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

    # Configure MangoHud for manual logging (no duration limit)
    mangohud_manager.backup_config()
    mangohud_manager.set_benchmark_config(
        output_folder=output_dir,
        show_hud=show_hud,
        manual_logging=True,
        log_duration=0,  # No auto-stop
    )

    # Set Steam launch options
    try:
        set_launch_options(steam_app_id, "MANGOHUD=1 %command%")
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

    def process_recording(log_path: Path) -> bool:
        """Process a recording. Returns False if user wants to end session."""
        console.print(f"\n[bold green]═══ Recording complete! ═══[/bold green]")

        try:
            analyzer = FrametimeAnalyzer(log_path)
            metrics = analyzer.analyze()
            fps = metrics.get("fps", {})
            frame_pacing = metrics.get("frame_pacing", {})
            stutter = metrics.get("stutter", {})

            # Calculate duration
            duration_sec = fps.get('duration_seconds', 0)
            minutes = int(duration_sec // 60)
            seconds = int(duration_sec % 60)
            frames = fps.get('frame_count', 0)

            console.print(f"\n  [bold]Recorded:[/bold] {minutes}m {seconds}s, {frames} frames")
            console.print(f"  [bold]AVG FPS:[/bold] {fps.get('average', 0):.1f}")
            console.print(f"  [bold]1% Low:[/bold] {fps.get('1_percent_low', 0):.1f}")
            console.print(f"  [bold]0.1% Low:[/bold] {fps.get('0.1_percent_low', 0):.1f}")

            # Get frametimes for upload
            frametimes = analyzer.frametimes if hasattr(analyzer, 'frametimes') else None

            # 1. Ask for resolution
            console.print(f"\n[bold]Which resolution was used?[/bold]")
            console.print("  [1] HD    (1280×720)")
            console.print("  [2] FHD   (1920×1080)")
            console.print("  [3] WQHD  (2560×1440)")
            console.print("  [4] UWQHD (3440×1440)")
            console.print("  [5] UHD   (3840×2160)")
            try:
                res_choice = typer.prompt("Resolution [1-5]", default="2").strip()
            except:
                res_choice = "2"
            resolution_map = {"1": "1280x720", "2": "1920x1080", "3": "2560x1440", "4": "3440x1440", "5": "3840x2160"}
            selected_resolution = resolution_map.get(res_choice, "1920x1080")

            # 2. Ask for comment
            try:
                comment = typer.prompt("Comment (optional, Enter to skip)", default="").strip()
            except:
                comment = ""

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

            # 4. Ask if user wants to upload
            console.print(f"\n[bold]Upload to community database?[/bold]")
            try:
                upload_choice = typer.prompt("Upload? [Y/n]", default="y").strip().lower()
            except:
                upload_choice = "n"

            if upload_choice in ["y", "yes", "j", "ja", ""]:
                # Check login status before upload
                from linux_game_benchmark.api.auth import get_auth_header, is_logged_in
                can_upload = True
                if not get_auth_header():
                    console.print("[yellow]Not logged in or session expired.[/yellow]")
                    login_choice = typer.prompt("Login now? [Y/n]", default="y").strip().lower()
                    if login_choice in ["y", "yes", "j", "ja", ""]:
                        # Prompt for login
                        email = typer.prompt("Email")
                        password = typer.prompt("Password", hide_input=True)
                        from linux_game_benchmark.api.auth import login
                        success, msg = login(email, password)
                        if success:
                            console.print(f"[green]✓ {msg}[/green]")
                        else:
                            console.print(f"[red]Login failed: {msg}[/red]")
                            console.print("[dim]Benchmark saved locally. Use 'lgb upload' later.[/dim]")
                            can_upload = False
                    else:
                        console.print("[dim]Upload skipped. Use 'lgb upload' after logging in.[/dim]")
                        can_upload = False

                if can_upload:
                    console.print("[dim]Uploading...[/dim]")
                    if check_api_status():
                        result = upload_benchmark(
                            steam_app_id=steam_app_id,
                            game_name=target_game["name"],
                            resolution=_normalize_resolution(selected_resolution),
                            system_info={
                                "gpu": _short_gpu(system_info.get("gpu", {}).get("model")),
                                "cpu": _short_cpu(system_info.get("cpu", {}).get("model")),
                                "os": system_info.get("os", {}).get("name", "Linux"),
                                "kernel": _short_kernel(system_info.get("os", {}).get("kernel")),
                                "gpu_driver": system_info.get("gpu", {}).get("driver_version"),
                                "vulkan": system_info.get("gpu", {}).get("vulkan_version"),
                                "ram_gb": int(system_info.get("ram", {}).get("total_gb", 0)),
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
                            comment=comment if comment else None,
                        )
                        if result.success:
                            console.print(f"[bold green]✓ Uploaded![/bold green]")
                            if result.url:
                                console.print(f"  {result.url}")
                        elif result.error and ("Authentication" in result.error or "Session expired" in result.error):
                            # Auth failed - offer to login and retry
                            console.print(f"[yellow]Session expired or invalid.[/yellow]")
                            retry_login = typer.prompt("Login now and retry? [Y/n]", default="y").strip().lower()
                            if retry_login in ["y", "yes", "j", "ja", ""]:
                                email = typer.prompt("Email")
                                password = typer.prompt("Password", hide_input=True)
                                from linux_game_benchmark.api.auth import login as do_login
                                login_ok, login_msg = do_login(email, password)
                                if login_ok:
                                    console.print(f"[green]✓ {login_msg}[/green]")
                                    console.print("[dim]Retrying upload...[/dim]")
                                    # Retry upload
                                    retry_result = upload_benchmark(
                                        steam_app_id=steam_app_id,
                                        game_name=target_game["name"],
                                        resolution=_normalize_resolution(selected_resolution),
                                        system_info={
                                            "gpu": _short_gpu(system_info.get("gpu", {}).get("model")),
                                            "cpu": _short_cpu(system_info.get("cpu", {}).get("model")),
                                            "os": system_info.get("os", {}).get("name", "Linux"),
                                            "kernel": _short_kernel(system_info.get("os", {}).get("kernel")),
                                            "gpu_driver": system_info.get("gpu", {}).get("driver_version"),
                                            "vulkan": system_info.get("gpu", {}).get("vulkan_version"),
                                            "ram_gb": int(system_info.get("ram", {}).get("total_gb", 0)),
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
                                        comment=comment if comment else None,
                                    )
                                    if retry_result.success:
                                        console.print(f"[bold green]✓ Uploaded![/bold green]")
                                        if retry_result.url:
                                            console.print(f"  {retry_result.url}")
                                    else:
                                        console.print(f"[red]Upload failed: {retry_result.error}[/red]")
                                else:
                                    console.print(f"[red]Login failed: {login_msg}[/red]")
                                    console.print("[dim]Benchmark saved locally. Use 'lgb upload' later.[/dim]")
                            else:
                                console.print("[dim]Upload skipped. Use 'lgb upload' after logging in.[/dim]")
                        else:
                            console.print(f"[red]Upload failed: {result.error}[/red]")
                    else:
                        console.print("[red]Server unreachable. Use 'lgb upload' later.[/red]")
            else:
                console.print("[dim]Not uploaded.[/dim]")

        except Exception as e:
            console.print(f"[red]Analysis error: {e}[/red]")
            return True  # Continue session

        # 5. Ask to continue or end
        console.print(f"\n[bold]Continue recording or end session?[/bold]")
        try:
            continue_choice = typer.prompt("[C]ontinue / [E]nd", default="c").strip().lower()
        except:
            return True

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
        console.print(f"[dim]Red dot in overlay = recording. Press Shift+F2 again to stop.[/dim]\n")

        # Monitor for recordings (no PID check - user ends session manually)
        session_active = True
        while session_active:
            new_logs = get_new_logs()
            for log_path in new_logs:
                processed_logs.add(log_path.name)
                session_active = process_recording(log_path)
                if not session_active:
                    break

            time.sleep(1.0)

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


@app.command()
def upload(
    game: Optional[str] = typer.Argument(
        None,
        help="Game App ID or name to upload benchmarks for",
    ),
    all_games: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Upload benchmarks for all games",
    ),
) -> None:
    """
    Upload benchmark results to community database.

    Uploads saved benchmarks to the Linux Game Bench server.
    """
    from linux_game_benchmark.api import upload_benchmark, check_api_status
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage
    from linux_game_benchmark.system.hardware_info import get_system_info

    # Check API
    console.print("[dim]Checking server connection...[/dim]")
    if not check_api_status():
        console.print("[red]Server unreachable![/red]")
        console.print("[dim]Please try again later.[/dim]")
        raise typer.Exit(1)

    console.print("[green]✓ Server reachable[/green]\n")

    storage = BenchmarkStorage()
    system_info = get_system_info()

    # Get games to upload
    if all_games:
        games_to_upload = storage.get_all_games()
    elif game:
        # Find specific game
        try:
            app_id = int(game)
            games_to_upload = [app_id]
        except ValueError:
            # Search by name
            all_games_list = storage.get_all_games()
            matching = [g for g in all_games_list if game.lower() in str(g).lower()]
            if not matching:
                console.print(f"[red]No game found: {game}[/red]")
                raise typer.Exit(1)
            games_to_upload = matching
    else:
        # Show available games
        available = storage.get_all_games()
        if not available:
            console.print("[yellow]No benchmarks available.[/yellow]")
            console.print("Create benchmarks first with: [cyan]lgb record <game>[/cyan]")
            raise typer.Exit(0)

        console.print("[bold]Available benchmarks:[/bold]")
        for i, game_id in enumerate(available, 1):
            resolutions = storage.get_all_resolutions(game_id)
            res_str = ", ".join(resolutions.keys()) if resolutions else "none"
            console.print(f"  [{i}] {game_id} ({res_str})")

        console.print(f"\n[dim]Use 'lgb upload <app_id>' or 'lgb upload --all'[/dim]")
        return

    # Upload each game
    uploaded = 0
    failed = 0

    for game_id in games_to_upload:
        console.print(f"\n[bold cyan]Uploading: {game_id}[/bold cyan]")

        resolutions = storage.get_all_resolutions(game_id)
        if not resolutions:
            console.print(f"  [yellow]No data for {game_id}[/yellow]")
            continue

        # Get game info for display name
        game_dir = storage.base_dir / f"steam_{game_id}"
        game_info_path = game_dir / "game_info.json"
        game_name = str(game_id)

        if game_info_path.exists():
            import json
            with open(game_info_path) as f:
                info = json.load(f)
                game_name = info.get("display_name", str(game_id))

        for resolution, runs in resolutions.items():
            if not runs:
                continue

            # Get aggregated metrics
            metrics = storage.aggregate_runs(runs)

            console.print(f"  {resolution}: ", end="")

            result = upload_benchmark(
                steam_app_id=game_id,
                game_name=game_name,
                resolution=_normalize_resolution(resolution),
                system_info={
                    "gpu": _short_gpu(system_info.get("gpu", {}).get("model")),
                    "cpu": _short_cpu(system_info.get("cpu", {}).get("model")),
                    "os": system_info.get("os", {}).get("name", "Linux"),
                    "kernel": _short_kernel(system_info.get("os", {}).get("kernel")),
                    "gpu_driver": system_info.get("gpu", {}).get("driver_version"),
                    "vulkan": system_info.get("gpu", {}).get("vulkan_version"),
                    "ram_gb": int(system_info.get("ram", {}).get("total_gb", 0)),
                },
                metrics=metrics,
            )

            if result.success:
                console.print(f"[green]✓[/green] {result.url}")
                uploaded += 1
            else:
                console.print(f"[red]✗[/red] {result.error}")
                failed += 1

    # Summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Uploaded: [green]{uploaded}[/green]")
    if failed:
        console.print(f"  Failed: [red]{failed}[/red]")

if __name__ == "__main__":
    app()
