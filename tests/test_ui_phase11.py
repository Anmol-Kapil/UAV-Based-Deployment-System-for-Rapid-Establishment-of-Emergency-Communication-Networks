"""Tests for Phase 11: Simulated RF Propagation Model & Link Budget Calculations.

Validates:
1. Log-distance path loss physics, FSPL calibration at d0=1m, and coverage radius formula inversion.
2. Multi-band frequency presets, antenna gains, and multi-node link estimation.
3. RFView UI controls, [CALCULATE COVERAGE] execution, and [APPLY TO VIRTUAL NODES] network synchronization.
4. Real-time UAV telemetry integration estimating instantaneous RF link RSSI and signal quality.
"""

import sys
import math
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gcs.state.app_state import app_state, ConnectionState
from gcs.rf.rf_model import (
    RfConfig,
    RfCalculationResult,
    RfPropagationEngine,
    rf_engine
)
from gcs.deployment.virtual_node_manager import (
    virtual_node_manager,
    VirtualNode
)
from gcs.widgets.rf_view import RFView

app = QApplication.instance() or QApplication(sys.argv)


class TestPhase11RfSimulation(unittest.TestCase):
    def setUp(self):
        app_state.reset_telemetry()
        app_state.clear_deployed_nodes()
        virtual_node_manager.clear()

    def tearDown(self):
        app_state.clear_deployed_nodes()
        virtual_node_manager.clear()

    def test_01_log_distance_path_loss_math(self):
        """Test Log-Distance path loss mathematics, FSPL calibration, and coverage radius inversion."""
        engine = RfPropagationEngine()
        cfg = RfConfig(
            frequency_band="2.4 GHz",
            frequency_mhz=2400.0,
            tx_power_dbm=20.0,
            tx_gain_dbi=2.15,
            rx_gain_dbi=2.15,
            ref_distance_m=1.0,
            path_loss_exponent=2.5,
            rx_sensitivity_dbm=-75.0,
            shadowing_std_db=0.0
        )

        # 1. FSPL at d0=1m for 2400 MHz: 20*log10(2400) - 27.55 = 67.60 - 27.55 = 40.05 dB
        fspl_d0 = engine.calculate_fspl_d0(2400.0, 1.0)
        self.assertAlmostEqual(fspl_d0, 40.05, places=1)

        # 2. Path loss at 10m: PL(1m) + 10*2.5*log10(10) = 40.05 + 25.0 = 65.05 dB
        pl_10m = engine.calculate_path_loss(10.0, cfg)
        self.assertAlmostEqual(pl_10m, 65.05, places=1)

        # 3. Path loss at 100m: 40.05 + 10*2.5*2 = 40.05 + 50.0 = 90.05 dB
        pl_100m = engine.calculate_path_loss(100.0, cfg)
        self.assertAlmostEqual(pl_100m, 90.05, places=1)

        # 4. Coverage Radius Inversion
        # Total link gain: 20 + 2.15 + 2.15 = 24.3 dBm
        # Max allowable PL = 24.3 - (-75.0) = 99.3 dB
        # R_cov = 1 * 10^((99.3 - 40.05) / (25)) = 10^(59.25 / 25) = 10^2.37 = 234.4 m
        radius = engine.calculate_coverage_radius(cfg)
        self.assertGreater(radius, 200.0)
        self.assertLess(radius, 300.0)

        # Confirm RSSI at exact coverage radius equals receiver sensitivity
        rssi_at_radius = engine.calculate_rssi(radius, cfg)
        self.assertAlmostEqual(rssi_at_radius, cfg.rx_sensitivity_dbm, places=1)

    def test_02_rf_engine_link_estimation(self):
        """Test multi-band frequency presets and nearest-node link estimation."""
        engine = RfPropagationEngine()

        # Check presets
        self.assertIn("2.4 GHz", engine.BAND_PRESETS)
        self.assertIn("5.8 GHz", engine.BAND_PRESETS)
        self.assertIn("915 MHz", engine.BAND_PRESETS)
        self.assertIn("433 MHz", engine.BAND_PRESETS)

        # FSPL at 5.8 GHz should be significantly higher than 433 MHz
        fspl_5800 = engine.calculate_fspl_d0(5800.0)
        fspl_433 = engine.calculate_fspl_d0(433.0)
        self.assertGreater(fspl_5800, fspl_433 + 20.0)

        # Test link estimation with two nodes at different distances
        nodes = [
            VirtualNode(node_id="NODE_001", lat=37.7750, lon=-122.4200, altitude_m=4.5),
            VirtualNode(node_id="NODE_002", lat=37.7850, lon=-122.4200, altitude_m=4.5),
        ]

        # UAV position right next to NODE_001
        link = engine.estimate_uav_link(
            uav_lat=37.7752,
            uav_lon=-122.4200,
            uav_alt_m=25.0,
            nodes=nodes
        )
        self.assertTrue(link["connected"])
        self.assertEqual(link["node_id"], "NODE_001")
        self.assertGreater(link["rssi_dbm"], -70.0)
        self.assertIn(link["quality"], ("EXCELLENT", "GOOD"))

    def test_03_rf_view_ui_controls_and_calculation(self):
        """Test RFView UI controls, [CALCULATE COVERAGE] execution, and node synchronization."""
        view = RFView()

        # Check initial widget setup
        self.assertEqual(view.combo_band.currentText(), "2.4 GHz")
        self.assertEqual(view.spin_tx_pwr.value(), 20.0)
        self.assertEqual(view.spin_n.value(), 2.5)
        self.assertEqual(view.spin_rx_sens.value(), -75.0)

        # Change frequency band to 5.8 GHz
        view.combo_band.setCurrentText("5.8 GHz")
        self.assertEqual(view.spin_freq.value(), 5800.0)

        # Trigger calculation
        view.btn_calc.click()

        # Check labels updated
        self.assertIn("m", view.lbl_radius_val.text())
        self.assertIn("km²", view.lbl_area_val.text())
        self.assertIn("dB", view.lbl_max_pl.text())

        # Deploy two virtual nodes and apply calculated RF coverage
        n1 = virtual_node_manager.deploy_node(lat=37.7750, lon=-122.4200, coverage_radius_m=100.0)
        n2 = virtual_node_manager.deploy_node(lat=37.7760, lon=-122.4210, coverage_radius_m=100.0)
        self.assertEqual(n1.coverage_radius_m, 100.0)

        # Click Apply to Virtual Nodes
        view.btn_apply_nodes.click()

        # Nodes should now reflect the newly calculated theoretical coverage radius
        res = rf_engine.last_result
        self.assertAlmostEqual(n1.coverage_radius_m, res.coverage_radius_m, places=1)
        self.assertAlmostEqual(n2.coverage_radius_m, res.coverage_radius_m, places=1)
        self.assertEqual(n1.frequency_band, "5.8 GHz")

    def test_04_full_telemetry_rf_link_sync(self):
        """Test real-time telemetry streaming updates UAV RF link and quality indicators."""
        view = RFView()

        # Deploy a node at specific coordinate
        vnode = virtual_node_manager.deploy_node(
            node_id="NODE_001",
            lat=37.7750,
            lon=-122.4200,
            altitude_m=4.5,
            frequency_band="2.4 GHz",
            tx_power_dbm=20.0
        )

        # Send UAV telemetry near the node
        app_state.update_telemetry({
            "lat": 37.7753,
            "lon": -122.4200,
            "alt_rel": 20.0,
            "groundspeed": 10.0
        })

        # Verify AppState RF link updated
        link = app_state.uav_rf_link
        self.assertTrue(link.get("connected"))
        self.assertEqual(link.get("node_id"), "NODE_001")
        self.assertGreater(link.get("dist_3d_m"), 10.0)
        self.assertLess(link.get("dist_3d_m"), 100.0)
        self.assertGreater(link.get("rssi_dbm"), -75.0)

        # Verify RFView labels reflect the link
        self.assertEqual(view.lbl_near_node.text(), "NODE_001")
        self.assertIn("m", view.lbl_link_dist.text())
        self.assertIn("dBm", view.lbl_link_rssi.text())
        self.assertIn(view.lbl_link_status_badge.text(), ("EXCELLENT", "GOOD"))


if __name__ == "__main__":
    unittest.main()
