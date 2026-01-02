"""
Steam-Only Game Finder.

Searches for Steam games only. Non-Steam games are not supported.
This ensures consistent game identification via Steam App ID.
"""

from typing import Optional, Callable
from rich.console import Console
from rich.table import Table

from linux_game_benchmark.games.models import GameInfo, GameSource
from linux_game_benchmark.games.registry import GameRegistry
from linux_game_benchmark.steam.library_scanner import SteamLibraryScanner
from linux_game_benchmark.steam.app_id_finder import (
    find_steam_app_id,
    get_multiple_matches,
    similarity,
)


class NoSteamGameFoundError(Exception):
    """Raised when no Steam game could be found for the query."""

    pass


class GameFinder:
    """
    Steam-Only Game Finder.

    Only finds Steam games. Without a Steam App ID, no benchmark is possible.
    This ensures:
    - No duplicate entries from typos
    - Consistent game identification
    - Cover images always available

    Usage:
        finder = GameFinder()
        game = finder.find("Baldur's Gate 3")
        if game:
            print(f"Found: {game.name} (App ID: {game.steam_app_id})")
        else:
            print("No Steam game found!")
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        on_status: Optional[Callable[[str], None]] = None,
        registry: Optional[GameRegistry] = None,
    ):
        """
        Initialize the game finder.

        Args:
            console: Rich console for output (optional)
            on_status: Callback for status messages (optional)
            registry: GameRegistry instance (optional, creates new if None)
        """
        self.console = console or Console()
        self.on_status = on_status
        self.registry = registry
        self._steam_scanner: Optional[SteamLibraryScanner] = None
        self._local_games_cache: Optional[list[dict]] = None

    def _log(self, message: str) -> None:
        """Log a status message."""
        if self.on_status:
            self.on_status(message)

    @property
    def steam_scanner(self) -> Optional[SteamLibraryScanner]:
        """Lazy-load Steam scanner."""
        if self._steam_scanner is None:
            try:
                self._steam_scanner = SteamLibraryScanner()
            except FileNotFoundError:
                pass
        return self._steam_scanner

    @property
    def local_games(self) -> list[dict]:
        """Get cached list of locally installed games."""
        if self._local_games_cache is None:
            if self.steam_scanner:
                try:
                    self._local_games_cache = self.steam_scanner.scan()
                except Exception:
                    self._local_games_cache = []
            else:
                self._local_games_cache = []
        return self._local_games_cache

    def find(
        self,
        query: str,
        interactive: bool = True,
        auto_select_threshold: float = 0.95,
        require_steam: bool = True,
    ) -> Optional[GameInfo]:
        """
        Find a Steam game by name or App ID.

        Search order:
        1. Local Steam library (installed games)
        2. Steam Store API (all Steam games)

        If no Steam game is found, returns None (no manual fallback!).

        Args:
            query: Game name or Steam App ID
            interactive: If True, show selection menu for multiple matches
            auto_select_threshold: Auto-select if similarity >= this value
            require_steam: If True, return None if no Steam game found

        Returns:
            GameInfo if found, None if not found or user cancelled
        """
        # Try to parse as App ID first
        try:
            app_id = int(query)
            return self._find_by_app_id(app_id)
        except ValueError:
            pass

        # Search by name
        self._log(f"Suche nach '{query}'...")

        # 1. Check local Steam library
        local_result = self._search_local(query)
        if local_result:
            self._log("Gefunden in lokaler Steam-Bibliothek")
            return local_result

        # 2. Search Steam Store
        steam_results = self._search_steam_store(query)
        if steam_results:
            self._log(f"Gefunden im Steam Store ({len(steam_results)} Treffer)")

            # Auto-select if high confidence match
            if steam_results[0].similarity_score >= auto_select_threshold:
                return steam_results[0]

            # Interactive selection
            if interactive and len(steam_results) > 1:
                return self._interactive_select(steam_results, query)

            return steam_results[0]

        # No Steam game found
        if require_steam:
            self.console.print(
                "\n[red]Kein Steam-Spiel gefunden![/red]\n"
                "[dim]Nur Steam-Spiele werden unterstützt.\n"
                "Tipp: Versuche den exakten Spielnamen oder die Steam App ID.[/dim]"
            )
            return None

        return None

    def find_required(
        self,
        query: str,
        interactive: bool = True,
    ) -> GameInfo:
        """
        Find a Steam game, raise exception if not found.

        Args:
            query: Game name or Steam App ID
            interactive: If True, show selection menu for multiple matches

        Returns:
            GameInfo (always has steam_app_id)

        Raises:
            NoSteamGameFoundError: If no Steam game found
        """
        result = self.find(query, interactive=interactive, require_steam=True)
        if result is None or result.steam_app_id is None:
            raise NoSteamGameFoundError(
                f"Kein Steam-Spiel gefunden für: {query}"
            )
        return result

    def _find_by_app_id(self, app_id: int) -> Optional[GameInfo]:
        """Find game by Steam App ID."""
        # Check local first
        if self.steam_scanner:
            local = self.steam_scanner.get_game_by_id(app_id)
            if local:
                return GameInfo.from_steam_local(local)

        # Create from App ID (valid Steam game, just not installed)
        return GameInfo(
            name=f"Steam App {app_id}",
            source=GameSource.STEAM_STORE,
            steam_app_id=app_id,
            is_installed=False,
        )

    def _search_local(self, query: str) -> Optional[GameInfo]:
        """Search local Steam library."""
        query_lower = query.lower()

        best_match: Optional[dict] = None
        best_score = 0.0

        for game in self.local_games:
            game_name = game.get("name", "").lower()

            # Exact match
            if query_lower == game_name:
                return GameInfo.from_steam_local(game)

            # Partial match
            if query_lower in game_name:
                score = similarity(query, game.get("name", ""))
                if score > best_score:
                    best_score = score
                    best_match = game

        if best_match and best_score >= 0.6:
            result = GameInfo.from_steam_local(best_match)
            result.similarity_score = best_score
            return result

        return None

    def _search_steam_store(self, query: str) -> list[GameInfo]:
        """Search Steam Store API."""
        matches = get_multiple_matches(query, limit=5)

        results = []
        for match in matches:
            game = GameInfo.from_steam_store(
                app_id=match["appid"],
                name=match["name"],
                similarity=match["similarity"],
            )
            results.append(game)

        return results

    def _interactive_select(
        self,
        games: list[GameInfo],
        original_query: str,
    ) -> Optional[GameInfo]:
        """
        Show interactive selection menu.

        Args:
            games: List of games to choose from
            original_query: Original search query

        Returns:
            Selected GameInfo or None if cancelled
        """
        self.console.print(f"\n[bold]Mehrere Treffer für '{original_query}':[/bold]")

        # Build selection table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Num", style="cyan", width=4)
        table.add_column("Name", style="white")
        table.add_column("ID", style="dim")
        table.add_column("Match", style="green")

        for i, game in enumerate(games, 1):
            match_pct = f"{game.similarity_score * 100:.0f}%"
            app_id = str(game.steam_app_id) if game.steam_app_id else "-"
            table.add_row(f"[{i}]", game.name, app_id, match_pct)

        table.add_row("[0]", "[red]Abbrechen[/red]", "", "")

        self.console.print(table)

        # Get selection
        try:
            choice = input("\nAuswahl [1]: ").strip() or "1"
            choice_idx = int(choice)

            if choice_idx == 0:
                # User cancelled
                return None

            if 1 <= choice_idx <= len(games):
                return games[choice_idx - 1]

            # Invalid choice, return first match
            return games[0]

        except (ValueError, KeyboardInterrupt):
            return games[0] if games else None

    def find_all_local(self) -> list[GameInfo]:
        """Get all locally installed games as GameInfo objects."""
        return [GameInfo.from_steam_local(g) for g in self.local_games]

    def register_game(self, game_info: GameInfo) -> str:
        """
        Register a game in the registry and return canonical ID.

        Args:
            game_info: The game to register

        Returns:
            Canonical ID (e.g., "steam_1086940")

        Raises:
            ValueError: If game has no Steam App ID
        """
        if game_info.steam_app_id is None:
            raise ValueError("Nur Steam-Spiele können registriert werden!")

        if self.registry is None:
            self.registry = GameRegistry()

        entry = self.registry.get_or_create(
            steam_app_id=game_info.steam_app_id,
            display_name=game_info.name,
            cover_url=game_info.get_cover_url(),
        )

        return entry.canonical_id
