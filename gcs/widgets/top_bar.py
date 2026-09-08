"""Top Status Bar for GCS.

Always visible, displaying:
- Connection state (DISCONNECTED, CONNECTING, CONNECTED, CONNECTION LOST)
- Quick Connect / Disconnect button
- Vehicle type & System ID
- Flight Mode
- GPS Fix & Satellite count
- Altitude
- Battery % & Voltage
- Safety state (NORMAL, WARNING, CRITICAL)
- Simulation indicators (SITL & Gazebo)
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal
from gcs.state.app_state import app_state, ConnectionState, SafetyState


class TopBar(QWidget):
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topStatusBar")
        self._init_ui()
        self._connect_signals()
        self.on_connection_changed(app_state.connection_status)


    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Connection status badge
        self.badge_conn = QLabel("● DISCONNECTED")
        self.badge_conn.setObjectName("badgeConn")
        self.badge_conn.setProperty("class", "status-badge status-badge-disconnected")
        self.badge_conn.setToolTip("MAVLink Connection Status")
        layout.addWidget(self.badge_conn)

        # Quick Connect/Disconnect button
        self.btn_top_connect = QPushButton("CONNECT")
        self.btn_top_connect.setObjectName("btnTopConnect")
        self.btn_top_connect.setToolTip("Open MAVLink Connection Setup")
        self.btn_top_connect.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #58a6ff;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 3px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #30363d;
                color: #79c0ff;
            }
        """)
        self.btn_top_connect.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.btn_top_connect)

        layout.addWidget(self._create_separator())

        # Vehicle & SysID
        self.label_vehicle = QLabel("VEHICLE: -- | SYSID: --")
        self.label_vehicle.setStyleSheet("font-weight: 600; color: #8b949e;")
        layout.addWidget(self.label_vehicle)

        layout.addWidget(self._create_separator())

        # Flight Mode
        self.label_mode = QLabel("MODE: --")
        self.label_mode.setStyleSheet("font-weight: 700; color: #79c0ff;")
        layout.addWidget(self.label_mode)

        layout.addWidget(self._create_separator())

        # GPS & Sats
        self.label_gps = QLabel("GPS: -- (SATS: --)")
        self.label_gps.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.label_gps)

        layout.addWidget(self._create_separator())

        # Altitude
        self.label_alt = QLabel("ALT: -- m")
        self.label_alt.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.label_alt)

        layout.addWidget(self._create_separator())

        # Battery
        self.label_battery = QLabel("BAT: --")
        self.label_battery.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.label_battery)

        layout.addWidget(self._create_separator())

        # Safety State
        self.badge_safety = QLabel("SAFE / NORMAL")
        self.badge_safety.setObjectName("badgeSafety")
        self.badge_safety.setProperty("class", "status-badge status-badge-safe")
        layout.addWidget(self.badge_safety)

        # Spacer to push simulation indicators to right
        layout.addStretch()

        # Simulation Indicators
        self.badge_sim = QLabel("SITL: OFFLINE | GAZEBO: OFFLINE")
        self.badge_sim.setProperty("class", "status-badge status-badge-simulation")
        self.badge_sim.setToolTip("Simulation Engine Status (Available in Phase 1 / SITL)")
        layout.addWidget(self.badge_sim)

    def _create_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #30363d;")
        return sep

    def _connect_signals(self):
        app_state.connection_changed.connect(self.on_connection_changed)
        app_state.flight_mode_changed.connect(self.on_mode_changed)
        app_state.safety_changed.connect(self.on_safety_changed)
        app_state.telemetry_updated.connect(self.on_telemetry_updated)

    def _on_connect_clicked(self):
        if app_state.connection_status == ConnectionState.CONNECTED:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit()

    def on_connection_changed(self, status: str):
        if status == ConnectionState.CONNECTED:
            self.badge_conn.setText("● CONNECTED")
            self.badge_conn.setProperty("class", "status-badge status-badge-connected")
            self.btn_top_connect.setText("DISCONNECT")
            self.btn_top_connect.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #f85149;
                    border: 1px solid #da3633;
                    border-radius: 4px;
                    padding: 3px 10px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #da3633;
                    color: #ffffff;
                }
            """)
        elif status == ConnectionState.CONNECTING:
            self.badge_conn.setText("◌ CONNECTING...")
            self.badge_conn.setProperty("class", "status-badge status-badge-warning")
            self.btn_top_connect.setText("CANCEL")
        elif status == ConnectionState.CONNECTION_LOST:
            self.badge_conn.setText("⚠ CONNECTION LOST")
            self.badge_conn.setProperty("class", "status-badge status-badge-disconnected")
            self.btn_top_connect.setText("RECONNECT")
        else:
            self.badge_conn.setText("● DISCONNECTED")
            self.badge_conn.setProperty("class", "status-badge status-badge-disconnected")
            self.btn_top_connect.setText("CONNECT")
            self.btn_top_connect.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #58a6ff;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    padding: 3px 10px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    color: #79c0ff;
                }
            """)
        self.badge_conn.style().unpolish(self.badge_conn)
        self.badge_conn.style().polish(self.badge_conn)

    def on_mode_changed(self, mode: str):
        self.label_mode.setText(f"MODE: {mode}")

    def on_safety_changed(self, safety: str):
        if safety == SafetyState.CRITICAL:
            self.badge_safety.setText("⚠ CRITICAL")
            self.badge_safety.setProperty("class", "status-badge status-badge-disconnected")
        elif safety == SafetyState.WARNING:
            self.badge_safety.setText("▲ WARNING")
            self.badge_safety.setProperty("class", "status-badge status-badge-warning")
        else:
            self.badge_safety.setText("● NORMAL")
            self.badge_safety.setProperty("class", "status-badge status-badge-safe")
        self.badge_safety.style().unpolish(self.badge_safety)
        self.badge_safety.style().polish(self.badge_safety)

    def on_telemetry_updated(self, data: dict):
        sysid = app_state.system_id
        vtype = app_state.vehicle_type
        self.label_vehicle.setText(f"VEHICLE: {vtype} | SYSID: {sysid}")
        self.label_mode.setText(f"MODE: {app_state.flight_mode}")

        gps_fix = app_state.gps_fix
        sats = app_state.satellites
        self.label_gps.setText(f"GPS: {gps_fix} (SATS: {sats})")

        alt = data.get("alt_rel", "--")
        if isinstance(alt, (int, float)):
            self.label_alt.setText(f"ALT: {alt:.1f} m")
        else:
            self.label_alt.setText(f"ALT: {alt} m")

        bat_pct = app_state.battery_pct
        bat_v = app_state.battery_voltage
        if bat_pct != "--" and bat_v != "--":
            self.label_battery.setText(f"BAT: {bat_pct} ({bat_v})")
        else:
            self.label_battery.setText(f"BAT: {bat_pct}")
