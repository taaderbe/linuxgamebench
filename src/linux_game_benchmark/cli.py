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

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional
from pathlib import Path

from linux_game_benchmark import __version__

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
    pass


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
    with_benchmark: bool = typer.Option(
        False,
        "--with-benchmark",
        "-b",
        help="Only show games with builtin benchmarks",
    ),
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
    if with_benchmark:
        games = [g for g in games if g.get("has_builtin_benchmark")]
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
    table.add_column("Benchmark", style="yellow")

    for game in sorted(games, key=lambda x: x.get("name", "")):
        game_type = "Proton" if game.get("requires_proton") else "Native"
        benchmark = "Yes" if game.get("has_builtin_benchmark") else "-"
        table.add_row(
            str(game.get("app_id", "?")),
            game.get("name", "Unknown"),
            game_type,
            benchmark,
        )

    console.print(table)
    console.print(f"\nTotal: {len(games)} games")


@app.command()
def check() -> None:
    """
    Check system requirements for benchmarking.

    Verifies MangoHud, Steam, Gamescope and other tools are available.
    """
    from linux_game_benchmark.mangohud.manager import check_mangohud_installation
    import shutil

    console.print("[bold]Checking system requirements...[/bold]\n")

    all_good = True

    # MangoHud
    mangohud = check_mangohud_installation()
    if mangohud["installed"]:
        console.print(f"[green]MangoHud:[/green] {mangohud.get('version', 'Installed')}")
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
    runs: int = typer.Option(
        3,
        "--runs",
        "-r",
        help="Number of benchmark runs",
    ),
    warmup: int = typer.Option(
        1,
        "--warmup",
        "-w",
        help="Number of warmup runs (not counted in results)",
    ),
    duration: int = typer.Option(
        60,
        "--duration",
        "-d",
        help="Duration per run in seconds (for timed benchmarks)",
    ),
    builtin: bool = typer.Option(
        False,
        "--builtin",
        "-B",
        help="Use game's builtin benchmark (auto-starts via command line)",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        "-m",
        help="Manual mode: start benchmark in-game, close game when done",
    ),
    gamescope: bool = typer.Option(
        False,
        "--gamescope",
        "-g",
        help="Run with Gamescope wrapper",
    ),
    proton: Optional[str] = typer.Option(
        None,
        "--proton",
        "-p",
        help="Proton version to use",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for results",
    ),
    cooldown: int = typer.Option(
        10,
        "--cooldown",
        "-c",
        help="Cooldown between runs in seconds",
    ),
    show_hud: bool = typer.Option(
        False,
        "--show-hud",
        help="Show MangoHud overlay during benchmark",
    ),
    manual_logging: bool = typer.Option(
        False,
        "--manual-logging",
        "-L",
        help="Manual logging: press Shift+F2 to start/stop recording",
    ),
) -> None:
    """
    Run benchmark for a game.

    Starts the game, records performance data with MangoHud,
    and generates a report with FPS metrics, stutter analysis, etc.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
    from linux_game_benchmark.benchmark.runner import (
        BenchmarkRunner,
        BenchmarkConfig,
        BenchmarkType,
    )
    from linux_game_benchmark.mangohud.manager import check_mangohud_installation

    # Check MangoHud
    mangohud_info = check_mangohud_installation()
    if not mangohud_info["installed"]:
        console.print("[red]Error: MangoHud is not installed.[/red]")
        console.print("Install it with: sudo pacman -S mangohud (Arch) or apt install mangohud (Debian/Ubuntu)")
        raise typer.Exit(1)

    console.print(f"[dim]MangoHud: {mangohud_info.get('version', 'installed')}[/dim]")

    # Find the game
    scanner = SteamLibraryScanner()
    try:
        games = scanner.scan()
    except Exception as e:
        console.print(f"[red]Error scanning Steam library: {e}[/red]")
        raise typer.Exit(1)

    # Match game by ID or name
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

    console.print(f"\n[bold]Game:[/bold] {target_game['name']}")
    console.print(f"[bold]App ID:[/bold] {target_game['app_id']}")

    # Determine benchmark type
    if manual:
        bench_type = BenchmarkType.MANUAL
        launch_args = []
        console.print("[bold]Mode:[/bold] Manual (start benchmark in-game, close when done)")
    elif builtin and target_game.get("has_builtin_benchmark"):
        bench_type = BenchmarkType.BUILTIN
        launch_args = target_game.get("benchmark_args", [])
        console.print("[bold]Mode:[/bold] Builtin benchmark (auto-start)")
    else:
        bench_type = BenchmarkType.TIMED
        launch_args = []
        console.print(f"[bold]Mode:[/bold] Timed ({duration}s per run)")

    console.print(f"[bold]Runs:[/bold] {runs} + {warmup} warmup\n")

    # Create config
    config = BenchmarkConfig(
        app_id=target_game["app_id"],
        game_name=target_game["name"],
        benchmark_type=bench_type,
        launch_args=launch_args,
        duration_seconds=duration,
        runs=runs,
        warmup_runs=warmup,
        cooldown_seconds=cooldown,
        proton_version=proton,
        use_gamescope=gamescope,
        show_hud=show_hud,
        manual_logging=manual_logging,
    )

    if manual_logging:
        console.print("[bold yellow]Manual Logging aktiviert:[/bold yellow]")
        console.print("  Drücke [bold]Shift+F2[/bold] um Aufnahme zu STARTEN")
        console.print("  Drücke [bold]Shift+F2[/bold] erneut um zu STOPPEN\n")

    # Status callback
    def on_status(msg: str) -> None:
        console.print(f"  {msg}")

    # Run benchmark
    runner = BenchmarkRunner(
        output_dir=output,
        on_status=on_status,
    )

    # Check requirements
    reqs = runner.check_requirements()
    if not reqs["mangohud"]["installed"]:
        console.print("[red]MangoHud not found![/red]")
        raise typer.Exit(1)

    console.print("[bold cyan]Starting benchmark...[/bold cyan]\n")

    try:
        session = runner.run(config)
    except KeyboardInterrupt:
        console.print("\n[yellow]Benchmark interrupted by user.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Benchmark failed: {e}[/red]")
        raise typer.Exit(1)

    # Display results
    console.print("\n" + "=" * 50)
    console.print("[bold green]Benchmark Complete![/bold green]\n")

    # Ask for resolution used during benchmark
    console.print("[bold]Welche Auflösung wurde im Benchmark verwendet?[/bold]")
    console.print("  [1] FHD  (1920×1080)")
    console.print("  [2] WQHD (2560×1440)")
    console.print("  [3] UHD  (3840×2160)")
    console.print("  [0] Abbrechen (nicht speichern)")

    resolution_map = {
        "1": "1920x1080",
        "2": "2560x1440",
        "3": "3840x2160",
    }
    resolution_choice = typer.prompt("Auswahl", default="1")

    if resolution_choice == "0":
        console.print("\n[yellow]Benchmark abgebrochen - Daten nicht gespeichert.[/yellow]")
        if session.output_dir:
            console.print(f"[dim]Raw data bleibt in: {session.output_dir}[/dim]")
        raise typer.Exit(0)

    selected_resolution = resolution_map.get(resolution_choice, "1920x1080")

    console.print(f"\n[dim]Auflösung: {selected_resolution}[/dim]")

    # Use new storage system
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage, SystemFingerprint
    from linux_game_benchmark.analysis.report_generator import generate_multi_resolution_report

    storage = BenchmarkStorage()

    # Check system fingerprint
    current_fp = SystemFingerprint.from_system_info(session.system_info)

    # Get Steam App ID for storage (canonical identifier)
    steam_app_id = target_game["app_id"]

    if not storage.check_fingerprint(steam_app_id, current_fp):
        console.print("\n[yellow]System-Konfiguration hat sich geändert![/yellow]")
        console.print("[dim]Alte Benchmark-Daten werden archiviert...[/dim]")
        archive_path = storage.archive_old_data(steam_app_id)
        if archive_path:
            console.print(f"[dim]Archiviert nach: {archive_path}[/dim]")

    # Save fingerprint and system info
    storage.save_fingerprint(steam_app_id, current_fp, session.system_info)

    # Register game in registry (creates game_info.json)
    from linux_game_benchmark.games.registry import GameRegistry
    registry = GameRegistry(base_dir=storage.base_dir)
    registry.get_or_create(
        steam_app_id=steam_app_id,
        display_name=target_game["name"],
    )

    # Get metrics from results and save run
    if session.results:
        for result in session.results:
            if not result.is_warmup and result.metrics:
                # Re-analyze to get frametimes for charting
                from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
                try:
                    analyzer = FrametimeAnalyzer(result.log_path)
                    frametimes = analyzer.frametimes
                except:
                    frametimes = None

                storage.save_run(
                    game_id=steam_app_id,
                    resolution=selected_resolution,
                    metrics=result.metrics,
                    log_path=result.log_path,
                    frametimes=frametimes,
                )

    # Generate multi-resolution report
    all_resolutions = storage.get_all_resolutions(steam_app_id)
    if all_resolutions:
        resolution_data = {}
        for res, runs in all_resolutions.items():
            resolution_data[res] = storage.aggregate_runs(runs)

        report_path = storage.get_report_path(steam_app_id)
        generate_multi_resolution_report(
            game_name=target_game["name"],  # Keep display name for report
            app_id=steam_app_id,
            system_info=session.system_info,
            resolution_data=resolution_data,
            output_path=report_path,
            runs_data=all_resolutions,  # Pass individual runs for charting
        )
        console.print(f"\n[bold]Report:[/bold] {report_path}")

    if session.output_dir:
        console.print(f"[dim]Raw data: {session.output_dir}[/dim]\n")

    # Summary
    summary = session.summary
    if "error" not in summary:
        fps = summary.get("fps", {})
        console.print("[bold cyan]FPS Summary (averaged across runs)[/bold cyan]")
        console.print(f"  Average:    {fps.get('average', 0):.1f} FPS")
        console.print(f"  Minimum:    {fps.get('minimum', 0):.1f} FPS")
        console.print(f"  1% Low:     {fps.get('1_percent_low', 0):.1f} FPS")
        console.print(f"  0.1% Low:   {fps.get('0.1_percent_low', 0):.1f} FPS")

        stutter = summary.get("stutter", {})
        frame_pacing = summary.get("frame_pacing", {})

        if stutter or frame_pacing:
            console.print(f"\n[bold cyan]Performance Quality[/bold cyan]")

            # Stutter (events/spikes)
            if stutter:
                rating = stutter.get('stutter_rating', 'unknown')
                rating_color = {
                    'excellent': 'green',
                    'good': 'green',
                    'moderate': 'yellow',
                    'poor': 'red'
                }.get(rating, 'white')
                event_count = stutter.get('gameplay_stutter_count', 0)
                console.print(f"  Stutter Events: [{rating_color}]{rating}[/{rating_color}] ({event_count} events)")

            # Frame consistency (variance)
            if frame_pacing:
                rating = frame_pacing.get('consistency_rating', 'unknown')
                rating_color = {
                    'excellent': 'green',
                    'good': 'green',
                    'moderate': 'yellow',
                    'poor': 'red'
                }.get(rating, 'white')
                cv = frame_pacing.get('cv_percent', 0)
                stability = frame_pacing.get('fps_stability', 0)
                console.print(f"  Consistency: [{rating_color}]{rating}[/{rating_color}] (CV: {cv:.1f}%, Stability: {stability:.1f}%)")

        # Consistency
        consistency = summary.get("consistency", {})
        if consistency:
            avg_cv = consistency.get("average_cv", 0)
            if avg_cv < 5:
                consistency_rating = "[green]Excellent[/green]"
            elif avg_cv < 10:
                consistency_rating = "[yellow]Good[/yellow]"
            else:
                consistency_rating = "[red]Variable[/red]"
            console.print(f"\n[bold cyan]Run Consistency[/bold cyan]")
            console.print(f"  Variation: {avg_cv:.1f}% - {consistency_rating}")

        # FPS targets
        fps_targets = summary.get("fps_targets", {})
        if fps_targets:
            console.print(f"\n[bold cyan]FPS Target Evaluation[/bold cyan]")
            targets_dict = fps_targets.get("targets", {})
            for target_name, result in targets_dict.items():
                if isinstance(result, dict):
                    target_fps = result.get("target_fps", 0)
                    meets = result.get("meets_target", False)
                    rating = result.get("rating", "")
                    if meets:
                        status = "[green]✓[/green]"
                    elif rating == "playable":
                        status = "[yellow]~[/yellow]"
                    else:
                        status = "[red]✗[/red]"
                    console.print(f"  {target_fps} Hz: {status} ({rating})")

            recommended = fps_targets.get("recommended", {})
            if recommended:
                rec_fps = recommended.get("fps", 0)
                rec_rating = recommended.get("rating", "")
                console.print(f"  [bold]Recommended:[/bold] {rec_fps} Hz ({rec_rating})")
    else:
        console.print(f"[yellow]{summary.get('error')}[/yellow]")

    # Upload prompt
    _prompt_upload(
        steam_app_id=steam_app_id,
        game_name=target_game["name"],
        resolution=selected_resolution,
        system_info=session.system_info,
        summary=summary,
    )


def _prompt_upload(
    steam_app_id: int,
    game_name: str,
    resolution: str,
    system_info: dict,
    summary: dict,
) -> None:
    """Ask user if they want to upload the benchmark."""
    from linux_game_benchmark.api import is_logged_in, upload_benchmark, check_api_status

    console.print("\n" + "─" * 50)

    # Check if logged in
    if not is_logged_in():
        console.print("[dim]Hochladen? Bitte zuerst einloggen: lgb login[/dim]")
        return

    # Ask for upload
    console.print("[bold]Benchmark zur Community-Datenbank hochladen?[/bold]")
    try:
        choice = typer.prompt("Hochladen? [J/n]", default="j").strip().lower()
    except:
        return

    if choice not in ["j", "y", "ja", "yes", ""]:
        console.print("[dim]Nicht hochgeladen.[/dim]")
        return

    # Check API
    console.print("[dim]Verbinde mit Server...[/dim]")
    if not check_api_status():
        console.print("[red]Server nicht erreichbar. Später mit 'lgb upload' versuchen.[/red]")
        return

    # Get metrics from summary
    fps = summary.get("fps", {})
    metrics = {
        "fps_avg": fps.get("average", 0),
        "fps_min": fps.get("minimum", 0),
        "fps_1low": fps.get("1_percent_low", 0),
        "fps_01low": fps.get("0.1_percent_low", 0),
        "stutter_rating": summary.get("stutter", {}).get("stutter_rating"),
        "consistency_rating": summary.get("frame_pacing", {}).get("consistency_rating"),
    }

    # Upload
    result = upload_benchmark(
        steam_app_id=steam_app_id,
        game_name=game_name,
        resolution=resolution,
        system_info={
            "gpu": system_info.get("gpu", {}).get("model", "Unknown"),
            "cpu": system_info.get("cpu", {}).get("model", "Unknown"),
            "os": system_info.get("os", {}).get("name", "Linux"),
            "kernel": system_info.get("os", {}).get("kernel"),
            "ram_gb": int(system_info.get("ram", {}).get("total_gb", 0)),
        },
        metrics=metrics,
    )

    if result.success:
        console.print(f"[bold green]✓ Hochgeladen![/bold green]")
        console.print(f"  {result.url}")
    else:
        console.print(f"[red]Upload fehlgeschlagen: {result.error}[/red]")
        console.print("[dim]Später mit 'lgb upload' erneut versuchen.[/dim]")


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
def record(
    game: str = typer.Argument(
        ...,
        help="Game App ID or name to benchmark",
    ),
    show_hud: bool = typer.Option(
        True,
        "--show-hud/--no-hud",
        help="Show MangoHud overlay",
    ),
    duration: int = typer.Option(
        60,
        "--duration",
        "-d",
        help="Recording duration in seconds (0 = manual stop with Shift+F2)",
    ),
) -> None:
    """
    Interaktiver Multi-Recording Modus.

    Startet das Spiel einmal und erlaubt mehrere Aufnahmen:
    - Shift+F2: Aufnahme starten
    - Nach 60s (oder --duration): Aufnahme stoppt automatisch
    - Auflösung wählen → speichern
    - Wiederholen für weitere Aufnahmen
    - Spiel schließen wenn fertig
    """
    import time
    import threading
    from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
    from linux_game_benchmark.benchmark.game_launcher import GameLauncher
    from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
    from linux_game_benchmark.mangohud.manager import MangoHudManager
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage, SystemFingerprint
    from linux_game_benchmark.analysis.report_generator import generate_multi_resolution_report
    from linux_game_benchmark.system.hardware_info import get_system_info
    from linux_game_benchmark.steam.launch_options import set_launch_options, restore_launch_options

    # Find game
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
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]╔══════════════════════════════════════════╗[/bold cyan]")
    console.print(f"[bold cyan]║     INTERAKTIVER BENCHMARK MODUS         ║[/bold cyan]")
    console.print(f"[bold cyan]╚══════════════════════════════════════════╝[/bold cyan]\n")
    console.print(f"[bold]Game:[/bold] {target_game['name']}")
    console.print(f"[bold]App ID:[/bold] {target_game['app_id']}\n")

    if duration > 0:
        console.print("[bold yellow]Steuerung:[/bold yellow]")
        console.print(f"  [bold]Shift+F2[/bold] → Aufnahme starten (läuft {duration}s)")
        console.print(f"  [bold]Automatischer Stop[/bold] nach {duration} Sekunden")
        console.print("  [bold]Spiel schließen[/bold] → Beenden\n")
    else:
        console.print("[bold yellow]Steuerung:[/bold yellow]")
        console.print("  [bold]Shift+F2[/bold] → Aufnahme STARTEN")
        console.print("  [bold]Shift+F2[/bold] → Aufnahme STOPPEN")
        console.print("  [bold]Spiel schließen[/bold] → Beenden\n")

    # Setup
    system_info = get_system_info()
    storage = BenchmarkStorage()
    mangohud_manager = MangoHudConfigManager()
    output_dir = Path.home() / "benchmark_results" / "recording_session"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure MangoHud for manual logging
    mangohud_manager.backup_config()
    mangohud_manager.set_benchmark_config(
        output_folder=output_dir,
        show_hud=show_hud,
        manual_logging=True,
        log_duration=duration,
    )

    # Set Steam launch options
    try:
        set_launch_options(target_game["app_id"], "MANGOHUD=1 %command%")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not set launch options: {e}[/yellow]")

    # Check/save fingerprint - use Steam App ID for storage
    steam_app_id = target_game["app_id"]
    fp = SystemFingerprint.from_system_info(system_info)
    if not storage.check_fingerprint(steam_app_id, fp):
        console.print("[yellow]System-Config geändert - alte Daten werden archiviert[/yellow]")
        storage.archive_old_data(steam_app_id)
    storage.save_fingerprint(steam_app_id, fp, system_info)

    # Register game in registry (creates game_info.json)
    from linux_game_benchmark.games.registry import GameRegistry
    registry = GameRegistry(base_dir=storage.base_dir)
    registry.get_or_create(
        steam_app_id=steam_app_id,
        display_name=target_game["name"],
    )

    # Track processed logs
    processed_logs = set()
    for existing in output_dir.glob("*.csv"):
        if "_summary" not in existing.name:
            processed_logs.add(existing.name)

    recording_count = 0

    def get_new_logs():
        """Find new log files that haven't been processed."""
        new_logs = []
        for log_file in output_dir.glob("*.csv"):
            if "_summary" not in log_file.name and log_file.name not in processed_logs:
                # Check if file is still being written (size changing)
                size1 = log_file.stat().st_size
                time.sleep(0.5)
                size2 = log_file.stat().st_size
                if size1 == size2 and size1 > 1000:  # File complete and has data
                    new_logs.append(log_file)
        return new_logs

    def process_log(log_path: Path) -> bool:
        """Process a completed log file."""
        nonlocal recording_count

        console.print(f"\n[bold green]═══ Aufnahme erkannt! ═══[/bold green]")

        try:
            analyzer = FrametimeAnalyzer(log_path)
            metrics = analyzer.analyze()
            fps = metrics.get("fps", {})

            console.print(f"  Frames: {fps.get('frame_count', 0)}")
            console.print(f"  Duration: {fps.get('duration_seconds', 0):.1f}s")
            console.print(f"  AVG FPS: {fps.get('average', 0):.1f}")
            console.print(f"  1% Low: {fps.get('1_percent_low', 0):.1f}")
        except Exception as e:
            console.print(f"[red]Analyse-Fehler: {e}[/red]")
            return False

        # Ask for resolution
        console.print(f"\n[bold]Auflösung?[/bold]")
        console.print("  [1] FHD (1920×1080)")
        console.print("  [2] WQHD (2560×1440)")
        console.print("  [3] UHD (3840×2160)")
        console.print("  [0] Verwerfen")

        resolution_map = {"1": "1920x1080", "2": "2560x1440", "3": "3840x2160"}

        try:
            choice = typer.prompt("Auswahl", default="1")
        except:
            return False

        if choice == "0":
            console.print("[yellow]Verworfen[/yellow]")
            return True

        resolution = resolution_map.get(choice, "1920x1080")

        # Save run (including frametimes for charting)
        storage.save_run(
            game_id=steam_app_id,
            resolution=resolution,
            metrics=metrics,
            log_path=log_path,
            frametimes=analyzer.frametimes if hasattr(analyzer, 'frametimes') else None,
        )
        recording_count += 1

        console.print(f"[green]✓ Gespeichert als {resolution}[/green]")
        console.print(f"[dim]Total: {recording_count} Aufnahme(n)[/dim]")

        # Ask if user wants to continue or stop
        console.print(f"\n[bold]Was möchtest du tun?[/bold]")
        console.print("  [1] Weiter aufnehmen (Shift+F2 für nächste Aufnahme)")
        console.print("  [2] Beenden und Report generieren")

        try:
            continue_choice = typer.prompt("Auswahl", default="1")
        except:
            return True

        if continue_choice == "2":
            console.print("[cyan]Recording wird beendet...[/cyan]")
            return False  # Signal to stop

        console.print(f"\n[bold yellow]Bereit für nächste Aufnahme (Shift+F2)...[/bold yellow]")
        return True

    # Launch game
    console.print("[bold]Starte Spiel...[/bold]")
    console.print("[dim]Warte auf Spiel-Prozess (max. 120s)...[/dim]")
    launcher = GameLauncher()

    try:
        success = launcher.launch(
            app_id=target_game["app_id"],
            wait_for_ready=True,
            ready_timeout=120.0,
            verbose=True,
        )

        if not success:
            console.print("[red]Timeout: Spiel-Prozess wurde nicht erkannt[/red]")
            console.print("[yellow]Suche nach laufenden Prozessen...[/yellow]")

            # Show what processes we can see
            import psutil
            game_like = []
            for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    name = proc.info.get("name", "")
                    mem = proc.info.get("memory_info")
                    if mem and mem.rss > 100 * 1024 * 1024:  # >100MB
                        if "steam" not in name.lower() and "chrome" not in name.lower():
                            game_like.append(f"{name} (PID {proc.info['pid']}, {mem.rss // (1024*1024)}MB)")
                except:
                    pass

            if game_like:
                console.print(f"[dim]Prozesse mit >100MB RAM gefunden:[/dim]")
                for p in game_like[:10]:
                    console.print(f"[dim]  - {p}[/dim]")

            raise typer.Exit(1)

        console.print(f"[green]Spiel läuft! (PID: {launcher._game_pids})[/green]")
        console.print(f"\n[bold yellow]Drücke Shift+F2 um erste Aufnahme zu starten...[/bold yellow]\n")

        # Manual stop flag
        user_requested_stop = False

        # Monitor for logs while game is running
        while launcher.is_running() and not user_requested_stop:
            new_logs = get_new_logs()
            for log_path in new_logs:
                processed_logs.add(log_path.name)
                should_continue = process_log(log_path)
                if not should_continue:
                    user_requested_stop = True
                    break

            time.sleep(1.0)

        # Check if manually stopped
        if user_requested_stop:
            console.print("\n[bold cyan]═══ Beende Recording... ═══[/bold cyan]")

        # Check for any remaining logs after game closes or manual stop
        if not user_requested_stop:
            time.sleep(2.0)
            new_logs = get_new_logs()
            for log_path in new_logs:
                processed_logs.add(log_path.name)
                process_log(log_path)

    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen[/yellow]")
    finally:
        # Restore configs
        mangohud_manager.restore_config()
        try:
            restore_launch_options(target_game["app_id"])
        except:
            pass

    # Generate report if any recordings were made
    if recording_count > 0:
        console.print(f"\n[bold]Generiere Report...[/bold]")
        all_res = storage.get_all_resolutions(steam_app_id)
        if all_res:
            resolution_data = {res: storage.aggregate_runs(runs) for res, runs in all_res.items()}
            report_path = storage.get_report_path(steam_app_id)
            generate_multi_resolution_report(
                game_name=target_game["name"],  # Keep display name for report
                app_id=steam_app_id,
                system_info=system_info,
                resolution_data=resolution_data,
                output_path=report_path,
                runs_data=all_res,  # Pass individual runs for charting
            )
            console.print(f"[bold green]Report:[/bold green] {report_path}")

    console.print(f"\n[bold]Session beendet - {recording_count} Aufnahme(n) gespeichert[/bold]")


@app.command()
def login() -> None:
    """
    Mit Steam-Account einloggen.

    Öffnet den Browser für Steam OpenID Login.
    Nach dem Login können Benchmarks zur Community-Datenbank hochgeladen werden.
    """
    from linux_game_benchmark.api.auth import login_with_steam, get_current_session

    # Check if already logged in
    session = get_current_session()
    if session:
        console.print(f"[yellow]Bereits eingeloggt als Steam ID: {session.steam_id}[/yellow]")
        if session.steam_name:
            console.print(f"[dim]Name: {session.steam_name}[/dim]")
        console.print("\nZum Ausloggen: [cyan]lgb logout[/cyan]")
        return

    console.print("[bold]Steam Login[/bold]\n")

    try:
        session = login_with_steam(timeout=120)
        if session:
            console.print(f"\n[bold green]Login erfolgreich![/bold green]")
            console.print(f"  Steam ID: {session.steam_id}")
            if session.steam_name:
                console.print(f"  Name: {session.steam_name}")
            console.print("\n[dim]Deine Benchmarks können jetzt hochgeladen werden.[/dim]")
        else:
            console.print("\n[red]Login fehlgeschlagen oder abgebrochen.[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Fehler beim Login: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def logout() -> None:
    """
    Vom Steam-Account ausloggen.

    Entfernt die gespeicherten Login-Daten.
    """
    from linux_game_benchmark.api.auth import logout as do_logout, get_current_session

    session = get_current_session()
    if not session:
        console.print("[yellow]Nicht eingeloggt.[/yellow]")
        return

    if do_logout():
        console.print(f"[green]Erfolgreich ausgeloggt.[/green]")
        console.print(f"[dim]Steam ID {session.steam_id} entfernt.[/dim]")
    else:
        console.print("[yellow]Bereits ausgeloggt.[/yellow]")


@app.command()
def status() -> None:
    """
    Zeigt den aktuellen Login-Status.

    Zeigt ob ein Steam-Account verknüpft ist und weitere Infos.
    """
    from linux_game_benchmark.api.auth import get_current_session
    from linux_game_benchmark.config.settings import settings

    console.print("[bold]Account Status[/bold]\n")

    session = get_current_session()
    if session:
        console.print(f"[green]Eingeloggt[/green]")
        console.print(f"  Steam ID: {session.steam_id}")
        if session.steam_name:
            console.print(f"  Name: {session.steam_name}")
        console.print(f"  Seit: {session.authenticated_at}")
        console.print(f"\n[dim]Auth-Datei: {settings.AUTH_FILE}[/dim]")
    else:
        console.print("[yellow]Nicht eingeloggt[/yellow]")
        console.print("\nZum Einloggen: [cyan]lgb login[/cyan]")


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
    Benchmark-Ergebnisse zur Community-Datenbank hochladen.

    Lädt gespeicherte Benchmarks zum Linux Game Bench Server hoch.
    Erfordert vorherigen Login mit 'lgb login'.
    """
    from linux_game_benchmark.api import upload_benchmark, is_logged_in, check_api_status
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage
    from linux_game_benchmark.system.hardware_info import get_system_info

    # Check login
    if not is_logged_in():
        console.print("[red]Nicht eingeloggt![/red]")
        console.print("Bitte zuerst einloggen: [cyan]lgb login[/cyan]")
        raise typer.Exit(1)

    # Check API
    console.print("[dim]Prüfe Server-Verbindung...[/dim]")
    if not check_api_status():
        console.print("[red]Server nicht erreichbar![/red]")
        console.print("[dim]Bitte später erneut versuchen.[/dim]")
        raise typer.Exit(1)

    console.print("[green]✓ Server erreichbar[/green]\n")

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
                console.print(f"[red]Kein Spiel gefunden: {game}[/red]")
                raise typer.Exit(1)
            games_to_upload = matching
    else:
        # Show available games
        available = storage.get_all_games()
        if not available:
            console.print("[yellow]Keine Benchmarks vorhanden.[/yellow]")
            console.print("Erstelle zuerst Benchmarks mit: [cyan]lgb record <game>[/cyan]")
            raise typer.Exit(0)

        console.print("[bold]Verfügbare Benchmarks:[/bold]")
        for i, game_id in enumerate(available, 1):
            resolutions = storage.get_all_resolutions(game_id)
            res_str = ", ".join(resolutions.keys()) if resolutions else "keine"
            console.print(f"  [{i}] {game_id} ({res_str})")

        console.print(f"\n[dim]Nutze 'lgb upload <app_id>' oder 'lgb upload --all'[/dim]")
        return

    # Upload each game
    uploaded = 0
    failed = 0

    for game_id in games_to_upload:
        console.print(f"\n[bold cyan]Uploading: {game_id}[/bold cyan]")

        resolutions = storage.get_all_resolutions(game_id)
        if not resolutions:
            console.print(f"  [yellow]Keine Daten für {game_id}[/yellow]")
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
                resolution=resolution,
                system_info={
                    "gpu": system_info.get("gpu", {}).get("model", "Unknown"),
                    "cpu": system_info.get("cpu", {}).get("model", "Unknown"),
                    "os": system_info.get("os", {}).get("name", "Linux"),
                    "kernel": system_info.get("os", {}).get("kernel"),
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
    console.print(f"\n[bold]Zusammenfassung:[/bold]")
    console.print(f"  Hochgeladen: [green]{uploaded}[/green]")
    if failed:
        console.print(f"  Fehlgeschlagen: [red]{failed}[/red]")


@app.command()
def record_manual(
    show_hud: bool = typer.Option(
        True,
        "--show-hud/--no-hud",
        help="Show MangoHud overlay",
    ),
    duration: int = typer.Option(
        60,
        "--duration",
        "-d",
        help="Recording duration in seconds (0 = manual stop with Shift+F2)",
    ),
) -> None:
    """
    Manueller Recording-Modus ohne Spiel-Auswahl.

    Konfiguriert MangoHud und wartet auf manuelle Aufnahmen.
    Du startest dein Spiel selbst, drückst Shift+F2 für Aufnahmen.
    Spielname und Auflösung werden nach jeder Aufnahme abgefragt.
    """
    import time
    from linux_game_benchmark.mangohud.config_manager import MangoHudConfigManager
    from linux_game_benchmark.analysis.metrics import FrametimeAnalyzer
    from linux_game_benchmark.benchmark.storage import BenchmarkStorage, SystemFingerprint
    from linux_game_benchmark.analysis.report_generator import generate_multi_resolution_report
    from linux_game_benchmark.system.hardware_info import get_system_info

    console.print(f"\n[bold cyan]╔══════════════════════════════════════════╗[/bold cyan]")
    console.print(f"[bold cyan]║     MANUELLER RECORDING MODUS            ║[/bold cyan]")
    console.print(f"[bold cyan]╚══════════════════════════════════════════╝[/bold cyan]\n")

    if duration > 0:
        console.print("[bold yellow]Steuerung:[/bold yellow]")
        console.print(f"  [bold]Shift+F2[/bold] → Aufnahme starten (läuft {duration}s)")
        console.print(f"  [bold]Automatischer Stop[/bold] nach {duration} Sekunden")
        console.print("  [bold]Ctrl+C[/bold] → Beenden\n")
    else:
        console.print("[bold yellow]Steuerung:[/bold yellow]")
        console.print("  [bold]Shift+F2[/bold] → Aufnahme STARTEN")
        console.print("  [bold]Shift+F2[/bold] → Aufnahme STOPPEN")
        console.print("  [bold]Ctrl+C[/bold] → Beenden\n")

    # Setup
    system_info = get_system_info()
    storage = BenchmarkStorage()
    mangohud_manager = MangoHudConfigManager()
    output_dir = Path.home() / "benchmark_results" / "recording_session"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure MangoHud
    mangohud_manager.backup_config()
    mangohud_manager.set_benchmark_config(
        output_folder=output_dir,
        show_hud=show_hud,
        manual_logging=True,
        log_duration=duration,
    )

    console.print("[bold green]✓ MangoHud konfiguriert[/bold green]")
    console.print(f"[dim]Output: {output_dir}[/dim]\n")

    console.print("[bold yellow]Starte jetzt dein Spiel mit:[/bold yellow]")
    console.print("  [cyan]mangohud %command%[/cyan]")
    console.print("  oder für Steam: Launch Options → [cyan]MANGOHUD=1 %command%[/cyan]\n")
    console.print("[bold]Drücke Shift+F2 im Spiel um Aufnahme zu starten...[/bold]")
    console.print("[dim]Warte auf Aufnahmen...[/dim]\n")

    # Track processed logs
    processed_logs = set()
    for existing in output_dir.glob("*.csv"):
        if "_summary" not in existing.name:
            processed_logs.add(existing.name)

    recording_count = 0
    game_reports = {}  # Track which games need reports

    def get_new_logs():
        """Find new log files that haven't been processed."""
        new_logs = []
        for log_file in output_dir.glob("*.csv"):
            if "_summary" not in log_file.name and log_file.name not in processed_logs:
                # Check if file is complete
                size1 = log_file.stat().st_size
                time.sleep(0.5)
                size2 = log_file.stat().st_size
                if size1 == size2 and size1 > 1000:
                    new_logs.append(log_file)
        return new_logs

    def process_log(log_path: Path) -> bool:
        """Process a completed log file."""
        nonlocal recording_count

        console.print(f"\n[bold green]═══ Aufnahme erkannt! ═══[/bold green]")

        try:
            analyzer = FrametimeAnalyzer(log_path)
            metrics = analyzer.analyze()
            fps = metrics.get("fps", {})

            console.print(f"  Frames: {fps.get('frame_count', 0)}")
            console.print(f"  Duration: {fps.get('duration_seconds', 0):.1f}s")
            console.print(f"  AVG FPS: {fps.get('average', 0):.1f}")
            console.print(f"  1% Low: {fps.get('1_percent_low', 0):.1f}")
        except Exception as e:
            console.print(f"[red]Analyse-Fehler: {e}[/red]")
            return True

        # Use GameFinder to find the game
        from linux_game_benchmark.games.game_finder import GameFinder

        finder = GameFinder(console=console)
        existing_games = storage.get_all_games()

        console.print(f"\n[bold]Spielname?[/bold]")

        if existing_games:
            console.print("[dim]Vorhandene Spiele:[/dim]")
            for i, game in enumerate(existing_games, 1):
                console.print(f"  [{i}] {game}")
            console.print(f"  [0] Neues Spiel suchen")
            console.print()

        try:
            query = typer.prompt("Auswahl oder Name", default="0").strip()
        except:
            return True

        # Check if it's a number (selection from existing list)
        game_info = None
        try:
            choice_idx = int(query)
            if 1 <= choice_idx <= len(existing_games):
                # User selected existing game - search for it to get App ID
                game_name = existing_games[choice_idx - 1]
                console.print(f"[green]✓ Ausgewählt: {game_name}[/green]")
                game_info = finder.find(game_name, interactive=False)
            elif choice_idx == 0:
                # User wants to enter new game name
                try:
                    new_name = typer.prompt("Spielname", default="").strip()
                    if new_name:
                        game_info = finder.find(new_name, interactive=True)
                except:
                    return True
        except ValueError:
            # Not a number, search for the game
            game_info = finder.find(query, interactive=True)

        # Extract game name and app_id from GameInfo - Steam App ID required!
        if game_info and game_info.steam_app_id:
            game_name = game_info.name
            app_id = game_info.steam_app_id
            console.print(f"[green]✓ {game_name} (App ID: {app_id})[/green]")
        else:
            console.print("[red]Kein Steam-Spiel gefunden![/red]")
            console.print("[dim]Nur Steam-Spiele können gebenchmarkt werden.[/dim]")
            return True  # Skip this recording, but continue session

        # Track games for report generation with App ID
        if game_name not in game_reports:
            game_reports[game_name] = {"count": 0, "app_id": app_id}
        else:
            # Update app_id if we found one and didn't have one before
            if app_id and not game_reports[game_name]["app_id"]:
                game_reports[game_name]["app_id"] = app_id

        game_reports[game_name]["count"] += 1

        # Ask for resolution
        console.print(f"\n[bold]Auflösung?[/bold]")
        console.print("  [1] FHD (1920×1080)")
        console.print("  [2] WQHD (2560×1440)")
        console.print("  [3] UHD (3840×2160)")
        console.print("  [0] Verwerfen")

        resolution_map = {"1": "1920x1080", "2": "2560x1440", "3": "3840x2160"}

        try:
            choice = typer.prompt("Auswahl", default="1")
        except:
            return True

        if choice == "0":
            console.print("[yellow]Verworfen[/yellow]")
            return True

        resolution = resolution_map.get(choice, "1920x1080")

        # Check/save fingerprint for this game - use Steam App ID for storage
        fp = SystemFingerprint.from_system_info(system_info)
        if not storage.check_fingerprint(app_id, fp):
            console.print("[yellow]Neue System-Config für dieses Spiel[/yellow]")
            storage.archive_old_data(app_id)
        storage.save_fingerprint(app_id, fp, system_info)

        # Register game in registry (creates game_info.json)
        from linux_game_benchmark.games.registry import GameRegistry
        registry = GameRegistry(base_dir=storage.base_dir)
        registry.get_or_create(
            steam_app_id=app_id,
            display_name=game_name,
        )

        # Save run using Steam App ID
        storage.save_run(
            game_id=app_id,
            resolution=resolution,
            metrics=metrics,
            log_path=log_path,
            frametimes=analyzer.frametimes if hasattr(analyzer, 'frametimes') else None,
        )
        recording_count += 1

        console.print(f"[green]✓ Gespeichert: {game_name} @ {resolution}[/green]")
        console.print(f"[dim]Total: {recording_count} Aufnahme(n)[/dim]")

        # Ask if user wants to continue
        console.print(f"\n[bold]Was möchtest du tun?[/bold]")
        console.print("  [1] Weiter aufnehmen (Shift+F2 für nächste)")
        console.print("  [2] Beenden und Reports generieren")

        try:
            continue_choice = typer.prompt("Auswahl", default="1")
        except:
            return True

        if continue_choice == "2":
            console.print("[cyan]Recording wird beendet...[/cyan]")
            return False

        console.print(f"\n[bold yellow]Bereit für nächste Aufnahme (Shift+F2)...[/bold yellow]")
        return True

    try:
        # Monitor for logs
        user_requested_stop = False

        while not user_requested_stop:
            new_logs = get_new_logs()
            for log_path in new_logs:
                processed_logs.add(log_path.name)
                should_continue = process_log(log_path)
                if not should_continue:
                    user_requested_stop = True
                    break

            time.sleep(1.0)

    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen[/yellow]")
    finally:
        # Restore MangoHud config
        mangohud_manager.restore_config()

    # Generate reports for all games
    if recording_count > 0:
        console.print(f"\n[bold]Generiere Reports für {len(game_reports)} Spiel(e)...[/bold]")

        for game_name, info in game_reports.items():
            console.print(f"\n[bold cyan]{game_name}[/bold cyan]")

            # Use Steam App ID for storage operations
            steam_app_id = info.get("app_id")
            if not steam_app_id:
                console.print("  [yellow]Übersprungen - keine Steam App ID[/yellow]")
                continue

            all_res = storage.get_all_resolutions(steam_app_id)
            if all_res:
                resolution_data = {res: storage.aggregate_runs(runs) for res, runs in all_res.items()}
                report_path = storage.get_report_path(steam_app_id)

                generate_multi_resolution_report(
                    game_name=game_name,  # Keep display name for report
                    app_id=steam_app_id,
                    system_info=system_info,
                    resolution_data=resolution_data,
                    output_path=report_path,
                    runs_data=all_res,
                )
                console.print(f"  [green]✓[/green] Report: {report_path}")

    console.print(f"\n[bold]Session beendet - {recording_count} Aufnahme(n) gespeichert[/bold]")


if __name__ == "__main__":
    app()
