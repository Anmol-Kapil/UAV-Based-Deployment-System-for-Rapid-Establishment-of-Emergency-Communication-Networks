"""Automated Unit & Integration Tests for Phase 4: Functional Mission Planner."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure application exists
app = QApplication.instance() or QApplication(sys.argv)

from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.mavlink.mission_manager import (
    Waypoint,
    MissionPlan,
    haversine_distance,
    MAV_CMD_NAV_WAYPOINT,
    MAV_CMD_NAV_TAKEOFF,
    MAV_CMD_NAV_LOITER_UNLIM,
)
from gcs.widgets.mission_view import MissionView
from gcs.widgets.left_panel import LeftPanel
from gcs.mavlink.mavlink_worker import QMavlinkWorker


class TestPhase4MissionPlanner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app_state.reset_telemetry()
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.set_mission_waypoints([])
        app_state.set_mission_status("IDLE")

    def test_01_mission_manager_models(self):
        """Test Waypoint and MissionPlan calculation, QGC JSON & WPL 110 serialization."""
        plan = MissionPlan()
        wp1 = plan.add_waypoint(lat=37.7749, lon=-122.4194, alt=25.0, command=MAV_CMD_NAV_TAKEOFF)
        wp2 = plan.add_waypoint(lat=37.7760, lon=-122.4180, alt=30.0, command=MAV_CMD_NAV_WAYPOINT)
        wp3 = plan.add_waypoint(lat=37.7770, lon=-122.4170, alt=30.0, command=MAV_CMD_NAV_LOITER_UNLIM, param1=10.0)

        self.assertEqual(len(plan.waypoints), 3)
        self.assertEqual(wp1.seq, 1)
        self.assertEqual(wp2.seq, 2)
        self.assertEqual(wp3.seq, 3)

        # Distance calculation
        dist = plan.calculate_total_distance()
        self.assertGreater(dist, 100.0)  # Should be several hundred meters

        # ETA calculation (12 m/s cruise + 10s hold)
        eta = plan.calculate_eta_seconds(cruise_speed_mps=12.0)
        self.assertGreater(eta, 10.0)

        # QGC .plan JSON round-trip
        qgc_json = plan.to_qgc_json()
        self.assertIn('"fileType": "Plan"', qgc_json)
        loaded_qgc = MissionPlan.from_qgc_json(qgc_json)
        self.assertEqual(len(loaded_qgc.waypoints), 3)
        self.assertAlmostEqual(loaded_qgc.waypoints[0].lat, 37.7749, places=4)

        # WPL 110 round-trip
        wpl_txt = plan.to_waypoints_text()
        self.assertTrue(wpl_txt.startswith("QGC WPL 110"))
        loaded_wpl = MissionPlan.from_waypoints_text(wpl_txt)
        self.assertEqual(len(loaded_wpl.waypoints), 3)
        self.assertAlmostEqual(loaded_wpl.waypoints[1].lat, 37.7760, places=4)

    def test_02_mission_view_table_operations(self):
        """Test MissionView waypoint table operations: add, delete, move, clear."""
        view = MissionView()
        self.assertEqual(view.table.rowCount(), 0)

        # Add waypoints
        view.add_waypoint_coords(37.7750, -122.4190, alt=25.0)
        view.add_waypoint_coords(37.7760, -122.4180, alt=30.0)
        self.assertEqual(view.table.rowCount(), 2)
        self.assertEqual(view.lbl_count.text(), "WPs: 2")

        # Select row 0 and move down
        view.table.selectRow(0)
        view._on_move_down_clicked()
        self.assertEqual(view.table.currentRow(), 1)
        self.assertAlmostEqual(view.get_plan().waypoints[0].lat, 37.7760, places=4)

        # Move back up
        view._on_move_up_clicked()
        self.assertEqual(view.table.currentRow(), 0)
        self.assertAlmostEqual(view.get_plan().waypoints[0].lat, 37.7750, places=4)

        # Delete selected
        view._on_delete_clicked()
        self.assertEqual(view.table.rowCount(), 1)

        # Clear
        view._on_clear_clicked()
        self.assertEqual(view.table.rowCount(), 0)
        self.assertEqual(view.lbl_count.text(), "WPs: 0")

    def test_03_left_panel_mission_controls_gating(self):
        """Test state-gated enable/disable of MISSION section buttons."""
        panel = LeftPanel()

        # 1. Disconnected, empty mission
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.set_mission_waypoints([])
        panel._refresh_mission_buttons()
        self.assertTrue(panel.btn_m_new.isEnabled())
        self.assertTrue(panel.btn_m_load.isEnabled())
        self.assertFalse(panel.btn_m_save.isEnabled())
        self.assertFalse(panel.btn_m_upload.isEnabled())
        self.assertFalse(panel.btn_m_download.isEnabled())
        self.assertFalse(panel.btn_m_start.isEnabled())

        # 2. Add waypoints while disconnected
        plan = MissionPlan()
        plan.add_waypoint(37.7750, -122.4190)
        app_state.set_mission_waypoints(plan.to_list_of_dicts())
        self.assertTrue(panel.btn_m_save.isEnabled())
        self.assertFalse(panel.btn_m_upload.isEnabled())  # not connected

        # 3. Connect vehicle
        app_state.set_connection(ConnectionState.CONNECTED)
        panel._on_connection_changed(ConnectionState.CONNECTED)
        self.assertTrue(panel.btn_m_upload.isEnabled())
        self.assertTrue(panel.btn_m_download.isEnabled())
        self.assertFalse(panel.btn_m_start.isEnabled())  # not armed

        # 4. Arm vehicle
        app_state.arm_state = FlightState.ARMED
        app_state.arm_state_changed.emit(FlightState.ARMED)
        self.assertTrue(panel.btn_m_start.isEnabled())

        # 5. Mission running
        app_state.set_mission_status("RUNNING")
        self.assertTrue(panel.btn_m_pause.isEnabled())
        self.assertTrue(panel.btn_m_cancel.isEnabled())

        # 6. Mission paused
        app_state.set_mission_status("PAUSED")
        self.assertTrue(panel.btn_m_resume.isEnabled())
        self.assertTrue(panel.btn_m_cancel.isEnabled())

        # Clean up
        app_state.set_mission_status("IDLE")
        app_state.set_connection(ConnectionState.DISCONNECTED)

    def test_04_full_mission_upload_download_mock_cycle(self):
        """Test MAVLink worker mock mission upload and download protocol."""
        worker = QMavlinkWorker("mock://sitl")
        app_state.set_connection(ConnectionState.CONNECTED)

        received_ack = []
        worker.mission_ack_signal.connect(lambda msg: received_ack.append(msg))

        # Upload
        wps = [
            Waypoint(seq=1, command=16, lat=37.7750, lon=-122.4190, alt=25.0),
            Waypoint(seq=2, command=16, lat=37.7760, lon=-122.4180, alt=30.0),
        ]
        worker.upload_mission(wps)

        self.assertGreater(len(received_ack), 0)
        self.assertIn("MISSION UPLOAD: SUCCESS", received_ack[-1])
        self.assertEqual(app_state.mission_status, "UPLOADED")

        # Download
        worker.download_mission()
        self.assertEqual(len(app_state.mission_waypoints), 2)
        self.assertEqual(app_state.mission_status, "LOADED")


if __name__ == "__main__":
    unittest.main()
