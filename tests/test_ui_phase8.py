"""Unit and integration tests for Phase 8: Deployment Algorithm & Coverage Optimization."""

import os
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure headless Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance() or QApplication([])

from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.disaster.disaster_manager import get_preset_scenarios, DisasterArea
from gcs.deployment.coverage_optimizer import (
    CandidateSite,
    OptimizationConfig,
    OptimizationResult,
    generate_candidate_grid,
    optimize_placement,
    generate_deployment_mission,
    point_in_polygon,
    haversine_distance_m,
)
from gcs.widgets.deployment_view import DeploymentView
from gcs.widgets.left_panel import LeftPanel


class TestUIPhase8(unittest.TestCase):
    """Test suite for Phase 8 Candidate Generation, Optimization & UI integration."""

    def setUp(self):
        app_state.clear_disaster_area()
        app_state.clear_hazard_zones()
        app_state.clear_candidates()
        app_state.clear_deployment_target()

    def tearDown(self):
        app_state.clear_disaster_area()
        app_state.clear_hazard_zones()
        app_state.clear_candidates()
        app_state.clear_deployment_target()

    def test_01_candidate_grid_generation(self):
        """Test candidate lattice generation strictly bounded inside disaster polygon."""
        presets = get_preset_scenarios()
        flood_area = presets["SF Flash Flood (1.2 km²)"]
        self.assertGreater(len(flood_area.vertices), 2)

        # Generate candidates with 100m grid resolution
        candidates = generate_candidate_grid(flood_area, grid_resolution_m=100.0)
        self.assertGreater(len(candidates), 5, "Should generate multiple candidates within 1.2 km² polygon")

        # Verify all candidates are strictly inside the disaster polygon
        poly_coords = [(v.lat, v.lon) for v in flood_area.vertices]
        for c in candidates:
            self.assertTrue(
                point_in_polygon(c.lat, c.lon, poly_coords),
                f"Candidate {c.candidate_id} ({c.lat}, {c.lon}) must be inside polygon"
            )
            self.assertEqual(c.coverage_radius_m, 250.0)
            self.assertFalse(c.is_selected)

    def test_02_hazard_exclusion_filtering(self):
        """Test that candidates falling within hazard zones and safety buffers are rejected."""
        presets = get_preset_scenarios()
        quake_area = presets["Urban Earthquake (0.85 km²)"]
        hazards = quake_area.hazard_zones
        self.assertGreaterEqual(len(hazards), 2, "Urban Earthquake preset should have hazard zones")

        hazard_buffer = 25.0
        candidates = generate_candidate_grid(
            quake_area,
            grid_resolution_m=70.0,
            hazard_zones=hazards,
            hazard_buffer_m=hazard_buffer
        )
        self.assertGreater(len(candidates), 3)

        # Check every candidate against all hazard exclusion zones
        for c in candidates:
            for hz in hazards:
                dist = haversine_distance_m(c.lat, c.lon, hz.lat, hz.lon)
                min_safe_dist = hz.radius_m + hazard_buffer
                self.assertGreaterEqual(
                    dist, min_safe_dist - 0.1,
                    f"Candidate {c.candidate_id} at {dist:.1f}m violates hazard '{hz.name}' ({min_safe_dist:.1f}m)"
                )

    def test_03_coverage_optimization_algorithm(self):
        """Test greedy maximum coverage optimization and metric computation."""
        presets = get_preset_scenarios()
        area = presets["Urban Earthquake (0.85 km²)"]
        candidates = generate_candidate_grid(area, grid_resolution_m=80.0, hazard_zones=area.hazard_zones)

        cfg = OptimizationConfig(num_nodes=3, coverage_radius_m=250.0, grid_resolution_m=80.0)
        result = optimize_placement(candidates, area, cfg, area.hazard_zones)

        self.assertIsInstance(result, OptimizationResult)
        self.assertGreater(result.total_area_m2, 0.0)
        self.assertGreater(result.covered_area_m2, 0.0)
        self.assertGreater(result.coverage_percent, 20.0, "3 nodes with 250m radius should cover >20% of area")
        self.assertLessEqual(result.coverage_percent, 100.0)
        self.assertGreaterEqual(result.overlap_percent, 0.0)

        # Exactly 3 nodes should be selected
        selected = [c for c in candidates if c.is_selected]
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(result.selected_candidates), 3)

        # Each selected node should have positive score and covered area
        for sel in selected:
            self.assertGreater(sel.score, 0.0)
            self.assertGreater(sel.covered_area_m2, 0.0)
            self.assertGreater(sel.coverage_ratio, 0.0)

    def test_04_deployment_mission_generation_and_ui_sync(self):
        """Test mission waypoint assembly, DeploymentView optimization card, and LeftPanel actions."""
        # 1. Mission Generation
        fake_candidates = [
            CandidateSite("C-01", 37.7750, -122.4180, alt=25.0, is_selected=True),
            CandidateSite("C-02", 37.7780, -122.4210, alt=25.0, is_selected=True),
        ]
        mission = generate_deployment_mission(fake_candidates, home_lat=37.7749, home_lon=-122.4194)
        self.assertEqual(len(mission), 4)  # Takeoff, Drop 1, Drop 2, RTL
        self.assertEqual(mission[0]["command"], "TAKEOFF")
        self.assertEqual(mission[1]["command"], "WAYPOINT")
        self.assertEqual(mission[2]["command"], "WAYPOINT")
        self.assertEqual(mission[3]["command"], "RTL")

        # 2. DeploymentView UI & Optimizer Trigger
        dv = DeploymentView()
        presets = get_preset_scenarios()
        quake_area = presets["Urban Earthquake (0.85 km²)"]
        app_state.set_disaster_area(quake_area)
        app_state.set_hazard_zones(quake_area.hazard_zones)

        # Configure parameters and click optimize
        dv.spin_num_nodes.setValue(3)
        dv.spin_rf_radius.setValue(250.0)
        dv.spin_grid_res.setValue(80.0)
        dv.btn_optimize.click()

        # Verify candidate table is populated
        self.assertGreater(dv.table_candidates.rowCount(), 0)
        self.assertIn("NODES OPTIMIZED", dv.lbl_algo_status.text())
        self.assertIn("Coverage:", dv.lbl_opt_metrics.text())

        # Verify selecting a candidate updates target coordinates
        first_row_item = dv.table_candidates.item(0, 1)
        self.assertIsNotNone(first_row_item)
        dv.table_candidates.itemClicked.emit(first_row_item)
        self.assertIsNotNone(app_state.selected_candidate)
        self.assertAlmostEqual(dv.spin_lat.value(), app_state.selected_candidate.lat, places=4)

        # 3. LeftPanel Tool Action Integration
        lp = LeftPanel()
        self.assertTrue(lp.btn_analyze_cov.isEnabled())
        self.assertTrue(lp.btn_gen_cand.isEnabled())
        self.assertTrue(lp.btn_sel_loc.isEnabled())
        self.assertTrue(lp.btn_gen_mission.isEnabled())

        # Generate Mission from UI button
        dv.btn_gen_mission.click()
        self.assertGreaterEqual(len(app_state.mission_waypoints), 3)


if __name__ == "__main__":
    unittest.main()
