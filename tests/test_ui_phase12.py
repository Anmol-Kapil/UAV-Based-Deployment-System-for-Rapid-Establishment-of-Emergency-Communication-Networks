"""Unit and Integration Tests for Phase 12: RF Survey.

Validates:
1. Lawnmower (Boustrophedon) survey pattern generation:
   - Alternating transect serpentine directions
   - Line spacing and survey altitude parameters
   - Target waypoint counts and GeoJSON feature structures
2. RF Survey Controller lifecycle and live sampling:
   - State machine (IDLE -> READY -> RUNNING -> PAUSED -> COMPLETED / STOPPED)
   - Simulated RSSI calculation at each waypoint
   - Real-time progress percentage, current RSSI, and coverage metrics matching Section 23
3. RFView UI controls, spinboxes, buttons, and telemetry readout labels
4. LeftPanel survey section integration (Create Survey, Start Survey, Stop Survey)
"""

import unittest
from PySide6.QtWidgets import QApplication

from gcs.state.app_state import app_state
from gcs.rf.survey_generator import LawnmowerSurveyGenerator, survey_generator, SurveyPlan
from gcs.rf.rf_survey_controller import (
    RfSurveyController,
    rf_survey_controller,
    SurveyStatus,
    SurveySample,
    SurveyMetrics,
)
from gcs.widgets.rf_view import RFView
from gcs.widgets.left_panel import LeftPanel
from gcs.deployment.virtual_node_manager import virtual_node_manager, VirtualNode

# Ensure single QApplication instance
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestPhase12Survey(unittest.TestCase):
    """Test suite for Phase 12 RF Survey features."""

    def setUp(self):
        """Reset state before each test."""
        rf_survey_controller.clear_survey()
        virtual_node_manager.clear_nodes()
        app_state.clear_virtual_nodes()

    def tearDown(self):
        """Clean up after test."""
        rf_survey_controller.clear_survey()

    def test_lawnmower_pattern_generation(self):
        """Test Boustrophedon sweep grid math, alternating lines, and waypoint sequence."""
        gen = LawnmowerSurveyGenerator()
        plan = gen.generate(
            center_lat=37.7749,
            center_lon=-122.4194,
            altitude_m=20.0,
            line_spacing_m=20.0,
            target_points=64,
            target_area_km2=1.2,
        )

        self.assertIsInstance(plan, SurveyPlan)
        self.assertEqual(plan.pattern_type, "LAWNMOWER")
        self.assertEqual(plan.altitude_m, 20.0)
        self.assertEqual(plan.line_spacing_m, 20.0)
        self.assertEqual(len(plan.waypoints), 64)
        self.assertAlmostEqual(plan.area_km2, 1.2, places=1)

        # Check serpentine alternating direction
        # Group by transect_id
        transects = {}
        for wp in plan.waypoints:
            transects.setdefault(wp.transect_id, []).append(wp)

        self.assertGreater(len(transects), 1)

        # Transect 1 (even 0-based idx) should have increasing longitude
        t1_lons = [wp.lon for wp in transects[1]]
        self.assertTrue(all(t1_lons[i] <= t1_lons[i + 1] for i in range(len(t1_lons) - 1)))

        # Transect 2 (odd 0-based idx) should have decreasing longitude
        if 2 in transects and len(transects[2]) > 1:
            t2_lons = [wp.lon for wp in transects[2]]
            self.assertTrue(all(t2_lons[i] >= t2_lons[i + 1] for i in range(len(t2_lons) - 1)))

        # Test GeoJSON serialization
        geojson = plan.to_geojson()
        self.assertEqual(geojson.get("type"), "FeatureCollection")
        self.assertGreaterEqual(len(geojson.get("features", [])), 65)  # 1 line + 64 points

    def test_survey_controller_lifecycle_and_sampling(self):
        """Test survey state machine, live stepping, RSSI evaluation, and metric calculation."""
        # Deploy a virtual node to establish an RF source
        v_node = VirtualNode(
            node_id="NODE_001",
            lat=37.7749,
            lon=-122.4194,
            altitude_m=4.5,
            tx_power_dbm=20.0,
            coverage_radius_m=250.0,
        )
        virtual_node_manager.deploy_node(v_node)

        ctrl = rf_survey_controller
        self.assertEqual(ctrl.status, SurveyStatus.IDLE)

        # 1. Generate Survey
        plan = ctrl.generate_survey(altitude_m=20.0, line_spacing_m=20.0, target_points=64)
        self.assertEqual(ctrl.status, SurveyStatus.READY)
        self.assertEqual(len(plan.waypoints), 64)
        self.assertEqual(ctrl.metrics.total_points, 64)
        self.assertEqual(ctrl.metrics.visited_points, 0)

        # 2. Start Survey
        ctrl.start_survey()
        self.assertEqual(ctrl.status, SurveyStatus.RUNNING)

        # 3. Step progress up to 32 points (Progress 32 / 64 = 50%)
        for i in range(32):
            sample = ctrl.step_progress()
            self.assertIsNotNone(sample)
            self.assertEqual(sample.index, i + 1)
            self.assertIsInstance(sample.rssi_dbm, float)
            self.assertIn(sample.quality, ["EXCELLENT", "GOOD", "WEAK", "NO COVERAGE"])

        self.assertEqual(ctrl.metrics.visited_points, 32)
        self.assertAlmostEqual(ctrl.metrics.progress_pct, 50.0, places=1)
        self.assertIsNotNone(ctrl.metrics.current_rssi_dbm)
        self.assertGreaterEqual(ctrl.metrics.coverage_pct, 0.0)
        self.assertLessEqual(ctrl.metrics.coverage_pct, 100.0)
        self.assertIsNotNone(ctrl.metrics.mean_rssi_dbm)

        # 4. Pause & Resume
        ctrl.pause_survey()
        self.assertEqual(ctrl.status, SurveyStatus.PAUSED)
        ctrl.resume_survey()
        self.assertEqual(ctrl.status, SurveyStatus.RUNNING)

        # 5. Complete remaining points (32 -> 64)
        for _ in range(32):
            ctrl.step_progress()

        # Step one more to trigger completion
        ctrl.step_progress()
        self.assertEqual(ctrl.status, SurveyStatus.COMPLETED)
        self.assertEqual(ctrl.metrics.visited_points, 64)
        self.assertAlmostEqual(ctrl.metrics.progress_pct, 100.0, places=1)

        # 6. Clear Survey
        ctrl.clear_survey()
        self.assertEqual(ctrl.status, SurveyStatus.IDLE)
        self.assertIsNone(ctrl.plan)
        self.assertEqual(len(ctrl.samples), 0)

    def test_rf_view_survey_ui(self):
        """Test RFView widget survey controls, buttons, and real-time metric updates."""
        view = RFView()

        # Check initial widgets
        self.assertEqual(view.spin_survey_alt.value(), 20.0)
        self.assertEqual(view.spin_survey_spacing.value(), 20.0)
        self.assertEqual(view.lbl_survey_pattern.text(), "LAWNMOWER")
        self.assertTrue(view.btn_gen_survey.isEnabled())
        self.assertFalse(view.btn_start_survey.isEnabled())
        self.assertFalse(view.btn_stop_survey.isEnabled())

        # Generate Survey via UI button
        view.btn_gen_survey.click()

        self.assertEqual(view.lbl_survey_status_badge.text(), "READY")
        self.assertEqual(view.lbl_survey_points.text(), "64")
        self.assertTrue(view.btn_start_survey.isEnabled())

        # Start Survey via UI button
        view.btn_start_survey.click()
        self.assertEqual(view.lbl_survey_status_badge.text(), "RUNNING")
        self.assertTrue(view.btn_stop_survey.isEnabled())

        # Simulate 16 steps
        for _ in range(16):
            rf_survey_controller.step_progress()

        self.assertIn("16 / 64", view.lbl_survey_progress.text())
        self.assertNotEqual(view.lbl_survey_current_rssi.text(), "-- dBm")

        # Stop Survey
        view.btn_stop_survey.click()
        self.assertEqual(view.lbl_survey_status_badge.text(), "STOPPED")

        # Clear
        view.btn_clear_survey.click()
        self.assertEqual(view.lbl_survey_status_badge.text(), "IDLE")

    def test_left_panel_survey_actions(self):
        """Test LeftPanel Survey section button hookups and actions."""
        panel = LeftPanel()

        self.assertTrue(hasattr(panel, "btn_create_survey"))
        self.assertTrue(hasattr(panel, "btn_start_survey"))
        self.assertTrue(hasattr(panel, "btn_stop_survey"))

        self.assertTrue(panel.btn_create_survey.isEnabled())
        self.assertTrue(panel.btn_start_survey.isEnabled())
        self.assertTrue(panel.btn_stop_survey.isEnabled())

        # Click Create Survey
        panel.btn_create_survey.click()
        self.assertIsNotNone(rf_survey_controller.plan)
        self.assertEqual(rf_survey_controller.status, SurveyStatus.READY)

        # Click Start Survey
        panel.btn_start_survey.click()
        self.assertEqual(rf_survey_controller.status, SurveyStatus.RUNNING)

        # Click Stop Survey
        panel.btn_stop_survey.click()
        self.assertEqual(rf_survey_controller.status, SurveyStatus.STOPPED)


if __name__ == "__main__":
    unittest.main()
