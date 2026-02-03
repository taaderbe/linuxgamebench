"""Sidebar auth status widget with login/logout functionality."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt

from linux_game_benchmark.gui.constants import (
    ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SUCCESS, ERROR,
    BG_SURFACE, BORDER,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import LogoutWorker


class AuthStatusWidget(QWidget):
    """Sidebar widget showing auth state with login/logout controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._logged_in = False
        self._username = ""
        self._logout_worker = None

        self._build_ui()
        AppSignals.instance().auth_changed.connect(self._on_auth_changed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Status row: indicator + username/status
        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(8)

        self._indicator = QLabel("\u25CF")
        self._indicator.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;"
        )
        self._indicator.setFixedWidth(14)
        status_layout.addWidget(self._indicator)

        self._status_label = QLabel("Not logged in")
        self._status_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        status_layout.addWidget(self._status_label, 1)

        layout.addWidget(status_row)

        # Login button (shown when not logged in)
        self._login_btn = QPushButton("Login")
        self._login_btn.setFixedHeight(40)
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: #00cdd7;
            }}
        """)
        self._login_btn.clicked.connect(self._open_login_dialog)
        layout.addWidget(self._login_btn)

        # Logout button (shown when logged in, hidden by default)
        self._logout_btn = QPushButton("Logout")
        self._logout_btn.setFixedHeight(30)
        self._logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                margin: 0 4px;
            }}
            QPushButton:hover {{
                color: {ERROR};
                background-color: rgba(231, 76, 60, 0.1);
            }}
        """)
        self._logout_btn.clicked.connect(self._do_logout)
        self._logout_btn.setVisible(False)
        layout.addWidget(self._logout_btn)

    # --- State ---

    def _on_auth_changed(self, logged_in: bool, username: str):
        self._logged_in = logged_in
        self._username = username

        if logged_in:
            self._indicator.setStyleSheet(
                f"color: {SUCCESS}; font-size: 10px; background: transparent;"
            )
            self._status_label.setText(username)
            self._status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px; font-weight: 600; "
                "background: transparent;"
            )
            self._login_btn.setVisible(False)
            self._logout_btn.setVisible(True)
        else:
            self._indicator.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;"
            )
            self._status_label.setText("Not logged in")
            self._status_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
            )
            self._login_btn.setVisible(True)
            self._logout_btn.setVisible(False)

    # --- Login ---

    def _open_login_dialog(self):
        from linux_game_benchmark.gui.views.auth_dialog import AuthDialog
        dialog = AuthDialog(self.window())
        dialog.exec()

    # --- Logout ---

    def _do_logout(self):
        self._logout_btn.setEnabled(False)
        self._logout_btn.setText("Logging out...")
        self._logout_worker = LogoutWorker(parent=self)
        self._logout_worker.finished.connect(self._on_logout_result)
        self._logout_worker.start()

    def _on_logout_result(self, success: bool, message: str):
        self._logout_btn.setEnabled(True)
        self._logout_btn.setText("Logout")
        AppSignals.instance().auth_changed.emit(False, "")
