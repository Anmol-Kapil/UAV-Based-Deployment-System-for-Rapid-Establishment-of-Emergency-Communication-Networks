"""Critical Command Confirmation Dialog for UAV GCS.

Provides a reusable dark-themed modal dialog for destructive or safety-critical
flight commands requiring explicit operator confirmation before execution.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QFrame,
)
from PySide6.QtCore import Qt


class ConfirmDialog(QDialog):
    """Confirmation modal for flight-critical commands."""

    def __init__(self, title: str, description: str, parent=None,
                 is_abort: bool = False, ask_altitude: bool = False,
                 default_altitude: float = 5.0):
        super().__init__(parent)
        self.setWindowTitle("Confirm Flight Command")
        self.setFixedWidth(380)
        self.setModal(True)

        self._altitude_spinbox = None
        self._init_ui(title, description, is_abort, ask_altitude, default_altitude)

    def _init_ui(self, title, description, is_abort, ask_altitude, default_altitude):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Command Title
        lbl_title = QLabel(title)
        if is_abort:
            lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f85149;")
        else:
            lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(lbl_title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #30363d;")
        layout.addWidget(sep)

        # Description
        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(lbl_desc)

        # Optional Altitude Input
        if ask_altitude:
            alt_row = QHBoxLayout()
            lbl_alt = QLabel("Takeoff Altitude:")
            lbl_alt.setStyleSheet("color: #c9d1d9; font-weight: 600;")
            alt_row.addWidget(lbl_alt)

            self._altitude_spinbox = QDoubleSpinBox()
            self._altitude_spinbox.setRange(1.0, 120.0)
            self._altitude_spinbox.setValue(default_altitude)
            self._altitude_spinbox.setSuffix(" m")
            self._altitude_spinbox.setSingleStep(0.5)
            self._altitude_spinbox.setStyleSheet("""
                QDoubleSpinBox {
                    background-color: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #388bfd;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 13px;
                }
            """)
            alt_row.addWidget(self._altitude_spinbox)
            layout.addLayout(alt_row)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_confirm = QPushButton("⚠  CONFIRM" if is_abort else "Confirm")
        if is_abort:
            btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #da3633;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 6px 16px;
                }
                QPushButton:hover { background-color: #f85149; }
            """)
        else:
            btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #238636;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 6px 16px;
                }
                QPushButton:hover { background-color: #2ea043; }
            """)
        btn_confirm.clicked.connect(self.accept)
        btn_layout.addWidget(btn_confirm)

        layout.addLayout(btn_layout)

    def get_altitude(self) -> float:
        """Return entered altitude value (only valid when ask_altitude=True)."""
        if self._altitude_spinbox:
            return self._altitude_spinbox.value()
        return 5.0
