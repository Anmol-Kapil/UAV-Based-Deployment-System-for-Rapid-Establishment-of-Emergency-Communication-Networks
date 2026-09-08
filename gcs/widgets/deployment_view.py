"""Emergency Communication Node Deployment Console for Right Context Panel.

Provides:
- Real-time Target Tracking (Distance to target, bearing, ETA, drop altitude)
- Target coordinate definition (direct coordinate entry, UAV position copy, or click on tactical map)
- Deployment state machine transitions (IDLE -> TARGET_SELECTED -> NAVIGATING -> ON_STATION -> DEPLOYING -> DEPLOYED)
- Payload release sequence with safety confirmation dialog
- Registry table of deployed emergency communication nodes
"""

import os
import json
from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.deployment.deployment_manager import (
    DeploymentState,
    DeploymentTarget,
    DeploymentNode,
    calculate_bearing,
    calculate_ground_distance,
)
from gcs.deployment.gps_mission_controller import (
    gps_mission_controller,
    GpsMissionConfig,
    GpsMissionState,
)
from gcs.deployment.virtual_node_manager import (
    virtual_node_manager,
    VirtualNode,
    NodeStatus,
)



class DeploymentView(QWidget):
    """Operational Deployment Workflow Console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("deploymentView")
        self._worker = None
        self._target: Optional[DeploymentTarget] = None
        self._node_count = 0

        self._init_ui()
        self._connect_signals()

    def set_worker(self, worker):
        self._worker = worker
        gps_mission_controller.set_worker(worker)
        self._update_button_states()


    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Header Status Card
        header = QFrame()
        header.setProperty("class", "telemetry-card")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel("DEPLOYMENT WORKFLOW")
        title.setStyleSheet("font-weight: 700; color: #58a6ff; font-size: 11px;")
        top_row.addWidget(title)

        top_row.addStretch()

        self.lbl_status = QLabel("STATUS: IDLE")
        self.lbl_status.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        top_row.addWidget(self.lbl_status)
        h_layout.addLayout(top_row)

        # Real-time metrics
        metrics = QHBoxLayout()
        metrics.setSpacing(10)

        self.lbl_dist = QLabel("Dist: -- m")
        self.lbl_dist.setStyleSheet("font-size: 10px; font-weight: 600; color: #f0f6fc;")
        metrics.addWidget(self.lbl_dist)

        self.lbl_bearing = QLabel("Bearing: --°")
        self.lbl_bearing.setStyleSheet("font-size: 10px; font-weight: 600; color: #79c0ff;")
        metrics.addWidget(self.lbl_bearing)

        self.lbl_eta = QLabel("ETA: -- s")
        self.lbl_eta.setStyleSheet("font-size: 10px; font-weight: 600; color: #e3b341;")
        metrics.addWidget(self.lbl_eta)

        metrics.addStretch()
        h_layout.addLayout(metrics)
        layout.addWidget(header)

        # 2. Disaster Incident Area Card (Phase 7)
        area_card = QFrame()
        area_card.setProperty("class", "telemetry-card")
        a_layout = QVBoxLayout(area_card)
        a_layout.setContentsMargins(8, 6, 8, 6)
        a_layout.setSpacing(5)

        a_top = QHBoxLayout()
        lbl_a_title = QLabel("DISASTER INCIDENT AREA")
        lbl_a_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #e3b341;")
        a_top.addWidget(lbl_a_title)
        a_top.addStretch()

        self.lbl_area_name = QLabel("NO AREA DEFINED")
        self.lbl_area_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #8b949e;")
        a_top.addWidget(self.lbl_area_name)
        a_layout.addLayout(a_top)

        self.lbl_area_metrics = QLabel("Area: -- km² | Perimeter: -- km | Vertices: 0")
        self.lbl_area_metrics.setStyleSheet("font-size: 9px; color: #79c0ff; font-family: Consolas, monospace;")
        a_layout.addWidget(self.lbl_area_metrics)

        p_row = QHBoxLayout()
        p_row.setSpacing(4)
        lbl_p = QLabel("Preset:")
        lbl_p.setStyleSheet("font-size: 9px; color: #8b949e;")
        p_row.addWidget(lbl_p)

        self.combo_area_preset = QComboBox()
        self.combo_area_preset.addItem("Select Scenario Preset...")
        from gcs.disaster.disaster_manager import get_preset_scenarios
        self._presets = get_preset_scenarios()
        for name in self._presets.keys():
            self.combo_area_preset.addItem(name)
        self.combo_area_preset.setStyleSheet("""
            QComboBox {
                background-color: #161b22;
                border: 1px solid #30363d;
                color: #c9d1d9;
                font-size: 9px;
                padding: 2px 4px;
                border-radius: 3px;
            }
        """)
        self.combo_area_preset.currentIndexChanged.connect(self._on_preset_selected)
        p_row.addWidget(self.combo_area_preset, stretch=1)
        a_layout.addLayout(p_row)

        a_btns = QHBoxLayout()
        a_btns.setSpacing(4)

        self.btn_draw_area_action = QPushButton("Draw on Map")
        self.btn_draw_area_action.setStyleSheet("color: #e3b341; font-weight: 600; font-size: 9px;")
        self.btn_draw_area_action.clicked.connect(self._on_draw_area_clicked)
        a_btns.addWidget(self.btn_draw_area_action)

        self.btn_clear_area = QPushButton("Clear Area")
        self.btn_clear_area.setStyleSheet("color: #8b949e; font-size: 9px;")
        self.btn_clear_area.clicked.connect(self._on_clear_area_clicked)
        a_btns.addWidget(self.btn_clear_area)

        self.btn_export_geojson = QPushButton("Export GeoJSON")
        self.btn_export_geojson.setStyleSheet("font-size: 9px;")
        self.btn_export_geojson.clicked.connect(self._on_export_geojson)
        a_btns.addWidget(self.btn_export_geojson)

        self.btn_import_geojson = QPushButton("Import GeoJSON")
        self.btn_import_geojson.setStyleSheet("font-size: 9px;")
        self.btn_import_geojson.clicked.connect(self._on_import_geojson)
        a_btns.addWidget(self.btn_import_geojson)

        a_layout.addLayout(a_btns)
        layout.addWidget(area_card)

        # 3. Deployment Algorithm & Candidates Card (Phase 8)
        algo_card = QFrame()
        algo_card.setProperty("class", "telemetry-card")
        algo_layout = QVBoxLayout(algo_card)
        algo_layout.setContentsMargins(8, 6, 8, 6)
        algo_layout.setSpacing(5)

        algo_top = QHBoxLayout()
        lbl_algo_title = QLabel("OPTIMIZATION & CANDIDATE SITES")
        lbl_algo_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff;")
        algo_top.addWidget(lbl_algo_title)
        algo_top.addStretch()

        self.lbl_algo_status = QLabel("NO CANDIDATES")
        self.lbl_algo_status.setStyleSheet("font-size: 9px; font-weight: 600; color: #8b949e;")
        algo_top.addWidget(self.lbl_algo_status)
        algo_layout.addLayout(algo_top)

        # Config row: Nodes, Radius, Grid, Strategy
        cfg_grid = QGridLayout()
        cfg_grid.setSpacing(4)

        cfg_grid.addWidget(QLabel("Nodes:"), 0, 0)
        self.spin_num_nodes = QSpinBox()
        self.spin_num_nodes.setRange(1, 10)
        self.spin_num_nodes.setValue(3)
        cfg_grid.addWidget(self.spin_num_nodes, 0, 1)

        cfg_grid.addWidget(QLabel("RF Rad (m):"), 0, 2)
        self.spin_rf_radius = QDoubleSpinBox()
        self.spin_rf_radius.setRange(50.0, 1000.0)
        self.spin_rf_radius.setValue(250.0)
        cfg_grid.addWidget(self.spin_rf_radius, 0, 3)

        cfg_grid.addWidget(QLabel("Grid (m):"), 1, 0)
        self.spin_grid_res = QDoubleSpinBox()
        self.spin_grid_res.setRange(20.0, 300.0)
        self.spin_grid_res.setValue(80.0)
        cfg_grid.addWidget(self.spin_grid_res, 1, 1)

        cfg_grid.addWidget(QLabel("Strategy:"), 1, 2)
        self.combo_strategy = QComboBox()
        self.combo_strategy.addItems(["Greedy Max Coverage", "Priority Hotspots", "Uniform Mesh"])
        cfg_grid.addWidget(self.combo_strategy, 1, 3)

        algo_layout.addLayout(cfg_grid)

        # Action Buttons row
        algo_btns = QHBoxLayout()
        algo_btns.setSpacing(4)

        self.btn_optimize = QPushButton("Optimize")
        self.btn_optimize.setToolTip("Run greedy maximum coverage optimization")
        self.btn_optimize.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-weight: bold; font-size: 9px; padding: 3px 6px;")
        self.btn_optimize.clicked.connect(self._on_optimize_clicked)
        algo_btns.addWidget(self.btn_optimize)

        self.btn_generate_candidates = QPushButton("Gen Grid")
        self.btn_generate_candidates.setToolTip("Generate candidate drop points lattice")
        self.btn_generate_candidates.setStyleSheet("font-size: 9px; padding: 3px 6px;")
        self.btn_generate_candidates.clicked.connect(self._on_generate_candidates_clicked)
        algo_btns.addWidget(self.btn_generate_candidates)

        self.btn_gen_mission = QPushButton("Gen Mission")
        self.btn_gen_mission.setToolTip("Generate automated deployment flight mission")
        self.btn_gen_mission.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: bold; font-size: 9px; padding: 3px 6px;")
        self.btn_gen_mission.clicked.connect(self._on_generate_mission_clicked)
        algo_btns.addWidget(self.btn_gen_mission)

        self.btn_clear_candidates = QPushButton("Clear")
        self.btn_clear_candidates.setStyleSheet("color: #8b949e; font-size: 9px; padding: 3px 4px;")
        self.btn_clear_candidates.clicked.connect(self._on_clear_candidates_clicked)
        algo_btns.addWidget(self.btn_clear_candidates)

        algo_layout.addLayout(algo_btns)

        # Metrics banner
        self.lbl_opt_metrics = QLabel("Coverage: --% (-- km²) | Overlap: --% | Mesh: --")
        self.lbl_opt_metrics.setStyleSheet("font-size: 9px; color: #79c0ff; font-family: Consolas, monospace;")
        algo_layout.addWidget(self.lbl_opt_metrics)

        # Candidate Sites Table
        self.table_candidates = QTableWidget(0, 6)
        self.table_candidates.setHorizontalHeaderLabels(["SEL", "ID", "LAT", "LON", "COV", "STATUS"])
        self.table_candidates.setFixedHeight(120)
        self.table_candidates.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_candidates.setSelectionMode(QTableWidget.SingleSelection)
        self.table_candidates.verticalHeader().setVisible(False)
        self.table_candidates.horizontalHeader().setStretchLastSection(True)
        self.table_candidates.setColumnWidth(0, 34)
        self.table_candidates.setColumnWidth(1, 44)
        self.table_candidates.setColumnWidth(2, 64)
        self.table_candidates.setColumnWidth(3, 64)
        self.table_candidates.setColumnWidth(4, 46)
        self.table_candidates.itemClicked.connect(self._on_candidate_table_clicked)
        algo_layout.addWidget(self.table_candidates)

        layout.addWidget(algo_card)

        # 4. Target Coordinate Configuration Frame
        cfg_frame = QFrame()
        cfg_frame.setProperty("class", "telemetry-card")
        cfg_layout = QVBoxLayout(cfg_frame)
        cfg_layout.setContentsMargins(8, 6, 8, 6)
        cfg_layout.setSpacing(6)

        lbl_sec = QLabel("TARGET DROP SITE COORDINATES")
        lbl_sec.setStyleSheet("font-size: 10px; font-weight: 700; color: #d29922;")
        cfg_layout.addWidget(lbl_sec)

        grid = QGridLayout()
        grid.setSpacing(4)

        grid.addWidget(QLabel("LAT:"), 0, 0)
        self.spin_lat = QDoubleSpinBox()
        self.spin_lat.setRange(-90.0, 90.0)
        self.spin_lat.setDecimals(6)
        self.spin_lat.setValue(37.774900)
        grid.addWidget(self.spin_lat, 0, 1)

        grid.addWidget(QLabel("LON:"), 0, 2)
        self.spin_lon = QDoubleSpinBox()
        self.spin_lon.setRange(-180.0, 180.0)
        self.spin_lon.setDecimals(6)
        self.spin_lon.setValue(-122.419400)
        grid.addWidget(self.spin_lon, 0, 3)

        grid.addWidget(QLabel("ALT (m):"), 1, 0)
        self.spin_alt = QDoubleSpinBox()
        self.spin_alt.setRange(0.0, 500.0)
        self.spin_alt.setValue(25.0)
        grid.addWidget(self.spin_alt, 1, 1)

        grid.addWidget(QLabel("RAD (m):"), 1, 2)
        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setRange(2.0, 100.0)
        self.spin_radius.setValue(15.0)
        grid.addWidget(self.spin_radius, 1, 3)

        cfg_layout.addLayout(grid)

        # Quick action row for coordinates
        t_actions = QHBoxLayout()
        t_actions.setSpacing(4)

        self.btn_set_target = QPushButton("Set Target")
        self.btn_set_target.setStyleSheet("font-weight: 600; color: #58a6ff;")
        self.btn_set_target.clicked.connect(self._on_set_target_clicked)
        t_actions.addWidget(self.btn_set_target)

        self.btn_use_uav_pos = QPushButton("Copy UAV Pos")
        self.btn_use_uav_pos.setToolTip("Set target to current UAV GPS position")
        self.btn_use_uav_pos.clicked.connect(self._on_copy_uav_pos)
        t_actions.addWidget(self.btn_use_uav_pos)

        self.btn_pick_map = QPushButton("Pick on Map")
        self.btn_pick_map.setToolTip("Click on tactical map to set deployment target")
        self.btn_pick_map.setStyleSheet("color: #d29922; font-weight: 600;")
        self.btn_pick_map.clicked.connect(self._on_pick_on_map)
        t_actions.addWidget(self.btn_pick_map)

        self.btn_clear_tgt = QPushButton("Clear Target")
        self.btn_clear_tgt.setStyleSheet("color: #8b949e;")
        self.btn_clear_tgt.clicked.connect(self._on_clear_target)
        t_actions.addWidget(self.btn_clear_tgt)

        # Aliases for compatibility
        self.btn_copy_uav = self.btn_use_uav_pos
        self.btn_clear_target = self.btn_clear_tgt

        cfg_layout.addLayout(t_actions)
        layout.addWidget(cfg_frame)

        # 3. GPS Deployment Mission Control (Phase 9)
        gps_card = QFrame()
        gps_card.setProperty("class", "telemetry-card")
        g_layout = QVBoxLayout(gps_card)
        g_layout.setContentsMargins(8, 6, 8, 6)
        g_layout.setSpacing(5)

        g_top = QHBoxLayout()
        lbl_g_title = QLabel("GPS DEPLOYMENT MISSION CONTROL")
        lbl_g_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #a371f7;")
        g_top.addWidget(lbl_g_title)
        g_top.addStretch()

        self.lbl_gps_state = QLabel("STATE: IDLE")
        self.lbl_gps_state.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        g_top.addWidget(self.lbl_gps_state)
        g_layout.addLayout(g_top)

        m_row = QHBoxLayout()
        m_row.setSpacing(4)
        lbl_m = QLabel("Mode:")
        lbl_m.setStyleSheet("font-size: 9px; color: #8b949e;")
        m_row.addWidget(lbl_m)
        self.combo_gps_mode = QComboBox()
        self.combo_gps_mode.addItems(["Autonomous (Auto-Release)", "Supervised (Confirm Drop)"])
        self.combo_gps_mode.setStyleSheet("font-size: 9px;")
        self.combo_gps_mode.currentIndexChanged.connect(self._on_gps_mode_changed)
        m_row.addWidget(self.combo_gps_mode)
        g_layout.addLayout(m_row)

        self.lbl_gps_target_info = QLabel("Target: None | Dist: -- m | Bearing: --°")
        self.lbl_gps_target_info.setStyleSheet("font-size: 9px; font-weight: 600; color: #79c0ff; font-family: Consolas, monospace;")
        g_layout.addWidget(self.lbl_gps_target_info)

        gps_btns = QHBoxLayout()
        gps_btns.setSpacing(4)

        self.btn_start_gps_mission = QPushButton("▶ Start Mission")
        self.btn_start_gps_mission.setToolTip("Start autonomous multi-node GPS deployment flight")
        self.btn_start_gps_mission.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: bold; font-size: 9px; padding: 4px 6px;")
        self.btn_start_gps_mission.clicked.connect(self._on_start_gps_mission)
        gps_btns.addWidget(self.btn_start_gps_mission)

        self.btn_pause_gps_mission = QPushButton("⏸ Pause")
        self.btn_pause_gps_mission.setToolTip("Hold position in LOITER over current point")
        self.btn_pause_gps_mission.setStyleSheet("color: #d29922; font-size: 9px; padding: 4px 5px;")
        self.btn_pause_gps_mission.clicked.connect(self._on_pause_gps_mission)
        self.btn_pause_gps_mission.setEnabled(False)
        gps_btns.addWidget(self.btn_pause_gps_mission)

        self.btn_resume_gps_mission = QPushButton("▶ Resume")
        self.btn_resume_gps_mission.setStyleSheet("color: #388bfd; font-size: 9px; padding: 4px 5px;")
        self.btn_resume_gps_mission.clicked.connect(self._on_resume_gps_mission)
        self.btn_resume_gps_mission.setEnabled(False)
        gps_btns.addWidget(self.btn_resume_gps_mission)

        self.btn_abort_gps_mission = QPushButton("⏹ Abort (RTL)")
        self.btn_abort_gps_mission.setStyleSheet("background-color: #b62324; color: #ffffff; font-weight: bold; font-size: 9px; padding: 4px 5px;")
        self.btn_abort_gps_mission.clicked.connect(self._on_abort_gps_mission)
        self.btn_abort_gps_mission.setEnabled(False)
        gps_btns.addWidget(self.btn_abort_gps_mission)

        g_layout.addLayout(gps_btns)

        self.btn_confirm_station_drop = QPushButton("⚡ CONFIRM STATION PAYLOAD RELEASE")
        self.btn_confirm_station_drop.setStyleSheet("""
            QPushButton {
                background-color: #d29922;
                color: #ffffff;
                font-weight: 800;
                font-size: 10px;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e3b341;
            }
        """)
        self.btn_confirm_station_drop.setVisible(False)
        self.btn_confirm_station_drop.clicked.connect(self._on_confirm_station_drop)
        g_layout.addWidget(self.btn_confirm_station_drop)

        layout.addWidget(gps_card)

        # 4. Flight Control Action Buttons
        ctrl_box = QFrame()
        ctrl_box.setProperty("class", "telemetry-card")
        ctrl_layout = QVBoxLayout(ctrl_box)
        ctrl_layout.setContentsMargins(8, 6, 8, 6)
        ctrl_layout.setSpacing(6)

        c_title = QLabel("OPERATIONAL FLIGHT CONTROLS")
        c_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #388bfd;")
        ctrl_layout.addWidget(c_title)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        self.btn_go_target = QPushButton("Go to Target")
        self.btn_go_target.setToolTip("Command UAV in GUIDED mode to fly to deployment target site")
        self.btn_go_target.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-weight: bold; padding: 5px;")
        self.btn_go_target.setEnabled(False)
        self.btn_go_target.clicked.connect(self._on_go_to_target)
        nav_row.addWidget(self.btn_go_target)

        self.btn_loiter_hold = QPushButton("Loiter Hold")
        self.btn_loiter_hold.setToolTip("Switch UAV to LOITER mode to hold position over drop station")
        self.btn_loiter_hold.setStyleSheet("color: #d29922; font-weight: bold; padding: 5px;")
        self.btn_loiter_hold.setEnabled(False)
        self.btn_loiter_hold.clicked.connect(self._on_loiter_hold)
        nav_row.addWidget(self.btn_loiter_hold)

        self.btn_manual = QPushButton("Manual Control")
        self.btn_manual.setToolTip("Revert flight control to STABILIZE mode")
        self.btn_manual.setEnabled(False)
        self.btn_manual.clicked.connect(self._on_manual_control)
        nav_row.addWidget(self.btn_manual)

        ctrl_layout.addLayout(nav_row)

        # 4. Primary Payload Release Button
        self.btn_deploy = QPushButton("DEPLOY VIRTUAL / PHYSICAL NODE")
        self.btn_deploy.setFixedHeight(34)
        self.btn_deploy.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border-radius: 4px;
                border: 1px solid #2ea043;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
            QPushButton:disabled {
                background-color: #21262d;
                color: #484f58;
                border: 1px solid #30363d;
            }
        """)
        self.btn_deploy.setEnabled(False)
        self.btn_deploy.clicked.connect(self.trigger_deployment_sequence)
        ctrl_layout.addWidget(self.btn_deploy)

        layout.addWidget(ctrl_box)

        # 5. Virtual Node Deployment & Telemetry Inspector (Phase 10)
        node_card = QFrame()
        node_card.setProperty("class", "telemetry-card")
        n_layout = QVBoxLayout(node_card)
        n_layout.setContentsMargins(8, 6, 8, 6)
        n_layout.setSpacing(5)

        n_top = QHBoxLayout()
        lbl_node_title = QLabel("NODE DEPLOYMENT")
        lbl_node_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff;")
        n_top.addWidget(lbl_node_title)
        n_top.addStretch()

        self.lbl_vnode_id = QLabel("NODE ID: NODE_001")
        self.lbl_vnode_id.setStyleSheet("font-size: 9px; font-weight: 700; color: #79c0ff; font-family: Consolas, monospace;")
        n_top.addWidget(self.lbl_vnode_id)

        self.lbl_vnode_status = QLabel("STATUS: READY")
        self.lbl_vnode_status.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        n_top.addWidget(self.lbl_vnode_status)
        n_layout.addLayout(n_top)

        # Coordinates & Altitude Target row (Target Lat, Lon, Alt per Phase 10 spec)
        coord_row = QHBoxLayout()
        coord_row.setSpacing(4)

        lbl_lat = QLabel("LAT:")
        lbl_lat.setStyleSheet("font-size: 9px; color: #8b949e;")
        coord_row.addWidget(lbl_lat)
        self.spin_vnode_lat = QDoubleSpinBox()
        self.spin_vnode_lat.setRange(-90.0, 90.0)
        self.spin_vnode_lat.setDecimals(6)
        self.spin_vnode_lat.setValue(37.774900)
        self.spin_vnode_lat.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        coord_row.addWidget(self.spin_vnode_lat)

        lbl_lon = QLabel("LON:")
        lbl_lon.setStyleSheet("font-size: 9px; color: #8b949e;")
        coord_row.addWidget(lbl_lon)
        self.spin_vnode_lon = QDoubleSpinBox()
        self.spin_vnode_lon.setRange(-180.0, 180.0)
        self.spin_vnode_lon.setDecimals(6)
        self.spin_vnode_lon.setValue(-122.419400)
        self.spin_vnode_lon.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        coord_row.addWidget(self.spin_vnode_lon)

        lbl_alt = QLabel("ALT:")
        lbl_alt.setStyleSheet("font-size: 9px; color: #8b949e;")
        coord_row.addWidget(lbl_alt)
        self.spin_vnode_alt = QDoubleSpinBox()
        self.spin_vnode_alt.setRange(0.5, 100.0)
        self.spin_vnode_alt.setValue(4.5)
        self.spin_vnode_alt.setSuffix(" m")
        self.spin_vnode_alt.setFixedWidth(62)
        coord_row.addWidget(self.spin_vnode_alt)
        n_layout.addLayout(coord_row)

        # [DEPLOY NODE] Primary Action Button (per Phase 10 spec)
        self.btn_deploy_vnode = QPushButton("DEPLOY NODE")
        self.btn_deploy_vnode.setFixedHeight(28)
        self.btn_deploy_vnode.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border-radius: 3px;
                border: 1px solid #2ea043;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
        """)
        self.btn_deploy_vnode.clicked.connect(self._on_deploy_vnode_clicked)
        n_layout.addWidget(self.btn_deploy_vnode)

        # Telemetry & Radio Inspector Frame
        self.vnode_vitals_frame = QFrame()
        self.vnode_vitals_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 3px; padding: 4px;")
        vf_layout = QGridLayout(self.vnode_vitals_frame)
        vf_layout.setContentsMargins(4, 2, 4, 2)
        vf_layout.setSpacing(4)

        lbl_b = QLabel("BAND:")
        lbl_b.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_b, 0, 0)
        self.combo_vnode_freq = QComboBox()
        self.combo_vnode_freq.addItems(["2.4 GHz", "5.8 GHz", "915 MHz", "433 MHz"])
        self.combo_vnode_freq.setStyleSheet("font-size: 9px;")
        vf_layout.addWidget(self.combo_vnode_freq, 0, 1)

        lbl_p = QLabel("TX POWER:")
        lbl_p.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_p, 0, 2)
        self.lbl_vnode_pwr = QLabel("20 dBm")
        self.lbl_vnode_pwr.setStyleSheet("font-size: 9px; font-weight: bold; color: #388bfd;")
        vf_layout.addWidget(self.lbl_vnode_pwr, 0, 3)

        lbl_bt = QLabel("BATTERY:")
        lbl_bt.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_bt, 1, 0)
        self.lbl_vnode_bat = QLabel("100%")
        self.lbl_vnode_bat.setStyleSheet("font-size: 9px; font-weight: bold; color: #3fb950;")
        vf_layout.addWidget(self.lbl_vnode_bat, 1, 1)

        lbl_pk = QLabel("PACKETS:")
        lbl_pk.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_pk, 1, 2)
        self.lbl_vnode_pkts = QLabel("TX: 0 | RX: 0")
        self.lbl_vnode_pkts.setStyleSheet("font-size: 9px; font-family: Consolas, monospace; color: #e3b341;")
        vf_layout.addWidget(self.lbl_vnode_pkts, 1, 3)

        lbl_cl = QLabel("CLIENTS:")
        lbl_cl.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_cl, 2, 0)
        self.lbl_vnode_clients = QLabel("0 Connected")
        self.lbl_vnode_clients.setStyleSheet("font-size: 9px; font-weight: bold; color: #58a6ff;")
        vf_layout.addWidget(self.lbl_vnode_clients, 2, 1)

        lbl_cv = QLabel("COVERAGE:")
        lbl_cv.setStyleSheet("font-size: 9px; color: #8b949e;")
        vf_layout.addWidget(lbl_cv, 2, 2)
        self.lbl_vnode_cov = QLabel("250 m")
        self.lbl_vnode_cov.setStyleSheet("font-size: 9px; font-weight: bold; color: #3fb950;")
        vf_layout.addWidget(self.lbl_vnode_cov, 2, 3)

        n_layout.addWidget(self.vnode_vitals_frame)
        layout.addWidget(node_card)

        # 6. Deployed Communication Nodes Registry Table
        table_card = QFrame()
        table_card.setProperty("class", "telemetry-card")
        t_card_layout = QVBoxLayout(table_card)
        t_card_layout.setContentsMargins(8, 6, 8, 6)
        t_card_layout.setSpacing(4)

        reg_row = QHBoxLayout()
        reg_title = QLabel("DEPLOYED COMMUNICATION NODES")
        reg_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #3fb950;")
        reg_row.addWidget(reg_title)

        reg_row.addStretch()

        self.btn_clear_nodes = QPushButton("Clear Nodes")
        self.btn_clear_nodes.setFixedHeight(20)
        self.btn_clear_nodes.setStyleSheet("font-size: 9px; padding: 1px 6px; color: #8b949e;")
        self.btn_clear_nodes.clicked.connect(self._on_clear_nodes)
        reg_row.addWidget(self.btn_clear_nodes)
        t_card_layout.addLayout(reg_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["NODE ID", "LAT", "LON", "ALT (m)", "TIME", "STATUS"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemClicked.connect(self._on_deployed_table_clicked)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d1117;
                border: 1px solid #30363d;
                color: #c9d1d9;
                font-family: Consolas, monospace;
                font-size: 9px;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                font-weight: 600;
                font-size: 9px;
                border: 1px solid #21262d;
                padding: 2px;
            }
        """)
        t_card_layout.addWidget(self.table)
        self.table_nodes = self.table
        layout.addWidget(table_card)

        self.scroll_area.setWidget(container)
        root_layout.addWidget(self.scroll_area)

    def _connect_signals(self):
        app_state.telemetry_updated.connect(self._on_telemetry_updated)
        app_state.connection_changed.connect(self._on_connection_changed)
        app_state.arm_state_changed.connect(self._on_arm_state_changed)
        app_state.deployment_target_updated.connect(self._on_target_updated)
        app_state.deployment_target_cleared.connect(self._on_target_cleared)
        app_state.deployment_state_changed.connect(self._on_deployment_state_changed)
        app_state.deployment_node_added.connect(self._on_node_added)
        app_state.deployed_nodes_cleared.connect(self._on_nodes_cleared)
        app_state.disaster_area_updated.connect(self._on_disaster_area_updated)
        app_state.disaster_area_cleared.connect(self._on_disaster_area_cleared)
        app_state.candidates_generated.connect(self._on_candidates_updated)
        app_state.candidate_selected.connect(self._on_candidate_selected)
        app_state.optimization_completed.connect(self._on_optimization_completed)
        app_state.candidates_cleared.connect(self._on_candidates_cleared)

        # GPS Mission Controller signals (Phase 9)
        gps_mission_controller.mission_state_changed.connect(self._on_gps_mission_state_changed)
        gps_mission_controller.progress_updated.connect(self._on_gps_mission_progress_updated)
        gps_mission_controller.awaiting_confirmation.connect(self._on_gps_mission_awaiting_confirm)
        gps_mission_controller.mission_completed.connect(self._on_gps_mission_completed)

        # Virtual Node Manager signals (Phase 10)
        app_state.virtual_nodes_updated.connect(self._on_virtual_nodes_updated)
        app_state.virtual_node_selected.connect(self._on_virtual_node_selected)
        virtual_node_manager.node_selected.connect(self._on_virtual_node_selected)

    def _update_button_states(self):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        has_tgt = (self._target is not None)
        state = app_state.deployment_state

        self.btn_go_target.setEnabled(is_conn and has_tgt)
        self.btn_loiter_hold.setEnabled(is_conn)
        self.btn_manual.setEnabled(is_conn)

        # Deployment enabled when on station or within acceptance radius
        can_deploy = is_conn and (state == DeploymentState.ON_STATION or state == DeploymentState.NAVIGATING)
        self.btn_deploy.setEnabled(can_deploy)

    def _on_connection_changed(self, status: str):
        self._update_button_states()

    def _on_arm_state_changed(self, arm_state: str):
        self._update_button_states()

    def _on_deployment_state_changed(self, state: str):
        self.lbl_status.setText(f"STATUS: {state}")
        if state == DeploymentState.ON_STATION:
            self.lbl_status.setStyleSheet("background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state == DeploymentState.NAVIGATING:
            self.lbl_status.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state == DeploymentState.DEPLOYED:
            self.lbl_status.setStyleSheet("background-color: #8957e5; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state == DeploymentState.TARGET_SELECTED:
            self.lbl_status.setStyleSheet("background-color: #d29922; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        else:
            self.lbl_status.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")
        self._update_button_states()

    def _on_target_updated(self, tgt):
        if hasattr(tgt, "to_dict"):
            self._target = DeploymentTarget.from_dict(tgt.to_dict())
        elif isinstance(tgt, dict):
            self._target = DeploymentTarget.from_dict(tgt)
        elif isinstance(tgt, DeploymentTarget):
            self._target = tgt
        if not self._target:
            return
        self.spin_lat.setValue(self._target.lat)
        self.spin_lon.setValue(self._target.lon)
        self.spin_alt.setValue(self._target.alt)
        self.spin_radius.setValue(self._target.acceptance_radius_m)
        if app_state.deployment_state == DeploymentState.IDLE:
            app_state.set_deployment_state(DeploymentState.TARGET_SELECTED)
        self._update_button_states()

    def _on_target_cleared(self):
        self._target = None
        self.lbl_dist.setText("Dist: -- m")
        self.lbl_bearing.setText("Bearing: --°")
        self.lbl_eta.setText("ETA: -- s")
        app_state.set_deployment_state(DeploymentState.IDLE)
        self._update_button_states()

    def _on_telemetry_updated(self, data: dict):
        # Always feed telemetry into GPS Mission Controller
        gps_mission_controller.process_telemetry(data)

        if not self._target:
            return

        uav_lat = data.get("lat")
        uav_lon = data.get("lon")
        speed = data.get("groundspeed", 0.0)

        if isinstance(uav_lat, (int, float)) and isinstance(uav_lon, (int, float)):
            dist_m = calculate_ground_distance(uav_lat, uav_lon, self._target.lat, self._target.lon)
            bearing_deg = calculate_bearing(uav_lat, uav_lon, self._target.lat, self._target.lon)

            self.lbl_dist.setText(f"Dist: {dist_m:.1f} m")
            self.lbl_bearing.setText(f"Bearing: {bearing_deg:.0f}°")

            spd = speed if (isinstance(speed, (int, float)) and speed > 0.5) else 12.0
            eta_s = dist_m / spd
            self.lbl_eta.setText(f"ETA: {eta_s:.0f} s")

            # Check if within acceptance radius while navigating
            if dist_m <= self._target.acceptance_radius_m:
                if app_state.deployment_state == DeploymentState.NAVIGATING:
                    app_state.set_deployment_state(DeploymentState.ON_STATION)
                    app_state.set_command_feedback(f"UAV ON STATION OVER TARGET (DIST: {dist_m:.1f}m)")
                    app_state.log("INFO", "DEPLOYMENT", f"UAV reached deployment station. Distance: {dist_m:.1f}m")

    def _on_set_target_clicked(self):
        tgt = DeploymentTarget(
            target_id="TGT-01",
            lat=self.spin_lat.value(),
            lon=self.spin_lon.value(),
            alt=self.spin_alt.value(),
            acceptance_radius_m=self.spin_radius.value()
        )
        app_state.set_deployment_target(tgt.to_dict())
        app_state.set_command_feedback(f"DEPLOYMENT TARGET SET: {tgt.lat:.6f}, {tgt.lon:.6f}")
        app_state.log("INFO", "DEPLOYMENT", f"Target set: {tgt.lat:.6f}, {tgt.lon:.6f}, alt={tgt.alt}m")

    def _on_copy_uav_pos(self):
        lat = app_state.telemetry.get("lat")
        lon = app_state.telemetry.get("lon")
        alt = app_state.telemetry.get("alt_rel", app_state.telemetry.get("alt"))
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            self.spin_lat.setValue(lat)
            self.spin_lon.setValue(lon)
            if isinstance(alt, (int, float)) and alt > 0:
                self.spin_alt.setValue(alt)
            self._on_set_target_clicked()
        else:
            app_state.set_command_feedback("CANNOT COPY UAV POS: NO GPS FIX")

    def _on_pick_on_map(self):
        app_state.set_map_click_mode("SET_DEPLOY_TARGET")

    def _on_clear_target(self):
        app_state.clear_deployment_target()
        app_state.set_command_feedback("DEPLOYMENT TARGET CLEARED")

    def _on_go_to_target(self):
        """Command guided transit to target."""
        if not self._target:
            return
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                # Patch mock vehicle to steer towards target
                self._worker._mock_telemetry_state.update({
                    "mode": "GUIDED",
                    "lat": self._target.lat,
                    "lon": self._target.lon,
                    "alt_rel": self._target.alt
                })
            else:
                commands.send_guided(self._worker._mav)
        app_state.set_deployment_state(DeploymentState.NAVIGATING)
        app_state.set_command_feedback("NAVIGATING TO DEPLOYMENT TARGET")
        app_state.log("INFO", "DEPLOYMENT", f"Navigating to deployment target: {self._target.lat:.6f}, {self._target.lon:.6f}")

    def _on_loiter_hold(self):
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                self._worker._mock_telemetry_state["mode"] = "LOITER"
            else:
                commands.send_loiter(self._worker._mav)
        app_state.set_deployment_state(DeploymentState.ON_STATION)
        app_state.set_command_feedback("STATION HOLD ENGAGED (LOITER)")

    def _on_manual_control(self):
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                self._worker._mock_telemetry_state["mode"] = "STABILIZE"
            else:
                commands.send_manual(self._worker._mav)
        app_state.set_deployment_state(DeploymentState.TARGET_SELECTED if self._target else DeploymentState.IDLE)
        app_state.set_command_feedback("MANUAL CONTROL ENGAGED")

    def _execute_node_deployment(self):
        """Execute node deployment (shared by confirmation trigger & automated tests)."""
        app_state.set_deployment_state(DeploymentState.DEPLOYING)
        app_state.set_command_feedback("DEPLOYING PAYLOAD...")

        self._node_count += 1
        node_id = f"NODE-{self._node_count:02d}"
        target_lat = self._target.lat if self._target else app_state.telemetry.get("lat", 37.7749)
        target_lon = self._target.lon if self._target else app_state.telemetry.get("lon", -122.4194)

        node = DeploymentNode(
            node_id=node_id,
            lat=target_lat,
            lon=target_lon,
            alt=0.0,
            status="ACTIVE",
            coverage_radius_m=250.0
        )
        app_state.add_deployed_node(node)
        app_state.set_deployment_state(DeploymentState.DEPLOYED)
        feedback = f"EMERGENCY NODE DEPLOYED: {node_id} (COV: 250m)"
        app_state.set_command_feedback(feedback)
        app_state.log("INFO", "DEPLOYMENT", f"Emergency Communication Node {node_id} successfully deployed at {target_lat:.6f}, {target_lon:.6f}")
        return node

    def trigger_deployment_sequence(self):
        """Execute the emergency communication node deployment release sequence."""
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog(
            "DEPLOY EMERGENCY RELAY NODE",
            "Confirm emergency payload release? This will deploy an operational communication relay node at the target drop station.",
            parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._execute_node_deployment()

    def _on_node_added(self, node):
        """Append deployed node to registry table and inspect."""
        if hasattr(node, "to_dict"):
            node = node.to_dict()
        row = self.table.rowCount()
        self.table.insertRow(row)

        item_id = QTableWidgetItem(node.get("node_id", "NODE"))
        item_id.setForeground(QColor("#58a6ff"))
        item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, item_id)

        item_lat = QTableWidgetItem(f"{node.get('lat', 0.0):.6f}")
        item_lat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, item_lat)

        item_lon = QTableWidgetItem(f"{node.get('lon', 0.0):.6f}")
        item_lon.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 2, item_lon)

        alt_val = node.get("altitude_m", node.get("alt", 4.5))
        item_alt = QTableWidgetItem(f"{alt_val:.1f}")
        item_alt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 3, item_alt)

        item_time = QTableWidgetItem(node.get("deploy_time", "--"))
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 4, item_time)

        status_text = node.get("status", "ACTIVE")
        item_status = QTableWidgetItem(status_text)
        if status_text in ("DEPLOYED", "ACTIVE"):
            item_status.setForeground(QColor("#3fb950"))
        elif status_text == "READY":
            item_status.setForeground(QColor("#d29922"))
        else:
            item_status.setForeground(QColor("#8b949e"))
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 5, item_status)

        # Inspect recently added node
        self._inspect_node(node)

    def _on_nodes_cleared(self):
        self.table.setRowCount(0)
        self.lbl_vnode_id.setText("NODE ID: NODE_001")
        self.lbl_vnode_status.setText("STATUS: READY")
        self.lbl_vnode_status.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")
        self.lbl_vnode_pkts.setText("TX: 0 | RX: 0")
        self.lbl_vnode_clients.setText("0 Connected")

    def _on_clear_nodes(self):
        app_state.clear_deployed_nodes()
        virtual_node_manager.clear()
        app_state.set_command_feedback("CLEARED DEPLOYED NODES")

    def _on_deploy_vnode_clicked(self):
        """Deploy virtual communication node directly from inspector panel."""
        lat = self.spin_vnode_lat.value()
        lon = self.spin_vnode_lon.value()
        alt = self.spin_vnode_alt.value()
        freq = self.combo_vnode_freq.currentText()

        vnode = virtual_node_manager.deploy_node(
            lat=lat,
            lon=lon,
            altitude_m=alt,
            frequency_band=freq,
            tx_power_dbm=20.0,
            mission_id=getattr(app_state, "current_mission_id", "MANUAL_DEPLOY"),
            coverage_radius_m=250.0
        )
        self._inspect_node(vnode.to_dict())
        app_state.set_command_feedback(f"NODE DEPLOYED: {vnode.node_id} (ALT: {vnode.altitude_m}m, BAND: {freq})")
        app_state.log("INFO", "DEPLOYMENT", f"Virtual node {vnode.node_id} deployed at {lat:.6f}, {lon:.6f}, alt {alt:.1f}m")

    def _on_deployed_table_clicked(self, item):
        row = item.row()
        item_id = self.table.item(row, 0)
        if item_id:
            node_id = item_id.text()
            app_state.select_virtual_node(node_id)

    def _on_virtual_node_selected(self, node):
        if not node:
            return
        node_dict = node.to_dict() if hasattr(node, "to_dict") else node
        self._inspect_node(node_dict)

        # Highlight in table
        target_id = node_dict.get("node_id", "")
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it and it.text() == target_id:
                self.table.selectRow(row)
                break

    def _on_virtual_nodes_updated(self, nodes):
        # Update ready ID placeholder if empty
        if not nodes:
            self.lbl_vnode_id.setText("NODE ID: NODE_001")
            self.lbl_vnode_status.setText("STATUS: READY")
            self.lbl_vnode_status.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")

    def _inspect_node(self, node: dict):
        """Populate Phase 10 Telemetry & Radio Inspector with node details."""
        node_id = node.get("node_id", "NODE_001")
        status = node.get("status", "DEPLOYED")
        lat = float(node.get("lat", 0.0))
        lon = float(node.get("lon", 0.0))
        alt = float(node.get("altitude_m", node.get("alt", 4.5)))
        freq = node.get("frequency_band", "2.4 GHz")
        pwr = float(node.get("tx_power_dbm", 20.0))
        bat = float(node.get("battery_pct", 100.0))
        tx = node.get("packets_tx", 0)
        rx = node.get("packets_rx", 0)
        clients = node.get("connected_clients", 0)
        cov = float(node.get("coverage_radius_m", 250.0))

        self.lbl_vnode_id.setText(f"NODE ID: {node_id}")
        self.lbl_vnode_status.setText(f"STATUS: {status}")
        if status in ("DEPLOYED", "ACTIVE"):
            self.lbl_vnode_status.setStyleSheet("background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif status == "READY":
            self.lbl_vnode_status.setStyleSheet("background-color: #d29922; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        else:
            self.lbl_vnode_status.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")

        self.spin_vnode_lat.setValue(lat)
        self.spin_vnode_lon.setValue(lon)
        self.spin_vnode_alt.setValue(alt)

        # Combo box frequency band
        idx = self.combo_vnode_freq.findText(freq)
        if idx >= 0:
            self.combo_vnode_freq.setCurrentIndex(idx)

        self.lbl_vnode_pwr.setText(f"{pwr:.0f} dBm")
        self.lbl_vnode_bat.setText(f"{bat:.0f}%")
        self.lbl_vnode_pkts.setText(f"TX: {tx} | RX: {rx}")
        self.lbl_vnode_clients.setText(f"{clients} Connected")
        self.lbl_vnode_cov.setText(f"{cov:.0f} m")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 7: Disaster Area Planning Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _on_preset_selected(self, index: int):
        if index <= 0:
            return
        preset_name = self.combo_area_preset.currentText()
        if preset_name in self._presets:
            preset = self._presets[preset_name]
            app_state.set_disaster_area(preset)
            app_state.set_hazard_zones(preset.hazard_zones)
            app_state.set_command_feedback(f"LOADED DISASTER SCENARIO: {preset.name}")

    def _on_draw_area_clicked(self):
        app_state.start_area_drawing()

    def _on_clear_area_clicked(self):
        app_state.clear_disaster_area()
        app_state.clear_hazard_zones()
        self.combo_area_preset.setCurrentIndex(0)
        app_state.set_command_feedback("CLEARED DISASTER AREA")

    def _on_disaster_area_updated(self, area_data):
        if not area_data:
            return
        data = area_data.to_dict() if hasattr(area_data, "to_dict") else area_data
        name = data.get("name", "Defined Area")
        sq_km = data.get("area_sq_km", 0.0)
        ha = data.get("area_hectares", 0.0)
        perim_km = data.get("perimeter_km", 0.0)
        n_verts = len(data.get("vertices", []))
        n_hazards = len(data.get("hazard_zones", []))

        self.lbl_area_name.setText(name)
        self.lbl_area_metrics.setText(f"Area: {sq_km:.2f} km² ({ha:.1f} ha) | Perim: {perim_km:.2f} km | Vertices: {n_verts} | Hazards: {n_hazards}")

    def _on_disaster_area_cleared(self):
        self.lbl_area_name.setText("NO AREA DEFINED")
        self.lbl_area_metrics.setText("Area: -- km² | Perimeter: -- km | Vertices: 0")

    def _on_export_geojson(self):
        from gcs.disaster.disaster_manager import DisasterArea
        if not app_state.disaster_area:
            app_state.set_command_feedback("NO DISASTER AREA TO EXPORT")
            return
        area = app_state.disaster_area
        if isinstance(area, dict):
            area = DisasterArea.from_dict(area)
        path, _ = QFileDialog.getSaveFileName(self, "Export Disaster Area GeoJSON", "disaster_area.geojson", "GeoJSON Files (*.geojson *.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(area.to_geojson(), f, indent=2)
            app_state.log("INFO", "DISASTER", f"Exported GeoJSON to {os.path.basename(path)}")
            app_state.set_command_feedback(f"EXPORTED GEOJSON: {os.path.basename(path)}")

    def _on_import_geojson(self):
        from gcs.disaster.disaster_manager import DisasterArea
        path, _ = QFileDialog.getOpenFileName(self, "Import Disaster Area GeoJSON", "", "GeoJSON Files (*.geojson *.json)")
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                area = DisasterArea.from_geojson(data)
                app_state.set_disaster_area(area)
                app_state.set_hazard_zones(area.hazard_zones)
                app_state.log("INFO", "DISASTER", f"Imported GeoJSON from {os.path.basename(path)}")
                app_state.set_command_feedback(f"IMPORTED GEOJSON: {area.name}")
            except Exception as e:
                app_state.set_command_feedback(f"GEOJSON IMPORT ERROR: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 8: Deployment Algorithm & Candidate Methods
    # ──────────────────────────────────────────────────────────────────────────
    def _on_optimize_clicked(self):
        if not app_state.disaster_area:
            app_state.set_command_feedback("ERROR: DEFINE OR LOAD DISASTER AREA FIRST")
            return
        from gcs.deployment.coverage_optimizer import (
            OptimizationConfig,
            generate_candidate_grid, optimize_placement
        )
        cfg = OptimizationConfig(
            num_nodes=self.spin_num_nodes.value(),
            coverage_radius_m=self.spin_rf_radius.value(),
            grid_resolution_m=self.spin_grid_res.value(),
        )
        candidates = generate_candidate_grid(
            app_state.disaster_area,
            grid_resolution_m=cfg.grid_resolution_m,
            hazard_zones=app_state.hazard_zones,
        )
        result = optimize_placement(candidates, app_state.disaster_area, cfg, app_state.hazard_zones)
        app_state.set_optimization_result(result)
        if result.selected_candidates:
            app_state.select_candidate(result.selected_candidates[0])

    def _on_generate_candidates_clicked(self):
        if not app_state.disaster_area:
            app_state.set_command_feedback("ERROR: DEFINE OR LOAD DISASTER AREA FIRST")
            return
        from gcs.deployment.coverage_optimizer import generate_candidate_grid
        cands = generate_candidate_grid(
            app_state.disaster_area,
            grid_resolution_m=self.spin_grid_res.value(),
            hazard_zones=app_state.hazard_zones,
        )
        app_state.set_candidates(cands)

    def _on_clear_candidates_clicked(self):
        app_state.clear_candidates()

    def _on_generate_mission_clicked(self):
        selected = [c for c in app_state.candidates if getattr(c, "is_selected", False)] if app_state.candidates else []
        if not selected and app_state.optimization_result:
            selected = app_state.optimization_result.selected_candidates
        if not selected:
            app_state.set_command_feedback("ERROR: NO OPTIMAL SITES SELECTED TO GENERATE MISSION")
            return
        from gcs.deployment.coverage_optimizer import generate_deployment_mission
        home_lat = 37.7749
        home_lon = -122.4194
        if isinstance(app_state.telemetry.get("lat"), (int, float)):
            home_lat = float(app_state.telemetry["lat"])
            home_lon = float(app_state.telemetry["lon"])
        mission_items = generate_deployment_mission(selected, home_lat, home_lon, cruise_alt_m=self.spin_alt.value())
        app_state.set_mission_waypoints(mission_items)
        gps_mission_controller.load_from_candidates(selected, drop_alt_m=self.spin_alt.value())
        app_state.set_command_feedback(f"MISSION GENERATED: {len(mission_items)} WAYS (TAKEOFF -> {len(selected)} DROPS -> RTL)")
        parent = self.parent()
        while parent:
            if hasattr(parent, "tabs"):
                parent.tabs.setCurrentIndex(2)  # Switch to MISSION tab
                break
            parent = parent.parent()

    def _on_candidate_table_clicked(self, item):
        row = item.row()
        cid_item = self.table_candidates.item(row, 1)
        if cid_item:
            cid = cid_item.text()
            app_state.select_candidate(cid)

    def _on_candidate_selected(self, cand_dict):
        if not cand_dict:
            return
        lat = cand_dict.get("lat", 0.0)
        lon = cand_dict.get("lon", 0.0)
        alt = cand_dict.get("alt", 25.0)
        self.spin_lat.setValue(lat)
        self.spin_lon.setValue(lon)
        self.spin_alt.setValue(alt)
        cid = cand_dict.get("candidate_id", "")
        for row in range(self.table_candidates.rowCount()):
            item = self.table_candidates.item(row, 1)
            if item and item.text() == cid:
                self.table_candidates.selectRow(row)
                break
        self._on_set_target_clicked()

    def _on_candidates_updated(self, candidates_list):
        self.lbl_algo_status.setText(f"{len(candidates_list)} CANDIDATES")
        self.table_candidates.setRowCount(len(candidates_list))
        for row, c in enumerate(candidates_list):
            is_sel = c.get("is_selected", False)
            cid = c.get("candidate_id", f"C-{row+1:02d}")
            lat = c.get("lat", 0.0)
            lon = c.get("lon", 0.0)
            cov = c.get("coverage_ratio", 0.0) * 100.0

            item_sel = QTableWidgetItem("[X]" if is_sel else "[ ]")
            item_sel.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_sel:
                item_sel.setForeground(QColor("#3fb950"))
            self.table_candidates.setItem(row, 0, item_sel)

            item_id = QTableWidgetItem(cid)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_sel:
                item_id.setForeground(QColor("#58a6ff"))
            self.table_candidates.setItem(row, 1, item_id)

            self.table_candidates.setItem(row, 2, QTableWidgetItem(f"{lat:.6f}"))
            self.table_candidates.setItem(row, 3, QTableWidgetItem(f"{lon:.6f}"))
            self.table_candidates.setItem(row, 4, QTableWidgetItem(f"{cov:.1f}%"))

            status_text = "SELECTED" if is_sel else "AVAILABLE"
            item_st = QTableWidgetItem(status_text)
            item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_sel:
                item_st.setForeground(QColor("#3fb950"))
            else:
                item_st.setForeground(QColor("#8b949e"))
            self.table_candidates.setItem(row, 5, item_st)

    def _on_optimization_completed(self, result_dict):
        if not result_dict:
            return
        cov_pct = result_dict.get("coverage_percent", 0.0)
        cov_m2 = result_dict.get("covered_area_m2", 0.0)
        cov_km2 = cov_m2 / 1e6
        overlap = result_dict.get("overlap_percent", 0.0)
        mesh_ok = result_dict.get("mesh_connectivity_ok", True)
        mesh_str = "CONNECTED" if mesh_ok else "ISOLATED"
        sel_cnt = result_dict.get("selected_count", 0)

        cands = result_dict.get("candidates", [])
        if cands:
            self._on_candidates_updated(cands)

        self.lbl_algo_status.setText(f"{sel_cnt} NODES OPTIMIZED")
        self.lbl_opt_metrics.setText(f"Coverage: {cov_pct:.1f}% ({cov_km2:.2f} km²) | Overlap: {overlap:.1f}% | Mesh: {mesh_str}")

    def _on_candidates_cleared(self):
        self.lbl_algo_status.setText("NO CANDIDATES")
        self.lbl_opt_metrics.setText("Coverage: --% (-- km²) | Overlap: --% | Mesh: --")
        self.table_candidates.setRowCount(0)

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 9: GPS Deployment Mission Action Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _on_gps_mode_changed(self, index: int):
        is_auto = (index == 0)
        gps_mission_controller.config.auto_release = is_auto
        mode_str = "AUTONOMOUS AUTO-RELEASE" if is_auto else "SUPERVISED OPERATOR CONFIRM"
        app_state.set_command_feedback(f"GPS MISSION MODE: {mode_str}")

    def _on_start_gps_mission(self):
        """Start autonomous multi-node GPS deployment flight."""
        if not gps_mission_controller.targets:
            # Check if candidates exist in app_state
            if app_state.candidates:
                selected = [c for c in app_state.candidates if (c.is_selected if hasattr(c, "is_selected") else c.get("is_selected", False))]
                if not selected:
                    selected = app_state.candidates[:3]
                gps_mission_controller.load_from_candidates(selected, drop_alt_m=self.spin_alt.value())
            elif app_state.mission_waypoints:
                gps_mission_controller.load_from_waypoints(app_state.mission_waypoints, drop_alt_m=self.spin_alt.value())
            else:
                app_state.set_command_feedback("NO TARGETS: Generate candidates or plan mission first!")
                return

        started = gps_mission_controller.start_mission()
        if started:
            self.btn_start_gps_mission.setEnabled(False)
            self.btn_pause_gps_mission.setEnabled(True)
            self.btn_resume_gps_mission.setEnabled(False)
            self.btn_abort_gps_mission.setEnabled(True)

    def _on_pause_gps_mission(self):
        gps_mission_controller.pause_mission()
        self.btn_pause_gps_mission.setEnabled(False)
        self.btn_resume_gps_mission.setEnabled(True)

    def _on_resume_gps_mission(self):
        gps_mission_controller.resume_mission()
        self.btn_pause_gps_mission.setEnabled(True)
        self.btn_resume_gps_mission.setEnabled(False)

    def _on_abort_gps_mission(self):
        gps_mission_controller.abort_mission()
        self.btn_start_gps_mission.setEnabled(True)
        self.btn_pause_gps_mission.setEnabled(False)
        self.btn_resume_gps_mission.setEnabled(False)
        self.btn_abort_gps_mission.setEnabled(False)
        self.btn_confirm_station_drop.setVisible(False)

    def _on_confirm_station_drop(self):
        self.btn_confirm_station_drop.setVisible(False)
        gps_mission_controller.trigger_payload_release()

    def _on_gps_mission_state_changed(self, state: str):
        self.lbl_gps_state.setText(f"STATE: {state}")
        if state in ("TRANSITING", "ARMING", "TAKEOFF"):
            self.lbl_gps_state.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state in ("ON_STATION", "RELEASING"):
            self.lbl_gps_state.setStyleSheet("background-color: #d29922; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state in ("NODE_DEPLOYED", "COMPLETED"):
            self.lbl_gps_state.setStyleSheet("background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state == "PAUSED":
            self.lbl_gps_state.setStyleSheet("background-color: #9e6a03; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        elif state == "ABORTED":
            self.lbl_gps_state.setStyleSheet("background-color: #b62324; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        else:
            self.lbl_gps_state.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")

    def _on_gps_mission_progress_updated(self, progress: dict):
        tid = progress.get("target_id", "--")
        cid = progress.get("candidate_id", "")
        t_idx = progress.get("target_index", 0) + 1
        t_tot = progress.get("total_targets", 0)
        dist = progress.get("distance_m", 0.0)
        brg = progress.get("bearing_deg", 0.0)
        display_name = f"{tid} ({cid})" if cid else tid
        self.lbl_gps_target_info.setText(f"Target: {display_name} [{t_idx}/{t_tot}] | Dist: {dist:.1f}m | Brg: {brg:.0f}°")

    def _on_gps_mission_awaiting_confirm(self, target_id: str):
        self.btn_confirm_station_drop.setText(f"⚡ RELEASE PAYLOAD AT {target_id}")
        self.btn_confirm_station_drop.setVisible(True)

    def _on_gps_mission_completed(self, msg: str):
        self.btn_start_gps_mission.setEnabled(True)
        self.btn_pause_gps_mission.setEnabled(False)
        self.btn_resume_gps_mission.setEnabled(False)
        self.btn_abort_gps_mission.setEnabled(False)
        self.btn_confirm_station_drop.setVisible(False)


