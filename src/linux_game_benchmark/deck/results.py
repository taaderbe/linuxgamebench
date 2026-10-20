"""The Steam Deck results of the website (/steamdeck), for the desktop app: fetch, filter, sort, describe.

No Qt in here - the tab only paints what these functions return, so the same numbers can be tested without a window.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import httpx

from linux_game_benchmark.config.settings import settings

MODELS = {"steam_deck_lcd": "LCD", "steam_deck_oled": "OLED", "steam_deck": "Deck"}
SORTS = ("fps", "runs", "name")
SORT_LABELS = {"fps": "Top FPS", "runs": "Most runs", "name": "A-Z"}


def fetch_summary(timeout: float = 15.0) -> dict:
    response = httpx.get(f"{settings.API_BASE_URL}/steamdeck/summary", timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_runs(game_name: str, timeout: float = 15.0) -> list[dict]:
    response = httpx.get(f"{settings.API_BASE_URL}/game/{quote(game_name, safe='')}/all-runs",
                         params={"device": "steamdeck"}, timeout=timeout)
    response.raise_for_status()
    return response.json().get("runs", [])


def games(data: dict, model: str = "all", query: str = "", sort: str = "fps") -> list[dict]:
    """The game rows for the chosen model / search / order: {name, steam_app_id, runs, fps, low, models}."""
    query = query.strip().lower()
    rows = []
    for game in data.get("top_games") or []:
        if model == "all":
            numbers = {"runs": game.get("runs", 0), "fps": game.get("fps_avg", 0), "low": game.get("fps_1low", 0)}
        else:
            part = (game.get("models") or {}).get(model)
            if not part:
                continue
            numbers = {"runs": part.get("runs", 0), "fps": part.get("fps_avg", 0), "low": part.get("fps_1low", 0)}
        if query and query not in str(game.get("name", "")).lower():
            continue
        rows.append({"name": game.get("name", ""), "steam_app_id": game.get("steam_app_id"),
                     "models": {k: round(v.get("fps_avg", 0)) for k, v in (game.get("models") or {}).items()}, **numbers})
    if sort == "name":
        rows.sort(key=lambda r: str(r["name"]).casefold())
    elif sort == "runs":
        rows.sort(key=lambda r: (-r["runs"], -r["fps"]))
    else:
        rows.sort(key=lambda r: (-r["fps"], -r["runs"]))
    return rows


def stats(data: dict) -> list[tuple[str, str]]:
    """The numbers of the header row: runs, games, players and one chip per model."""
    out = [("runs", f"{data.get('runs', 0):,}"), ("games", f"{data.get('games', 0):,}"), ("players", f"{data.get('players', 0):,}")]
    for key in ("steam_deck_lcd", "steam_deck_oled"):
        model = (data.get("models") or {}).get(key)
        if model:
            out.append((f"{MODELS[key]} runs", f"{model.get('runs', 0):,}"))
    return out


def fps_level(fps: float) -> str:
    """Same colours as the website: good from 55, mid from 30."""
    return "good" if fps >= 55 else "mid" if fps >= 30 else "low"


def describe_power(state: Optional[dict], fps: float = 0.0) -> str:
    """'Battery - 12 W TDP - 2.9 FPS/W' style summary of a run's device_state ('' when there is none)."""
    if not state:
        return ""
    power, limits = state.get("power") or {}, state.get("limits") or {}
    source = {"battery": "Battery", "ac": "Plugged in", "mixed": "Plugged/unplugged"}.get(power.get("source"), "")
    parts = [source] if source else []
    if limits.get("tdp_w") is not None:
        parts.append(f"{limits['tdp_w']:g} W TDP")
    watts = power.get("battery_power_avg_w")
    if power.get("source") == "battery" and watts and watts > 1 and fps:
        parts.append(f"{fps / watts:.1f} FPS/W")
    return " - ".join(parts)


def describe_run(run: dict) -> dict:
    """One line of a game's run list."""
    fps = ((run.get("run") or {}).get("metrics") or {}).get("fps") or {}
    average = float(fps.get("average") or 0)
    return {
        "id": run.get("id"),
        "date": str(run.get("timestamp") or "")[:10],
        "model": MODELS.get(run.get("device_class"), "Deck"),
        "resolution": run.get("resolution") or "",
        "fps": round(average), "low1": round(float(fps.get("1_percent_low") or 0)),
        "power": describe_power(run.get("device_state"), average),
        "player": run.get("username") or "anonymous",
    }


def runs_for(runs: list[dict], model: str = "all") -> list[dict]:
    return [describe_run(r) for r in runs if model == "all" or r.get("device_class") == model]
