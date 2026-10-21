"""`lgb deck ...` - everything the Steam Deck needs, in a handful of commands."""

from __future__ import annotations

import json
import os
import signal
import time
import webbrowser
from typing import Optional

import typer
from rich.console import Console

from linux_game_benchmark.deck import config as deck_config
from linux_game_benchmark.deck import setup as deck_setup
from linux_game_benchmark.deck.chord import (
    ChordLearner, GamepadReader, format_chord, parse_chord,
)
from linux_game_benchmark.deck.detect import detect_steam_deck

deck_app = typer.Typer(help="Steam Deck: record with a controller chord, upload automatically.", no_args_is_help=True)
console = Console()


@deck_app.command()
def setup(
    yes: bool = typer.Option(False, "--yes", "-y", help="No questions: auto-upload on, pair if needed"),
    anonymous: bool = typer.Option(False, "--anonymous", envvar="LGB_ANON",
                                   help="No account: recordings upload anonymously (link one any time with: deck link)"),
    no_pair: bool = typer.Option(False, "--no-pair", hidden=True, help="Same as --anonymous"),
    force: bool = typer.Option(False, "--force", help="Set up even if this is not a Steam Deck"),
    seconds: Optional[int] = typer.Option(None, "--seconds", help="Length of one recording in seconds (30-300, default 60)"),
) -> None:
    """One-time setup (safe to run again): recorder, background service, sounds, account link."""
    deck = detect_steam_deck()
    if deck.is_deck:
        console.print(f"[green]{deck.name} detected[/green]"
                      f"{' (SteamOS ' + deck.steamos_version + ')' if deck.steamos_version else ''}")
        if deck.handheld:
            console.print("[dim]Only the Steam Deck is verified on real hardware - on this handheld some values may be missing "
                          "and the controller chord may differ. Please tell us what you find.[/dim]")
    elif not force:
        console.print("[yellow]This does not look like a Steam Deck or another supported handheld "
                      "(ROG Ally, Legion Go, MSI Claw, AYANEO, GPD, ONEXPLAYER). Use --force to set it up anyway.[/yellow]")
        raise typer.Exit(1)

    cfg = deck_config.DeckConfig.load()
    if seconds is not None:
        cfg.record_seconds = float(min(max(seconds, cfg.min_seconds), cfg.max_seconds))
    if not yes:
        cfg.auto_upload = typer.confirm("Upload every recording automatically as soon as it is done?", default=True)
    cfg.save()

    deck_setup.write_mangohud_conf()
    deck_setup.write_env_file()
    deck_setup.ensure_sounds()
    deck_setup.write_link_launcher()
    ok, message = deck_setup.install_service()
    console.print(f"{'[green]✓[/green]' if ok else '[red]✗[/red]'} background service: {message}")

    from linux_game_benchmark.api.auth import is_logged_in
    if is_logged_in():
        console.print("[green]✓[/green] account already linked")
    elif anonymous or no_pair:
        console.print("[green]✓[/green] no account: recordings upload anonymously")
        _link_later_hint()
    elif yes or typer.confirm("Link your Linux Game Bench account now? (optional, no password needed)", default=True):
        if _pair(allow_skip=True) != "linked":
            _link_later_hint()
    else:
        console.print("[green]✓[/green] no account: recordings upload anonymously")
        _link_later_hint()

    console.print(f"\nRecord with: hold [bold]{cfg.chord.split('>')[0].replace('+', ' + ')}[/bold], "
                  f"then press [bold]{cfg.chord.split('>')[1]}[/bold]. It records {cfg.record_seconds:.0f} s, "
                  f"stops by itself{' and uploads' if cfg.auto_upload else ''} (the same chord ends it earlier).")
    console.print("[bold]Now switch back to Game Mode - that is all.[/bold]")


def _link_later_hint() -> None:
    console.print("  An account is optional. To link one any time:")
    console.print(f"    [bold]{deck_setup.app_command()} deck link[/bold]")
    console.print('    or open "Linux Game Bench - link account" in the application menu (Desktop Mode),')
    console.print("    or use the Steam Deck tab of the app.")


def _pair(allow_skip: bool = False) -> str:
    """Run the account link. Returns "linked", "skipped" (Enter pressed) or "failed"."""
    from linux_game_benchmark.deck import pairing
    from linux_game_benchmark.deck.ttyinput import EnterWatcher

    watcher = EnterWatcher() if allow_skip else None
    can_skip = watcher is not None and watcher.available

    def show(info: dict) -> None:
        console.print(f"\nOn your phone or PC open  [bold cyan]{info['verification_url']}[/bold cyan]")
        console.print(f"and enter the code  [bold yellow]{info['user_code']}[/bold yellow]\n")
        complete = info.get("verification_url_complete")
        if complete and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            webbrowser.open(complete or info["verification_url"])
        console.print("[dim]Waiting for approval..." + (" (press Enter to continue without an account)" if can_skip else "") + "[/dim]")

    try:
        session = pairing.pair(show, interrupt=watcher.wait if can_skip else None)
    except pairing.PairingSkipped:
        console.print("[green]✓[/green] continuing without an account - recordings upload anonymously")
        return "skipped"
    except pairing.PairingError as exc:
        console.print(f"[red]Linking failed:[/red] {exc}")
        return "failed"
    finally:
        if watcher is not None:
            watcher.close()
    console.print(f"[green]✓ linked as {session.get_username()}[/green]")
    return "linked"


@deck_app.command(name="link")
def link(
    again: bool = typer.Option(False, "--again", help="Link even if an account is already linked (replaces it)"),
    pause: bool = typer.Option(False, "--pause", help="Wait for Enter before closing (used by the menu entry)"),
) -> None:
    """Link this Deck to your account with a short code - optional, uploads work without one."""
    from linux_game_benchmark.api.auth import get_current_session

    session = get_current_session()
    result = "linked"
    if session and not again:
        console.print(f"Already linked as [bold]{session.get_username()}[/bold]. "
                      f"To use another account: {deck_setup.app_command()} deck unlink, then deck link.")
    else:
        result = _pair(allow_skip=True)
    if pause:
        try:
            input("\nPress Enter to close this window ... ")
        except EOFError:
            pass
    raise typer.Exit(1 if result == "failed" else 0)


deck_app.command(name="pair", hidden=True)(link)             # the first name of the command


@deck_app.command()
def unlink() -> None:
    """Stop using your account on this Deck: recordings upload anonymously again."""
    from linux_game_benchmark.api.auth import get_current_session, logout

    session = get_current_session()
    if session is None:
        console.print("No account is linked - recordings already upload anonymously.")
        return
    name = session.get_username()
    ok, message = logout()
    if not ok:
        console.print(f"[red]{message}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] {name} unlinked - recordings upload anonymously now. Link again any time: {deck_setup.app_command()} deck link")


@deck_app.command()
def run() -> None:
    """Run the recorder in the foreground (the background service does exactly this)."""
    from linux_game_benchmark.deck.queue import Queue
    from linux_game_benchmark.deck.service import DeckService, run_forever

    cfg = deck_config.DeckConfig.load()
    deck = detect_steam_deck()
    sounds = deck_setup.ensure_sounds()

    def play(name: str) -> None:
        if name in sounds:
            deck_setup.play(sounds[name])

    stopping = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.update(flag=True))

    reader = GamepadReader()
    service = DeckService(
        cfg, deck,
        queue=Queue(deck_config.queue_dir()),
        log_dir=deck_config.log_dir(),
        work_dir=deck_config.data_dir() / "work",
        play=play,
        say=lambda text: print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True),
        status_file=deck_config.data_dir() / "status.json",
    )
    print(f"Linux Game Bench Deck recorder - chord {cfg.chord}, auto-upload {'on' if cfg.auto_upload else 'off'}", flush=True)
    run_forever(service, reader, stop=lambda: stopping["flag"])
    reader.close()


@deck_app.command()
def status() -> None:
    """What is set up, is the service running, what happened to the latest recordings."""
    from linux_game_benchmark.api.auth import get_current_session
    from linux_game_benchmark.deck.queue import Queue

    deck = detect_steam_deck()
    cfg = deck_config.DeckConfig.load()
    console.print(f"Device:      {deck.name if deck.is_deck else 'not a supported handheld'}"
                  f"{' (Game Mode)' if deck.game_mode else ''}")
    console.print(f"Service:     {deck_setup.service_state()}")
    console.print(f"Chord:       {cfg.chord}   recording: {cfg.record_seconds:.0f} s   "
                  f"auto-upload: {'on' if cfg.auto_upload else 'off'}")
    session = get_current_session()
    console.print(f"Account:     {session.get_username() if session else 'none - uploads are anonymous (link: ' + deck_setup.app_command() + ' deck link)'}")
    reader = GamepadReader()
    pads = reader.rescan()
    console.print(f"Controller:  {', '.join(pads) if pads else 'no gamepad found'}"
                  f"{'  (no permission for ' + ', '.join(reader.denied) + ')' if reader.denied else ''}")
    reader.close()
    conf_ok = deck_setup.is_managed(deck_setup.mangohud_conf_path())
    console.print(f"MangoHud:    {'configured' if conf_ok else 'not configured (lgb deck setup)'}")
    items = Queue(deck_config.queue_dir()).items()
    console.print(f"Recordings:  {len(items)}  (" + ", ".join(
        f"{n} {s}" for s, n in sorted({s: sum(1 for i in items if i.status == s) for s in {i.status for i in items}}.items())) + ")")
    for item in items[-5:]:
        meta = item.meta
        console.print(f"  {item.id}  {meta.get('game_name') or '?'}  {meta.get('seconds', 0):.0f}s  [{item.status}]"
                      f"{'  ' + meta['url'] if meta.get('url') else ''}{'  ' + meta['error'] if meta.get('error') else ''}")
    status_file = deck_config.data_dir() / "status.json"
    try:
        info = json.loads(status_file.read_text())
        age = time.time() - info.get("time", 0)
        console.print(f"Recorder:    {info.get('phase')} (updated {age:.0f}s ago) - {info.get('message') or ''}")
    except (OSError, ValueError):
        console.print("Recorder:    no status yet (service not started?)")


@deck_app.command()
def chord(
    set_to: Optional[str] = typer.Option(None, "--set", help="e.g. LB+RB>VIEW (hold LB and RB, press VIEW)"),
    learn: bool = typer.Option(False, "--learn", help="Press and hold two buttons, then press a third"),
) -> None:
    """Show, set or learn the recording chord."""
    cfg = deck_config.DeckConfig.load()
    if learn:
        reader = GamepadReader()
        if not reader.rescan():
            console.print("[red]No gamepad found.[/red]" + (" No permission for: " + ", ".join(reader.denied) if reader.denied else ""))
            raise typer.Exit(1)
        console.print("Hold two buttons, then press a third one ... (Ctrl+C to abort)")
        learner = ChordLearner()
        try:
            while True:
                for code, value in reader.read(0.5):
                    found = learner.feed(code, value)
                    if found:
                        set_to = format_chord(found)
                        raise StopIteration
        except StopIteration:
            pass
        finally:
            reader.close()
    if set_to:
        try:
            parse_chord(set_to)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        cfg.chord = set_to.upper()
        cfg.save()
        console.print(f"[green]Chord set to {cfg.chord}[/green] (restart the service: systemctl --user restart lgb-deck)")
        return
    console.print(f"Current chord: {cfg.chord}  (hold {cfg.chord.split('>')[0].replace('+', ' + ')}, press {cfg.chord.split('>')[1]})")


@deck_app.command()
def upload() -> None:
    """Upload everything that is still waiting (offline recordings) right now."""
    from linux_game_benchmark.deck.queue import Queue
    from linux_game_benchmark.deck.service import DeckService

    cfg = deck_config.DeckConfig.load()
    service = DeckService(cfg, detect_steam_deck(), queue=Queue(deck_config.queue_dir()),
                          log_dir=deck_config.log_dir(), work_dir=deck_config.data_dir() / "work",
                          say=lambda text: console.print(text))
    waiting = [i for i in service.queue.items() if i.status in ("pending", "local", "failed")]
    if not waiting:
        console.print("Nothing waiting.")
        return
    for item in waiting:
        service.upload_item(item)


@deck_app.command()
def remove() -> None:
    """Undo the setup (service, MangoHud config, environment). Recordings stay."""
    for path in deck_setup.remove_all():
        console.print(f"removed {path}")
    console.print("Done. Switch to Desktop Mode and back (or reboot) to stop MangoHud loading.")
