"""Unit and Integration Tests for Phase 14: Coverage Gap & Shadow Detection.

Validates:
1. Gap classification algorithm -- cell clustering (8-neighbourhood connected components).
2. Section 25 metrics computation -- Covered %, Weak %, Uncovered %, GapZone properties.
3. Recommended secondary relay coordinate calculation.
4. RFView Section 25 COVERAGE ANALYSIS card: readouts, badge, [FIND GAPS], [RECALCULATE LOCATIONS].
5. LeftPanel Coverage Analysis button activation (triggers _on_coverage_analysis).
6. AppState Phase 14 signals: coverage_analysis_completed, gaps_updated, gaps_cleared.
"""

import math
import unittest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from gcs.state.app_state import app_state
from gcs.rf.coverage_gap_analyzer import (
    CoverageGapAnalyzer,
    CoverageAnalysisReport,
    CoverageRegionType,
    GapZone,
    coverage_gap_analyzer,
)
from gcs.rf.rf_heatmap import (
    RfHeatmapEngine,
    HeatmapCell,
    RfCategory,
)
from gcs.widgets.rf_view import RFView
from gcs.widgets.left_panel import LeftPanel

# Ensure single QApplication instance
app_instance = QApplication.instance()
if app_instance is None:
    app_instance = QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cell(row, col, rssi):
    """Minimal synthetic HeatmapCell."""
    lat = 37.7749 + row * 0.0005
    lon = -122.4194 + col * 0.0005
    half = 0.00025
    return HeatmapCell(
        row=row, col=col,
        lat=lat, lon=lon,
        rssi_dbm=rssi,
        category=RfCategory.NO_COVERAGE if rssi < -85 else RfCategory.WEAK,
        color="#e74c3c" if rssi < -85 else "#f39c12",
        opacity=0.45,
        bounds=(lat - half, lon - half, lat + half, lon + half),
    )


# ---------------------------------------------------------------------------
# Test 1: Gap Classification & Clustering
# ---------------------------------------------------------------------------

class TestPhase14GapClustering(unittest.TestCase):
    """Test 1 - Connected-component 8-neighbourhood clustering."""

    def test_no_gap_cells_returns_empty(self):
        self.assertEqual(CoverageGapAnalyzer._cluster_adjacent_cells([]), [])

    def test_single_cell_one_cluster(self):
        clusters = CoverageGapAnalyzer._cluster_adjacent_cells([_make_cell(0, 0, -92.0)])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 1)

    def test_adjacent_cells_merge(self):
        cells = [_make_cell(0, 0, -91.0), _make_cell(0, 1, -93.0)]
        clusters = CoverageGapAnalyzer._cluster_adjacent_cells(cells)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_diagonal_adjacency_merges(self):
        cells = [_make_cell(0, 0, -91.0), _make_cell(1, 1, -92.0)]
        clusters = CoverageGapAnalyzer._cluster_adjacent_cells(cells)
        self.assertEqual(len(clusters), 1, "Diagonal neighbours must merge")

    def test_two_separate_blobs(self):
        blob_a = [_make_cell(0, 0, -91.0), _make_cell(0, 1, -92.0)]
        blob_b = [_make_cell(5, 5, -90.0), _make_cell(5, 6, -93.0)]
        clusters = CoverageGapAnalyzer._cluster_adjacent_cells(blob_a + blob_b)
        self.assertEqual(len(clusters), 2)

    def test_3x3_block_is_single_cluster(self):
        cells = [_make_cell(r, c, -91.0) for r in range(3) for c in range(3)]
        clusters = CoverageGapAnalyzer._cluster_adjacent_cells(cells)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 9)


# ---------------------------------------------------------------------------
# Test 2: Section 25 Metrics Computation
# ---------------------------------------------------------------------------

class TestPhase14SectionMetrics(unittest.TestCase):
    """Test 2 - Section 25 coverage metrics and GapZone properties."""

    def _report(self, cells, total_area=1.2):
        hm = MagicMock()
        hm.cells = cells
        return CoverageGapAnalyzer.analyze_gaps(heatmap_result=hm, total_area_km2=total_area)

    def test_all_covered_no_gaps(self):
        cells = [_make_cell(r, c, -60.0) for r in range(4) for c in range(4)]
        report = self._report(cells)
        self.assertAlmostEqual(report.uncovered_pct, 0.0, places=1)
        self.assertEqual(report.gaps_detected, 0)

    def test_mixed_cells_percentages(self):
        covered = [_make_cell(r, c, -60.0) for r in range(2) for c in range(4)]   # 8
        weak    = [_make_cell(2, c, -80.0) for c in range(4)]                      # 4
        gap     = [_make_cell(3, c, -91.0) for c in range(4)]                      # 4
        report = self._report(covered + weak + gap)
        self.assertAlmostEqual(report.covered_pct,    50.0, places=1)
        self.assertAlmostEqual(report.weak_pct,       25.0, places=1)
        self.assertAlmostEqual(report.uncovered_pct,  25.0, places=1)
        self.assertGreater(report.gaps_detected, 0)

    def test_default_section25_specification(self):
        """No-input call must return Section 25 reference values."""
        report = CoverageGapAnalyzer.analyze_gaps()
        self.assertAlmostEqual(report.total_area_km2, 1.2, places=1)
        self.assertAlmostEqual(report.covered_pct,   78.0, places=0)
        self.assertAlmostEqual(report.weak_pct,      12.0, places=0)
        self.assertAlmostEqual(report.uncovered_pct, 10.0, places=0)
        self.assertEqual(report.gaps_detected, 1)

    def test_gap_zone_fields_populated(self):
        hm = MagicMock()
        hm.cells = [_make_cell(0, 0, -91.0)] + [_make_cell(r, c, -60.0) for r in range(3) for c in range(3)]
        report = CoverageGapAnalyzer.analyze_gaps(heatmap_result=hm)
        self.assertGreater(len(report.gaps), 0)
        zone = report.gaps[0]
        self.assertTrue(zone.gap_id.startswith("GAP_"))
        self.assertGreater(zone.area_sq_m, 0)
        self.assertIn(zone.severity, ("CRITICAL", "HIGH", "MODERATE"))

    def test_gap_zone_to_dict_keys(self):
        zone = CoverageGapAnalyzer.analyze_gaps().gaps[0]
        d = zone.to_dict()
        for key in ("gap_id", "centroid", "area_sq_km", "area_sq_m", "cells_count",
                    "mean_rssi_dbm", "severity", "recommended_relay", "bounding_box"):
            self.assertIn(key, d)

    def test_report_to_geojson_featurecollection(self):
        report = CoverageGapAnalyzer.analyze_gaps()
        gj = report.to_geojson()
        self.assertEqual(gj["type"], "FeatureCollection")
        self.assertEqual(len(gj["features"]), report.gaps_detected)
        self.assertEqual(gj["features"][0]["geometry"]["type"], "Polygon")


# ---------------------------------------------------------------------------
# Test 3: Recommended Relay Location
# ---------------------------------------------------------------------------

class TestPhase14RelayLocation(unittest.TestCase):
    """Test 3 - Recommended secondary relay placement coordinates."""

    def test_relay_at_centroid(self):
        hm = MagicMock()
        hm.cells = [_make_cell(r, c, -91.0) for r in range(2) for c in range(2)]
        report = CoverageGapAnalyzer.analyze_gaps(heatmap_result=hm)
        zone = report.gaps[0]
        self.assertAlmostEqual(zone.recommended_relay_lat, zone.centroid_lat, places=5)
        self.assertAlmostEqual(zone.recommended_relay_lon, zone.centroid_lon, places=5)

    def test_largest_gap_sorted_first(self):
        hm = MagicMock()
        small = [_make_cell(0, 0, -91.0)]
        large = [_make_cell(r, c, -91.0) for r in range(3) for c in range(3)]
        hm.cells = small + large + [_make_cell(10, 10, -60.0)]
        report = CoverageGapAnalyzer.analyze_gaps(heatmap_result=hm)
        if len(report.gaps) >= 2:
            self.assertGreaterEqual(report.gaps[0].area_sq_km, report.gaps[1].area_sq_km)

    def test_relay_valid_coordinates(self):
        zone = CoverageGapAnalyzer.analyze_gaps().gaps[0]
        self.assertTrue(math.isfinite(zone.recommended_relay_lat))
        self.assertTrue(math.isfinite(zone.recommended_relay_lon))
        self.assertGreater(zone.recommended_relay_lat, -90)
        self.assertLess(zone.recommended_relay_lat, 90)


# ---------------------------------------------------------------------------
# Test 4: RFView Section 25 Card
# ---------------------------------------------------------------------------

class TestPhase14RFViewCoverageCard(unittest.TestCase):
    """Test 4 - Section 25 COVERAGE ANALYSIS card UI."""

    def setUp(self):
        self.rf_view = RFView()
        app_state.coverage_analysis_report = None
        app_state.detected_gaps = []

    def tearDown(self):
        self.rf_view.close()
        self.rf_view.deleteLater()

    def test_initial_section25_values(self):
        self.assertIn("1.2", self.rf_view.lbl_cov_total_area.text())
        self.assertIn("78", self.rf_view.lbl_cov_covered.text())
        self.assertIn("12", self.rf_view.lbl_cov_weak.text())
        self.assertIn("10", self.rf_view.lbl_cov_uncovered.text())

    def test_find_gaps_button_exists(self):
        self.assertTrue(hasattr(self.rf_view, "btn_find_gaps"))
        self.assertTrue(self.rf_view.btn_find_gaps.isEnabled())

    def test_recalculate_button_exists(self):
        self.assertTrue(hasattr(self.rf_view, "btn_recalc_locations"))
        self.assertTrue(self.rf_view.btn_recalc_locations.isEnabled())

    def test_find_gaps_updates_badge(self):
        self.rf_view._on_find_gaps()
        self.assertNotEqual(self.rf_view.lbl_gap_badge.text(), "READY")

    def test_find_gaps_updates_metrics(self):
        self.rf_view._on_find_gaps()
        self.assertNotIn("--", self.rf_view.lbl_cov_covered.text())
        self.assertNotIn("--", self.rf_view.lbl_cov_weak.text())
        self.assertNotIn("--", self.rf_view.lbl_cov_uncovered.text())

    def test_gaps_cleared_resets_card(self):
        self.rf_view._on_find_gaps()
        self.rf_view._on_gaps_cleared_external()
        self.assertEqual(self.rf_view.lbl_gap_badge.text(), "READY")
        self.assertIn("1.2", self.rf_view.lbl_cov_total_area.text())


# ---------------------------------------------------------------------------
# Test 5: LeftPanel Coverage Analysis
# ---------------------------------------------------------------------------

class TestPhase14LeftPanel(unittest.TestCase):
    """Test 5 - LeftPanel Coverage Analysis button."""

    def setUp(self):
        self.lp = LeftPanel()

    def tearDown(self):
        self.lp.close()
        self.lp.deleteLater()

    def test_button_exists(self):
        self.assertTrue(hasattr(self.lp, "btn_cov_analysis"))

    def test_button_enabled(self):
        self.assertTrue(self.lp.btn_cov_analysis.isEnabled())

    def test_button_text_contains_coverage(self):
        self.assertIn("Coverage", self.lp.btn_cov_analysis.text())

    def test_handler_callable(self):
        self.assertTrue(callable(getattr(self.lp, "_on_coverage_analysis", None)))


# ---------------------------------------------------------------------------
# Test 6: AppState Phase 14 Signals
# ---------------------------------------------------------------------------

class TestPhase14AppStateSignals(unittest.TestCase):
    """Test 6 - Phase 14 signal emissions."""

    def test_signals_declared(self):
        self.assertTrue(hasattr(app_state, "coverage_analysis_completed"))
        self.assertTrue(hasattr(app_state, "gaps_updated"))
        self.assertTrue(hasattr(app_state, "gaps_cleared"))

    def test_coverage_analysis_completed_fires(self):
        received = []
        app_state.coverage_analysis_completed.connect(lambda gj: received.append(gj))
        app_state.set_coverage_analysis_report(CoverageGapAnalyzer.analyze_gaps())
        app_instance.processEvents()
        self.assertGreater(len(received), 0)
        self.assertEqual(received[-1].get("type"), "FeatureCollection")

    def test_gaps_updated_fires(self):
        received = []
        app_state.gaps_updated.connect(lambda gaps: received.append(gaps))
        app_state.set_coverage_analysis_report(CoverageGapAnalyzer.analyze_gaps())
        app_instance.processEvents()
        self.assertGreater(len(received), 0)
        self.assertIsInstance(received[-1], list)

    def test_gaps_cleared_fires(self):
        cleared = []
        app_state.gaps_cleared.connect(lambda: cleared.append(True))
        app_state.clear_coverage_analysis()
        app_instance.processEvents()
        self.assertGreater(len(cleared), 0)

    def test_state_stored_after_set(self):
        report = CoverageGapAnalyzer.analyze_gaps()
        app_state.set_coverage_analysis_report(report)
        self.assertIsNotNone(app_state.coverage_analysis_report)

    def test_state_cleared_after_clear(self):
        app_state.set_coverage_analysis_report(CoverageGapAnalyzer.analyze_gaps())
        app_state.clear_coverage_analysis()
        self.assertIsNone(app_state.coverage_analysis_report)
        self.assertEqual(len(app_state.detected_gaps), 0)


if __name__ == "__main__":
    unittest.main()
