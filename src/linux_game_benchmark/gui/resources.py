"""Image cache for Steam header images and other assets."""

import hashlib
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtGui import QPixmap


CACHE_DIR = Path.home() / ".cache" / "lgb" / "covers"
STEAM_HEADER_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"


class ImageCache(QObject):
    """Async image loader with disk cache in ~/.cache/lgb/covers/."""

    image_ready = Signal(int, QPixmap)  # (app_id, pixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._pending = set()

    def get(self, app_id: int) -> Optional[QPixmap]:
        """Return cached pixmap if available, else return None and start async load."""
        path = CACHE_DIR / f"{app_id}.jpg"
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                return pix

        if app_id not in self._pending:
            self._pending.add(app_id)
            worker = _ImageDownloadWorker(app_id, self)
            worker.finished.connect(self._on_downloaded)
            worker.start()
        return None

    def _on_downloaded(self, app_id: int, pixmap: QPixmap):
        self._pending.discard(app_id)
        if not pixmap.isNull():
            self.image_ready.emit(app_id, pixmap)


class _ImageDownloadWorker(QThread):
    finished = Signal(int, QPixmap)

    def __init__(self, app_id: int, parent=None):
        super().__init__(parent)
        self._app_id = app_id

    def run(self):
        import httpx

        url = STEAM_HEADER_URL.format(app_id=self._app_id)
        path = CACHE_DIR / f"{self._app_id}.jpg"
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 100:
                path.write_bytes(resp.content)
                pix = QPixmap(str(path))
                self.finished.emit(self._app_id, pix)
                return
        except Exception:
            pass
        self.finished.emit(self._app_id, QPixmap())
