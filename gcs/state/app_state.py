"""Central Application State and Signal Bus for UAV GCS.

Maintains operational state, telemetry, connection status, log messages, and map state.
Phase 3 addition: flight_phase state machine, arm_state_changed signal.
"""

from datetime import datetime
from PySide6.QtCore import QObject, Signal


class ConnectionState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    CONNECTION_LOST = "CONNECTION LOST"


class SafetyState:
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FlightState:
    DISARMED = "DISARMED"
    ARMED = "ARMED"
    TAKING_OFF = "TAKING OFF"
    FLYING = "FLYING"
    LOITERING = "LOITERING"
    MANUAL = "MANUAL"
    DEPLOYMENT_READY = "DEPLOYMENT READY"
    DEPLOYED = "DEPLOYED"
    SURVEYING = "SURVEYING"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    ERROR = "ERROR"


class FlightPhase:
    """High-level operational phase of the UAV."""
    GROUNDED = "GROUNDED"
    ARMED = "ARMED"
    AIRBORNE = "AIRBORNE"
    RETURNING = "RETURNING"
    LANDED = "LANDED"


class AppState(QObject):
    """Central state container and Qt signal dispatcher."""

    # Signals
    connection_changed = Signal(str)
    flight_mode_changed = Signal(str)
    arm_state_changed = Signal(str)       # "ARMED" or "DISARMED"
    safety_changed = Signal(str)
    telemetry_updated = Signal(dict)
    log_event = Signal(str, str, str, str)  # timestamp, severity, category, message
    command_feedback = Signal(str)
    map_follow_toggled = Signal(bool)
    map_clear_track = Signal()
    map_click_mode_changed = Signal(str)
    waypoint_added_from_map = Signal(float, float)

    # Mission signals
    mission_updated = Signal(list)            # List of Waypoint dicts
    mission_current_changed = Signal(int)     # Active waypoint sequence number (1-based)
    mission_status_changed = Signal(str)      # "IDLE", "EDITING", "UPLOADING", "RUNNING", etc.

    # Deployment signals
    deployment_state_changed = Signal(str)
    deployment_target_updated = Signal(object)
    deployment_target_cleared = Signal()
    deployment_node_added = Signal(object)
    deployed_nodes_cleared = Signal()

    # Disaster area signals (Phase 7)
    disaster_area_updated = Signal(object)
    disaster_area_cleared = Signal()
    hazard_zones_updated = Signal(list)
    area_drawing_mode_changed = Signal(bool)

    # Deployment Algorithm signals (Phase 8)
    candidates_generated = Signal(list)
    candidate_selected = Signal(object)
    optimization_completed = Signal(object)
    candidates_cleared = Signal()

    # GPS Deployment Mission signals (Phase 9)
    gps_mission_state_changed = Signal(str)
    gps_mission_progress_updated = Signal(dict)
    gps_mission_node_deployed = Signal(object)

    # Virtual Node signals (Phase 10)
    virtual_nodes_updated = Signal(list)
    virtual_node_selected = Signal(object)

    # RF Simulation signals (Phase 11)
    rf_config_changed = Signal(object)
    rf_coverage_calculated = Signal(object)
    rf_uav_link_updated = Signal(object)

    # RF Survey signals (Phase 12)
    survey_plan_generated = Signal(object)
    survey_state_changed = Signal(str)
    survey_progress_updated = Signal(object)
    survey_sample_acquired = Signal(object)
    survey_completed = Signal(object)
    survey_cleared = Signal()

    # RSSI Heatmap signals (Phase 13)
    rssi_heatmap_generated = Signal(object)
    rf_analysis_updated = Signal(object)
    rssi_heatmap_cleared = Signal()

    # Coverage Gap signals (Phase 14)
    coverage_analysis_completed = Signal(object)
    gaps_updated = Signal(object)
    gaps_cleared = Signal()

    # Adaptive Deployment signals (Phase 15)
    adaptive_plan_generated = Signal(object)   # AdaptiveDeploymentPlan
    adaptive_plan_updated = Signal(object)     # plan after advance/skip
    adaptive_plan_cleared = Signal()

    # Phase 16: Backend FastAPI Integration
    backend_connection_changed = Signal(bool)  # True if backend server reachable
    backend_analysis_updated = Signal(dict)    # backend REST analysis result
    backend_candidates_updated = Signal(dict)   # backend REST candidates result

    def __init__(self):
        super().__init__()

        # Phase 16: Backend FastAPI Integration
        self.backend_connected = False
        self.backend_url = "http://localhost:8000"
        self.last_backend_status = None



        # Connection & System info
        self.connection_status = ConnectionState.DISCONNECTED
        self.vehicle_type = "--"
        self.system_id = "--"
        self.flight_mode = "--"
        self.arm_state = FlightState.DISARMED
        self.flight_phase = FlightPhase.GROUNDED
        self.safety_status = SafetyState.NORMAL

        # GPS & Sensors
        self.gps_fix = "--"
        self.satellites = "--"
        self.hdop = "--"

        # Power
        self.battery_pct = "--"
        self.battery_voltage = "--"

        # Home Position
        self.home_lat = 37.7749
        self.home_lon = -122.4194
        self.home_alt = 0.0

        # Map state
        self.map_follow_uav = True
        self.map_click_mode = "NAV"  # "NAV", "ADD_WAYPOINT", "SET_DEPLOY_TARGET"

        # Mission state
        self.mission_waypoints = []  # List of Waypoint dicts
        self.mission_current_wp = 0  # 1-indexed active waypoint, 0 if none
        self.mission_status = "IDLE"

        # Deployment state
        self.deployment_state = "IDLE"
        self.deployment_target = None   # dict or None
        self.deployed_nodes = []        # list of dicts

        # Disaster Area Planning (Phase 7)
        self.disaster_area = None
        self.hazard_zones = []
        self.is_drawing_area = False
        self.temp_area_vertices = []

        # Phase 8: Candidate Generation & Placement Optimization
        self.candidates = []
        self.selected_candidate = None
        self.optimization_result = None

        # Phase 9: GPS Deployment Mission
        self.gps_mission_state = "IDLE"
        self.gps_mission_progress = {}

        # Phase 10: Virtual Nodes
        self.virtual_nodes = []
        self.selected_virtual_node = None

        # Phase 11: Simulated RF Propagation Model
        self.rf_config = None
        self.rf_results = None
        self.uav_rf_link = {
            "connected": False,
            "node_id": "NONE",
            "ground_dist_m": 0.0,
            "dist_3d_m": 0.0,
            "rssi_dbm": -120.0,
            "quality": "NO COVERAGE",
            "color": "#8b949e"
        }

        # Phase 12: Autonomous RF Survey
        self.survey_plan = None
        self.survey_samples = []
        self.survey_status = "IDLE"
        self.survey_metrics = None

        # Phase 13: RSSI Heatmap & Spatial RF Analysis
        self.heatmap_cells = []
        self.rf_analysis_result = None
        self.heatmap_visible = True

        # Phase 14: Coverage Gap Analysis
        self.coverage_analysis_report = None
        self.detected_gaps = []

        # Phase 15: Adaptive Deployment Plan
        self.adaptive_plan = None          # AdaptiveDeploymentPlan | None
        self.adaptive_stage_index = 0      # 1-based index of active stage

        # Simulation

        self.sitl_status = "OFFLINE"

        self.gazebo_status = "OFFLINE"
        self.sim_time = "--"

        # Telemetry readouts
        self.telemetry = self._get_empty_telemetry()

        # Command status feedback
        self.last_command_feedback = "SYSTEM READY - DISCONNECTED"

    def _get_empty_telemetry(self):
        return {
            "lat": "--", "lon": "--", "alt_rel": "--", "alt_abs": "--",
            "groundspeed": "--", "heading": "--",
            "roll": "--", "pitch": "--", "yaw": "--",
            "battery_pct": "--", "battery_v": "--",
            "gps_fix": "--", "satellites": "--", "hdop": "--",
            "mode": "--", "armed": "--",
            "system_id": "--", "component_id": "--", "autopilot": "--",
        }

    def log(self, severity: str, category: str, message: str):
        """Append an event to the log system."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_event.emit(timestamp, severity, category, message)

    def set_connection(self, status: str):
        self.connection_status = status
        if status in (ConnectionState.DISCONNECTED, ConnectionState.CONNECTION_LOST):
            self.reset_telemetry()
        self.connection_changed.emit(status)
        self.log("INFO", "MAVLINK", f"Connection state changed: {status}")

    def update_telemetry(self, data: dict = None, **kwargs):
        """Update live telemetry from MAVLink worker thread."""
        payload = {}
        if data:
            payload.update(data)
        if kwargs:
            payload.update(kwargs)
        if not payload:
            return

        data = payload
        prev_armed = self.arm_state

        self.telemetry.update(data)

        if "system_id" in data:
            self.system_id = str(data["system_id"])
        if "autopilot" in data:
            self.vehicle_type = str(data["autopilot"])
        if "mode" in data:
            self.flight_mode = str(data["mode"])
        if "armed" in data:
            new_arm = FlightState.ARMED if data["armed"] else FlightState.DISARMED
            if new_arm != prev_armed:
                self.arm_state = new_arm
                self.arm_state_changed.emit(new_arm)
                self._update_flight_phase(data)
        if "gps_fix" in data:
            self.gps_fix = str(data["gps_fix"])
        if "satellites" in data:
            self.satellites = str(data["satellites"])
        if "hdop" in data:
            self.hdop = f"{data['hdop']:.2f}" if isinstance(data['hdop'], (int, float)) else str(data['hdop'])
        if "battery_pct" in data:
            self.battery_pct = f"{data['battery_pct']}%" if isinstance(data['battery_pct'], (int, float)) else str(data['battery_pct'])
        if "battery_v" in data:
            self.battery_voltage = f"{data['battery_v']:.1f} V" if isinstance(data['battery_v'], (int, float)) else str(data['battery_v'])

        # Estimate simulated UAV-to-node RF link if coordinates present (Phase 11)
        uav_lat = self.telemetry.get("lat")
        uav_lon = self.telemetry.get("lon")
        uav_alt = self.telemetry.get("alt_rel", self.telemetry.get("alt", 0.0))
        if isinstance(uav_lat, (int, float)) and isinstance(uav_lon, (int, float)):
            nodes_to_check = self.virtual_nodes or self.deployed_nodes
            if nodes_to_check:
                try:
                    from gcs.rf.rf_model import rf_engine
                    alt_m = float(uav_alt) if isinstance(uav_alt, (int, float)) else 25.0
                    link_info = rf_engine.estimate_uav_link(uav_lat, uav_lon, alt_m, nodes_to_check)
                    self.update_uav_rf_link(link_info)
                except Exception:
                    pass

        self.telemetry_updated.emit(self.telemetry)

    def _update_flight_phase(self, data: dict):
        """Advance flight phase state machine based on armed + mode transitions."""
        armed = data.get("armed", False)
        mode = str(data.get("mode", "")).upper()

        if not armed:
            self.flight_phase = FlightPhase.GROUNDED
        elif mode in ("RTL", "RETURNING"):
            self.flight_phase = FlightPhase.RETURNING
        elif mode in ("LAND", "LANDING"):
            self.flight_phase = FlightPhase.LANDED
        elif armed:
            alt = data.get("alt_rel", 0)
            if isinstance(alt, (int, float)) and alt > 0.5:
                self.flight_phase = FlightPhase.AIRBORNE
            else:
                self.flight_phase = FlightPhase.ARMED

    def reset_telemetry(self):
        """Reset all telemetry readouts back to placeholders."""
        self.vehicle_type = "--"
        self.system_id = "--"
        self.flight_mode = "--"
        prev_arm = self.arm_state
        self.arm_state = FlightState.DISARMED
        self.flight_phase = FlightPhase.GROUNDED
        if prev_arm != FlightState.DISARMED:
            self.arm_state_changed.emit(FlightState.DISARMED)
        self.gps_fix = "--"
        self.satellites = "--"
        self.hdop = "--"
        self.battery_pct = "--"
        self.battery_voltage = "--"
        self.telemetry = self._get_empty_telemetry()
        self.telemetry_updated.emit(self.telemetry)

    def set_map_follow_uav(self, enabled: bool):
        self.map_follow_uav = enabled
        self.map_follow_toggled.emit(enabled)

    def trigger_clear_track(self):
        self.map_clear_track.emit()

    def set_command_feedback(self, text: str):
        self.last_command_feedback = text
        self.command_feedback.emit(text)

    def set_mission_status(self, status: str):
        self.mission_status = status
        self.mission_status_changed.emit(status)

    def set_mission_waypoints(self, waypoints: list):
        self.mission_waypoints = waypoints
        self.mission_updated.emit(waypoints)

    def set_active_waypoint(self, seq: int):
        self.mission_current_wp = seq
        self.mission_current_changed.emit(seq)

    def set_map_click_mode(self, mode: str):
        self.map_click_mode = mode
        self.map_click_mode_changed.emit(mode)

    def add_waypoint_from_coords(self, lat: float, lon: float):
        self.waypoint_added_from_map.emit(lat, lon)

    def set_deployment_state(self, state: str):
        self.deployment_state = state
        self.deployment_state_changed.emit(state)

    def set_deployment_target(self, target):
        if target is None:
            self.deployment_target = None
            t_dict = None
        elif isinstance(target, dict):
            from gcs.deployment.deployment_manager import DeploymentTarget
            self.deployment_target = DeploymentTarget.from_dict(target)
            t_dict = target
        elif hasattr(target, "to_dict"):
            self.deployment_target = target
            t_dict = target.to_dict()
        else:
            self.deployment_target = target
            t_dict = target
        self.deployment_target_updated.emit(t_dict)

    def clear_deployment_target(self):
        self.deployment_target = None
        self.deployment_target_cleared.emit()

    def add_deployed_node(self, node):
        if isinstance(node, dict):
            from gcs.deployment.deployment_manager import DeploymentNode
            node_obj = DeploymentNode.from_dict(node)
            n_dict = node
        elif hasattr(node, "to_dict"):
            node_obj = node
            n_dict = node.to_dict()
        else:
            node_obj = node
            n_dict = node
        self.deployed_nodes.append(node_obj)
        self.deployment_node_added.emit(n_dict)

    def clear_deployed_nodes(self):
        self.deployed_nodes.clear()
        self.deployed_nodes_cleared.emit()

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 7: Disaster Area Planning Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_disaster_area(self, area):
        if area is None:
            self.disaster_area = None
            self.disaster_area_cleared.emit()
            return
        if isinstance(area, dict):
            from gcs.disaster.disaster_manager import DisasterArea
            self.disaster_area = DisasterArea.from_dict(area)
            a_dict = area
        elif hasattr(area, "to_dict"):
            self.disaster_area = area
            a_dict = area.to_dict()
        else:
            self.disaster_area = area
            a_dict = area
        self.disaster_area_updated.emit(a_dict)
        self.log("INFO", "DISASTER", f"Disaster area defined: '{self.disaster_area.name}' ({len(self.disaster_area.vertices)} vertices)")

    def clear_disaster_area(self):
        self.disaster_area = None
        self.temp_area_vertices.clear()
        self.is_drawing_area = False
        self.disaster_area_cleared.emit()
        self.log("INFO", "DISASTER", "Disaster area cleared")

    def set_hazard_zones(self, hazards: list):
        self.hazard_zones = list(hazards)
        hz_dicts = [h.to_dict() if hasattr(h, "to_dict") else h for h in hazards]
        self.hazard_zones_updated.emit(hz_dicts)

    def add_hazard_zone(self, hazard):
        self.hazard_zones.append(hazard)
        hz_dicts = [h.to_dict() if hasattr(h, "to_dict") else h for h in self.hazard_zones]
        self.hazard_zones_updated.emit(hz_dicts)

    def clear_hazard_zones(self):
        self.hazard_zones.clear()
        self.hazard_zones_updated.emit([])

    def start_area_drawing(self):
        self.is_drawing_area = True
        self.temp_area_vertices.clear()
        self.set_map_click_mode("DRAW_DISASTER_AREA")
        self.area_drawing_mode_changed.emit(True)
        self.set_command_feedback("CLICK MAP TO DRAW DISASTER AREA VERTICES")

    def add_drawing_vertex(self, lat: float, lon: float):
        from gcs.disaster.disaster_manager import DisasterVertex
        seq = len(self.temp_area_vertices) + 1
        v = DisasterVertex(lat=lat, lon=lon, seq=seq)
        self.temp_area_vertices.append(v)
        self.set_command_feedback(f"ADDED VERTEX V{seq}: {lat:.6f}, {lon:.6f}")

    def pop_drawing_vertex(self):
        if self.temp_area_vertices:
            removed = self.temp_area_vertices.pop()
            self.set_command_feedback(f"REMOVED VERTEX V{removed.seq}")

    def finish_area_drawing(self, name: str = "Defined Disaster Area"):
        if len(self.temp_area_vertices) < 3:
            self.set_command_feedback("CANNOT FINISH: NEED AT LEAST 3 VERTICES")
            return None
        from gcs.disaster.disaster_manager import DisasterArea
        area = DisasterArea(name=name, vertices=list(self.temp_area_vertices))
        self.temp_area_vertices.clear()
        self.is_drawing_area = False
        self.set_map_click_mode("NAV")
        self.area_drawing_mode_changed.emit(False)
        self.set_disaster_area(area)
        self.set_command_feedback(f"DISASTER AREA COMPLETED: {area.calculate_area_sq_meters()/1e6:.2f} km²")
        return area

    def cancel_area_drawing(self):
        self.temp_area_vertices.clear()
        self.is_drawing_area = False
        self.set_map_click_mode("NAV")
        self.area_drawing_mode_changed.emit(False)
        self.set_command_feedback("DISASTER AREA DRAWING CANCELLED")

    @property
    def disaster_polygon(self):
        """Extract polygon coordinates [(lat, lon), ...] from active disaster area."""
        if not self.disaster_area:
            return None
        if hasattr(self.disaster_area, "vertices"):
            return [(v.lat, v.lon) for v in self.disaster_area.vertices]
        elif isinstance(self.disaster_area, dict) and "vertices" in self.disaster_area:
            return [(v.get("lat"), v.get("lon")) for v in self.disaster_area["vertices"]]
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 8: Candidate Generation & Placement Optimization Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_candidates(self, candidates: list):
        self.candidates = list(candidates)
        c_dicts = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.candidates]
        self.candidates_generated.emit(c_dicts)
        self.log("INFO", "OPTIMIZER", f"Generated {len(self.candidates)} candidate drop locations")

    def select_candidate(self, candidate_or_id):
        cand_obj = None
        if isinstance(candidate_or_id, str):
            for c in self.candidates:
                cid = c.candidate_id if hasattr(c, "candidate_id") else c.get("candidate_id")
                if cid == candidate_or_id:
                    cand_obj = c
                    break
        else:
            cand_obj = candidate_or_id

        if cand_obj is not None:
            self.selected_candidate = cand_obj
            c_dict = cand_obj.to_dict() if hasattr(cand_obj, "to_dict") else cand_obj
            self.candidate_selected.emit(c_dict)
            cid = c_dict.get("candidate_id", "C-XX")
            self.set_command_feedback(f"CANDIDATE SELECTED: {cid} ({c_dict.get('lat'):.6f}, {c_dict.get('lon'):.6f})")

    def clear_candidates(self):
        self.candidates.clear()
        self.selected_candidate = None
        self.optimization_result = None
        self.candidates_cleared.emit()
        self.log("INFO", "OPTIMIZER", "Candidate deployment sites cleared")

    def set_optimization_result(self, result):
        self.optimization_result = result
        if result and hasattr(result, "candidates"):
            self.candidates = list(result.candidates)
        res_dict = result.to_dict() if hasattr(result, "to_dict") else result
        self.optimization_completed.emit(res_dict)
        if result:
            cov_pct = res_dict.get("coverage_percent", 0.0)
            sel_cnt = res_dict.get("selected_count", 0)
            self.log("INFO", "OPTIMIZER", f"Optimization complete: {sel_cnt} nodes selected, {cov_pct}% coverage")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 9: GPS Deployment Mission Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_gps_mission_state(self, state: str):
        self.gps_mission_state = str(state)
        self.gps_mission_state_changed.emit(self.gps_mission_state)

    def set_gps_mission_progress(self, progress: dict):
        self.gps_mission_progress = dict(progress)
        self.gps_mission_progress_updated.emit(self.gps_mission_progress)

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 10: Virtual Node Methods
    # ──────────────────────────────────────────────────────────────────────────
    def add_virtual_node(self, node):
        node_dict = node.to_dict() if hasattr(node, "to_dict") else dict(node)
        self.virtual_nodes.append(node_dict)
        self.virtual_nodes_updated.emit(self.virtual_nodes)
        self.add_deployed_node(node)
        self.log("INFO", "VIRTUAL_NODE", f"Virtual Node {node_dict.get('node_id')} deployed at {node_dict.get('lat'):.6f}, {node_dict.get('lon'):.6f} (Alt: {node_dict.get('altitude_m', 4.5)}m)")

    def select_virtual_node(self, node_id: str):
        found = None
        for n in self.virtual_nodes:
            if n.get("node_id") == node_id:
                found = n
                break
        self.selected_virtual_node = found
        if found:
            self.virtual_node_selected.emit(found)
            self.set_command_feedback(f"NODE SELECTED: {node_id} (Status: {found.get('status')})")

    def clear_virtual_nodes(self):
        self.virtual_nodes.clear()
        self.selected_virtual_node = None
        self.virtual_nodes_updated.emit([])
        self.clear_deployed_nodes()

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 11: RF Simulation Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_rf_config(self, config):
        cfg_dict = config.to_dict() if hasattr(config, "to_dict") else dict(config)
        self.rf_config = cfg_dict
        self.rf_config_changed.emit(cfg_dict)

    def set_rf_calculation_result(self, result):
        res_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        self.rf_results = res_dict
        self.rf_coverage_calculated.emit(res_dict)
        r_cov = res_dict.get('coverage_radius_m', 0)
        a_cov = res_dict.get('coverage_area_km2', 0)
        self.log("INFO", "RF_MODEL", f"Simulated RF coverage calculated: Radius = {r_cov:.1f}m, Area = {a_cov:.3f} km²")

    def update_uav_rf_link(self, link_info: dict):
        self.uav_rf_link = dict(link_info)
        self.rf_uav_link_updated.emit(self.uav_rf_link)

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 12: RF Survey Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_survey_plan(self, plan):
        self.survey_plan = plan
        self.survey_plan_generated.emit(plan)

    def set_survey_state(self, status: str):
        self.survey_status = status
        self.survey_state_changed.emit(status)

    def update_survey_metrics(self, metrics):
        self.survey_metrics = metrics
        self.survey_progress_updated.emit(metrics)

    def clear_survey(self):
        self.survey_plan = None
        self.survey_samples.clear()
        self.survey_status = "IDLE"
        self.survey_metrics = None
        self.survey_cleared.emit()

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 13: RSSI Heatmap & Spatial RF Analysis Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_rssi_heatmap(self, analysis_result):
        self.rf_analysis_result = analysis_result
        self.heatmap_cells = getattr(analysis_result, "cells", [])
        geojson = analysis_result.to_geojson() if hasattr(analysis_result, "to_geojson") else analysis_result
        self.rssi_heatmap_generated.emit(geojson)
        self.rf_analysis_updated.emit(analysis_result)
        cov = getattr(analysis_result, "coverage_pct", 0.0)
        mean_r = getattr(analysis_result, "mean_rssi_dbm", 0.0)
        pts = getattr(analysis_result, "total_points", len(self.heatmap_cells))
        self.log("INFO", "RF_HEATMAP", f"Spatial RSSI heatmap generated: {pts} points, Mean RSSI: {mean_r:.1f} dBm, Coverage: {cov:.1f}%")

    def clear_rssi_heatmap(self):
        self.rf_analysis_result = None
        self.heatmap_cells.clear()
        self.rssi_heatmap_cleared.emit()
        self.log("INFO", "RF_HEATMAP", "Spatial RSSI heatmap cleared from tactical display")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 14: Coverage Gap Analysis Methods
    # ──────────────────────────────────────────────────────────────────────────
    def set_coverage_analysis_report(self, report):
        self.coverage_analysis_report = report
        self.detected_gaps = getattr(report, "gaps", [])
        geojson = report.to_geojson() if hasattr(report, "to_geojson") else report
        self.coverage_analysis_completed.emit(geojson)
        self.gaps_updated.emit(self.detected_gaps)
        g_cnt = getattr(report, "gaps_detected", len(self.detected_gaps))
        cov = getattr(report, "covered_pct", 0.0)
        self.log("INFO", "COVERAGE_GAP", f"Coverage gap analysis completed: {g_cnt} gaps detected, Covered: {cov:.1f}%")

    def clear_coverage_analysis(self):
        self.coverage_analysis_report = None
        self.detected_gaps.clear()
        self.gaps_cleared.emit()
        self.log("INFO", "COVERAGE_GAP", "Coverage gap analysis cleared")

    # ────────────────────────────────────────────────────────────────────────────
    # Phase 15: Adaptive Deployment Methods
    # ────────────────────────────────────────────────────────────────────────────
    def set_adaptive_plan(self, plan):
        """Store a new AdaptiveDeploymentPlan and broadcast to all listeners."""
        self.adaptive_plan = plan
        self.adaptive_stage_index = plan.active_stage_index if plan else 0
        self.adaptive_plan_generated.emit(plan)
        n  = getattr(plan, "total_stages", 0)
        cb = getattr(plan, "coverage_before_pct", 0.0)
        ca = getattr(plan, "estimated_coverage_after_pct", 0.0)
        self.log("INFO", "ADAPTIVE_PLAN",
                 f"Adaptive deployment plan generated: {n} stages, "
                 f"Coverage {cb:.1f}% -> est. {ca:.1f}%")

    def advance_adaptive_stage(self):
        """Mark current ACTIVE stage COMPLETED; promote next PENDING to ACTIVE."""
        if not self.adaptive_plan:
            return
        from gcs.deployment.adaptive_deployment_engine import adaptive_deployment_engine
        nxt = adaptive_deployment_engine.advance_stage(self.adaptive_plan)
        self.adaptive_stage_index = self.adaptive_plan.active_stage_index
        self.adaptive_plan_updated.emit(self.adaptive_plan)
        if nxt:
            self.log("INFO", "ADAPTIVE_PLAN",
                     f"Stage advanced: {nxt.stage_id} ({nxt.gap_id}) now ACTIVE")
        else:
            self.log("INFO", "ADAPTIVE_PLAN", "Adaptive deployment plan complete")

    def skip_adaptive_stage(self):
        """Mark current ACTIVE stage SKIPPED; promote next PENDING to ACTIVE."""
        if not self.adaptive_plan:
            return
        from gcs.deployment.adaptive_deployment_engine import adaptive_deployment_engine
        nxt = adaptive_deployment_engine.skip_stage(self.adaptive_plan)
        self.adaptive_stage_index = self.adaptive_plan.active_stage_index
        self.adaptive_plan_updated.emit(self.adaptive_plan)
        if nxt:
            self.log("INFO", "ADAPTIVE_PLAN",
                     f"Stage skipped: {nxt.stage_id} ({nxt.gap_id}) now ACTIVE")
        else:
            self.log("INFO", "ADAPTIVE_PLAN", "All remaining stages skipped")

    def clear_adaptive_plan(self):
        """Clear the adaptive deployment plan and emit cleared signal."""
        self.adaptive_plan = None
        self.adaptive_stage_index = 0
        self.adaptive_plan_cleared.emit()
        self.log("INFO", "ADAPTIVE_PLAN", "Adaptive deployment plan cleared")

    # ---------------------------------------------------------------------------
    # Phase 16: Backend FastAPI Integration Methods
    # ---------------------------------------------------------------------------

    def set_backend_connected(self, connected: bool):
        """Update backend server connection state and emit signal."""
        if self.backend_connected != connected:
            self.backend_connected = connected
            self.backend_connection_changed.emit(connected)
            status_str = "ONLINE (localhost:8000)" if connected else "OFFLINE (Local Engine)"
            self.log("INFO", "BACKEND", f"FastAPI REST API Status: {status_str}")

    def fetch_backend_status(self):
        """Trigger async GET /api/status request via BackendClient."""
        from gcs.network.backend_client import backend_client
        if not getattr(self, "_backend_signal_connected", False):
            backend_client.connection_changed.connect(self.set_backend_connected)
            self._backend_signal_connected = True
        backend_client.check_status()



    def post_area_to_backend(self, polygon: list):
        """Trigger async POST /api/area request via BackendClient."""
        from gcs.network.backend_client import backend_client
        backend_client.post_area(polygon)


    @property
    def uav_latitude(self) -> float:
        """Returns the current UAV latitude from telemetry (fallback to home_lat)."""
        lat = self.telemetry.get("lat", self.home_lat)
        try:
            return float(lat)
        except (ValueError, TypeError):
            return self.home_lat

    @property
    def uav_longitude(self) -> float:
        """Returns the current UAV longitude from telemetry (fallback to home_lon)."""
        lon = self.telemetry.get("lon", self.home_lon)
        try:
            return float(lon)
        except (ValueError, TypeError):
            return self.home_lon


# Singleton instance
app_state = AppState()




