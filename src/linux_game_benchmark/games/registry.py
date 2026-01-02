"""
Game Registry - Steam-Only Game Management.

Manages game entries using Steam App ID as the canonical identifier.
This ensures no duplicates through typos or name variations.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class GameEntry:
    """A registered game entry."""

    steam_app_id: int
    display_name: str
    cover_url: str
    added_at: str

    @property
    def canonical_id(self) -> str:
        """Get the canonical folder name for this game."""
        return f"steam_{self.steam_app_id}"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "steam_app_id": self.steam_app_id,
            "display_name": self.display_name,
            "cover_url": self.cover_url,
            "added_at": self.added_at,
            "canonical_id": self.canonical_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameEntry":
        """Create from dictionary."""
        return cls(
            steam_app_id=data["steam_app_id"],
            display_name=data["display_name"],
            cover_url=data.get("cover_url", ""),
            added_at=data.get("added_at", datetime.now().isoformat()),
        )


class GameRegistry:
    """
    Steam-Only Game Registry.

    Uses Steam App ID as the canonical identifier for games.
    This prevents duplicates from typos or name variations.

    Structure:
        ~/benchmark_results/
            games.json              <- This registry
            steam_1086940/          <- Game folder (Baldur's Gate 3)
                game_info.json
                ...
            steam_1091500/          <- Game folder (Cyberpunk 2077)
                game_info.json
                ...
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the registry.

        Args:
            base_dir: Base directory for benchmark results.
                     Defaults to ~/benchmark_results
        """
        self.base_dir = base_dir or Path.home() / "benchmark_results"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.base_dir / "games.json"
        self._registry: dict[int, GameEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text())
                for app_id_str, entry_data in data.items():
                    app_id = int(app_id_str)
                    self._registry[app_id] = GameEntry.from_dict(entry_data)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupted file, start fresh
                self._registry = {}

    def _save(self) -> None:
        """Save registry to disk."""
        data = {
            str(app_id): entry.to_dict()
            for app_id, entry in self._registry.items()
        }
        self.registry_file.write_text(json.dumps(data, indent=2))

    def get(self, steam_app_id: int) -> Optional[GameEntry]:
        """
        Get a game entry by Steam App ID.

        Args:
            steam_app_id: The Steam App ID

        Returns:
            GameEntry if found, None otherwise
        """
        return self._registry.get(steam_app_id)

    def get_or_create(
        self,
        steam_app_id: int,
        display_name: str,
        cover_url: Optional[str] = None,
    ) -> GameEntry:
        """
        Get existing entry or create new one.

        Args:
            steam_app_id: The Steam App ID
            display_name: Display name for the game
            cover_url: Optional cover image URL

        Returns:
            The GameEntry (existing or newly created)
        """
        if steam_app_id in self._registry:
            return self._registry[steam_app_id]

        # Generate cover URL if not provided
        if not cover_url:
            cover_url = (
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/"
                f"{steam_app_id}/header.jpg"
            )

        # Create new entry
        entry = GameEntry(
            steam_app_id=steam_app_id,
            display_name=display_name,
            cover_url=cover_url,
            added_at=datetime.now().isoformat(),
        )

        self._registry[steam_app_id] = entry
        self._save()

        # Also save game_info.json in the game folder
        self._save_game_info(entry)

        return entry

    def _save_game_info(self, entry: GameEntry) -> None:
        """Save game_info.json in the game folder."""
        game_dir = self.base_dir / entry.canonical_id
        game_dir.mkdir(parents=True, exist_ok=True)

        info_file = game_dir / "game_info.json"
        info_file.write_text(json.dumps(entry.to_dict(), indent=2))

    def get_canonical_id(self, steam_app_id: int) -> str:
        """
        Get the canonical folder name for a Steam App ID.

        Args:
            steam_app_id: The Steam App ID

        Returns:
            Canonical ID like "steam_1086940"
        """
        return f"steam_{steam_app_id}"

    def get_game_dir(self, steam_app_id: int) -> Path:
        """
        Get the directory path for a game.

        Args:
            steam_app_id: The Steam App ID

        Returns:
            Path to the game directory
        """
        canonical_id = self.get_canonical_id(steam_app_id)
        game_dir = self.base_dir / canonical_id
        game_dir.mkdir(parents=True, exist_ok=True)
        return game_dir

    def list_all(self) -> list[GameEntry]:
        """
        List all registered games.

        Returns:
            List of all GameEntry objects
        """
        return list(self._registry.values())

    def find_by_name(self, query: str) -> list[GameEntry]:
        """
        Find games by name (fuzzy search).

        Args:
            query: Search query

        Returns:
            List of matching GameEntry objects
        """
        query_lower = query.lower()
        matches = []

        for entry in self._registry.values():
            if query_lower in entry.display_name.lower():
                matches.append(entry)

        return matches

    def remove(self, steam_app_id: int) -> bool:
        """
        Remove a game from the registry.

        Note: This only removes from registry, not the actual data!

        Args:
            steam_app_id: The Steam App ID

        Returns:
            True if removed, False if not found
        """
        if steam_app_id in self._registry:
            del self._registry[steam_app_id]
            self._save()
            return True
        return False

    def sync_from_folders(self) -> int:
        """
        Sync registry from existing folder structure.

        Useful for migrating from old format or recovering registry.

        Returns:
            Number of games synced
        """
        synced = 0

        for folder in self.base_dir.iterdir():
            if not folder.is_dir():
                continue

            # Check for steam_XXXXX format
            if folder.name.startswith("steam_"):
                try:
                    app_id = int(folder.name.replace("steam_", ""))

                    # Check for game_info.json
                    info_file = folder / "game_info.json"
                    if info_file.exists():
                        data = json.loads(info_file.read_text())
                        if app_id not in self._registry:
                            self._registry[app_id] = GameEntry.from_dict(data)
                            synced += 1

                except (ValueError, json.JSONDecodeError, KeyError):
                    continue

        if synced > 0:
            self._save()

        return synced
