"""
Remember the GPU driver and Proton build of the last upload per game.

After a Mesa/NVIDIA or Proton update the client can then suggest a re-run
("did the update make it faster?") - the data that makes performance-over-time
comparisons on the website interesting.

Stored in ~/.config/lgb/last_env.json, never uploaded.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from linux_game_benchmark.config.settings import settings

MAX_GAMES = 200


def _env_file() -> Path:
    return settings.CONFIG_DIR / "last_env.json"


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(_env_file().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: Dict[str, Any]) -> None:
    path = _env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def record_upload(steam_app_id: int, game_name: str, system: Dict[str, Any]) -> None:
    """Store the environment of a successful upload (called by the API client)."""
    if not steam_app_id:
        return
    data = _load()
    games = data.setdefault("games", {})
    games[str(steam_app_id)] = {
        "name": game_name,
        "gpu": system.get("gpu"),
        "gpu_driver": system.get("gpu_driver"),
        "kernel": system.get("kernel"),
        "proton_build": system.get("proton_build"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if len(games) > MAX_GAMES:  # keep the most recent ones
        newest = sorted(games.items(), key=lambda kv: kv[1].get("uploaded_at", ""), reverse=True)
        data["games"] = dict(newest[:MAX_GAMES])
    _save(data)


def _same_gpu(recorded: Optional[str], current: Optional[str]) -> bool:
    if not recorded or not current:
        return True
    a, b = recorded.lower(), current.lower()
    return a in b or b in a


def driver_changes(current_gpu: Optional[str], current_driver: Optional[str]) -> List[Dict[str, Any]]:
    """Games last uploaded on this GPU with a different driver version."""
    if not current_driver:
        return []
    changes = []
    for app_id, entry in _load().get("games", {}).items():
        old = entry.get("gpu_driver")
        if old and old != current_driver and _same_gpu(entry.get("gpu"), current_gpu):
            changes.append({"app_id": int(app_id), "name": entry.get("name") or app_id,
                            "old": old, "new": current_driver})
    return changes


def proton_changes() -> List[Dict[str, Any]]:
    """Games whose prefix now points to a different Proton build than at the last upload.

    Rolling tools (Experimental, Hotfix) update in place, so this also catches
    "Proton Experimental got a new build" before the game was started again."""
    from linux_game_benchmark.steam.proton_detect import _compatdata_dirs, read_prefix_proton

    changes = []
    for app_id, entry in _load().get("games", {}).items():
        old = entry.get("proton_build")
        if not old:
            continue
        try:
            dirs = _compatdata_dirs(int(app_id))
            current = read_prefix_proton(dirs[0]).get("proton_build") if dirs else None
        except Exception:
            current = None
        if current and current != old:
            changes.append({"app_id": int(app_id), "name": entry.get("name") or app_id,
                            "old": old, "new": current})
    return changes


def _names(changes: List[Dict[str, Any]], limit: int = 3) -> str:
    names = [str(c["name"]) for c in changes[:limit]]
    more = len(changes) - limit
    return ", ".join(names) + (f" and {more} more" if more > 0 else "")


def rerun_hints(current_gpu: Optional[str] = None, current_driver: Optional[str] = None) -> List[str]:
    """Human-readable re-run suggestions (empty list = nothing changed / nothing recorded)."""
    hints = []
    try:
        drv = driver_changes(current_gpu, current_driver)
        if drv:
            hints.append(f"GPU driver changed since your last upload ({drv[0]['old']} → {drv[0]['new']}). "
                         f"Re-run {_names(drv)} to see if it got faster.")
        prot = proton_changes()
        if prot:
            if len(prot) == 1:
                hints.append(f"Proton for {prot[0]['name']} changed ({prot[0]['old']} → {prot[0]['new']}). "
                             "A new run shows whether the update helped.")
            else:
                hints.append(f"Proton changed for {_names(prot)} since your last upload. "
                             "New runs show whether the update helped.")
    except Exception:
        return []
    return hints
