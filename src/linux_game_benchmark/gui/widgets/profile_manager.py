"""Per-game settings profiles stored in ~/.config/lgb/profiles.json."""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QPushButton, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer

from linux_game_benchmark.gui.constants import (
    ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER, BG_SURFACE, ERROR,
    SUCCESS,
)

PROFILES_FILE = Path.home() / ".config" / "lgb" / "profiles.json"


class ProfileManager(QWidget):
    """Profile toolbar for saving/loading per-game settings profiles."""

    profile_loaded = Signal(dict)   # emits settings dict when a profile is loaded
    profile_saved = Signal(str)     # emits profile name on save

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_id: str = ""
        self._profiles: dict = {}  # {app_id: {name: {settings}}}
        self._load_profiles_file()
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._combo = QComboBox()
        self._combo.setFixedHeight(30)
        self._combo.setMinimumWidth(180)
        self._combo.addItem("-- No profile --")
        self._combo.currentIndexChanged.connect(self._on_profile_selected)
        layout.addWidget(self._combo, 1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedSize(80, 32)
        self._save_btn.setProperty("class", "secondary")
        self._save_btn.clicked.connect(self._save_profile)
        layout.addWidget(self._save_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedSize(72, 32)
        self._delete_btn.setProperty("class", "danger")
        self._delete_btn.clicked.connect(self._delete_profile)
        layout.addWidget(self._delete_btn)

    # --- Game selection ---

    def set_game(self, app_id: int):
        """Load profiles for a specific game."""
        self._app_id = str(app_id)
        self._refresh_combo()

    # --- Profile combo ---

    def _refresh_combo(self):
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("-- No profile --")
        game_profiles = self._profiles.get(self._app_id, {})
        for name in sorted(game_profiles.keys()):
            self._combo.addItem(name, userData=name)
        self._combo.blockSignals(False)

    def _on_profile_selected(self, index: int):
        if index <= 0:
            return
        name = self._combo.currentData()
        if not name:
            return
        game_profiles = self._profiles.get(self._app_id, {})
        settings = game_profiles.get(name, {})
        if settings:
            self.profile_loaded.emit(dict(settings))

    # --- Save / Delete ---

    def _save_profile(self):
        """Save current settings as a named profile."""
        # If a profile is already selected, overwrite it directly
        if self._combo.currentIndex() > 0:
            name = self._combo.currentData()
            if name:
                self.profile_saved.emit(name)
                return
        # Otherwise ask for a new name
        name, ok = QInputDialog.getText(
            self, "Save Profile", "Profile name:",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        self.profile_saved.emit(name)

    def store_profile(self, name: str, settings: dict):
        """Actually store a profile (called by benchmark_view after getting settings)."""
        if not self._app_id:
            return
        if self._app_id not in self._profiles:
            self._profiles[self._app_id] = {}
        self._profiles[self._app_id][name] = settings
        self._save_profiles_file()
        self._refresh_combo()
        # Select the just-saved profile
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == name:
                self._combo.setCurrentIndex(i)
                break
        self._show_saved_feedback()

    def _show_saved_feedback(self):
        """Briefly show 'Saved!' on the save button."""
        self._save_btn.setText("Saved!")
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(78, 204, 163, 0.15);
                color: {SUCCESS};
                border: 1px solid {SUCCESS};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)
        QTimer.singleShot(1500, self._reset_save_btn)

    def _reset_save_btn(self):
        """Reset save button to normal state."""
        self._save_btn.setText("Save")
        self._save_btn.setStyleSheet("")  # Revert to class-based QSS

    def _delete_profile(self):
        idx = self._combo.currentIndex()
        if idx <= 0:
            return
        name = self._combo.currentData()
        if not name:
            return

        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        game_profiles = self._profiles.get(self._app_id, {})
        game_profiles.pop(name, None)
        if not game_profiles:
            self._profiles.pop(self._app_id, None)
        self._save_profiles_file()
        self._refresh_combo()

    # --- File IO ---

    def _load_profiles_file(self):
        try:
            if PROFILES_FILE.exists():
                self._profiles = json.loads(PROFILES_FILE.read_text())
        except Exception:
            self._profiles = {}

    def _save_profiles_file(self):
        try:
            PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROFILES_FILE.write_text(json.dumps(self._profiles, indent=2))
        except Exception:
            pass
