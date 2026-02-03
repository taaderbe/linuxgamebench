"""Generate and cache GUI icon PNG files at runtime."""

from pathlib import Path

from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QPainterPath, QIcon
from PySide6.QtCore import Qt, QPointF

ICON_CACHE_DIR = Path.home() / ".cache" / "lgb" / "icons"

_VERSION = "3"  # Bump to force regeneration


def ensure_icons() -> Path:
    """Generate icon PNGs if needed. Returns icon cache directory."""
    ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    version_file = ICON_CACHE_DIR / ".version"

    if version_file.exists() and version_file.read_text().strip() == _VERSION:
        # Already up to date
        return ICON_CACHE_DIR

    # Generate all icons
    for color, suffix in [("#8892b0", ""), ("#00adb5", "_hover")]:
        _gen_chevron(ICON_CACHE_DIR / f"arrow_down{suffix}.png", color, down=True)
        _gen_chevron(ICON_CACHE_DIR / f"arrow_up{suffix}.png", color, down=False)

    _gen_eye(ICON_CACHE_DIR / "eye.png", slash=False)
    _gen_eye(ICON_CACHE_DIR / "eye_slash.png", slash=True)

    version_file.write_text(_VERSION)
    return ICON_CACHE_DIR


def _gen_chevron(path: Path, color: str, down: bool):
    """Generate a V or ^ chevron arrow PNG."""
    w, h = 32, 20
    pm = QPixmap(w, h)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 2.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if down:
        p.drawLine(QPointF(6, 5), QPointF(16, 15))
        p.drawLine(QPointF(16, 15), QPointF(26, 5))
    else:
        p.drawLine(QPointF(6, 15), QPointF(16, 5))
        p.drawLine(QPointF(16, 5), QPointF(26, 15))
    p.end()
    pm.save(str(path))


def _gen_eye(path: Path, slash: bool):
    """Generate an eye or eye-slash icon PNG."""
    size = 48
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor("#b0b8d0")
    p.setPen(QPen(c, 2.5))
    # Almond eye outline
    ep = QPainterPath()
    ep.moveTo(4, 24)
    ep.cubicTo(12, 10, 36, 10, 44, 24)
    ep.cubicTo(36, 38, 12, 38, 4, 24)
    p.drawPath(ep)
    # Pupil
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(18, 18, 12, 12)
    if slash:
        p.setPen(QPen(c, 3.0))
        p.drawLine(8, 8, 40, 40)
    p.end()
    pm.save(str(path))


def get_arrow_qss(icon_dir: str) -> str:
    """Return QSS for combo/spin arrows using generated icon PNGs."""
    ad = f"{icon_dir}/arrow_down.png"
    adh = f"{icon_dir}/arrow_down_hover.png"
    au = f"{icon_dir}/arrow_up.png"
    auh = f"{icon_dir}/arrow_up_hover.png"
    return f"""
    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}
    QComboBox::down-arrow {{
        image: url({ad});
        width: 14px;
        height: 10px;
    }}
    QComboBox::down-arrow:hover {{
        image: url({adh});
    }}

    QSpinBox::up-button, QSpinBox::down-button {{
        background: transparent;
        border: none;
        width: 28px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: rgba(0, 173, 181, 0.12);
    }}
    QSpinBox::up-arrow {{
        image: url({au});
        width: 12px;
        height: 8px;
    }}
    QSpinBox::up-arrow:hover {{
        image: url({auh});
    }}
    QSpinBox::down-arrow {{
        image: url({ad});
        width: 12px;
        height: 8px;
    }}
    QSpinBox::down-arrow:hover {{
        image: url({adh});
    }}
    """


def get_eye_icon() -> QIcon:
    """Return eye icon (password hidden - click to show)."""
    ensure_icons()
    return QIcon(str(ICON_CACHE_DIR / "eye.png"))


def get_eye_slash_icon() -> QIcon:
    """Return eye-slash icon (password visible - click to hide)."""
    ensure_icons()
    return QIcon(str(ICON_CACHE_DIR / "eye_slash.png"))
