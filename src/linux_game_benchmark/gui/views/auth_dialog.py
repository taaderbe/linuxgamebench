"""Modal login dialog with email, password, 2FA, and error display."""

import webbrowser

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QWidget, QToolButton,
)
from PySide6.QtCore import Qt, Signal

from linux_game_benchmark.gui.constants import (
    BG_DARK, BG_SURFACE, BG_INPUT, ACCENT, ACCENT_HOVER, ACCENT_PRESSED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER, ERROR, SUCCESS,
)
from linux_game_benchmark.gui.signals import AppSignals
from linux_game_benchmark.gui.workers import LoginWorker


class AuthDialog(QDialog):
    """Modal login dialog with 2FA support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login - Linux Game Bench")
        self.setFixedSize(420, 0)  # width fixed, height auto
        self.setModal(True)

        self._login_worker = None
        self._email_value = ""
        self._password_value = ""
        self._awaiting_2fa = False

        self._build_ui()
        self.adjustSize()

    def _build_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DARK};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(0)

        # Header
        title = QLabel("Login")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: 700; "
            "background: transparent;"
        )
        layout.addWidget(title)
        layout.addSpacing(4)

        subtitle = QLabel("Sign in to upload benchmarks and access your data.")
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; background: transparent;"
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(20)

        # Email field
        email_label = QLabel("Email")
        email_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        layout.addWidget(email_label)
        layout.addSpacing(4)

        self._email = QLineEdit()
        self._email.setPlaceholderText("your@email.com")
        self._email.setFixedHeight(40)
        layout.addWidget(self._email)
        layout.addSpacing(14)

        # Password field with visibility toggle
        pw_label = QLabel("Password")
        pw_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        layout.addWidget(pw_label)
        layout.addSpacing(4)

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setFixedHeight(40)
        self._password.setTextMargins(0, 0, 32, 0)  # right margin for toggle
        layout.addWidget(self._password)

        # Toggle embedded inside the password field: (O) = hidden, (X) = visible
        self._pw_toggle = QToolButton(self._password)
        self._pw_toggle.setText("(O)")
        self._pw_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pw_toggle.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {TEXT_MUTED};
                font-size: 13px;
                padding: 0;
            }}
            QToolButton:hover {{
                color: {ACCENT};
            }}
        """)
        self._pw_toggle.clicked.connect(self._toggle_password_visibility)
        inner_layout = QHBoxLayout(self._password)
        inner_layout.setContentsMargins(0, 0, 6, 0)
        inner_layout.addStretch()
        inner_layout.addWidget(self._pw_toggle)

        layout.addSpacing(14)

        # 2FA field (hidden by default)
        self._totp_container = QWidget()
        self._totp_container.setStyleSheet("background: transparent;")
        self._totp_container.setVisible(False)
        totp_layout = QVBoxLayout(self._totp_container)
        totp_layout.setContentsMargins(0, 0, 0, 0)
        totp_layout.setSpacing(4)

        totp_label = QLabel("2FA Code")
        totp_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        totp_layout.addWidget(totp_label)

        self._totp_hint = QLabel("Enter the 6-digit code from your authenticator app.")
        self._totp_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        totp_layout.addWidget(self._totp_hint)

        self._totp = QLineEdit()
        self._totp.setPlaceholderText("000000")
        self._totp.setFixedHeight(40)
        self._totp.setMaxLength(6)
        totp_layout.addWidget(self._totp)

        layout.addWidget(self._totp_container)
        layout.addSpacing(6)

        # Error display
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; background: transparent; "
            "padding: 4px 0;"
        )
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)
        layout.addSpacing(10)

        # Login button
        self._login_btn = QPushButton("Login")
        self._login_btn.setFixedHeight(42)
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {BG_SURFACE};
                color: {TEXT_MUTED};
            }}
        """)
        self._login_btn.clicked.connect(self._do_login)
        layout.addWidget(self._login_btn)
        layout.addSpacing(16)

        # Register link
        register_row = QWidget()
        register_row.setStyleSheet("background: transparent;")
        reg_layout = QHBoxLayout(register_row)
        reg_layout.setContentsMargins(0, 0, 0, 0)
        reg_layout.setSpacing(4)

        reg_text = QLabel("Don't have an account?")
        reg_text.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        reg_layout.addStretch(1)
        reg_layout.addWidget(reg_text)

        reg_link = QPushButton("Register")
        reg_link.setCursor(Qt.CursorShape.PointingHandCursor)
        reg_link.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT};
                border: none;
                font-size: 12px;
                font-weight: 600;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {ACCENT_HOVER};
                text-decoration: underline;
            }}
        """)
        reg_link.clicked.connect(self._open_register)
        reg_layout.addWidget(reg_link)
        reg_layout.addStretch(1)

        layout.addWidget(register_row)

        # Enter key triggers login
        self._email.returnPressed.connect(self._focus_next_or_login)
        self._password.returnPressed.connect(self._focus_next_or_login)
        self._totp.returnPressed.connect(self._do_login)

    # --- Actions ---

    def _focus_next_or_login(self):
        """Move focus to next empty field or trigger login."""
        if not self._email.text().strip():
            self._email.setFocus()
        elif not self._password.text().strip():
            self._password.setFocus()
        elif self._awaiting_2fa and not self._totp.text().strip():
            self._totp.setFocus()
        else:
            self._do_login()

    def _do_login(self):
        email = self._email.text().strip()
        password = self._password.text()
        totp = self._totp.text().strip() if self._awaiting_2fa else ""

        if not email:
            self._show_error("Please enter your email address.")
            self._email.setFocus()
            return
        if not password:
            self._show_error("Please enter your password.")
            self._password.setFocus()
            return
        if self._awaiting_2fa and not totp:
            self._show_error("Please enter your 2FA code.")
            self._totp.setFocus()
            return

        self._set_loading(True)
        self._hide_error()

        # Store for potential 2FA retry
        self._email_value = email
        self._password_value = password

        self._login_worker = LoginWorker(email, password, totp, parent=self)
        self._login_worker.finished.connect(self._on_login_result)
        self._login_worker.start()

    def _on_login_result(self, success: bool, message: str):
        self._set_loading(False)

        if success:
            # Extract username from message "Logged in as {username}"
            username = message.replace("Logged in as ", "") if "Logged in as " in message else message
            AppSignals.instance().auth_changed.emit(True, username)
            self.accept()
        elif message == "2FA_REQUIRED":
            self._awaiting_2fa = True
            self._totp_container.setVisible(True)
            self._totp.setFocus()
            self._show_error("")  # Clear previous errors
            self._error_label.setVisible(False)
            self.adjustSize()
        else:
            self._show_error(message)

    # --- UI Helpers ---

    def _toggle_password_visibility(self):
        if self._password.echoMode() == QLineEdit.EchoMode.Password:
            self._password.setEchoMode(QLineEdit.EchoMode.Normal)
            self._pw_toggle.setText("(X)")
        else:
            self._password.setEchoMode(QLineEdit.EchoMode.Password)
            self._pw_toggle.setText("(O)")

    def _set_loading(self, loading: bool):
        self._login_btn.setEnabled(not loading)
        self._login_btn.setText("Logging in..." if loading else "Login")
        self._email.setEnabled(not loading)
        self._password.setEnabled(not loading)
        self._totp.setEnabled(not loading)

    def _show_error(self, message: str):
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _hide_error(self):
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _open_register(self):
        try:
            from linux_game_benchmark.config.settings import settings
            stage = settings.CURRENT_STAGE
            if stage == "prod":
                url = "https://linuxgamebench.com/register.html"
            else:
                base = settings.API_BASE_URL.replace("/api/v1", "")
                url = f"{base}/register.html"
        except Exception:
            url = "https://linuxgamebench.com/register.html"
        webbrowser.open(url)
