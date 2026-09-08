"""Main Application Window for GCS.

Assembles:
- TOP STATUS BAR
- LEFT TOOL PANEL (Collapsible)
- CENTRAL TACTICAL MAP
- RIGHT CONTEXT PANEL (Tabs: Telemetry, Camera, Mission, Deployment, RF, Log)
- BOTTOM FLIGHT ACTION BAR
- MAVLink worker thread manager & connection dialog lifecycle
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
    QDialog,
)
from PySide6.QtCore import Qt
from gcs.widgets.top_bar import TopBar
from gcs.widgets.left_panel import LeftPanel
from gcs.widgets.map_view import MapView
from gcs.widgets.right_panel import RightPanel
from gcs.widgets.bottom_bar import BottomBar
from gcs.widgets.connection_dialog import ConnectionDialog
from gcs.mavlink.mavlink_worker import QMavlinkWorker
from gcs.state.app_state import app_state, ConnectionState


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "UAV Ground Control Station — Rapid Emergency Communication Deployment (Phase 16)"
        )
        self.resize(1380, 880)
        self.setMinimumSize(1024, 680)
        self._mav_worker = None
        self._init_ui()
        self._connect_signals()
        self._post_init()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Bar
        self.top_bar = TopBar(self)
        root_layout.addWidget(self.top_bar)

        # 2. Main Horizontal Splitter (Left Tools, Center Map, Right Context)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.left_panel = LeftPanel(self)
        self.map_view = MapView(self)
        self.right_panel = RightPanel(self)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.map_view)
        self.splitter.addWidget(self.right_panel)

        # Proportions: Left ~240, Center ~780, Right ~360
        self.splitter.setSizes([240, 780, 360])
        root_layout.addWidget(self.splitter, stretch=1)

        # 3. Bottom Control Bar
        self.bottom_bar = BottomBar(self)
        root_layout.addWidget(self.bottom_bar)

    def _connect_signals(self):
        # Connection actions
        self.top_bar.connect_requested.connect(self.open_connection_dialog)
        self.top_bar.disconnect_requested.connect(self.disconnect_mavlink)
        self.left_panel.connect_requested.connect(self.open_connection_dialog)
        self.left_panel.disconnect_requested.connect(self.disconnect_mavlink)

    def open_connection_dialog(self):
        """Open the connection setup modal dialog."""
        dlg = ConnectionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            conn_str, baud = dlg.get_connection_string()
            self.start_mavlink_worker(conn_str, baud)

    def start_mavlink_worker(self, connection_str: str, baud: int = 57600):
        """Instantiate and launch the background MAVLink receiver thread."""
        self.disconnect_mavlink()  # Clean up existing thread if any

        app_state.set_connection(ConnectionState.CONNECTING)
        app_state.log("INFO", "MAVLINK", f"Connecting to MAVLink endpoint: {connection_str} (baud={baud})")

        self._mav_worker = QMavlinkWorker(connection_str=connection_str, baud=baud, parent=self)
        self._mav_worker.connected_signal.connect(self._on_mav_connected)
        self._mav_worker.disconnected_signal.connect(self._on_mav_disconnected)
        self._mav_worker.connection_error_signal.connect(self._on_mav_error)
        self._mav_worker.telemetry_updated.connect(self._on_telemetry_updated)
        self._mav_worker.statustext_signal.connect(self._on_statustext_received)
        self._mav_worker.command_ack_signal.connect(app_state.set_command_feedback)
        self._mav_worker.start()

        # Phase 3 & 4: inject worker reference into command-dispatching & mission panels
        self.bottom_bar.set_worker(self._mav_worker)
        self.left_panel.set_worker(self._mav_worker)
        self.right_panel.set_worker(self._mav_worker)

    def disconnect_mavlink(self):
        """Disconnect MAVLink stream and stop worker thread."""
        if self._mav_worker:
            self._mav_worker.stop()
            self._mav_worker = None
        self.bottom_bar.set_worker(None)
        self.left_panel.set_worker(None)
        self.right_panel.set_worker(None)
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.set_command_feedback("DISCONNECTED FROM VEHICLE")

    def _on_mav_connected(self, sys_id: int, comp_id: int, vehicle_type: str):
        app_state.set_connection(ConnectionState.CONNECTED)
        app_state.log("INFO", "MAVLINK", f"Connected to Vehicle [SYSID {sys_id}, COMPID {comp_id}, Type: {vehicle_type}]")
        app_state.set_command_feedback(f"CONNECTED - SYSID {sys_id} [{vehicle_type}]")

    def _on_mav_disconnected(self, reason: str):
        app_state.set_connection(ConnectionState.CONNECTION_LOST if "timeout" in reason.lower() else ConnectionState.DISCONNECTED)
        app_state.log("WARNING" if "timeout" in reason.lower() else "INFO", "MAVLINK", f"MAVLink Stream Disconnected: {reason}")
        app_state.set_command_feedback("DISCONNECTED - " + reason)

    def _on_mav_error(self, err_msg: str):
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.log("CRITICAL", "MAVLINK", f"MAVLink Connection Error: {err_msg}")
        app_state.set_command_feedback("ERROR: " + err_msg)

    def _on_telemetry_updated(self, telemetry: dict):
        app_state.update_telemetry(telemetry)

    def _on_statustext_received(self, severity: int, text: str):
        # MAVLink STATUSTEXT severity levels (0=EMERGENCY .. 7=DEBUG)
        sev_map = {0: "CRITICAL", 1: "CRITICAL", 2: "CRITICAL", 3: "CRITICAL", 4: "WARNING", 5: "INFO", 6: "INFO", 7: "INFO"}
        app_state.log(sev_map.get(severity, "INFO"), "VEHICLE", text)

    def _post_init(self):
        app_state.log(
            "INFO",
            "SYSTEM",
            "GCS Phase 16 Backend FastAPI Integration & Async REST Client active. Dual-mode support "
            "(Remote REST API vs Local Embedded Engine), async QThread worker execution, /api endpoints, "
            "and live backend connection telemetry indicator.",
        )
        app_state.fetch_backend_status()


    def closeEvent(self, event):
        self.disconnect_mavlink()
        event.accept()
