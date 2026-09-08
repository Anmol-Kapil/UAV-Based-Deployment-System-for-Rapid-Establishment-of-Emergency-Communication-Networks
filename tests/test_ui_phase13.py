"""Unit and Integration Tests for Phase 13: RSSI Heatmap & Spatial RF Analysis.

Validates:
1. RF Category classification thresholds matching Section 24 specification:
   - Strong: >= -65 dBm
   - Good: -75 to -65 dBm
   - Weak: -85 to -75 dBm
   - No coverage: < -85 dBm
2. 2D Inverse Distance Weighting (IDW) interpolation engine:
   - Interpolation from survey samples
   - Direct calculation from active virtual nodes
   - GeoJSON FeatureCollection export and cell bounding boxes
3. RfAnalysisResult metrics computation:
   - Survey points count, Mean RSSI, Min RSSI, Max RSSI
   - Coverage %, Weak %, No coverage %
4. RFView RF ANALYSIS card UI components:
   - Metric readouts and badges
   - Dynamic proportional breakdown bar
   - [GENERATE HEATMAP] and [CLEAR HEATMAP] actions
5. LeftPanel RSSI Heatmap button activation
6. AppState Phase 13 signal broadcasts
"""

import unittest
from PySide6.QtWidgets import QApplication

from gcs.state.app_state import app_state
from gcs.rf.rf_heatmap import (
    RfHeatmapEngine,
    RfAnalysisResult,
    HeatmapCell,
    RfCategory,
    classify_rssi,
    CATEGORY_COLORS,
)
from gcs.rf.rf_survey_controller import (
    rf_survey_controller,
    SurveySample,
)
from gcs.widgets.rf_view import RFView
from gcs.widgets.left_panel import LeftPanel
from gcs.deployment.virtual_node_manager import virtual_node_manager, VirtualNode

# Ensure single QApplication instance
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestPhase13RssiHeatmap(unittest.TestCase):
    """Test suite for Phase 13 RSSI Heatmap & Spatial RF Analysis."""

    def setUp(self):
        """Reset state before each test."""
        app_state.clear_rssi_heatmap()
        rf_survey_controller.clear_survey()
        virtual_node_manager.clear_nodes()
        app_state.clear_virtual_nodes()

    def tearDown(self):
        """Clean up after test."""
        app_state.clear_rssi_heatmap()
        rf_survey_controller.clear_survey()

    def test_rssi_quality_classification(self):
        """Verify RSSI value thresholds map accurately to Section 24 specification."""
        # Strong: >= -65 dBm
        cat, col, op = classify_rssi(-50.0)
        self.assertEqual(cat, RfCategory.STRONG)
        self.assertEqual(col, "#2ecc71")

        cat, col, op = classify_rssi(-65.0)
        self.assertEqual(cat, RfCategory.STRONG)

        # Good: -75 to -65 dBm
        cat, col, op = classify_rssi(-65.1)
        self.assertEqual(cat, RfCategory.GOOD)
        self.assertEqual(col, "#a3e635")

        cat, col, op = classify_rssi(-74.9)
        self.assertEqual(cat, RfCategory.GOOD)

        # Weak: -85 to -75 dBm
        cat, col, op = classify_rssi(-75.1)
        self.assertEqual(cat, RfCategory.WEAK)
        self.assertEqual(col, "#f39c12")

        cat, col, op = classify_rssi(-84.9)
        self.assertEqual(cat, RfCategory.WEAK)

        # No coverage: < -85 dBm
        cat, col, op = classify_rssi(-85.1)
        self.assertEqual(cat, RfCategory.NO_COVERAGE)
        self.assertEqual(col, "#e74c3c")

        cat, col, op = classify_rssi(-105.0)
        self.assertEqual(cat, RfCategory.NO_COVERAGE)

    def test_idw_heatmap_generation_from_samples(self):
        """Verify IDW 2D interpolation and statistical analysis from survey samples."""
        # Create 16 mock survey samples in a 4x4 coordinate area
        samples = []
        base_lat = 37.7749
        base_lon = -122.4194

        for i in range(4):
            for j in range(4):
                # Strong signal near center (i=1,2, j=1,2), weaker outside
                dist_from_center = abs(i - 1.5) + abs(j - 1.5)
                rssi = -50.0 - (dist_from_center * 15.0)  # ranges from -50 to -95 dBm
                s = SurveySample(
                    index=i * 4 + j + 1,
                    lat=base_lat + i * 0.001,
                    lon=base_lon + j * 0.001,
                    altitude_m=20.0,
                    rssi_dbm=rssi,
                    quality="SIMULATED",
                    timestamp="12:00:00",
                )
                samples.append(s)

        res = RfHeatmapEngine.generate_heatmap_from_samples(samples, grid_resolution=10)

        self.assertIsInstance(res, RfAnalysisResult)
        self.assertEqual(res.total_points, 16)
        self.assertEqual(len(res.cells), 100)  # 10x10 resolution

        # Check statistical ranges
        self.assertGreater(res.max_rssi_dbm, -70.0)
        self.assertLess(res.min_rssi_dbm, -75.0)
        self.assertLess(res.min_rssi_dbm, res.mean_rssi_dbm)
        self.assertLess(res.mean_rssi_dbm, res.max_rssi_dbm)

        # Proportions must sum to 100%
        sum_pct = res.strong_pct + res.good_pct + res.weak_pct + res.no_coverage_pct
        self.assertAlmostEqual(sum_pct, 100.0, places=1)
        self.assertAlmostEqual(res.coverage_pct, res.strong_pct + res.good_pct + res.weak_pct, places=1)

        # Verify GeoJSON FeatureCollection
        geojson = res.to_geojson()
        self.assertEqual(geojson.get("type"), "FeatureCollection")
        self.assertEqual(len(geojson.get("features", [])), 100)
        first_feat = geojson["features"][0]
        self.assertEqual(first_feat["geometry"]["type"], "Polygon")
        self.assertIn("rssi_dbm", first_feat["properties"])
        self.assertIn("color", first_feat["properties"])
        self.assertIn("category", first_feat["properties"])

    def test_heatmap_generation_from_virtual_nodes(self):
        """Verify direct propagation heatmap generation from deployed virtual nodes."""
        node1 = VirtualNode(
            node_id="NODE_001",
            lat=37.7749,
            lon=-122.4194,
            altitude_m=5.0,
            tx_power_dbm=20.0,
        )
        virtual_node_manager.deploy_node(node1)

        res = RfHeatmapEngine.generate_heatmap_from_nodes(
            nodes=virtual_node_manager.get_all_nodes(),
            center_lat=37.7749,
            center_lon=-122.4194,
            radius_m=400.0,
            grid_resolution=12,
        )

        self.assertIsInstance(res, RfAnalysisResult)
        self.assertEqual(res.total_points, 1)
        self.assertEqual(len(res.cells), 144)  # 12x12
        # Max RSSI near center should be strong
        self.assertGreater(res.max_rssi_dbm, -65.0)
        self.assertGreater(res.coverage_pct, 10.0)

    def test_rf_view_analysis_card_and_actions(self):
        """Verify RFView RF ANALYSIS card matching Section 24 UI specification."""
        rf_view = RFView()

        # Check that UI elements exist
        self.assertTrue(hasattr(rf_view, "analysis_card"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_points"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_mean"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_min"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_max"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_coverage"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_weak"))
        self.assertTrue(hasattr(rf_view, "lbl_analysis_no_cov"))
        self.assertTrue(hasattr(rf_view, "btn_gen_heatmap"))
        self.assertTrue(hasattr(rf_view, "btn_clear_heatmap"))

        # Initial clean state
        self.assertEqual(rf_view.lbl_analysis_points.text(), "--")
        self.assertEqual(rf_view.lbl_analysis_mean.text(), "-- dBm")
        self.assertEqual(rf_view.lbl_analysis_coverage.text(), "--%")

        # Deploy a node and generate heatmap via UI button
        node = VirtualNode(
            node_id="NODE_TEST",
            lat=37.7749,
            lon=-122.4194,
            altitude_m=5.0,
            tx_power_dbm=20.0,
        )
        virtual_node_manager.deploy_node(node)

        rf_view.btn_gen_heatmap.click()

        # Check that values updated
        self.assertNotEqual(rf_view.lbl_analysis_points.text(), "--")
        self.assertIn("dBm", rf_view.lbl_analysis_mean.text())
        self.assertIn("%", rf_view.lbl_analysis_coverage.text())
        self.assertIn("%", rf_view.lbl_analysis_weak.text())
        self.assertIn("%", rf_view.lbl_analysis_no_cov.text())
        self.assertEqual(rf_view.lbl_heatmap_badge.text(), "ACTIVE")

        # Test Clear Heatmap action
        rf_view.btn_clear_heatmap.click()
        self.assertEqual(rf_view.lbl_analysis_points.text(), "--")
        self.assertEqual(rf_view.lbl_analysis_mean.text(), "-- dBm")
        self.assertEqual(rf_view.lbl_analysis_coverage.text(), "--%")
        self.assertEqual(rf_view.lbl_heatmap_badge.text(), "READY")

    def test_left_panel_rssi_heatmap_button(self):
        """Verify LeftPanel RSSI Heatmap button is active and functional."""
        panel = LeftPanel()
        self.assertTrue(hasattr(panel, "btn_rssi_heatmap"))
        self.assertTrue(panel.btn_rssi_heatmap.isEnabled())
        self.assertEqual(panel.btn_rssi_heatmap.text(), "RSSI Heatmap")

        # Calling _on_rssi_heatmap directly without active parent window should run safely
        try:
            panel._on_rssi_heatmap()
        except Exception as e:
            self.fail(f"panel._on_rssi_heatmap raised unexpected exception: {e}")

    def test_app_state_heatmap_lifecycle(self):
        """Verify AppState signals and lifecycle methods for Phase 13."""
        received_generated = []
        received_updated = []
        received_cleared = []

        app_state.rssi_heatmap_generated.connect(lambda g: received_generated.append(g))
        app_state.rf_analysis_updated.connect(lambda r: received_updated.append(r))
        app_state.rssi_heatmap_cleared.connect(lambda: received_cleared.append(True))

        # Create sample analysis result
        cell = HeatmapCell(
            row=0,
            col=0,
            lat=37.7749,
            lon=-122.4194,
            rssi_dbm=-60.0,
            category=RfCategory.STRONG,
            color="#2ecc71",
            opacity=0.55,
            bounds=(37.774, -122.420, 37.775, -122.419),
        )
        res = RfAnalysisResult(
            total_points=64,
            mean_rssi_dbm=-61.0,
            min_rssi_dbm=-87.0,
            max_rssi_dbm=-42.0,
            coverage_pct=76.0,
            strong_pct=50.0,
            good_pct=26.0,
            weak_pct=14.0,
            no_coverage_pct=10.0,
            cells=[cell],
        )

        app_state.set_rssi_heatmap(res)

        self.assertEqual(len(received_generated), 1)
        self.assertEqual(len(received_updated), 1)
        self.assertIsNotNone(app_state.rf_analysis_result)
        self.assertEqual(len(app_state.heatmap_cells), 1)

        # Clear heatmap
        app_state.clear_rssi_heatmap()

        self.assertEqual(len(received_cleared), 1)
        self.assertIsNone(app_state.rf_analysis_result)
        self.assertEqual(len(app_state.heatmap_cells), 0)


if __name__ == "__main__":
    unittest.main()
