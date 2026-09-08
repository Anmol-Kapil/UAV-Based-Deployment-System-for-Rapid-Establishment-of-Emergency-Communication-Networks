"""Connection Settings Dialog for MAVLink Ground Control Station."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QGroupBox
)
from PySide6.QtCore import Qt


class ConnectionDialog(QDialog):
    """Modal dialog to select MAVLink connection interface and parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MAVLink Connection Setup")
        self.setFixedWidth(420)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Title
        title_label = QLabel("Connect to UAV Vehicle")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(title_label)

        # Group Box
        group = QGroupBox("Connection Configuration")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Connection Mode
        self.combo_type = QComboBox()
        self.combo_type.addItems([
            "Mock Telemetry (Demo / Simulation)",
            "PX4 SITL / Gazebo GCS Port (UDP 14550)",
            "PX4 SITL Companion Port (UDP 14540)",
            "UDP Client (Custom Host/Port)",
            "TCP Client",
            "Serial (Radio / USB)"
        ])
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Protocol:", self.combo_type)

        # Host / IP
        self.input_host = QLineEdit("0.0.0.0")
        form.addRow("Host / IP:", self.input_host)

        # Port
        self.input_port = QLineEdit("14550")
        form.addRow("Port:", self.input_port)

        # Baud Rate
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["57600", "115200", "921600", "230400"])
        self.combo_baud.setEnabled(False)
        form.addRow("Baud Rate:", self.combo_baud)

        layout.addWidget(group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
        """)
        self.btn_connect.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_connect)

        layout.addLayout(btn_layout)

        # Initialize field state based on default selection
        self._on_type_changed(0)

    def _on_type_changed(self, index):
        """Update field editability based on protocol selection."""
        # 0: Mock Telemetry
        # 1: UDP Server
        # 2: UDP Client
        # 3: TCP Client
        # 4: Serial
        if index == 0:  # Mock
            self.input_host.setEnabled(False)
            self.input_port.setEnabled(False)
            self.combo_baud.setEnabled(False)
        elif index == 1:  # PX4 SITL 14550 GCS
            self.input_host.setText("0.0.0.0")
            self.input_port.setText("14550")
            self.input_host.setEnabled(True)
            self.input_port.setEnabled(True)
            self.combo_baud.setEnabled(False)
        elif index == 2:  # PX4 SITL 14540 Companion
            self.input_host.setText("0.0.0.0")
            self.input_port.setText("14540")
            self.input_host.setEnabled(True)
            self.input_port.setEnabled(True)
            self.combo_baud.setEnabled(False)
        elif index in (3, 4):  # UDP/TCP Client
            self.input_host.setEnabled(True)
            self.input_port.setEnabled(True)
            self.combo_baud.setEnabled(False)
        elif index == 5:  # Serial
            self.input_host.setText("COM3" if self._is_windows() else "/dev/ttyUSB0")
            self.input_host.setEnabled(True)
            self.input_port.setEnabled(False)
            self.combo_baud.setEnabled(True)

    def _is_windows(self):
        import sys
        return sys.platform.startswith("win")

    def get_connection_string(self):
        """Build MAVLink connection string from dialog inputs."""
        idx = self.combo_type.currentIndex()
        if idx == 0:
            return "mock://127.0.0.1:14550", 57600
        elif idx in (1, 2):
            host = self.input_host.text().strip() or "0.0.0.0"
            port = self.input_port.text().strip() or ("14550" if idx == 1 else "14540")
            return f"udpin:{host}:{port}", 57600
        elif idx == 3:
            return f"udpout:{self.input_host.text().strip()}:{self.input_port.text().strip()}", 57600
        elif idx == 4:
            return f"tcp:{self.input_host.text().strip()}:{self.input_port.text().strip()}", 57600
        elif idx == 5:
            baud = int(self.combo_baud.currentText())
            return self.input_host.text().strip(), baud
        return "udpin:0.0.0.0:14550", 57600


