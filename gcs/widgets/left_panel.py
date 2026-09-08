"""Left-side Control and Tool Panel for GCS.

Contains collapsible tool groups:
- VEHICLE (Connect, Disconnect, Arm, Disarm, Takeoff, Land, RTL, Loiter, Guided, Manual)
- MISSION (New, Load, Save, Upload, Download, Start, Pause, Resume, Cancel)
- DEPLOYMENT (Define Area, Analyze Coverage, Generate Candidates, Select Location, Generate Mission, Deploy Node)
- SURVEY (Create Survey, Start Survey, Stop Survey, RSSI Heatmap, Coverage Analysis)
- SAFETY (Abort, RTL, Geofence, Vehicle Health)

In Phase 1, Connect and Disconnect buttons are fully enabled and functional.
In Phase 3, all VEHICLE flight control buttons are enabled with state gating.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QFrame,
    QGridLayout,
    QDialog,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.mavlink.mission_manager import MissionPlan, Waypoint


class ToolSection(QFrame):
    """A clean collapsible or styled section box for GCS tool categories."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "section-box")
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(0, 0, 0, 0)
        self.layout_root.setSpacing(0)

        # Header bar
        self.header_btn = QPushButton(f"▼  {title}")
        self.header_btn.setProperty("class", "section-header")
        self.header_btn.setStyleSheet(
            "text-align: left; padding: 6px 8px; border: none; border-bottom: 1px solid #30363d; font-weight: 700;"
        )
        self.header_btn.clicked.connect(self.toggle_collapse)
        self.layout_root.addWidget(self.header_btn)

        # Content container
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(6)
        self.layout_root.addWidget(self.content_widget)

        self._title = title
        self._is_collapsed = False

    def toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.content_widget.setVisible(not self._is_collapsed)
        arrow = "►" if self._is_collapsed else "▼"
        self.header_btn.setText(f"{arrow}  {self._title}")

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


class LeftPanel(QWidget):
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leftPanel")
        self.setFixedWidth(240)
        self._init_ui()
        self._connect_signals()
        self._on_connection_changed(app_state.connection_status)
        self._on_backend_connection_changed(app_state.backend_connected)


    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar Title / Collapse Toggle Header
        header = QWidget()
        header.setStyleSheet("background-color: #161b22; border-bottom: 1px solid #30363d; padding: 4px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)

        title = QLabel("TOOLS & CONTROLS")
        title.setStyleSheet("font-weight: 700; font-size: 11px; color: #8b949e; letter-spacing: 0.5px;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.btn_collapse_all = QPushButton("⊟")
        self.btn_collapse_all.setToolTip("Toggle panels")
        self.btn_collapse_all.setFixedSize(22, 20)
        self.btn_collapse_all.setStyleSheet("padding: 0px; font-size: 11px;")
        h_layout.addWidget(self.btn_collapse_all)

        root_layout.addWidget(header)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(6, 6, 6, 6)
        self.scroll_layout.setSpacing(6)

        # 1. VEHICLE SECTION
        self.sec_vehicle = ToolSection("VEHICLE")
        grid_v = QGridLayout()
        grid_v.setSpacing(4)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setEnabled(True)
        self.btn_connect.setToolTip("Open MAVLink connection setup dialog")
        self.btn_connect.setStyleSheet("font-weight: bold; color: #58a6ff;")
        self.btn_connect.clicked.connect(self.connect_requested.emit)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setToolTip("Disconnect active MAVLink telemetry stream")
        self.btn_disconnect.setStyleSheet("color: #f85149;")
        self.btn_disconnect.clicked.connect(self.disconnect_requested.emit)

        self.btn_arm = QPushButton("Arm")
        self.btn_arm.setEnabled(False)
        self.btn_arm.setToolTip("Arm vehicle motors — requires confirmation")
        self.btn_arm.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.btn_arm.clicked.connect(self._on_arm)

        self.btn_disarm = QPushButton("Disarm")
        self.btn_disarm.setEnabled(False)
        self.btn_disarm.setToolTip("Disarm vehicle motors — requires confirmation")
        self.btn_disarm.setStyleSheet("color: #d29922;")
        self.btn_disarm.clicked.connect(self._on_disarm)

        self.btn_takeoff = QPushButton("Takeoff")
        self.btn_takeoff.setEnabled(False)
        self.btn_takeoff.setToolTip("Takeoff to specified altitude")
        self.btn_takeoff.clicked.connect(self._on_takeoff)

        self.btn_land = QPushButton("Land")
        self.btn_land.setEnabled(False)
        self.btn_land.setToolTip("Land at current position")
        self.btn_land.clicked.connect(self._on_land)

        self.btn_loiter = QPushButton("Loiter")
        self.btn_loiter.setEnabled(False)
        self.btn_loiter.setToolTip("Switch to LOITER (position hold) mode")
        self.btn_loiter.clicked.connect(self._on_loiter)

        self.btn_guided = QPushButton("Guided")
        self.btn_guided.setEnabled(False)
        self.btn_guided.setToolTip("Switch to GUIDED mode")
        self.btn_guided.clicked.connect(self._on_guided)

        self.btn_rtl = QPushButton("RTL")
        self.btn_rtl.setEnabled(False)
        self.btn_rtl.setToolTip("Return to Launch — requires confirmation")
        self.btn_rtl.clicked.connect(self._on_rtl)

        self.btn_manual = QPushButton("Manual")
        self.btn_manual.setEnabled(False)
        self.btn_manual.setToolTip("Switch to STABILIZE (manual) mode")
        self.btn_manual.clicked.connect(self._on_manual)

        self._flight_panel_buttons = [
            self.btn_arm, self.btn_disarm, self.btn_takeoff, self.btn_land,
            self.btn_loiter, self.btn_guided, self.btn_rtl, self.btn_manual
        ]

        grid_v.addWidget(self.btn_connect, 0, 0)
        grid_v.addWidget(self.btn_disconnect, 0, 1)
        grid_v.addWidget(self.btn_arm, 1, 0)
        grid_v.addWidget(self.btn_disarm, 1, 1)
        grid_v.addWidget(self.btn_takeoff, 2, 0)
        grid_v.addWidget(self.btn_land, 2, 1)
        grid_v.addWidget(self.btn_loiter, 3, 0)
        grid_v.addWidget(self.btn_guided, 3, 1)
        grid_v.addWidget(self.btn_rtl, 4, 0)
        grid_v.addWidget(self.btn_manual, 4, 1)
        self.sec_vehicle.add_layout(grid_v)
        self.scroll_layout.addWidget(self.sec_vehicle)

        # 2. MISSION SECTION
        self.sec_mission = ToolSection("MISSION")
        grid_m = QGridLayout()
        grid_m.setSpacing(4)

        self.btn_m_new = QPushButton("New Mission")
        self.btn_m_new.setToolTip("Create a new empty mission plan")
        self.btn_m_new.clicked.connect(self._on_m_new)

        self.btn_m_load = QPushButton("Load Mission")
        self.btn_m_load.setToolTip("Load mission plan from .plan or .waypoints file")
        self.btn_m_load.clicked.connect(self._on_m_load)

        self.btn_m_save = QPushButton("Save Mission")
        self.btn_m_save.setToolTip("Save mission plan to .plan or .waypoints file")
        self.btn_m_save.setEnabled(False)
        self.btn_m_save.clicked.connect(self._on_m_save)

        self.btn_m_upload = QPushButton("Upload")
        self.btn_m_upload.setToolTip("Upload mission to UAV via MAVLink")
        self.btn_m_upload.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.btn_m_upload.setEnabled(False)
        self.btn_m_upload.clicked.connect(self._on_m_upload)

        self.btn_m_download = QPushButton("Download")
        self.btn_m_download.setToolTip("Download active mission from UAV via MAVLink")
        self.btn_m_download.setStyleSheet("color: #a371f7;")
        self.btn_m_download.setEnabled(False)
        self.btn_m_download.clicked.connect(self._on_m_download)

        self.btn_m_start = QPushButton("Start")
        self.btn_m_start.setToolTip("Start autonomous mission flight")
        self.btn_m_start.setStyleSheet("color: #58a6ff; font-weight: bold;")
        self.btn_m_start.setEnabled(False)
        self.btn_m_start.clicked.connect(self._on_m_start)

        self.btn_m_pause = QPushButton("Pause")
        self.btn_m_pause.setToolTip("Pause mission flight and hold position (LOITER)")
        self.btn_m_pause.setStyleSheet("color: #d29922;")
        self.btn_m_pause.setEnabled(False)
        self.btn_m_pause.clicked.connect(self._on_m_pause)

        self.btn_m_resume = QPushButton("Resume")
        self.btn_m_resume.setToolTip("Resume autonomous mission flight")
        self.btn_m_resume.setStyleSheet("color: #3fb950;")
        self.btn_m_resume.setEnabled(False)
        self.btn_m_resume.clicked.connect(self._on_m_resume)

        self.btn_m_cancel = QPushButton("Cancel")
        self.btn_m_cancel.setToolTip("Cancel mission and hold position")
        self.btn_m_cancel.setStyleSheet("color: #f85149;")
        self.btn_m_cancel.setEnabled(False)
        self.btn_m_cancel.clicked.connect(self._on_m_cancel)

        grid_m.addWidget(self.btn_m_new, 0, 0)
        grid_m.addWidget(self.btn_m_load, 0, 1)
        grid_m.addWidget(self.btn_m_save, 1, 0)
        grid_m.addWidget(self.btn_m_upload, 1, 1)
        grid_m.addWidget(self.btn_m_download, 2, 0)
        grid_m.addWidget(self.btn_m_start, 2, 1)
        grid_m.addWidget(self.btn_m_pause, 3, 0)
        grid_m.addWidget(self.btn_m_resume, 3, 1)
        grid_m.addWidget(self.btn_m_cancel, 4, 0, 1, 2)
        self.sec_mission.add_layout(grid_m)
        self.scroll_layout.addWidget(self.sec_mission)

        # 3. DEPLOYMENT SECTION
        self.sec_deployment = ToolSection("DEPLOYMENT")
        v_dep = QVBoxLayout()
        self.btn_define_area = QPushButton("Define Area")
        self.btn_define_area.setToolTip("Define disaster boundary perimeter on tactical map")
        self.btn_define_area.setStyleSheet("color: #e3b341; font-weight: bold;")
        self.btn_define_area.setEnabled(True)
        self.btn_define_area.clicked.connect(self._on_define_area)
        v_dep.addWidget(self.btn_define_area)

        self.btn_analyze_cov = QPushButton("Analyze Coverage")
        self.btn_analyze_cov.setToolTip("Run coverage analysis and optimize node placement")
        self.btn_analyze_cov.setStyleSheet("color: #58a6ff; font-weight: 600;")
        self.btn_analyze_cov.clicked.connect(self._on_analyze_coverage)
        v_dep.addWidget(self.btn_analyze_cov)

        self.btn_gen_cand = QPushButton("Generate Candidates")
        self.btn_gen_cand.setToolTip("Generate lattice candidate locations inside disaster area")
        self.btn_gen_cand.clicked.connect(self._on_generate_candidates)
        v_dep.addWidget(self.btn_gen_cand)

        self.btn_sel_loc = QPushButton("Select Location")
        self.btn_sel_loc.setToolTip("Select optimal or next candidate deployment location")
        self.btn_sel_loc.clicked.connect(self._on_select_location)
        v_dep.addWidget(self.btn_sel_loc)

        self.btn_gen_mission = QPushButton("Generate Mission")
        self.btn_gen_mission.setToolTip("Generate automated deployment waypoint mission")
        self.btn_gen_mission.setStyleSheet("color: #3fb950; font-weight: 600;")
        self.btn_gen_mission.clicked.connect(self._on_generate_mission)
        v_dep.addWidget(self.btn_gen_mission)

        self.btn_dep_node = QPushButton("Deploy Node")
        self.btn_dep_node.setToolTip("Execute GPS multi-node deployment mission")
        self.btn_dep_node.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.btn_dep_node.setEnabled(False)
        self.btn_dep_node.clicked.connect(self._on_deploy_node)
        v_dep.addWidget(self.btn_dep_node)

        self.sec_deployment.add_layout(v_dep)
        self.scroll_layout.addWidget(self.sec_deployment)

        # 4. SURVEY SECTION
        self.sec_survey = ToolSection("SURVEY")
        v_sur = QVBoxLayout()
        v_sur.setSpacing(4)
        self.btn_create_survey = QPushButton("Create Survey")
        self.btn_create_survey.setToolTip("Generate Lawnmower RF survey flight pattern")
        self.btn_create_survey.setStyleSheet("color: #58a6ff; font-weight: 600;")
        self.btn_create_survey.clicked.connect(self._on_create_survey)
        v_sur.addWidget(self.btn_create_survey)

        self.btn_start_survey = QPushButton("Start Survey")
        self.btn_start_survey.setToolTip("Start autonomous RF survey flight and RSSI sampling")
        self.btn_start_survey.setStyleSheet("color: #3fb950; font-weight: 600;")
        self.btn_start_survey.clicked.connect(self._on_start_survey)
        v_sur.addWidget(self.btn_start_survey)

        self.btn_stop_survey = QPushButton("Stop Survey")
        self.btn_stop_survey.setToolTip("Stop active RF survey")
        self.btn_stop_survey.setStyleSheet("color: #da3633; font-weight: 600;")
        self.btn_stop_survey.clicked.connect(self._on_stop_survey)
        self.btn_rssi_heatmap = QPushButton("RSSI Heatmap")
        self.btn_rssi_heatmap.setToolTip("Generate and toggle spatial RF RSSI heatmap layer")
        self.btn_rssi_heatmap.setStyleSheet("color: #58a6ff; font-weight: 600;")
        self.btn_rssi_heatmap.clicked.connect(self._on_rssi_heatmap)
        v_sur.addWidget(self.btn_rssi_heatmap)

        self.btn_cov_analysis = QPushButton("Coverage Analysis")
        self.btn_cov_analysis.setToolTip("Analyze coverage gaps and detect shadow zones")
        self.btn_cov_analysis.setStyleSheet("color: #d29922; font-weight: 600;")
        self.btn_cov_analysis.clicked.connect(self._on_coverage_analysis)
        v_sur.addWidget(self.btn_cov_analysis)

        self.sec_survey.add_layout(v_sur)
        self.scroll_layout.addWidget(self.sec_survey)

        # 5. SAFETY SECTION
        self.sec_safety = ToolSection("SAFETY")
        v_saf = QVBoxLayout()
        v_saf.setSpacing(4)
        btn_abort = self._create_btn("ABORT MISSION", "Available in Phase 3 / Safety")
        btn_abort.setProperty("class", "btn-flight-abort")
        v_saf.addWidget(btn_abort)
        v_saf.addWidget(self._create_btn("RTL (Return)", "Available in Phase 3 (Flight Control)"))
        v_saf.addWidget(self._create_btn("Geofence", "Available in Phase 16 (Safety Integration)"))
        v_saf.addWidget(self._create_btn("Vehicle Health", "Available in Phase 1 (MAVLink Heartbeat)"))
        # 6. REST BACKEND SECTION (Phase 16)
        self.sec_backend = ToolSection("REST API")
        v_back = QVBoxLayout()
        v_back.setSpacing(4)

        self.lbl_rest_status = QLabel("REST API: OFFLINE (Local)")
        self.lbl_rest_status.setStyleSheet("color: #8b949e; font-weight: 600; font-size: 11px;")
        v_back.addWidget(self.lbl_rest_status)

        self.btn_check_rest = QPushButton("Ping REST API")
        self.btn_check_rest.setToolTip("Ping FastAPI server at http://localhost:8000/api/status")
        self.btn_check_rest.setStyleSheet("color: #58a6ff; font-weight: 600;")
        self.btn_check_rest.clicked.connect(self._on_ping_rest)
        v_back.addWidget(self.btn_check_rest)

        self.sec_backend.add_layout(v_back)
        self.scroll_layout.addWidget(self.sec_backend)

        self.scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        root_layout.addWidget(scroll)

        self.btn_collapse_all.clicked.connect(self._toggle_all)
        self._all_collapsed = False

    def _create_btn(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setEnabled(False)
        btn.setToolTip(tooltip)
        return btn

    def _connect_signals(self):
        app_state.connection_changed.connect(self._on_connection_changed)
        app_state.arm_state_changed.connect(self._on_arm_state_changed)
        app_state.mission_updated.connect(self._on_mission_updated)
        app_state.mission_status_changed.connect(self._on_mission_status_changed)
        app_state.deployment_state_changed.connect(self._on_deployment_state_changed)
        app_state.backend_connection_changed.connect(self._on_backend_connection_changed)

    def _on_backend_connection_changed(self, connected: bool):
        if connected:
            self.lbl_rest_status.setText("REST API: ONLINE (8000)")
            self.lbl_rest_status.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_rest_status.setText("REST API: OFFLINE (Local)")
            self.lbl_rest_status.setStyleSheet("color: #8b949e; font-weight: 600; font-size: 11px;")

    def _on_ping_rest(self):
        app_state.fetch_backend_status()



    def _on_connection_changed(self, status: str):
        if status == ConnectionState.CONNECTED:
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            # Enable arm when connected & disarmed
            self._refresh_flight_buttons(app_state.arm_state)
            self._refresh_mission_buttons()
            self._refresh_deployment_buttons()
        else:
            self.btn_connect.setEnabled(True)
            self.btn_disconnect.setEnabled(False)
            for btn in self._flight_panel_buttons:
                btn.setEnabled(False)
            self._refresh_mission_buttons()
            self._refresh_deployment_buttons()

    def _on_arm_state_changed(self, arm_state: str):
        if app_state.connection_status == ConnectionState.CONNECTED:
            self._refresh_flight_buttons(arm_state)
            self._refresh_mission_buttons()
            self._refresh_deployment_buttons()

    def _on_deployment_state_changed(self, state: str):
        self._refresh_deployment_buttons()

    def _refresh_deployment_buttons(self):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        state = app_state.deployment_state
        can_deploy = is_conn and (state in ("ON STATION", "NAVIGATING"))
        self.btn_dep_node.setEnabled(can_deploy)

    def _on_mission_updated(self, waypoints: list):
        self._refresh_mission_buttons()

    def _on_mission_status_changed(self, status: str):
        self._refresh_mission_buttons()

    def _refresh_flight_buttons(self, arm_state: str):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        is_armed = (arm_state == FlightState.ARMED)
        self.btn_arm.setEnabled(is_conn and not is_armed)
        self.btn_disarm.setEnabled(is_conn and is_armed)
        self.btn_takeoff.setEnabled(is_conn)
        self.btn_land.setEnabled(is_conn)
        self.btn_loiter.setEnabled(is_conn)
        self.btn_guided.setEnabled(is_conn)
        self.btn_rtl.setEnabled(is_conn)
        self.btn_manual.setEnabled(is_conn)

    def _refresh_mission_buttons(self):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        is_armed = (app_state.arm_state == FlightState.ARMED)
        has_wps = len(app_state.mission_waypoints) > 0
        status = app_state.mission_status

        self.btn_m_save.setEnabled(has_wps)
        self.btn_m_upload.setEnabled(is_conn and has_wps)
        self.btn_m_download.setEnabled(is_conn)

        is_running = (status == "RUNNING")
        is_paused = (status == "PAUSED")

        can_start = is_conn and is_armed and has_wps and not is_running
        self.btn_m_start.setEnabled(can_start)
        if not is_armed and is_conn and has_wps:
            self.btn_m_start.setToolTip("Start Mission (Arm vehicle first to enable)")
        else:
            self.btn_m_start.setToolTip("Start autonomous mission flight")

        self.btn_m_pause.setEnabled(is_conn and is_running)
        self.btn_m_resume.setEnabled(is_conn and is_paused)
        self.btn_m_cancel.setEnabled(is_conn and (is_running or is_paused))



    def set_worker(self, worker):
        """Inject MAVLink worker reference for command dispatch."""
        self._worker = worker
        self._on_connection_changed(app_state.connection_status)


    def _dispatch(self, mock_func, real_func=None, *args):
        if not hasattr(self, '_worker') or self._worker is None:
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
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("ARM VEHICLE",
            "Arming will enable motors. Ensure area is clear.", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_arm", "send_arm")

    def _on_disarm(self):
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("DISARM VEHICLE",
            "Disarming will cut motor power immediately.", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_disarm", "send_disarm")

    def _on_takeoff(self):
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("TAKEOFF", "Vehicle will climb to specified altitude.",
            parent=self, ask_altitude=True, default_altitude=5.0)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_takeoff", "send_takeoff", dlg.get_altitude())

    def _on_land(self):
        self._dispatch("mock_land", "send_land")

    def _on_loiter(self):
        self._dispatch("mock_loiter", "send_loiter")

    def _on_guided(self):
        self._dispatch("mock_guided", "send_guided")

    def _on_rtl(self):
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("RETURN TO LAUNCH (RTL)",
            "Vehicle will fly back to home position and land.", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_rtl", "send_rtl")

    def _on_manual(self):
        self._dispatch("mock_manual", "send_manual")

    def _on_m_new(self):
        app_state.set_mission_waypoints([])
        app_state.set_mission_status("IDLE")
        app_state.set_active_waypoint(0)
        app_state.set_command_feedback("NEW MISSION INITIALIZED")
        app_state.log("INFO", "MISSION", "Created new empty mission plan")

    def _on_m_load(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Mission Plan", "", "Mission Plans (*.plan *.waypoints *.txt);;All Files (*)"
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            if filename.endswith(".plan") or content.strip().startswith("{"):
                plan = MissionPlan.from_qgc_json(content)
            else:
                plan = MissionPlan.from_waypoints_text(content)

            app_state.set_mission_waypoints(plan.to_list_of_dicts())
            app_state.set_mission_status("LOADED")
            app_state.set_command_feedback(f"MISSION LOADED: {len(plan.waypoints)} WPs")
            app_state.log("INFO", "MISSION", f"Loaded mission from {filename} ({len(plan.waypoints)} WPs)")
        except Exception as e:
            app_state.set_command_feedback(f"LOAD FAILED: {str(e)}")
            app_state.log("ERROR", "MISSION", f"Failed to load mission: {e}")

    def _on_m_save(self):
        if not app_state.mission_waypoints:
            app_state.set_command_feedback("CANNOT SAVE: EMPTY MISSION")
            return
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Mission Plan", "mission.plan", "QGC Plan (*.plan);;Waypoints File (*.waypoints)"
        )
        if not filename:
            return
        try:
            plan = MissionPlan([Waypoint.from_dict(d) for d in app_state.mission_waypoints])
            if filename.endswith(".waypoints") or "Waypoints" in selected_filter:
                content = plan.to_waypoints_text()
            else:
                content = plan.to_qgc_json()
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            app_state.set_command_feedback(f"MISSION SAVED: {len(plan.waypoints)} WPs")
            app_state.log("INFO", "MISSION", f"Saved mission to {filename}")
        except Exception as e:
            app_state.set_command_feedback(f"SAVE FAILED: {str(e)}")
            app_state.log("ERROR", "MISSION", f"Failed to save mission: {e}")

    def _on_m_upload(self):
        if not hasattr(self, '_worker') or self._worker is None:
            app_state.set_command_feedback("UPLOAD FAILED: NO WORKER")
            return
        wps = [Waypoint.from_dict(d) for d in app_state.mission_waypoints]
        app_state.set_mission_status("UPLOADING")
        self._worker.upload_mission(wps)

    def _on_m_download(self):
        if not hasattr(self, '_worker') or self._worker is None:
            app_state.set_command_feedback("DOWNLOAD FAILED: NO WORKER")
            return
        app_state.set_mission_status("DOWNLOADING")
        self._worker.download_mission()

    def _on_m_start(self):
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("START MISSION", "Vehicle will engage autonomous flight along mission waypoints.", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_mission_start", "send_mission_start")
            app_state.set_mission_status("RUNNING")

    def _on_m_pause(self):
        self._dispatch("mock_loiter", "send_loiter")
        app_state.set_mission_status("PAUSED")
        app_state.set_command_feedback("MISSION PAUSED (LOITER)")

    def _on_m_resume(self):
        self._dispatch("mock_mission_start", "send_mission_start")
        app_state.set_mission_status("RUNNING")
        app_state.set_command_feedback("MISSION RESUMED (AUTO)")

    def _on_m_cancel(self):
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("CANCEL MISSION", "Cancel autonomous mission and hold position?", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dispatch("mock_loiter", "send_loiter")
            app_state.set_mission_status("IDLE")
            app_state.set_active_waypoint(0)
            app_state.set_command_feedback("MISSION CANCELLED")

    def _on_deploy_node(self):
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "deployment_view"):
            win.right_panel.tabs.setCurrentIndex(3)
            dep_view = win.right_panel.deployment_view
            from gcs.deployment.gps_mission_controller import gps_mission_controller, GpsMissionState
            if gps_mission_controller.state in (GpsMissionState.READY, GpsMissionState.IDLE):
                dep_view._on_start_gps_mission()
            elif gps_mission_controller.state == GpsMissionState.ON_STATION:
                dep_view._on_confirm_station_drop()
            else:
                dep_view.trigger_deployment_sequence()
            return

        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog(
            "DEPLOY EMERGENCY RELAY NODE",
            "Confirm payload release sequence? This will deploy an operational communication relay node at the target drop station.",
            parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            from gcs.deployment.deployment_manager import DeploymentNode, DeploymentState
            lat = app_state.telemetry.get("lat", 37.7749)
            lon = app_state.telemetry.get("lon", -122.4194)
            if app_state.deployment_target:
                tgt = app_state.deployment_target
                lat = tgt.lat if hasattr(tgt, "lat") else tgt.get("lat", lat)
                lon = tgt.lon if hasattr(tgt, "lon") else tgt.get("lon", lon)
            count = len(app_state.deployed_nodes) + 1
            node = DeploymentNode(
                node_id=f"NODE-{count:02d}",
                lat=lat,
                lon=lon,
                alt=0.0,
                status="ACTIVE",
                coverage_radius_m=250.0
            )
            app_state.add_deployed_node(node)
            app_state.set_deployment_state(DeploymentState.DEPLOYED)
            app_state.set_command_feedback(f"EMERGENCY NODE DEPLOYED: {node.node_id}")
            app_state.log("INFO", "DEPLOYMENT", f"Deployed emergency communication relay {node.node_id} at {lat:.6f}, {lon:.6f}")


    def _on_define_area(self):
        """Activate disaster boundary drawing on map and focus deployment workflow."""
        app_state.start_area_drawing()
        app_state.set_command_feedback("CLICK MAP TO DRAW DISASTER POLYGON VERTICES")

    def _on_analyze_coverage(self):
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "deployment_view"):
            win.right_panel.tabs.setCurrentIndex(3)
            win.right_panel.deployment_view._on_optimize_clicked()

    def _on_generate_candidates(self):
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "deployment_view"):
            win.right_panel.tabs.setCurrentIndex(3)
            win.right_panel.deployment_view._on_generate_candidates_clicked()

    def _on_select_location(self):
        if app_state.candidates:
            selected = [c for c in app_state.candidates if getattr(c, "is_selected", False)]
            cand = selected[0] if selected else app_state.candidates[0]
            app_state.select_candidate(cand)
            win = self.window()
            if hasattr(win, "right_panel"):
                win.right_panel.tabs.setCurrentIndex(3)

    def _on_generate_mission(self):
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "deployment_view"):
            win.right_panel.deployment_view._on_generate_mission_clicked()

    def _on_create_survey(self):
        """Create and preview RF lawnmower survey flight plan."""
        from gcs.rf.rf_survey_controller import rf_survey_controller
        rf_survey_controller.generate_survey()
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
            win.right_panel.tabs.setCurrentIndex(4)

    def _on_start_survey(self):
        """Start autonomous RF survey."""
        from gcs.rf.rf_survey_controller import rf_survey_controller
        rf_survey_controller.start_survey()
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
            win.right_panel.tabs.setCurrentIndex(4)

    def _on_stop_survey(self):
        """Stop active RF survey."""
        from gcs.rf.rf_survey_controller import rf_survey_controller
        rf_survey_controller.stop_survey()

    def _on_rssi_heatmap(self):
        """Generate and visualize spatial RSSI heatmap."""
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
            win.right_panel.tabs.setCurrentIndex(4)
            if hasattr(win.right_panel, "rf_view"):
                win.right_panel.rf_view._on_generate_heatmap()

    def _on_coverage_analysis(self):
        """Execute and display coverage gap analysis."""
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
            win.right_panel.tabs.setCurrentIndex(4)
            if hasattr(win.right_panel, "rf_view"):
                win.right_panel.rf_view._on_find_gaps()

    def _toggle_all(self):
        self._all_collapsed = not self._all_collapsed
        for sec in [self.sec_vehicle, self.sec_mission, self.sec_deployment, self.sec_survey, self.sec_safety]:
            if sec._is_collapsed != self._all_collapsed:
                sec.toggle_collapse()
        self.btn_collapse_all.setText("⊞" if self._all_collapsed else "⊟")
