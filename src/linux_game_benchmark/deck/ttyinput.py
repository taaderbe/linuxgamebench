"""Wait for a key press on the terminal while something else is polling (the account link).

`curl ... | bash` uses stdin for the script itself, so "press Enter to skip" has to read the terminal device directly.
Without a terminal (a service, a script over ssh without -t, a background job) nothing is read and nothing can be skipped.
"""

from __future__ import annotations

import os
import select
import time


class EnterWatcher:
    def __init__(self, path: str = "/dev/tty"):
        self.fd = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            return
        try:
            # Reading the controlling terminal from a background job would stop the process (SIGTTIN): only the foreground may read.
            if os.tcgetpgrp(fd) != os.getpgrp():
                os.close(fd)
                return
        except OSError:                                          # not our controlling terminal: no job control applies
            pass
        self.fd = fd

    @property
    def available(self) -> bool:
        return self.fd is not None

    def wait(self, seconds: float) -> bool:
        """Sleep up to `seconds`; True as soon as Enter was pressed."""
        if self.fd is None:
            time.sleep(seconds)
            return False
        try:
            ready, _, _ = select.select([self.fd], [], [], seconds)
            if not ready:
                return False
            data = os.read(self.fd, 4096)
        except (OSError, ValueError):
            return False
        return b"\n" in data or b"\r" in data

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
