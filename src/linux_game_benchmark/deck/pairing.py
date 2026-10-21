"""Link the Deck to an account without typing a password (device code flow).

The Deck asks the server for a short code, shows it (and opens the link), the user approves it
on a phone or PC where they are logged in, and the Deck receives the same tokens 'lgb login' stores.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import httpx

from linux_game_benchmark.api.auth import AuthSession
from linux_game_benchmark.config.settings import settings


class PairingError(Exception):
    pass


class PairingSkipped(PairingError):
    """The person chose to go on without an account."""


def start(base_url: Optional[str] = None, label: str = "Steam Deck", timeout: float = 15.0) -> dict:
    base_url = base_url or settings.API_BASE_URL
    try:
        response = httpx.post(f"{base_url}/auth/device/start", json={"label": label}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise PairingError(f"cannot reach the server: {exc}") from exc
    if response.status_code != 200:
        raise PairingError(f"the server refused the request ({response.status_code})")
    data = response.json()
    for key in ("device_code", "user_code", "verification_url", "expires_in"):
        if key not in data:
            raise PairingError("unexpected answer from the server")
    return data


def poll(device_code: str, base_url: Optional[str] = None, timeout: float = 15.0) -> dict:
    """{'status': 'pending'} or {'status': 'approved', access_token, refresh_token, user}; raises when expired/denied."""
    base_url = base_url or settings.API_BASE_URL
    try:
        response = httpx.post(f"{base_url}/auth/device/poll", json={"device_code": device_code}, timeout=timeout)
    except httpx.HTTPError:
        return {"status": "pending"}                 # a network blip must not end the pairing
    if response.status_code == 200:
        return response.json()
    if response.status_code in (400, 403, 404, 410):
        detail = ""
        try:
            detail = str(response.json().get("detail", ""))
        except ValueError:
            pass
        raise PairingError(detail or "the code expired or was denied")
    return {"status": "pending"}


def _session_from(answer: dict, save: bool) -> AuthSession:
    session = AuthSession(
        access_token=answer["access_token"],
        refresh_token=answer["refresh_token"],
        user=answer.get("user", {}),
        stage=settings.CURRENT_STAGE,
    )
    if save:
        session.save()
    return session


def redeem(ticket: str, base_url: Optional[str] = None, save: bool = True, tries: int = 3,
           sleep: Callable[[float], None] = time.sleep) -> AuthSession:
    """Collect the session of a ticket the website approved in advance (the install file carries one).

    The ticket works once and for a short time; an unknown, used or expired one raises PairingError. A network blip is
    retried a few times - the ticket is only used up when the server actually hands out the session."""
    for attempt in range(max(1, tries)):
        answer = poll(ticket.strip(), base_url)       # raises PairingError for unknown / used / expired / denied
        if answer.get("status") == "approved":
            return _session_from(answer, save)
        if attempt + 1 < tries:
            sleep(2.0)
    raise PairingError("the server did not answer in time")


def pair(show: Callable[[dict], None], base_url: Optional[str] = None, label: str = "Steam Deck",
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
         save: bool = True, interrupt: Optional[Callable[[float], bool]] = None) -> AuthSession:
    """Run the whole flow; `show` gets the start answer (code + link) once. Returns the saved session.

    `interrupt(seconds)` replaces the sleep between two polls: it returns True when the person wants to stop
    (Enter pressed) and the flow ends with PairingSkipped - the code simply expires on the server."""
    info = start(base_url, label)
    show(info)
    interval = max(1.0, float(info.get("interval", 3)))
    deadline = clock() + float(info["expires_in"])
    while clock() < deadline:
        if interrupt is not None:
            if interrupt(interval):
                raise PairingSkipped("continued without an account")
        else:
            sleep(interval)
        answer = poll(info["device_code"], base_url)
        if answer.get("status") == "approved":
            return _session_from(answer, save)
    raise PairingError("the code expired before it was approved")
