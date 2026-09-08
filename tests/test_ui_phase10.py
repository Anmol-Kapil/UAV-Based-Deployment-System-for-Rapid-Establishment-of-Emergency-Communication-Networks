"""Tests for Phase 10: Virtual Nodes & Communication Node Lifecycle Management.

Validates:
1. VirtualNode dataclass creation, status transitions, radio parameters, and serialization.
2. VirtualNodeManager registration, incremental naming (NODE_001, NODE_002), telemetry updates, and query methods.
3. DeploymentView UI Inspector controls, [DEPLOY NODE] button action, vitals synchronization, and table row formatting.
4. GPS Mission Controller integration with VirtualNodeManager upon payload release.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gcs.state.app_state import app_state, ConnectionState
from gcs.deployment.virtual_node_manager import (
    VirtualNode,
    VirtualNodeManager,
    NodeStatus,
    virtual_node_manager
)
from gcs.deployment.gps_mission_controller import (
    gps_mission_controller,
    GpsMissionState
)
from gcs.widgets.deployment_view import DeploymentView

app = QApplication.instance() or QApplication(sys.argv)


class TestPhase10VirtualNodes(unittest.TestCase):
    def setUp(self):
        app_state.reset_telemetry()
        app_state.clear_deployed_nodes()
        virtual_node_manager.clear()
        gps_mission_controller.reset()

    def tearDown(self):
        app_state.clear_deployed_nodes()
        virtual_node_manager.clear()
        gps_mission_controller.reset()

    def test_01_virtual_node_creation_and_serialization(self):
        """Test VirtualNode defaults, serialization, and dictionary round-trip."""
        node = VirtualNode(
            node_id="NODE_001",
            lat=37.774929,
            lon=-122.419416,
            altitude_m=4.5,
            mission_id="TEST_MISSION_01",
            frequency_band="2.4 GHz",
            tx_power_dbm=20.0,
            battery_pct=100.0,
            coverage_radius_m=250.0
        )
        self.assertEqual(node.node_id, "NODE_001")
        self.assertEqual(node.status, NodeStatus.READY)
        self.assertEqual(node.altitude_m, 4.5)
        self.assertEqual(node.frequency_band, "2.4 GHz")
        self.assertEqual(node.tx_power_dbm, 20.0)

        # Serialization to dict
        d = node.to_dict()
        self.assertIn("node_id", d)
        self.assertEqual(d["node_id"], "NODE_001")
        self.assertEqual(d["altitude_m"], 4.5)
        self.assertEqual(d["battery_pct"], 100.0)

        # Deserialization from dict
        node2 = VirtualNode.from_dict(d)
        self.assertEqual(node2.node_id, node.node_id)
        self.assertEqual(node2.lat, node.lat)
        self.assertEqual(node2.lon, node.lon)
        self.assertEqual(node2.altitude_m, node.altitude_m)
        self.assertEqual(node2.status, node.status)

        # GeoJSON feature export
        geojson = node.to_geojson_feature()
        self.assertEqual(geojson["type"], "Feature")
        self.assertEqual(geojson["geometry"]["type"], "Point")
        self.assertEqual(geojson["geometry"]["coordinates"], [-122.419416, 37.774929])
        self.assertEqual(geojson["properties"]["node_id"], "NODE_001")

    def test_02_virtual_node_manager_lifecycle(self):
        """Test VirtualNodeManager deploy, telemetry update, selection, and collection."""
        mgr = VirtualNodeManager()

        # Initial state
        self.assertEqual(len(mgr.nodes), 0)

        # Deploy first node
        n1 = mgr.deploy_node(
            lat=37.7750,
            lon=-122.4200,
            altitude_m=4.5,
            frequency_band="2.4 GHz",
            mission_id="TEST_M1"
        )
        self.assertEqual(n1.node_id, "NODE_001")
        self.assertIn(n1.status, (NodeStatus.DEPLOYED.value, NodeStatus.ACTIVE.value))
        self.assertEqual(len(mgr.nodes), 1)

        # Deploy second node (incremental naming)
        n2 = mgr.deploy_node(
            lat=37.7760,
            lon=-122.4210,
            altitude_m=5.0,
            frequency_band="5.8 GHz",
            mission_id="TEST_M1"
        )
        self.assertEqual(n2.node_id, "NODE_002")
        self.assertEqual(len(mgr.nodes), 2)

        # Update telemetry
        updated = mgr.update_telemetry("NODE_001", battery_pct=95.5, packets_tx=42, packets_rx=38, connected_clients=3)
        self.assertTrue(updated)
        self.assertEqual(n1.battery_pct, 95.5)
        self.assertEqual(n1.packets_tx, 42)
        self.assertEqual(n1.connected_clients, 3)

        # Select node
        selected = mgr.select_node("NODE_002")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.node_id, "NODE_002")

        # GeoJSON FeatureCollection
        fc = mgr.to_geojson(as_dict=True)
        self.assertEqual(fc["type"], "FeatureCollection")
        self.assertEqual(len(fc["features"]), 2)

    def test_03_deployment_view_node_inspector_sync(self):
        """Test DeploymentView UI inspector controls, [DEPLOY NODE] button action, and table columns."""
        view = DeploymentView()

        # Verify initial inspector labels
        self.assertIn("NODE_001", view.lbl_vnode_id.text())
        self.assertIn("READY", view.lbl_vnode_status.text())
        self.assertEqual(view.spin_vnode_alt.value(), 4.5)
        self.assertEqual(view.table.columnCount(), 6)

        # Set target coordinates in spinboxes
        view.spin_vnode_lat.setValue(37.7780)
        view.spin_vnode_lon.setValue(-122.4250)
        view.spin_vnode_alt.setValue(4.5)
        view.combo_vnode_freq.setCurrentText("5.8 GHz")

        # Click [DEPLOY NODE] button
        view.btn_deploy_vnode.click()

        # Verify node was registered and UI inspector updated
        self.assertEqual(len(virtual_node_manager.nodes), 1)
        vnode = virtual_node_manager.get_node("NODE_001")
        self.assertIsNotNone(vnode)
        self.assertEqual(vnode.altitude_m, 4.5)
        self.assertEqual(vnode.frequency_band, "5.8 GHz")

        # Verify inspector labels updated
        self.assertIn("NODE_001", view.lbl_vnode_id.text())
        self.assertTrue(any(s in view.lbl_vnode_status.text() for s in ("DEPLOYED", "ACTIVE")))
        self.assertEqual(view.combo_vnode_freq.currentText(), "5.8 GHz")
        self.assertEqual(view.lbl_vnode_pwr.text(), "20 dBm")

        # Verify table row was inserted with 6 columns
        self.assertEqual(view.table.rowCount(), 1)
        self.assertEqual(view.table.item(0, 0).text(), "NODE_001")
        self.assertAlmostEqual(float(view.table.item(0, 1).text()), 37.7780, places=4)
        self.assertAlmostEqual(float(view.table.item(0, 2).text()), -122.4250, places=4)
        self.assertEqual(view.table.item(0, 3).text(), "4.5")  # ALT (m)
        self.assertIn(view.table.item(0, 5).text(), ("DEPLOYED", "ACTIVE"))

        # Add second node and test selection
        vnode2 = virtual_node_manager.deploy_node(
            lat=37.7790,
            lon=-122.4260,
            altitude_m=6.0,
            frequency_band="915 MHz"
        )
        self.assertEqual(view.table.rowCount(), 2)

        # Select first row
        view._on_deployed_table_clicked(view.table.item(0, 0))
        self.assertIn("NODE_001", view.lbl_vnode_id.text())

        # Select second row
        view._on_deployed_table_clicked(view.table.item(1, 0))
        self.assertIn("NODE_002", view.lbl_vnode_id.text())
        self.assertEqual(view.combo_vnode_freq.currentText(), "915 MHz")
        self.assertEqual(view.spin_vnode_alt.value(), 6.0)

    def test_04_map_and_gps_mission_node_integration(self):
        """Test GPS Mission Controller triggers VirtualNodeManager deployment and updates app_state."""
        # Configure GPS Mission with a drop station
        gps_mission_controller.reset()
        gps_mission_controller.config.auto_release = True

        test_cand = {
            "candidate_id": "C-01",
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 25.0,
            "coverage_radius_m": 250.0
        }
        gps_mission_controller.load_from_candidates([test_cand], drop_alt_m=20.0)
        self.assertEqual(len(gps_mission_controller.targets), 1)

        # Start mission
        started = gps_mission_controller.start_mission()
        self.assertTrue(started)
        self.assertEqual(gps_mission_controller.state, GpsMissionState.TRANSITING)

        # Simulate UAV reaching drop station
        gps_mission_controller.process_telemetry({
            "lat": 37.7749,
            "lon": -122.4194,
            "alt_rel": 20.0,
            "groundspeed": 0.2
        })

        # Trigger payload release
        node = gps_mission_controller.trigger_payload_release()
        self.assertIsNotNone(node)
        self.assertIn("NODE_", node.node_id)
        self.assertIn(node.status, (NodeStatus.DEPLOYED.value, NodeStatus.ACTIVE.value))

        # Verify synced with app_state and virtual_node_manager
        self.assertEqual(len(app_state.deployed_nodes), 1)
        self.assertEqual(len(virtual_node_manager.nodes), 1)
        self.assertIn(node.node_id, [n.node_id for n in virtual_node_manager.nodes])


if __name__ == "__main__":
    unittest.main()
