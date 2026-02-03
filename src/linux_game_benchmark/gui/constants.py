"""Dark theme colors, QSS stylesheet, and dimension constants."""

# --- Colors ---
BG_DARK = "#1a1a2e"
BG_SURFACE = "#16213e"
BG_SIDEBAR = "#0f1529"
BG_CARD = "#1c2a4a"
BG_INPUT = "#0d1117"

ACCENT = "#00adb5"
ACCENT_HOVER = "#00cdd7"
ACCENT_PRESSED = "#008a91"

SUCCESS = "#4ecca3"
ERROR = "#e74c3c"
WARNING = "#f39c12"
INFO = "#3498db"

TEXT_PRIMARY = "#e6e6e6"
TEXT_SECONDARY = "#8892b0"
TEXT_MUTED = "#5a6580"
TEXT_ON_ACCENT = "#ffffff"

BORDER = "#233554"
BORDER_FOCUS = ACCENT

# Sidebar
SIDEBAR_WIDTH = 230
SIDEBAR_ITEM_HEIGHT = 46
SIDEBAR_ICON_SIZE = 20

# Window
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 700
DEFAULT_WINDOW_WIDTH = 1400
DEFAULT_WINDOW_HEIGHT = 850

# --- Reusable secondary button style ---
SECONDARY_BTN_STYLE = f"""
    QPushButton {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        padding: 0 16px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
        background-color: rgba(0, 173, 181, 0.08);
    }}
"""

# --- QSS Dark Theme ---
DARK_THEME_QSS = f"""
    /* === Global === */
    QWidget {{
        color: {TEXT_PRIMARY};
        font-family: "Segoe UI", "Noto Sans", "Ubuntu", sans-serif;
        font-size: 14px;
    }}

    /* Background on content containers (not top-level window, to preserve WM decorations) */
    QDialog {{
        background-color: {BG_DARK};
    }}

    /* === Sidebar === */
    #sidebar {{
        background-color: {BG_SIDEBAR};
        border-right: 1px solid {BORDER};
        min-width: {SIDEBAR_WIDTH}px;
        max-width: {SIDEBAR_WIDTH}px;
    }}

    #sidebar QPushButton {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        text-align: left;
        font-size: 14px;
        font-weight: 500;
        min-height: {SIDEBAR_ITEM_HEIGHT}px;
    }}

    #sidebar QPushButton:hover {{
        background-color: rgba(0, 173, 181, 0.1);
        color: {TEXT_PRIMARY};
    }}

    #sidebar QPushButton[active="true"] {{
        background-color: rgba(0, 173, 181, 0.15);
        color: {ACCENT};
        font-weight: 600;
        border-left: 3px solid {ACCENT};
        border-radius: 0 8px 8px 0;
    }}

    /* === Scrollbar === */
    QScrollBar:vertical {{
        background: {BG_DARK};
        width: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {TEXT_MUTED};
        min-height: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_SECONDARY};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: {BG_DARK};
        height: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {TEXT_MUTED};
        min-width: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {TEXT_SECONDARY};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* === Buttons === */
    QPushButton {{
        background-color: {ACCENT};
        color: {TEXT_ON_ACCENT};
        border: none;
        border-radius: 6px;
        padding: 8px 20px;
        font-weight: 600;
        font-size: 14px;
    }}
    QPushButton:hover {{
        background-color: {ACCENT_HOVER};
    }}
    QPushButton:pressed {{
        background-color: {ACCENT_PRESSED};
    }}
    QPushButton:disabled {{
        background-color: {BG_CARD};
        color: {TEXT_MUTED};
    }}

    /* === Input fields === */
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 14px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border-color: {ACCENT};
    }}

    /* Arrow icons for QComboBox/QSpinBox are appended at runtime via icon_gen */

    QComboBox QAbstractItemView {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        selection-background-color: rgba(0, 173, 181, 0.3);
        selection-color: {TEXT_PRIMARY};
        padding: 4px;
    }}

    /* === Labels === */
    QLabel {{
        background: transparent;
        color: {TEXT_PRIMARY};
    }}
    QLabel[class="heading"] {{
        font-size: 24px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QLabel[class="subheading"] {{
        font-size: 16px;
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}
    QLabel[class="muted"] {{
        color: {TEXT_MUTED};
        font-size: 13px;
    }}

    /* === Cards === */
    QFrame[class="card"] {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 16px;
    }}
    QFrame[class="card"]:hover {{
        border-color: {ACCENT};
    }}

    /* === Tab-like stacked widget area === */
    #content_area {{
        background-color: {BG_DARK};
    }}

    /* === Separator === */
    QFrame[class="separator"] {{
        background-color: {BORDER};
        max-height: 1px;
    }}

    /* === Secondary Buttons (property-based override) === */
    QPushButton[class="secondary"] {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        padding: 0 16px;
    }}
    QPushButton[class="secondary"]:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
        background-color: rgba(0, 173, 181, 0.08);
    }}
    QPushButton[class="secondary"]:pressed {{
        background-color: rgba(0, 173, 181, 0.15);
    }}

    /* === Delete / Danger Buttons === */
    QPushButton[class="danger"] {{
        background-color: rgba(231, 76, 60, 0.12);
        color: {ERROR};
        border: 1px solid rgba(231, 76, 60, 0.4);
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        padding: 0 12px;
    }}
    QPushButton[class="danger"]:hover {{
        background-color: rgba(231, 76, 60, 0.25);
        border-color: {ERROR};
    }}

    /* === Link-style Buttons (accent text, no background) === */
    QPushButton[class="link"] {{
        background: transparent;
        color: {ACCENT};
        border: 1px solid {ACCENT};
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
        padding: 0 12px;
    }}
    QPushButton[class="link"]:hover {{
        background-color: rgba(0, 173, 181, 0.15);
    }}

    /* === ToolTip === */
    QToolTip {{
        background-color: {BG_SURFACE};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 13px;
    }}
"""
