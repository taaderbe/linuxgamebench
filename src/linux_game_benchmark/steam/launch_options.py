"""
Steam Launch Options Manager.

Modifies Steam's localconfig.vdf to set launch options for games.
"""

import re
import shutil
from pathlib import Path
from typing import Optional


def find_localconfig() -> Optional[Path]:
    """Find Steam's localconfig.vdf file."""
    from linux_game_benchmark.steam.library_scanner import (
        STEAM_PATH_CANDIDATES, find_steam_path,
    )

    # Detected/saved Steam path first (covers Snap and custom locations)
    steam_paths = []
    detected = find_steam_path()
    if detected:
        steam_paths.append(detected)
    steam_paths.extend(p for p in STEAM_PATH_CANDIDATES if p not in steam_paths)

    for steam_path in steam_paths:
        userdata = steam_path / "userdata"
        if userdata.exists():
            # Find first user directory
            for user_dir in userdata.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    config = user_dir / "config" / "localconfig.vdf"
                    if config.exists():
                        return config
    return None


def get_launch_options(app_id: int) -> Optional[str]:
    """Get current launch options for a game."""
    config_path = find_localconfig()
    if not config_path:
        return None

    content = config_path.read_text()

    # Look for LaunchOptions in the apps section
    # Pattern: "apps" { ... "<app_id>" { ... "LaunchOptions" "<options>" ... } ... }
    pattern = rf'"apps"[^{{]*\{{[^}}]*"{app_id}"[^{{]*\{{[^}}]*"LaunchOptions"\s+"([^"]*)"'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1)
    return None


def set_launch_options(app_id: int, options: str, backup: bool = True) -> bool:
    """
    Set launch options for a Steam game.

    Args:
        app_id: Steam App ID
        options: Launch options string
        backup: Create backup before modifying

    Returns:
        True if successful
    """
    config_path = find_localconfig()
    if not config_path:
        raise FileNotFoundError("Steam localconfig.vdf not found")

    # Create backup
    if backup:
        backup_path = config_path.with_suffix(".vdf.bak")
        shutil.copy2(config_path, backup_path)

    content = config_path.read_text()

    # Check if app entry exists in "apps" section under "Software" -> "Valve" -> "Steam"
    # VDF structure is nested, we need to find the right place

    # First, try to find existing LaunchOptions for this app
    # Pattern to find the app block
    app_pattern = rf'("{app_id}"\s*\{{[^}}]*)\}}'

    def replace_or_add_launch_options(match):
        block = match.group(1)
        # Check if LaunchOptions already exists
        if '"LaunchOptions"' in block:
            # Replace existing
            block = re.sub(
                r'"LaunchOptions"\s+"[^"]*"',
                f'"LaunchOptions"\t\t"{options}"',
                block
            )
        else:
            # Add new LaunchOptions before closing brace
            block = block.rstrip() + f'\n\t\t\t\t\t\t"LaunchOptions"\t\t"{options}"\n\t\t\t\t\t'
        return block + "}"

    # Find the apps section and modify
    new_content = content

    # Look for the app in the Apps section (capital A)
    apps_section_pattern = r'("Apps"\s*\{)(.*?)(\n\s*\})'
    apps_match = re.search(apps_section_pattern, content, re.DOTALL | re.IGNORECASE)

    if apps_match:
        apps_content = apps_match.group(2)

        # Check if our app exists
        app_entry_pattern = rf'("{app_id}"\s*\{{)(.*?)(\}})'
        app_match = re.search(app_entry_pattern, apps_content, re.DOTALL)

        if app_match:
            app_block = app_match.group(2)
            if '"LaunchOptions"' in app_block:
                # Replace existing
                new_app_block = re.sub(
                    r'"LaunchOptions"\s+"[^"]*"',
                    f'"LaunchOptions"\t\t"{options}"',
                    app_block
                )
            else:
                # Add LaunchOptions
                new_app_block = app_block.rstrip() + f'\n\t\t\t\t\t\t"LaunchOptions"\t\t"{options}"\n\t\t\t\t\t'

            new_apps_content = apps_content.replace(
                app_match.group(0),
                app_match.group(1) + new_app_block + app_match.group(3)
            )
            new_content = content.replace(apps_content, new_apps_content)
        else:
            # App doesn't exist in Apps section, need to add it
            new_app_entry = f'\n\t\t\t\t\t"{app_id}"\n\t\t\t\t\t{{\n\t\t\t\t\t\t"LaunchOptions"\t\t"{options}"\n\t\t\t\t\t}}'
            new_apps_content = apps_content + new_app_entry
            new_content = content.replace(apps_content, new_apps_content)

    # Write the modified content
    config_path.write_text(new_content)
    return True


def set_benchmark_launch_options(
    app_id: int,
    mangohud_config: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
) -> str:
    """
    Set launch options for benchmarking with MangoHud.

    Args:
        app_id: Steam App ID
        mangohud_config: Path to MangoHud config file
        extra_args: Extra arguments (e.g., ["-benchmark"])

    Returns:
        The launch options string that was set
    """
    parts = ["MANGOHUD=1"]

    if mangohud_config:
        parts.append(f"MANGOHUD_CONFIGFILE={mangohud_config}")

    parts.append("MANGOHUD_LOG_INTERVAL=0")  # Per-frame logging
    parts.append("%command%")

    if extra_args:
        parts.extend(extra_args)

    options = " ".join(parts)
    set_launch_options(app_id, options)

    return options


def clear_launch_options(app_id: int) -> bool:
    """Remove launch options for a game."""
    return set_launch_options(app_id, "")


def get_original_launch_options(app_id: int) -> Optional[str]:
    """Get launch options from backup file."""
    config_path = find_localconfig()
    if not config_path:
        return None

    backup_path = config_path.with_suffix(".vdf.bak")
    if not backup_path.exists():
        return None

    content = backup_path.read_text()
    pattern = rf'"Apps"[^{{]*\{{[^}}]*"{app_id}"[^{{]*\{{[^}}]*"LaunchOptions"\s+"([^"]*)"'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1)
    return None


def restore_launch_options(app_id: int) -> bool:
    """Restore original launch options from backup."""
    original = get_original_launch_options(app_id)
    if original is not None:
        return set_launch_options(app_id, original, backup=False)
    return clear_launch_options(app_id)
