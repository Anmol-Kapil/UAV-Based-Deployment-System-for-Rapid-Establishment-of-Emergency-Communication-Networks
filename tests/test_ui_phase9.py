"""Unit and Integration Tests for Phase 9: GPS Deployment Missions.

Tests:
1. GpsMissionController initialization, candidate loading, and waypoint parsing.
2. Geofenced proximity detection, arrival triggers, and automated payload release.
3. Supervised mode station hold and operator confirmation workflow.
4. End-to-end multi-node deployment lifecycle with UI table and state synchronization.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gcs.state.app_state import app_state, ConnectionState
from gcs.deployment.gps_mission_controller import (
    GpsMissionController,
    GpsMissionConfig,
    GpsMissionState,
    GpsDropTarget,
)
from gcs.deployment.coverage_optimizer import CandidateSite
from gcs.mavlink.mission_manager import Waypoint, MAV_CMD_NAV_TAKEOFF, MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_RETURN_TO_LAUNCH
from gcs.widgets.main_window import MainWindow

# Initialize Qt Application for UI tests
app = QApplication.instance() or QApplication(sys.argv)


class TestPhase9GpsDeploymentMission(unittest.TestCase):

    def setUp(self):
        app_state.clear_deployed_nodes()
        app_state.clear_candidates()
        app_state.set_gps_mission_state("IDLE")
        from gcs.deployment.gps_mission_controller import gps_mission_controller
        gps_mission_controller.reset()


    def test_01_gps_mission_controller_initialization_and_targets(self):
        """Verify controller initialization and target generation from candidate sites and waypoints."""
        controller = GpsMissionController(GpsMissionConfig(acceptance_radius_m=15.0))
        self.assertEqual(controller.state, GpsMissionState.IDLE)
        self.assertEqual(len(controller.targets), 0)

        # 1. Load from CandidateSite list
        candidates = [
            CandidateSite("C-01", 37.7750, -122.4180, is_selected=True),
            CandidateSite("C-02", 37.7760, -122.4190, is_selected=True),
            CandidateSite("C-03", 37.7770, -122.4200, is_selected=True),
        ]
        controller.load_from_candidates(candidates, drop_alt_m=22.0)
        self.assertEqual(len(controller.targets), 3)
        self.assertEqual(controller.state, GpsMissionState.READY)
        self.assertEqual(controller.targets[0].candidate_id, "C-01")
        self.assertEqual(controller.targets[0].alt, 22.0)
        self.assertEqual(controller.active_target_index, 0)

        # 2. Load from Waypoint list
        waypoints = [
            Waypoint(seq=1, command=MAV_CMD_NAV_TAKEOFF, lat=37.7740, lon=-122.4170, alt=25.0),
            Waypoint(seq=2, command=MAV_CMD_NAV_WAYPOINT, lat=37.7755, lon=-122.4185, alt=20.0),
            Waypoint(seq=3, command=MAV_CMD_NAV_WAYPOINT, lat=37.7765, lon=-122.4195, alt=20.0),
            Waypoint(seq=4, command=MAV_CMD_NAV_RETURN_TO_LAUNCH, lat=37.7740, lon=-122.4170, alt=25.0),
        ]
        controller.load_from_waypoints(waypoints, drop_alt_m=20.0)
        # Only WPs 2 and 3 should be drop targets
        self.assertEqual(len(controller.targets), 2)
        self.assertEqual(controller.targets[0].target_id, "DROP-01")
        self.assertEqual(controller.targets[0].lat, 37.7755)
        self.assertEqual(controller.targets[1].target_id, "DROP-02")
        self.assertEqual(controller.targets[1].lat, 37.7765)

    def test_02_geofenced_proximity_detection_and_auto_release(self):
        """Verify geofenced proximity detection and automated payload release upon arrival."""
        config = GpsMissionConfig(
            acceptance_radius_m=15.0,
            settle_delay_sec=0.0,  # Instant release for test
            auto_release=True,
            rf_coverage_radius_m=250.0
        )
        controller = GpsMissionController(config)
        candidates = [
            CandidateSite("C-10", 37.775000, -122.418000, is_selected=True),
            CandidateSite("C-11", 37.776000, -122.419000, is_selected=True),
        ]
        controller.load_from_candidates(candidates)

        started = controller.start_mission()
        self.assertTrue(started)
        self.assertEqual(controller.state, GpsMissionState.TRANSITING)

        # Telemetry far away: ~1 km away
        controller.process_telemetry({"lat": 37.765000, "lon": -122.418000, "alt_rel": 20.0})
        self.assertEqual(controller.state, GpsMissionState.TRANSITING)
        self.assertEqual(len(app_state.deployed_nodes), 0)

        # Telemetry within acceptance radius: 37.775001, -122.418001 (< 1m distance)
        controller.process_telemetry({"lat": 37.775001, "lon": -122.418001, "alt_rel": 20.0})

        # Node 1 should be deployed and controller should advance to target 2
        self.assertEqual(len(app_state.deployed_nodes), 1)
        self.assertEqual(app_state.deployed_nodes[0].lat, 37.7750)
        self.assertEqual(app_state.deployed_nodes[0].lon, -122.4180)
        self.assertEqual(controller.active_target_index, 1)
        self.assertEqual(controller.state, GpsMissionState.TRANSITING)

    def test_03_supervised_mode_station_hold_and_manual_release(self):
        """Verify supervised mode station hold and operator confirmation trigger."""
        config = GpsMissionConfig(
            acceptance_radius_m=15.0,
            settle_delay_sec=0.0,
            auto_release=False,  # Supervised mode
        )
        controller = GpsMissionController(config)
        candidates = [
            CandidateSite("C-20", 37.775000, -122.418000, is_selected=True),
        ]
        controller.load_from_candidates(candidates)
        controller.start_mission()

        awaiting_events = []
        controller.awaiting_confirmation.connect(lambda tid: awaiting_events.append(tid))

        # Arrive at station
        controller.process_telemetry({"lat": 37.775002, "lon": -122.418001, "alt_rel": 20.0})

        # In supervised mode, should be ON_STATION waiting for confirm
        self.assertEqual(controller.state, GpsMissionState.ON_STATION)
        self.assertEqual(len(awaiting_events), 1)
        self.assertEqual(awaiting_events[0], "DROP-01")
        self.assertEqual(len(app_state.deployed_nodes), 0)  # Not deployed yet

        # Operator triggers release
        controller.trigger_payload_release()
        self.assertEqual(len(app_state.deployed_nodes), 1)
        self.assertTrue(controller.targets[0].deployed)
        self.assertEqual(controller.state, GpsMissionState.COMPLETED)

    def test_04_full_gps_deployment_lifecycle_and_ui_sync(self):
        """Verify complete multi-node deployment lifecycle with UI table and widget sync."""
        window = MainWindow()
        dep_view = window.right_panel.deployment_view

        # Check UI components exist
        self.assertIsNotNone(dep_view.btn_start_gps_mission)
        self.assertIsNotNone(dep_view.btn_pause_gps_mission)
        self.assertIsNotNone(dep_view.btn_resume_gps_mission)
        self.assertIsNotNone(dep_view.btn_abort_gps_mission)
        self.assertIsNotNone(dep_view.combo_gps_mode)
        self.assertIsNotNone(dep_view.lbl_gps_state)

        # Setup 2 candidate sites in app_state
        candidates = [
            CandidateSite("C-31", 37.775000, -122.418000, is_selected=True),
            CandidateSite("C-32", 37.776000, -122.419000, is_selected=True),
        ]
        app_state.set_candidates(candidates)

        from gcs.deployment.gps_mission_controller import gps_mission_controller
        gps_mission_controller.config.settle_delay_sec = 0.0
        gps_mission_controller.config.auto_release = True

        # Start GPS deployment mission from UI
        dep_view._on_start_gps_mission()
        self.assertEqual(gps_mission_controller.state, GpsMissionState.TRANSITING)
        self.assertEqual(len(gps_mission_controller.targets), 2)

        # Fly to Drop 1
        dep_view._on_telemetry_updated({"lat": 37.775001, "lon": -122.418001, "alt_rel": 20.0})
        self.assertEqual(len(app_state.deployed_nodes), 1)
        self.assertEqual(dep_view.table.rowCount(), 1)

        # Fly to Drop 2
        dep_view._on_telemetry_updated({"lat": 37.776001, "lon": -122.419001, "alt_rel": 20.0})
        self.assertEqual(len(app_state.deployed_nodes), 2)
        self.assertEqual(dep_view.table.rowCount(), 2)

        # Mission should be completed and vehicle returning
        self.assertEqual(gps_mission_controller.state, GpsMissionState.COMPLETED)
        self.assertIn("COMPLETED", dep_view.lbl_gps_state.text())

        window.close()


if __name__ == "__main__":
    unittest.main()
