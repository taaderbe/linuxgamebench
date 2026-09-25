"""How to update this installation - pipx install vs. AppImage download.

AppImage users can't run `pipx upgrade`: they have to download the new
AppImage and replace their file. The AppImage runtime sets $APPIMAGE to the
path of the running file, which is how we tell the two apart.
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional

PIPX_COMMAND = "pipx upgrade linux-game-benchmark"


@dataclass
class UpdateInstructions:
    kind: str                         # "appimage" or "pipx"
    text: str                         # shown under the message
    button: str                       # label of the action button
    open_url: Optional[str] = None    # appimage: page to open
    copy_text: Optional[str] = None   # pipx: command to copy


def site_url(api_base_url: str) -> str:
    """https://linuxgamebench.com/api/v1 -> https://linuxgamebench.com"""
    base = api_base_url.rstrip("/")
    return base[: -len("/api/v1")] if base.endswith("/api/v1") else base


def update_instructions(api_base_url: str, env: Optional[Mapping[str, str]] = None) -> UpdateInstructions:
    env = os.environ if env is None else env
    appimage = env.get("APPIMAGE")
    if appimage:
        return UpdateInstructions(
            kind="appimage",
            text=("Download the new AppImage and replace this file:\n"
                  f"{appimage}\n\n"
                  "Then make it executable (chmod +x) and start it again."),
            button="Open Download Page",
            open_url=f"{site_url(api_base_url)}/faq.html#install-gui",
        )
    return UpdateInstructions(
        kind="pipx",
        text=f"Run:  {PIPX_COMMAND}",
        button="Copy Update Command",
        copy_text=PIPX_COMMAND,
    )
