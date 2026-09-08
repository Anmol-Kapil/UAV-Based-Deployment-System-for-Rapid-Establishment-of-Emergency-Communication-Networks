"""Automated Unit & Integration Tests for Phase 7: Disaster-Area Planning."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

# Ensure application exists
app = QApplication.instance() or QApplication(sys.argv)

from gcs.state.app_state import app_state, ConnectionState
from gcs.disaster.disaster_manager import (
    DisasterVertex,
    HazardZone,
    DisasterArea,
    get_preset_scenarios,
)
from gcs.widgets.deployment_view import DeploymentView
from gcs.widgets.left_panel import LeftPanel


class TestPhase7DisasterAreaPlanning(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app_state.reset_telemetry()
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.clear_disaster_area()
        app_state.clear_hazard_zones()

    def setUp(self):
        app_state.reset_telemetry()
        app_state.clear_disaster_area()
        app_state.clear_hazard_zones()

    def test_01_disaster_manager_geometry_and_geojson(self):
        """Test DisasterArea spherical area calculation, perimeter, centroid, and GeoJSON conversion."""
        # Setup 4-point quadrilateral (approx 1 km square)
        # 37.77 to 37.78 is ~1.11 km, -122.42 to -122.41 is ~0.88 km
        v1 = DisasterVertex(lat=37.7700, lon=-122.4200, seq=1)
        v2 = DisasterVertex(lat=37.7800, lon=-122.4200, seq=2)
        v3 = DisasterVertex(lat=37.7800, lon=-122.4100, seq=3)
        v4 = DisasterVertex(lat=37.7700, lon=-122.4100, seq=4)

        hz = HazardZone(zone_id="HZ-01", name="Chemical Spill NFZ", lat=37.7750, lon=-122.4150, radius_m=150.0)

        area = DisasterArea(
            name="Test Quad Sector",
            description="Unit test disaster area",
            vertices=[v1, v2, v3, v4],
            hazard_zones=[hz],
        )

        # Spherical area calculation
        area_m2 = area.calculate_area_sq_meters()
        self.assertGreater(area_m2, 500000.0)  # At least 0.5 km²
        self.assertLess(area_m2, 2000000.0)    # Less than 2 km²

        # Perimeter calculation
        perim_m = area.calculate_perimeter_meters()
        self.assertGreater(perim_m, 3000.0)    # Around 4 km

        # Centroid
        c_lat, c_lon = area.calculate_centroid()
        self.assertAlmostEqual(c_lat, 37.7750, places=3)
        self.assertAlmostEqual(c_lon, -122.4150, places=3)

        # Dict serialization round-trip
        d = area.to_dict()
        self.assertEqual(d["name"], "Test Quad Sector")
        self.assertEqual(len(d["vertices"]), 4)
        self.assertEqual(len(d["hazard_zones"]), 1)

        area_rec = DisasterArea.from_dict(d)
        self.assertEqual(area_rec.name, area.name)
        self.assertEqual(len(area_rec.vertices), 4)

        # GeoJSON serialization round-trip
        geojson = area.to_geojson()
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 2)  # 1 Polygon + 1 Hazard Point

        area_from_geo = DisasterArea.from_geojson(geojson)
        self.assertEqual(len(area_from_geo.vertices), 4)
        self.assertEqual(len(area_from_geo.hazard_zones), 1)
        self.assertEqual(area_from_geo.hazard_zones[0].name, "Chemical Spill NFZ")

    def test_02_scenario_presets(self):
        """Test loading built-in realistic emergency disaster scenario presets."""
        presets = get_preset_scenarios()
        self.assertGreaterEqual(len(presets), 3)

        for name, area in presets.items():
            self.assertTrue(len(area.vertices) >= 4, f"Preset {name} must have at least 4 vertices")
            area_km2 = area.calculate_area_sq_meters() / 1e6
            self.assertGreater(area_km2, 0.5, f"Preset {name} must cover > 0.5 km²")
            self.assertTrue(len(area.hazard_zones) >= 1, f"Preset {name} must include at least 1 hazard zone")

    def test_03_interactive_drawing_flow(self):
        """Test interactive polygon vertex accumulation and finish/cancel drawing workflow."""
        state = app_state

        # Start drawing mode
        state.start_area_drawing()
        self.assertTrue(state.is_drawing_area)
        self.assertEqual(state.map_click_mode, "DRAW_DISASTER_AREA")
        self.assertEqual(len(state.temp_area_vertices), 0)

        # Add 3 vertices
        state.add_drawing_vertex(37.7780, -122.4220)
        state.add_drawing_vertex(37.7810, -122.4160)
        state.add_drawing_vertex(37.7740, -122.4140)
        self.assertEqual(len(state.temp_area_vertices), 3)

        # Test pop / undo last vertex
        state.pop_drawing_vertex()
        self.assertEqual(len(state.temp_area_vertices), 2)

        # Cannot finish with only 2 vertices
        res = state.finish_area_drawing()
        self.assertIsNone(res)
        self.assertTrue(state.is_drawing_area)

        # Add 2 more vertices and finish
        state.add_drawing_vertex(37.7740, -122.4140)
        state.add_drawing_vertex(37.7730, -122.4200)
        self.assertEqual(len(state.temp_area_vertices), 4)

        completed_area = state.finish_area_drawing(name="Incident Zone Bravo")
        self.assertIsNotNone(completed_area)
        self.assertFalse(state.is_drawing_area)
        self.assertEqual(state.map_click_mode, "NAV")
        self.assertIsNotNone(state.disaster_area)
        self.assertEqual(state.disaster_area.name, "Incident Zone Bravo")
        self.assertEqual(len(state.disaster_area.vertices), 4)
        self.assertGreater(state.disaster_area.calculate_area_sq_meters(), 10000.0)

    def test_04_ui_left_panel_and_deployment_view(self):
        """Test LeftPanel Define Area button and DeploymentView disaster management console."""
        view = DeploymentView()
        left_panel = LeftPanel()
        state = app_state

        # LeftPanel btn_define_area should be enabled in Phase 7
        self.assertTrue(left_panel.btn_define_area.isEnabled())

        # Clicking Define Area starts map drawing mode
        left_panel.btn_define_area.click()
        self.assertTrue(state.is_drawing_area)
        self.assertEqual(state.map_click_mode, "DRAW_DISASTER_AREA")
        state.cancel_area_drawing()

        # Test selecting scenario preset in DeploymentView
        self.assertIn("NO AREA DEFINED", view.lbl_area_name.text())
        # Index 1 is SF Flash Flood
        view.combo_area_preset.setCurrentIndex(1)
        app.processEvents()

        self.assertIsNotNone(state.disaster_area)
        self.assertIn("Flood", view.lbl_area_name.text())
        self.assertIn("km²", view.lbl_area_metrics.text())
        self.assertGreater(len(state.hazard_zones), 0)

        # Test Clear Area button
        view.btn_clear_area.click()
        app.processEvents()

        self.assertIsNone(state.disaster_area)
        self.assertEqual(len(state.hazard_zones), 0)
        self.assertIn("NO AREA DEFINED", view.lbl_area_name.text())
        self.assertIn("0", view.lbl_area_metrics.text())

        view.deleteLater()
        left_panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
