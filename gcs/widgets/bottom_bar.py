"""Bottom Flight Action Bar for GCS.

Phase 3: All flight control buttons are now state-aware and functional:
- ARM / DISARM  (requires confirmation)
- TAKEOFF       (requires altitude input confirmation)
- GUIDED / LOITER / MANUAL  (immediate mode switch, no dialog)
- LAND          (immediate, no dialog)
- RTL           (requires confirmation)
- ABORT         (prominent red emergency dialog)

Buttons are gated on connection_status AND arm_state.
Commands dispatched via QMavlinkWorker through the main_window reference.
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QDialog,
)
from PySide6.QtCore import Qt
from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.widgets.confirm_dialog import ConfirmDialog


class BottomBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomBar")
        self._worker = None   # Set by MainWindow after worker starts
        self._init_ui()
        self._connect_signals()
        self._on_connection_changed(app_state.connection_status)

    def set_worker(self, worker):
        """Inject MAVLink worker reference for command dispatch."""
        self._worker = worker
        self._on_connection_changed(app_state.connection_status)


    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # ARM button (green accent)
        self.btn_arm = QPushButton("ARM")
        self.btn_arm.setProperty("class", "btn-flight btn-flight-arm")
        self.btn_arm.setStyleSheet("font-weight: bold; color: #3fb950;")
        self.btn_arm.setEnabled(False)
        self.btn_arm.setToolTip("Arm vehicle motors — requires confirmation")
        self.btn_arm.clicked.connect(self._on_arm)

        self.btn_takeoff = QPushButton("TAKEOFF")
        self.btn_takeoff.setProperty("class", "btn-flight")
        self.btn_takeoff.setEnabled(False)
        self.btn_takeoff.setToolTip("Takeoff to specified altitude")
        self.btn_takeoff.clicked.connect(self._on_takeoff)

        self.btn_guided = QPushButton("GUIDED")
        self.btn_guided.setProperty("class", "btn-flight")
        self.btn_guided.setEnabled(False)
        self.btn_guided.setToolTip("Switch to GUIDED mode")
        self.btn_guided.clicked.connect(self._on_guided)

        self.btn_loiter = QPushButton("LOITER")
        self.btn_loiter.setProperty("class", "btn-flight")
        self.btn_loiter.setEnabled(False)
        self.btn_loiter.setToolTip("Switch to LOITER mode (position hold)")
        self.btn_loiter.clicked.connect(self._on_loiter)

        self.btn_manual = QPushButton("MANUAL")
        self.btn_manual.setProperty("class", "btn-flight")
        self.btn_manual.setEnabled(False)
        self.btn_manual.setToolTip("Switch to STABILIZE (manual) mode")
        self.btn_manual.clicked.connect(self._on_manual)

        self.btn_land = QPushButton("LAND")
        self.btn_land.setProperty("class", "btn-flight")
        self.btn_land.setEnabled(False)
        self.btn_land.setToolTip("Command vehicle to land at current position")
        self.btn_land.clicked.connect(self._on_land)

        self.btn_rtl = QPushButton("RTL")
        self.btn_rtl.setProperty("class", "btn-flight")
        self.btn_rtl.setEnabled(False)
        self.btn_rtl.setToolTip("Return to Launch — requires confirmation")
        self.btn_rtl.clicked.connect(self._on_rtl)

        self.btn_abort = QPushButton("⚠ ABORT")
        self.btn_abort.setProperty("class", "btn-flight btn-flight-abort")
        self.btn_abort.setStyleSheet(
            "font-weight: bold; color: #f85149; border: 1px solid #da3633;"
        )
        self.btn_abort.setEnabled(False)
        self.btn_abort.setToolTip("Emergency abort — RTL immediately — requires confirmation")
        self.btn_abort.clicked.connect(self._on_abort)

        self.flight_buttons = [
            self.btn_arm, self.btn_takeoff, self.btn_guided,
            self.btn_loiter, self.btn_manual, self.btn_land,
            self.btn_rtl, self.btn_abort,
        ]

        for btn in self.flight_buttons:
            layout.addWidget(btn)

        layout.addSpacing(16)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #30363d;")
        layout.addWidget(sep)

        self.lbl_feedback = QLabel("STATUS: SYSTEM READY - DISCONNECTED")
        self.lbl_feedback.setStyleSheet(
            "color: #8b949e; font-weight: 700; font-family: 'Consolas', monospace;"
            " font-size: 11px; padding: 4px 8px; background-color: #21262d;"
            " border-radius: 4px; border: 1px solid #30363d;"
        )
        layout.addWidget(self.lbl_feedback)
        layout.addStretch()

        lbl_notice = QLabel("OPERATOR CONTROL ACTIVE")
        lbl_notice.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 600;")
        layout.addWidget(lbl_notice)

    def _connect_signals(self):
        app_state.connection_changed.connect(self._on_connection_changed)
        app_state.arm_state_changed.connect(self._on_arm_state_changed)
        app_state.command_feedback.connect(self.on_feedback)

    # ──────────────────────────────────────────────────────────────────────────
    # State Management
    # ──────────────────────────────────────────────────────────────────────────
    def _on_connection_changed(self, status: str):
        connected = status == ConnectionState.CONNECTED
        if not connected:
            for btn in self.flight_buttons:
                btn.setEnabled(False)
            self.lbl_feedback.setText("STATUS: SYSTEM READY - DISCONNECTED")
            self.lbl_feedback.setStyleSheet(
                "color: #8b949e; font-weight: 700; font-family: 'Consolas', monospace;"
                " font-size: 11px; padding: 4px 8px; background-color: #21262d;"
                " border-radius: 4px; border: 1px solid #30363d;"
            )
        else:
            # Enable abort always when connected; arm/mode buttons gated on arm state
            self.btn_abort.setEnabled(True)
            self._refresh_arm_buttons(app_state.arm_state)

    def _on_arm_state_changed(self, arm_state: str):
        if app_state.connection_status == ConnectionState.CONNECTED:
            self._refresh_arm_buttons(arm_state)

    def _refresh_arm_buttons(self, arm_state: str):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        is_armed = (arm_state == FlightState.ARMED)
        self.btn_arm.setEnabled(is_conn)
        self.btn_takeoff.setEnabled(is_conn and is_armed)
        self.btn_guided.setEnabled(is_conn and is_armed)
        self.btn_loiter.setEnabled(is_conn and is_armed)
        self.btn_manual.setEnabled(is_conn and is_armed)
        self.btn_land.setEnabled(is_conn and is_armed)
        self.btn_rtl.setEnabled(is_conn and is_armed)
        # Disarm shown as DISARM label when armed, ARM label when disarmed
        if is_armed:
            self.btn_arm.setText("DISARM")
            self.btn_arm.setToolTip("Disarm vehicle motors — requires confirmation")
            self.btn_arm.setStyleSheet("font-weight: bold; color: #d29922;")
        else:
            self.btn_arm.setText("ARM")
            self.btn_arm.setToolTip("Arm vehicle motors — requires confirmation")
            self.btn_arm.setStyleSheet("font-weight: bold; color: #3fb950;")



    def on_feedback(self, text: str):
        self.lbl_feedback.setText(f"STATUS: {text}")
        # Colour feedback based on content
        if "ERROR" in text or "FAIL" in text:
            colour = "#f85149"
        elif "ABORT" in text or "EMERGENCY" in text:
            colour = "#f85149"
        elif "SENT" in text or "CONNECTED" in text:
            colour = "#3fb950"
        else:
            colour = "#58a6ff"
        self.lbl_feedback.setStyleSheet(
            f"color: {colour}; font-weight: 700; font-family: 'Consolas', monospace;"
            f" font-size: 11px; padding: 4px 8px; background-color: #21262d;"
            f" border-radius: 4px; border: 1px solid #30363d;"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Command Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _dispatch(self, mock_func, real_func=None, *args):
        """Send a command via the injected worker (mock or real)."""
        if self._worker is None:
            app_state.set_command_feedback("NO WORKER — NOT CONNECTED")
            return
        if self._worker._mock_mode:
            from gcs.mavlink import commands
            result = getattr(commands, mock_func)(*args)
            self._worker.dispatch_mock(result)
            app_state.log("INFO", "COMMAND", result.get("result", "COMMAND SENT"))
        else:
            from gcs.mavlink import commands
            func = getattr(commands, real_func or mock_func.replace("mock_", "send_"))
            self._worker.dispatch_real(func, *args)

    def _on_arm(self):
        is_armed = app_state.arm_state == FlightState.ARMED
        if is_armed:
            dlg = ConfirmDialog(
                "DISARM VEHICLE",
                "Disarming the vehicle will immediately cut motor power.\n"
                "Only disarm when the vehicle is safely on the ground.",
                parent=self
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._dispatch("mock_disarm", "send_disarm")
        else:
            dlg = ConfirmDialog(
                "ARM VEHICLE",
                "Arming the vehicle will enable the motors.\n"
                "Ensure the area is clear of personnel and obstacles.",
                parent=self
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._dispatch("mock_arm", "send_arm")

    def _on_takeoff(self):
        dlg = ConfirmDialog(
            "TAKEOFF",
            "Vehicle will take off and hover at the specified altitude.\n"
            "Ensure the area above is clear.",
            parent=self, ask_altitude=True, default_altitude=5.0
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            alt = dlg.get_altitude()
            self._dispatch("mock_takeoff", "send_takeoff", alt)

    def _on_guided(self):
        self._dispatch("mock_guided", "send_guided")

    def _on_loiter(self):
        self._dispatch("mock_loiter", "send_loiter")

    def _on_manual(self):
        self._dispatch("mock_manual", "send_manual")

    def _on_land(self):
        self._dispatch("mock_land", "send_land")

    def _on_rtl(self):
        dlg = ConfirmDialog(
            "RETURN TO LAUNCH (RTL)",
            "Vehicle will fly back to the home launch position and land automatically.",
            parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_rtl", "send_rtl")

    def _on_abort(self):
        dlg = ConfirmDialog(
            "⚠  EMERGENCY ABORT",
            "The vehicle will immediately switch to RTL and return to launch.\n\n"
            "USE ONLY IN AN EMERGENCY SITUATION.",
            parent=self, is_abort=True
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_abort", "send_abort")
            app_state.log("CRITICAL", "SAFETY", "EMERGENCY ABORT ACTIVATED BY OPERATOR")
