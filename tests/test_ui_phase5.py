"""Automated Unit & Integration Tests for Phase 5: Deployment Workflow (Emergency Communication Nodes)."""

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
from gcs.deployment.deployment_manager import (
    DeploymentState,
    DeploymentTarget,
    DeploymentNode,
    calculate_bearing,
    calculate_ground_distance,
)
from gcs.widgets.deployment_view import DeploymentView
from gcs.widgets.left_panel import LeftPanel
from gcs.mavlink.mavlink_worker import QMavlinkWorker


class TestPhase5DeploymentWorkflow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app_state.reset_telemetry()
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.clear_deployment_target()
        app_state.clear_deployed_nodes()

    def setUp(self):
        app_state.reset_telemetry()
        app_state.clear_deployment_target()
        app_state.clear_deployed_nodes()

    def test_01_deployment_models(self):
        """Test DeploymentTarget, DeploymentNode, bearing and ground distance calculations."""
        # Target model
        tgt = DeploymentTarget(target_id="RELAY-01", lat=37.7749, lon=-122.4194, alt=30.0, acceptance_radius_m=20.0)
        self.assertEqual(tgt.target_id, "RELAY-01")
        self.assertAlmostEqual(tgt.lat, 37.7749)
        self.assertAlmostEqual(tgt.lon, -122.4194)
        self.assertEqual(tgt.alt, 30.0)
        self.assertEqual(tgt.acceptance_radius_m, 20.0)

        # Target dict serialization round-trip
        d = tgt.to_dict()
        self.assertEqual(d["target_id"], "RELAY-01")
        tgt_reconstructed = DeploymentTarget.from_dict(d)
        self.assertEqual(tgt_reconstructed.target_id, tgt.target_id)
        self.assertAlmostEqual(tgt_reconstructed.lat, tgt.lat)

        # Node model
        node = DeploymentNode(
            node_id="NODE-01",
            lat=37.7750,
            lon=-122.4190,
            alt=0.0,
            deploy_time="12:00:00",
            status="ACTIVE",
            tx_power_dbm=20.0,
            coverage_radius_m=250.0,
        )
        self.assertEqual(node.node_id, "NODE-01")
        self.assertEqual(node.coverage_radius_m, 250.0)

        # Node dict serialization round-trip
        nd = node.to_dict()
        node_rec = DeploymentNode.from_dict(nd)
        self.assertEqual(node_rec.node_id, node.node_id)
        self.assertEqual(node_rec.status, "ACTIVE")

        # Distance & bearing
        lat1, lon1 = 37.7749, -122.4194
        lat2, lon2 = 37.7759, -122.4184  # NE direction
        dist = calculate_ground_distance(lat1, lon1, lat2, lon2)
        bearing = calculate_bearing(lat1, lon1, lat2, lon2)
        self.assertGreater(dist, 100.0)
        self.assertGreater(bearing, 0.0)
        self.assertLess(bearing, 90.0)  # NE is in first quadrant (0 - 90 deg)

    def test_02_deployment_view_ui(self):
        """Test DeploymentView widgets, coordinate entry, copy UAV pos, and clearing."""
        view = DeploymentView()

        # Check default UI components exist
        self.assertIsNotNone(view.spin_lat)
        self.assertIsNotNone(view.spin_lon)
        self.assertIsNotNone(view.spin_alt)
        self.assertIsNotNone(view.spin_radius)
        self.assertIsNotNone(view.btn_set_target)
        self.assertIsNotNone(view.btn_copy_uav)
        self.assertIsNotNone(view.btn_clear_target)
        self.assertIsNotNone(view.table_nodes)

        # Set coordinates via spinboxes and click Set Target
        view.spin_lat.setValue(37.7800)
        view.spin_lon.setValue(-122.4100)
        view.spin_alt.setValue(35.0)
        view.spin_radius.setValue(25.0)
        view.btn_set_target.click()

        # Check app_state
        self.assertIsNotNone(app_state.deployment_target)
        self.assertAlmostEqual(app_state.deployment_target.lat, 37.7800)
        self.assertAlmostEqual(app_state.deployment_target.lon, -122.4100)
        self.assertEqual(app_state.deployment_target.alt, 35.0)
        self.assertEqual(app_state.deployment_target.acceptance_radius_m, 25.0)
        self.assertEqual(app_state.deployment_state, DeploymentState.TARGET_SELECTED)

        # Test Copy UAV Pos
        app_state.update_telemetry(lat=37.7755, lon=-122.4185, alt_rel=28.5)
        view.btn_copy_uav.click()
        self.assertAlmostEqual(view.spin_lat.value(), 37.7755)
        self.assertAlmostEqual(view.spin_lon.value(), -122.4185)
        self.assertAlmostEqual(view.spin_alt.value(), 28.5)

        # Test metrics display update
        view.btn_set_target.click()  # Target is now at 37.7755, -122.4185
        # Move UAV slightly away
        app_state.update_telemetry(lat=37.7745, lon=-122.4185, groundspeed=10.0)
        QApplication.processEvents()
        self.assertIn("Dist:", view.lbl_dist.text())
        self.assertNotIn("--", view.lbl_dist.text())
        self.assertIn("Bearing:", view.lbl_bearing.text())
        self.assertIn("ETA:", view.lbl_eta.text())

        # Test Clear Target
        view.btn_clear_target.click()
        self.assertIsNone(app_state.deployment_target)
        self.assertEqual(app_state.deployment_state, DeploymentState.IDLE)
        self.assertIn("--", view.lbl_dist.text())

    def test_03_deployment_controls_and_left_panel_gating(self):
        """Test deployment navigation controls and LeftPanel deploy button state gating."""
        view = DeploymentView()
        left_panel = LeftPanel()

        worker = QMavlinkWorker(connection_str="mock://sitl")
        view.set_worker(worker)
        left_panel.set_worker(worker)

        # LeftPanel btn_dep_node should be disabled initially (IDLE / DISCONNECTED)
        self.assertFalse(left_panel.btn_dep_node.isEnabled())

        # Set target
        target = DeploymentTarget(target_id="RELAY-TGT", lat=37.7800, lon=-122.4100, alt=30.0)
        app_state.set_deployment_target(target)

        # Still disabled in TARGET_SELECTED even when connected until NAVIGATING or ON_STATION
        app_state.set_connection(ConnectionState.CONNECTED)
        self.assertFalse(left_panel.btn_dep_node.isEnabled())

        # Navigation controls on deployment view should be enabled when connected and target set
        self.assertTrue(view.btn_go_target.isEnabled())
        self.assertTrue(view.btn_loiter_hold.isEnabled())
        self.assertTrue(view.btn_manual.isEnabled())

        # Click Go to Target -> initiates GUIDED navigation
        view.btn_go_target.click()
        self.assertEqual(app_state.deployment_state, DeploymentState.NAVIGATING)
        self.assertEqual(worker._mock_telemetry_state.get("mode"), "GUIDED")
        self.assertTrue(left_panel.btn_dep_node.isEnabled())

        # Transition to ON_STATION
        app_state.set_deployment_state(DeploymentState.ON_STATION)
        self.assertTrue(left_panel.btn_dep_node.isEnabled())

        # Transition to DEPLOYED -> disabled again
        app_state.set_deployment_state(DeploymentState.DEPLOYED)
        self.assertFalse(left_panel.btn_dep_node.isEnabled())

        # Disconnecting disables deployment button
        app_state.set_deployment_state(DeploymentState.ON_STATION)
        self.assertTrue(left_panel.btn_dep_node.isEnabled())
        app_state.set_connection(ConnectionState.DISCONNECTED)
        self.assertFalse(left_panel.btn_dep_node.isEnabled())

    def test_04_node_deployment_flow(self):
        """Test complete node deployment execution, table registration, and state updates."""
        view = DeploymentView()
        worker = QMavlinkWorker(connection_str="mock://sitl")
        view.set_worker(worker)

        # Setup target and vehicle position
        target = DeploymentTarget(target_id="TGT-TEST", lat=37.7780, lon=-122.4150, alt=25.0)
        app_state.set_deployment_target(target)
        app_state.update_telemetry(lat=37.7780, lon=-122.4150, alt_rel=25.0)
        app_state.set_deployment_state(DeploymentState.ON_STATION)

        self.assertEqual(len(app_state.deployed_nodes), 0)
        self.assertEqual(view.table_nodes.rowCount(), 0)

        # Execute deployment directly (bypassing blocking dialog for automated test)
        view._execute_node_deployment()

        # Check state transitions
        self.assertEqual(app_state.deployment_state, DeploymentState.DEPLOYED)
        self.assertEqual(len(app_state.deployed_nodes), 1)

        node = app_state.deployed_nodes[0]
        self.assertEqual(node.node_id, "NODE-01")
        self.assertAlmostEqual(node.lat, 37.7780)
        self.assertAlmostEqual(node.lon, -122.4150)
        self.assertEqual(node.status, "ACTIVE")

        # Check table
        self.assertEqual(view.table_nodes.rowCount(), 1)
        self.assertEqual(view.table_nodes.item(0, 0).text(), "NODE-01")
        status_col = view.table_nodes.columnCount() - 1
        self.assertEqual(view.table_nodes.item(0, status_col).text(), "ACTIVE")

        # Deploy second node
        view._execute_node_deployment()
        self.assertEqual(len(app_state.deployed_nodes), 2)
        self.assertEqual(view.table_nodes.rowCount(), 2)
        self.assertEqual(app_state.deployed_nodes[1].node_id, "NODE-02")

        # Clear deployed nodes
        app_state.clear_deployed_nodes()
        self.assertEqual(len(app_state.deployed_nodes), 0)
        self.assertEqual(view.table_nodes.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
