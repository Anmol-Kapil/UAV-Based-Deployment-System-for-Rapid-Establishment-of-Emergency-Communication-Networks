"""Central Tactical Map View for GCS.

Embeds a QtWebEngineView running a Leaflet tactical map with:
- Offline tactical canvas grid fallback
- Real-time MAVLink UAV position marker & heading rotation
- Continuous flight trajectory polyline track
- Interactive map toolbar (Center UAV, Center Home, Follow UAV toggle, Clear Track, Click-to-Add WP toggle)
- Mission waypoints & flight route vector overlays
- Interactive map-click coordinate placement
"""

import json
import os
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
)
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from gcs.state.app_state import app_state, ConnectionState


class MapView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mapView")
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Embedded Web View
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #080c10;")
        self.web_view.page().setBackgroundColor(QColor("#080c10"))
        self.web_view.titleChanged.connect(self._on_title_changed)

        # Resolve path to map.html
        res_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources"))
        map_path = os.path.join(res_dir, "map.html")
        if os.path.exists(map_path):
            self.web_view.load(QUrl.fromLocalFile(map_path))
        else:
            self.web_view.setHtml("<h2 style='color: white;'>Map resource not found</h2>")

        layout.addWidget(self.web_view)

        # Map Quick Action Overlay Bar (Bottom of Map)
        overlay_bar = QFrame(self)
        overlay_bar.setStyleSheet(
            "background-color: rgba(22, 27, 34, 0.95); border-top: 1px solid #30363d; padding: 4px 10px;"
        )
        bar_layout = QHBoxLayout(overlay_bar)
        bar_layout.setContentsMargins(8, 2, 8, 2)
        bar_layout.setSpacing(8)

        lbl_map_info = QLabel("MAP ENGINE: LEAFLET / TACTICAL CANVAS (PHASE 15 ACTIVE)")
        lbl_map_info.setStyleSheet("font-size: 10px; font-weight: 600; color: #58a6ff;")
        bar_layout.addWidget(lbl_map_info)

        bar_layout.addStretch()

        # Click-to-add Waypoint Mode Toggle
        self.btn_click_wp = QPushButton("ADD WP ON MAP: OFF")
        self.btn_click_wp.setToolTip("Toggle click on map to add waypoint at cursor location")
        self.btn_click_wp.setFixedHeight(24)
        self.btn_click_wp.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 3px;
                padding: 2px 8px;
                font-weight: 600;
            }
        """)
        self.btn_click_wp.clicked.connect(self.toggle_click_wp_mode)
        bar_layout.addWidget(self.btn_click_wp)

        self.btn_draw_area = QPushButton("DRAW AREA: OFF")
        self.btn_draw_area.setToolTip("Click on tactical map to define disaster perimeter vertices")
        self.btn_draw_area.setFixedHeight(24)
        self.btn_draw_area.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 3px;
                padding: 2px 8px;
                font-weight: 600;
            }
        """)
        self.btn_draw_area.clicked.connect(self.toggle_draw_area_mode)
        bar_layout.addWidget(self.btn_draw_area)

        self.btn_center_uav = QPushButton("Center UAV")
        self.btn_center_uav.setEnabled(False)
        self.btn_center_uav.setToolTip("Pan map to active UAV position")
        self.btn_center_uav.setFixedHeight(24)
        self.btn_center_uav.clicked.connect(self.center_on_uav)
        bar_layout.addWidget(self.btn_center_uav)

        self.btn_center_home = QPushButton("Center Home")
        self.btn_center_home.setEnabled(True)
        self.btn_center_home.setToolTip("Pan map to default launch/disaster center position")
        self.btn_center_home.setFixedHeight(24)
        self.btn_center_home.clicked.connect(self.center_on_home)
        bar_layout.addWidget(self.btn_center_home)

        self.btn_follow = QPushButton("FOLLOW: ON")
        self.btn_follow.setToolTip("Toggle automatic map centering on UAV position updates")
        self.btn_follow.setFixedHeight(24)
        self.btn_follow.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb;
                color: #ffffff;
                font-weight: bold;
                border-radius: 3px;
                padding: 2px 8px;
            }
        """)
        self.btn_follow.clicked.connect(self.toggle_follow_mode)
        bar_layout.addWidget(self.btn_follow)

        self.btn_clear_track = QPushButton("Clear Track")
        self.btn_clear_track.setToolTip("Erase flight trajectory line history")
        self.btn_clear_track.setFixedHeight(24)
        self.btn_clear_track.clicked.connect(self.clear_flight_track)
        bar_layout.addWidget(self.btn_clear_track)

        layout.addWidget(overlay_bar)

    def _connect_signals(self):
        app_state.telemetry_updated.connect(self.on_telemetry_updated)
        app_state.connection_changed.connect(self.on_connection_changed)
        app_state.mission_updated.connect(self.on_mission_updated)
        app_state.mission_current_changed.connect(self.on_mission_current_changed)
        app_state.map_click_mode_changed.connect(self.on_map_click_mode_changed)
        app_state.deployment_target_updated.connect(self.on_deployment_target_updated)
        app_state.deployment_target_cleared.connect(self.on_deployment_target_cleared)
        app_state.deployment_node_added.connect(self.on_deployment_node_added)
        app_state.deployed_nodes_cleared.connect(self.on_deployed_nodes_cleared)
        app_state.disaster_area_updated.connect(self.on_disaster_area_updated)
        app_state.disaster_area_cleared.connect(self.on_disaster_area_cleared)
        app_state.hazard_zones_updated.connect(self.on_hazard_zones_updated)
        app_state.area_drawing_mode_changed.connect(self.on_area_drawing_mode_changed)
        app_state.candidates_generated.connect(self.on_candidates_generated)
        app_state.candidate_selected.connect(self.on_candidate_selected)
        app_state.optimization_completed.connect(self.on_optimization_completed)
        app_state.candidates_cleared.connect(self.on_candidates_cleared)
        app_state.rf_coverage_calculated.connect(self.on_rf_coverage_calculated)
        app_state.survey_plan_generated.connect(self.on_survey_plan_generated)
        app_state.survey_sample_acquired.connect(self.on_survey_sample_acquired)
        app_state.survey_cleared.connect(self.on_survey_cleared)
        app_state.rssi_heatmap_generated.connect(self.on_rssi_heatmap_generated)
        app_state.rssi_heatmap_cleared.connect(self.on_rssi_heatmap_cleared)

        # Phase 14: Coverage Gap Analysis signals
        app_state.coverage_analysis_completed.connect(self.on_coverage_analysis_completed)
        app_state.gaps_cleared.connect(self.on_gaps_cleared)

        # Phase 15: Adaptive Deployment signals
        app_state.adaptive_plan_generated.connect(self.on_adaptive_plan_generated)
        app_state.adaptive_plan_updated.connect(self.on_adaptive_plan_updated)
        app_state.adaptive_plan_cleared.connect(self.on_adaptive_plan_cleared)

    def _on_title_changed(self, title: str):
        """Receive coordinate messages transmitted via document.title from Leaflet."""
        if title.startswith("MAP_CLICK:"):
            parts = title.split(":")
            if len(parts) >= 3:
                try:
                    lat = float(parts[1])
                    lon = float(parts[2])
                    app_state.add_waypoint_from_coords(lat, lon)
                except ValueError:
                    pass
        elif title.startswith("MAP_TARGET_CLICK:"):
            parts = title.split(":")
            if len(parts) >= 3:
                try:
                    lat = float(parts[1])
                    lon = float(parts[2])
                    app_state.set_deployment_target({
                        "target_id": "TGT-01",
                        "lat": lat,
                        "lon": lon,
                        "alt": 25.0,
                        "acceptance_radius_m": 15.0
                    })
                except ValueError:
                    pass
        elif title.startswith("MAP_AREA_CLICK:"):
            parts = title.split(":")
            if len(parts) >= 3:
                try:
                    lat = float(parts[1])
                    lon = float(parts[2])
                    app_state.add_drawing_vertex(lat, lon)
                    n_pts = len(app_state.temp_area_vertices)
                    self.btn_draw_area.setText(f"DRAW AREA: {n_pts} PTS")
                except ValueError:
                    pass
        elif title.startswith("MAP_CANDIDATE_CLICK:"):
            parts = title.split(":")
            if len(parts) >= 2:
                cand_id = parts[1]
                app_state.select_candidate(cand_id)
        elif title.startswith("MAP_NODE_CLICK:"):
            parts = title.split(":")
            if len(parts) >= 2:
                node_id = parts[1]
                app_state.select_virtual_node(node_id)

    def toggle_draw_area_mode(self):
        if app_state.is_drawing_area:
            # If already drawing and has at least 3 points, finish; otherwise cancel
            if len(app_state.temp_area_vertices) >= 3:
                app_state.finish_area_drawing()
            else:
                app_state.cancel_area_drawing()
        else:
            app_state.start_area_drawing()

    def on_area_drawing_mode_changed(self, is_drawing: bool):
        if is_drawing:
            self.btn_draw_area.setText("DRAW AREA: ACTIVE (0)")
            self.btn_draw_area.setStyleSheet("""
                QPushButton {
                    background-color: #d29922;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 8px;
                }
            """)
        else:
            self.btn_draw_area.setText("DRAW AREA: OFF")
            self.btn_draw_area.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-weight: 600;
                }
            """)

    def on_disaster_area_updated(self, area):
        if not area:
            return
        area_dict = area.to_dict() if hasattr(area, "to_dict") else area
        area_json = json.dumps(area_dict).replace("'", "\\'")
        self.web_view.page().runJavaScript(f"if (window.setDisasterArea) setDisasterArea('{area_json}');")

    def on_disaster_area_cleared(self):
        self.web_view.page().runJavaScript("if (window.clearDisasterArea) clearDisasterArea();")

    def on_hazard_zones_updated(self, hazards: list):
        hz_list = [h.to_dict() if hasattr(h, "to_dict") else h for h in hazards]
        hz_json = json.dumps(hz_list).replace("'", "\\'")
        self.web_view.page().runJavaScript(f"if (window.setHazardZones) setHazardZones('{hz_json}');")

    def on_deployment_target_updated(self, target: dict):
        lat = target.get("lat")
        lon = target.get("lon")
        rad = target.get("acceptance_radius_m", 15.0)
        self.web_view.page().runJavaScript(f"if (window.setDeploymentTarget) setDeploymentTarget({lat}, {lon}, {rad});")

    def on_deployment_target_cleared(self):
        self.web_view.page().runJavaScript("if (window.clearDeploymentTarget) clearDeploymentTarget();")

    def on_deployment_node_added(self, node: dict):
        node_json = json.dumps(node).replace("'", "\\'")
        self.web_view.page().runJavaScript(f"if (window.addDeployedNode) addDeployedNode('{node_json}');")

    def on_deployed_nodes_cleared(self):
        self.web_view.page().runJavaScript("if (window.clearDeployedNodes) clearDeployedNodes();")

    def on_rf_coverage_calculated(self, result: dict):
        """Update deployed node coverage circle radius on tactical map."""
        if not result:
            return
        radius = float(result.get("coverage_radius_m", 250.0))
        self.web_view.page().runJavaScript(f"if (window.updateNodeCoverageRadius) updateNodeCoverageRadius({radius});")

    def on_mission_updated(self, waypoints: list):
        """Sync mission waypoints to Leaflet map layer."""
        wp_json = json.dumps(waypoints)
        # Escape any single quotes/backslashes
        escaped_json = wp_json.replace("\\", "\\\\").replace("'", "\\'")
        self.web_view.page().runJavaScript(f"if (window.setMissionWaypoints) setMissionWaypoints('{escaped_json}');")

    def on_mission_current_changed(self, seq: int):
        """Highlight active waypoint index on map."""
        self.web_view.page().runJavaScript(f"if (window.setActiveWaypoint) setActiveWaypoint({seq});")

    def on_map_click_mode_changed(self, mode: str):
        """Update map click mode (crosshair / add waypoint)."""
        is_add = (mode == "ADD_WAYPOINT")
        if is_add:
            self.btn_click_wp.setText("ADD WP ON MAP: ACTIVE")
            self.btn_click_wp.setStyleSheet("""
                QPushButton {
                    background-color: #d29922;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 8px;
                }
            """)
        else:
            self.btn_click_wp.setText("ADD WP ON MAP: OFF")
            self.btn_click_wp.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-weight: 600;
                }
            """)
        self.web_view.page().runJavaScript(f"if (window.setMapClickMode) setMapClickMode('{mode}');")

    def toggle_click_wp_mode(self):
        new_mode = "NAV" if app_state.map_click_mode == "ADD_WAYPOINT" else "ADD_WAYPOINT"
        app_state.set_map_click_mode(new_mode)

    def on_telemetry_updated(self, data: dict):
        lat = data.get("lat")
        lon = data.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            alt = data.get("alt_rel", 0.0)
            heading = data.get("heading", 0.0)
            armed = "ARMED" if data.get("armed") else "DISARMED"
            mode = str(data.get("mode", "UNKNOWN"))

            js_code = f"if (window.updateUAVPosition) updateUAVPosition({lat}, {lon}, {alt}, {heading}, '{armed}', '{mode}');"
            self.web_view.page().runJavaScript(js_code)

            if not self.btn_center_uav.isEnabled():
                self.btn_center_uav.setEnabled(True)

    def on_connection_changed(self, status: str):
        if status in (ConnectionState.DISCONNECTED, ConnectionState.CONNECTION_LOST):
            self.web_view.page().runJavaScript("if (window.setUAVDisconnected) setUAVDisconnected();")
            self.btn_center_uav.setEnabled(False)

    def center_on_uav(self):
        self.web_view.page().runJavaScript("if (window.centerOnUAV) centerOnUAV();")

    def center_on_home(self):
        self.web_view.page().runJavaScript("if (window.centerOnHome) centerOnHome();")

    def toggle_follow_mode(self):
        app_state.set_map_follow_uav(not app_state.map_follow_uav)
        enabled = app_state.map_follow_uav
        if enabled:
            self.btn_follow.setText("FOLLOW: ON")
            self.btn_follow.setStyleSheet("""
                QPushButton {
                    background-color: #1f6feb;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 8px;
                }
            """)
        else:
            self.btn_follow.setText("FOLLOW: OFF")
            self.btn_follow.setStyleSheet("""
                QPushButton {
                    background-color: #21262d;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    border-radius: 3px;
                    padding: 2px 8px;
                }
            """)
        self.web_view.page().runJavaScript(f"if (window.setFollowMode) setFollowMode({str(enabled).lower()});")

    def clear_flight_track(self):
        self.web_view.page().runJavaScript("if (window.clearFlightTrack) clearFlightTrack();")

    def _run_js(self, script: str):
        self.web_view.page().runJavaScript(script)

    def on_candidates_generated(self, candidates: list):
        import json
        c_json = json.dumps(candidates)
        self._run_js(f"window.setCandidates({c_json});")

    def on_candidate_selected(self, candidate):
        import json
        c_list = [c.to_dict() if hasattr(c, "to_dict") else c for c in app_state.candidates]
        c_json = json.dumps(c_list)
        self._run_js(f"window.setCandidates({c_json});")

    def on_optimization_completed(self, result):
        import json
        if result and "candidates" in result:
            c_json = json.dumps(result["candidates"])
            self._run_js(f"window.setCandidates({c_json});")

    def on_candidates_cleared(self):
        self._run_js("window.clearCandidates();")

    def on_survey_plan_generated(self, plan):
        import json
        if hasattr(plan, "to_dict"):
            p_json = json.dumps(plan.to_dict())
            self._run_js(f"if (window.displaySurveyPlan) window.displaySurveyPlan({p_json});")

    def on_survey_sample_acquired(self, sample):
        import json
        if hasattr(sample, "to_dict"):
            s_json = json.dumps(sample.to_dict())
            self._run_js(f"if (window.updateSurveyProgress) window.updateSurveyProgress({s_json});")

    def on_survey_cleared(self):
        self._run_js("if (window.clearSurvey) window.clearSurvey();")

    def on_rssi_heatmap_generated(self, geojson):
        import json
        if isinstance(geojson, dict):
            j_str = json.dumps(geojson)
        else:
            j_str = str(geojson)
        self._run_js(f"if (window.displayRssiHeatmap) window.displayRssiHeatmap({j_str});")

    def on_rssi_heatmap_cleared(self):
        self._run_js("if (window.clearRssiHeatmap) window.clearRssiHeatmap();")

    # ─── Phase 14: Coverage Gap Analysis ─────────────────────────────────────

    def on_coverage_analysis_completed(self, geojson):
        """Bridge coverage gap GeoJSON to the Leaflet/canvas map."""
        import json
        if isinstance(geojson, dict):
            j_str = json.dumps(geojson)
        else:
            j_str = str(geojson)
        self._run_js(f"if (window.displayCoverageGaps) window.displayCoverageGaps({j_str});")

    def on_gaps_cleared(self):
        """Remove all gap overlays from the Leaflet/canvas map."""
        self._run_js("if (window.clearCoverageGaps) window.clearCoverageGaps();")

    # ─── Phase 15: Adaptive Deployment Plan ──────────────────────────────────

    def on_adaptive_plan_generated(self, plan):
        """Bridge adaptive deployment plan to map (initial render)."""
        import json
        if not plan or plan.total_stages == 0:
            return
        gj = plan.to_geojson() if hasattr(plan, "to_geojson") else {}
        j_str = json.dumps(gj)
        self._run_js(f"if (window.displayAdaptivePlan) window.displayAdaptivePlan({j_str});")

    def on_adaptive_plan_updated(self, plan):
        """Update the active stage highlight on the map after advance/skip."""
        import json
        if not plan:
            return
        active = plan.active_stage
        if active:
            stage_dict = active.to_dict()
            stage_dict["stage_index"] = plan.active_stage_index
            j_str = json.dumps(stage_dict)
            self._run_js(
                f"if (window.updateAdaptiveStage) window.updateAdaptiveStage({j_str});"
            )
        else:
            # Plan complete
            gj = plan.to_geojson() if hasattr(plan, "to_geojson") else {}
            j_str = json.dumps(gj)
            self._run_js(f"if (window.displayAdaptivePlan) window.displayAdaptivePlan({j_str});")

    def on_adaptive_plan_cleared(self):
        """Remove all adaptive plan overlays from the map."""
        self._run_js("if (window.clearAdaptivePlan) window.clearAdaptivePlan();")
