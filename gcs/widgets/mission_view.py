"""Mission Planner View for Right Context Panel.

Provides:
- Interactive Waypoint Table with Add, Delete, Up, Down, Clear operations
- Live mission metrics summary (Total waypoints, total distance km, estimated flight time)
- Seamless synchronization with MapView via AppState signals
- Direct map-click coordinate placement handler
- MAVLink Mission upload and download actions
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QFrame,
    QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from gcs.state.app_state import app_state, ConnectionState
from gcs.mavlink.mission_manager import (
    MissionPlan,
    Waypoint,
    MAV_CMD_NAV_WAYPOINT,
    MAV_CMD_NAV_TAKEOFF,
    MAV_CMD_NAV_LAND,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    COMMAND_NAMES,
    NAME_TO_COMMAND,
)


class MissionView(QWidget):
    """Functional Mission Planner tab interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("missionView")
        self._worker = None
        self._plan = MissionPlan()
        self._is_syncing = False

        self._init_ui()
        self._connect_signals()

    def set_worker(self, worker):
        """Set MAVLink worker instance for upload/download."""
        self._worker = worker
        self._update_button_states()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Mission Header Card & Metrics
        header_card = QFrame()
        header_card.setProperty("class", "telemetry-card")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel("MISSION PLANNER")
        title.setStyleSheet("font-weight: 700; color: #58a6ff; font-size: 11px;")
        top_row.addWidget(title)

        top_row.addStretch()

        self.lbl_status = QLabel("IDLE")
        self.lbl_status.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        top_row.addWidget(self.lbl_status)
        h_layout.addLayout(top_row)

        # Metrics readouts
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)

        self.lbl_count = QLabel("WPs: 0")
        self.lbl_count.setStyleSheet("font-size: 10px; font-weight: 600; color: #f0f6fc;")
        metrics_row.addWidget(self.lbl_count)

        self.lbl_dist = QLabel("Dist: 0.00 km")
        self.lbl_dist.setStyleSheet("font-size: 10px; font-weight: 600; color: #d29922;")
        metrics_row.addWidget(self.lbl_dist)

        self.lbl_eta = QLabel("Est Time: 00:00")
        self.lbl_eta.setStyleSheet("font-size: 10px; font-weight: 600; color: #3fb950;")
        metrics_row.addWidget(self.lbl_eta)

        metrics_row.addStretch()
        h_layout.addLayout(metrics_row)
        layout.addWidget(header_card)

        # 2. Waypoint Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "COMMAND", "LAT", "LON", "ALT (m)", "HOLD (s)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d1117;
                border: 1px solid #30363d;
                gridline-color: #21262d;
                color: #c9d1d9;
                font-family: Consolas, monospace;
                font-size: 10px;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                font-weight: 600;
                font-size: 9px;
                border: 1px solid #21262d;
                padding: 3px;
            }
            QTableWidget::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
        """)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)

        # 3. Table Editing Toolbar (Row 1)
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.btn_add = QPushButton("+ Add")
        self.btn_add.setToolTip("Add new waypoint at vehicle position or default offset")
        self.btn_add.setStyleSheet("font-weight: 600; color: #58a6ff;")
        self.btn_add.clicked.connect(self._on_add_clicked)
        row1.addWidget(self.btn_add)

        self.btn_del = QPushButton("- Delete")
        self.btn_del.setToolTip("Delete selected waypoint")
        self.btn_del.setStyleSheet("color: #f85149;")
        self.btn_del.clicked.connect(self._on_delete_clicked)
        row1.addWidget(self.btn_del)

        self.btn_up = QPushButton("▲ Up")
        self.btn_up.setToolTip("Move selected waypoint earlier")
        self.btn_up.clicked.connect(self._on_move_up_clicked)
        row1.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ Down")
        self.btn_down.setToolTip("Move selected waypoint later")
        self.btn_down.clicked.connect(self._on_move_down_clicked)
        row1.addWidget(self.btn_down)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setToolTip("Clear all waypoints from mission")
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        row1.addWidget(self.btn_clear)

        layout.addLayout(row1)

        # 4. Action & Transfer Toolbar (Row 2)
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self.btn_click_mode = QPushButton("Click Map: OFF")
        self.btn_click_mode.setToolTip("Toggle click on tactical map to add waypoints directly")
        self.btn_click_mode.setStyleSheet("font-weight: 600; color: #d29922;")
        self.btn_click_mode.clicked.connect(self._on_toggle_map_click)
        row2.addWidget(self.btn_click_mode)

        self.btn_upload = QPushButton("Upload")
        self.btn_upload.setToolTip("Upload mission to UAV via MAVLink")
        self.btn_upload.setStyleSheet("font-weight: 600; color: #3fb950;")
        self.btn_upload.setEnabled(False)
        self.btn_upload.clicked.connect(self.upload_mission)
        row2.addWidget(self.btn_upload)

        self.btn_download = QPushButton("Download")
        self.btn_download.setToolTip("Download mission from UAV via MAVLink")
        self.btn_download.setStyleSheet("font-weight: 600; color: #a371f7;")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.download_mission)
        row2.addWidget(self.btn_download)

        layout.addLayout(row2)

    def _connect_signals(self):
        app_state.connection_changed.connect(self._on_connection_changed)
        app_state.mission_updated.connect(self._on_external_mission_updated)
        app_state.mission_current_changed.connect(self._on_mission_current_changed)
        app_state.map_click_mode_changed.connect(self._on_map_click_mode_changed)
        app_state.waypoint_added_from_map.connect(self.add_waypoint_coords)

    def _update_button_states(self):
        is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
        has_wps = len(self._plan.waypoints) > 0
        self.btn_upload.setEnabled(is_conn and has_wps)
        self.btn_download.setEnabled(is_conn)

    def _on_connection_changed(self, status: str):
        self._update_button_states()

    def _on_map_click_mode_changed(self, mode: str):
        if mode == "ADD_WAYPOINT":
            self.btn_click_mode.setText("Click Map: ON")
            self.btn_click_mode.setStyleSheet("background-color: #d29922; color: #ffffff; font-weight: bold;")
        else:
            self.btn_click_mode.setText("Click Map: OFF")
            self.btn_click_mode.setStyleSheet("background-color: #21262d; color: #d29922; font-weight: 600;")

    def _on_toggle_map_click(self):
        new_mode = "NAV" if app_state.map_click_mode == "ADD_WAYPOINT" else "ADD_WAYPOINT"
        app_state.set_map_click_mode(new_mode)

    def _on_add_clicked(self):
        """Append a waypoint defaulting to near UAV or disaster center."""
        lat = app_state.telemetry.get("lat")
        lon = app_state.telemetry.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            lat = app_state.home_lat
            lon = app_state.home_lon

        # Offset slightly if waypoints already exist
        offset = len(self._plan.waypoints) * 0.001
        new_lat = lat + (offset if offset != 0 else 0.0008)
        new_lon = lon + (offset if offset != 0 else 0.0008)

        self.add_waypoint_coords(new_lat, new_lon, alt=25.0)

    def add_waypoint_coords(self, lat: float, lon: float, alt: float = 25.0, command: int = MAV_CMD_NAV_WAYPOINT):
        """Add a waypoint at given coordinates and refresh table & map."""
        wp = self._plan.add_waypoint(lat=lat, lon=lon, alt=alt, command=command)
        self._sync_plan_to_table()
        self._broadcast_mission()
        app_state.log("INFO", "MISSION", f"Added Waypoint #{wp.seq} at {lat:.6f}, {lon:.6f} alt={alt:.1f}m")

    def _on_delete_clicked(self):
        row = self.table.currentRow()
        if row >= 0 and row < len(self._plan.waypoints):
            removed = self._plan.remove_waypoint(row)
            self._sync_plan_to_table()
            self._broadcast_mission()
            if removed:
                app_state.log("INFO", "MISSION", f"Deleted Waypoint #{removed.seq}")

    def _on_move_up_clicked(self):
        row = self.table.currentRow()
        if row > 0:
            self._plan.move_waypoint(row, row - 1)
            self._sync_plan_to_table()
            self.table.selectRow(row - 1)
            self._broadcast_mission()

    def _on_move_down_clicked(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._plan.waypoints) - 1:
            self._plan.move_waypoint(row, row + 1)
            self._sync_plan_to_table()
            self.table.selectRow(row + 1)
            self._broadcast_mission()

    def _on_clear_clicked(self):
        if not self._plan.waypoints:
            return
        self._plan.clear()
        self._sync_plan_to_table()
        self._broadcast_mission()
        app_state.set_mission_status("IDLE")
        app_state.log("INFO", "MISSION", "Cleared mission waypoints")

    def _on_cell_changed(self, row: int, col: int):
        if self._is_syncing:
            return
        if 0 <= row < len(self._plan.waypoints):
            wp = self._plan.waypoints[row]
            item = self.table.item(row, col)
            if not item:
                return
            val_text = item.text().strip()
            try:
                if col == 1:  # Command
                    wp.command = NAME_TO_COMMAND.get(val_text.upper(), MAV_CMD_NAV_WAYPOINT)
                elif col == 2:  # Lat
                    wp.lat = float(val_text)
                elif col == 3:  # Lon
                    wp.lon = float(val_text)
                elif col == 4:  # Alt
                    wp.alt = float(val_text)
                elif col == 5:  # Hold
                    wp.param1 = float(val_text)
            except ValueError:
                pass
            self._update_metrics()
            self._broadcast_mission()

    def _sync_plan_to_table(self):
        """Populate the table with current MissionPlan waypoints."""
        self._is_syncing = True
        self.table.setRowCount(len(self._plan.waypoints))
        for row, wp in enumerate(self._plan.waypoints):
            # #
            item_seq = QTableWidgetItem(str(wp.seq))
            item_seq.setFlags(item_seq.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_seq)

            # COMMAND
            item_cmd = QTableWidgetItem(wp.command_name)
            item_cmd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item_cmd)

            # LAT
            item_lat = QTableWidgetItem(f"{wp.lat:.6f}")
            item_lat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_lat)

            # LON
            item_lon = QTableWidgetItem(f"{wp.lon:.6f}")
            item_lon.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item_lon)

            # ALT
            item_alt = QTableWidgetItem(f"{wp.alt:.1f}")
            item_alt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_alt)

            # HOLD
            item_hold = QTableWidgetItem(f"{wp.param1:.1f}")
            item_hold.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, item_hold)

        self._is_syncing = False
        self._update_metrics()
        self._update_button_states()

    def _update_metrics(self):
        count = len(self._plan.waypoints)
        dist_m = self._plan.calculate_total_distance()
        eta_s = self._plan.calculate_eta_seconds(cruise_speed_mps=12.0)

        self.lbl_count.setText(f"WPs: {count}")
        self.lbl_dist.setText(f"Dist: {dist_m / 1000.0:.2f} km")

        mins = int(eta_s // 60)
        secs = int(eta_s % 60)
        self.lbl_eta.setText(f"Est Time: {mins:02d}:{secs:02d}")

        if count > 0:
            self.lbl_status.setText(f"PLANNING ({count} WPs)")
            self.lbl_status.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
        else:
            self.lbl_status.setText("IDLE")
            self.lbl_status.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")

    def _broadcast_mission(self):
        """Emit mission updated signal to app_state for MapView."""
        app_state.set_mission_waypoints(self._plan.to_list_of_dicts())

    def _on_external_mission_updated(self, waypoints: list):
        """Handle mission loaded from file or downloaded from vehicle."""
        # Only rebuild if different from local plan to avoid loop
        if len(waypoints) != len(self._plan.waypoints):
            self._plan = MissionPlan([Waypoint.from_dict(d) for d in waypoints])
            self._sync_plan_to_table()

    def _on_mission_current_changed(self, seq: int):
        """Highlight active waypoint row in the table."""
        for r in range(self.table.rowCount()):
            is_active = (r + 1 == seq)
            bg = QColor("#1b4729") if is_active else QColor("#0d1117")
            fg = QColor("#3fb950") if is_active else QColor("#c9d1d9")
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setBackground(bg)
                    item.setForeground(fg)

    def load_plan(self, plan: MissionPlan):
        """Set plan from loaded file and refresh."""
        self._plan = plan
        self._sync_plan_to_table()
        self._broadcast_mission()
        app_state.set_mission_status("LOADED")

    def get_plan(self) -> MissionPlan:
        return self._plan

    def upload_mission(self):
        """Send mission to vehicle via worker."""
        if not self._plan.waypoints:
            app_state.set_command_feedback("CANNOT UPLOAD: EMPTY MISSION")
            return
        if self._worker:
            app_state.set_mission_status("UPLOADING")
            self.lbl_status.setText("UPLOADING...")
            self.lbl_status.setStyleSheet("background-color: #d29922; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
            self._worker.upload_mission(self._plan.waypoints)
        else:
            app_state.set_command_feedback("UPLOAD FAILED: NO ACTIVE WORKER")

    def download_mission(self):
        """Download mission from vehicle via worker."""
        if self._worker:
            app_state.set_mission_status("DOWNLOADING")
            self.lbl_status.setText("DOWNLOADING...")
            self.lbl_status.setStyleSheet("background-color: #a371f7; color: #ffffff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;")
            self._worker.download_mission()
        else:
            app_state.set_command_feedback("DOWNLOAD FAILED: NO ACTIVE WORKER")
