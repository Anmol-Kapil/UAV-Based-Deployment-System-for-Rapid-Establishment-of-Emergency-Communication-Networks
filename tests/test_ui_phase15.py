"""
tests/test_ui_phase15.py

Phase 15: Adaptive UAV Deployment Algorithm
Unit and integration tests for:
  - DeploymentPriority classification
  - AdaptiveDeploymentPlan construction from GapZones
  - Stage lifecycle (advance / skip / reset)
  - RFView ADAPTIVE DEPLOYMENT card UI
  - AppState Phase 15 signals (adaptive_plan_generated / updated / cleared)
  - map_view.py Phase 15 bridge methods
"""

import sys
import os
import unittest
from dataclasses import dataclass, field
from typing import List

# ── Project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)


# ── Minimal GapZone stub (mirrors Phase 14 GapZone interface) ────────────────

@dataclass
class _GapZone:
    gap_id: str
    centroid_lat: float
    centroid_lon: float
    area_sq_km: float
    gap_severity: str
    mean_rssi_dbm: float = -90.0
    recommended_relay_lat: float = 0.0
    recommended_relay_lon: float = 0.0

    def __post_init__(self):
        if not self.recommended_relay_lat:
            self.recommended_relay_lat = self.centroid_lat
        if not self.recommended_relay_lon:
            self.recommended_relay_lon = self.centroid_lon


def _make_gaps():
    return [
        _GapZone("GAP_001", 37.780, -122.420, 0.18, "CRITICAL", -95.0, 37.780, -122.420),
        _GapZone("GAP_002", 37.760, -122.400, 0.08, "HIGH",     -88.0, 37.760, -122.400),
        _GapZone("GAP_003", 37.790, -122.430, 0.02, "MODERATE", -86.0, 37.790, -122.430),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Class 1: DeploymentPriority classification
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15StagePriority(unittest.TestCase):
    """Test DeploymentPriority tier assignment rules."""

    def setUp(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        self.engine = AdaptiveDeploymentEngine

    def test_critical_by_severity(self):
        p = self.engine._classify_priority(0.05, "CRITICAL")
        self.assertEqual(p, "CRITICAL")

    def test_critical_by_area(self):
        p = self.engine._classify_priority(0.20, "MODERATE")
        self.assertEqual(p, "CRITICAL")

    def test_high_by_severity(self):
        p = self.engine._classify_priority(0.04, "HIGH")
        self.assertEqual(p, "HIGH")

    def test_high_by_area(self):
        p = self.engine._classify_priority(0.10, "MODERATE")
        self.assertEqual(p, "HIGH")

    def test_moderate_default(self):
        p = self.engine._classify_priority(0.01, "MODERATE")
        self.assertEqual(p, "MODERATE")

    def test_priority_order_critical_first(self):
        from gcs.deployment.adaptive_deployment_engine import DeploymentPriority
        self.assertLess(
            DeploymentPriority.ORDER["CRITICAL"],
            DeploymentPriority.ORDER["HIGH"],
        )
        self.assertLess(
            DeploymentPriority.ORDER["HIGH"],
            DeploymentPriority.ORDER["MODERATE"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Class 2: AdaptiveDeploymentPlan construction
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15PlanConstruction(unittest.TestCase):
    """Test build_plan() output correctness."""

    def setUp(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        self.engine = AdaptiveDeploymentEngine
        self.gaps = _make_gaps()

    def test_plan_stage_count(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.assertEqual(plan.total_stages, 3)
        self.assertEqual(len(plan.stages), 3)

    def test_empty_gaps_returns_zero_stage_plan(self):
        plan = self.engine.build_plan([], 37.7749, -122.4194, 78.0, 1.2)
        self.assertEqual(plan.total_stages, 0)
        self.assertEqual(len(plan.stages), 0)

    def test_critical_gap_is_first_stage(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.assertEqual(plan.stages[0].priority, "CRITICAL")
        self.assertEqual(plan.stages[0].gap_id, "GAP_001")

    def test_first_stage_is_active(self):
        from gcs.deployment.adaptive_deployment_engine import StageStatus
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.assertEqual(plan.stages[0].status, StageStatus.ACTIVE)

    def test_other_stages_are_pending(self):
        from gcs.deployment.adaptive_deployment_engine import StageStatus
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        for s in plan.stages[1:]:
            self.assertEqual(s.status, StageStatus.PENDING)

    def test_coverage_estimate_increases(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.assertGreater(
            plan.estimated_coverage_after_pct,
            plan.coverage_before_pct,
        )

    def test_to_dict_has_stages(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        d = plan.to_dict()
        self.assertIn("stages", d)
        self.assertEqual(len(d["stages"]), 3)

    def test_to_geojson_feature_collection(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        gj = plan.to_geojson()
        self.assertEqual(gj["type"], "FeatureCollection")
        # 3 point features + 1 route polyline
        self.assertEqual(len(gj["features"]), 4)

    def test_flight_time_positive(self):
        plan = self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)
        for s in plan.stages:
            self.assertGreater(s.estimated_flight_time_s, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3: Stage lifecycle management
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15StageLifecycle(unittest.TestCase):
    """Test advance_stage, skip_stage, reset_plan."""

    def setUp(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine, StageStatus
        self.engine = AdaptiveDeploymentEngine
        self.StageStatus = StageStatus
        self.gaps = _make_gaps()

    def _build(self):
        return self.engine.build_plan(self.gaps, 37.7749, -122.4194, 78.0, 1.2)

    def test_advance_completes_stage_1(self):
        plan = self._build()
        self.engine.advance_stage(plan)
        self.assertEqual(plan.stages[0].status, self.StageStatus.COMPLETED)

    def test_advance_activates_stage_2(self):
        plan = self._build()
        self.engine.advance_stage(plan)
        self.assertEqual(plan.stages[1].status, self.StageStatus.ACTIVE)

    def test_advance_returns_next_stage(self):
        plan = self._build()
        nxt = self.engine.advance_stage(plan)
        self.assertEqual(nxt.stage_id, "S02")

    def test_skip_marks_stage_skipped(self):
        plan = self._build()
        self.engine.skip_stage(plan)
        self.assertEqual(plan.stages[0].status, self.StageStatus.SKIPPED)

    def test_skip_activates_next(self):
        plan = self._build()
        self.engine.skip_stage(plan)
        self.assertEqual(plan.stages[1].status, self.StageStatus.ACTIVE)

    def test_advance_all_returns_none_at_end(self):
        plan = self._build()
        self.engine.advance_stage(plan)  # S01 -> COMPLETED, S02 ACTIVE
        self.engine.advance_stage(plan)  # S02 -> COMPLETED, S03 ACTIVE
        result = self.engine.advance_stage(plan)  # S03 -> COMPLETED, no more
        self.assertIsNone(result)

    def test_is_complete_after_all_advanced(self):
        plan = self._build()
        for _ in plan.stages:
            self.engine.advance_stage(plan)
        self.assertTrue(plan.is_complete)

    def test_reset_restores_all_pending(self):
        plan = self._build()
        self.engine.advance_stage(plan)
        self.engine.advance_stage(plan)
        self.engine.reset_plan(plan)
        for s in plan.stages:
            if s == plan.stages[0]:
                self.assertEqual(s.status, self.StageStatus.ACTIVE)
            else:
                self.assertEqual(s.status, self.StageStatus.PENDING)

    def test_active_stage_index_advances(self):
        plan = self._build()
        self.assertEqual(plan.active_stage_index, 1)
        self.engine.advance_stage(plan)
        self.assertEqual(plan.active_stage_index, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Class 4: RFView ADAPTIVE DEPLOYMENT card UI
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15RFViewAdaptiveCard(unittest.TestCase):
    """Test the ADAPTIVE DEPLOYMENT card widget in RFView."""

    def setUp(self):
        from gcs.widgets.rf_view import RFView
        self.view = RFView()

    def test_adaptive_card_exists(self):
        self.assertTrue(hasattr(self.view, "adaptive_card"))

    def test_badge_initial_state(self):
        self.assertEqual(self.view.lbl_adp_badge.text(), "READY")

    def test_cov_before_initial(self):
        self.assertEqual(self.view.lbl_adp_cov_before.text(), "78%")

    def test_cov_after_initial(self):
        self.assertEqual(self.view.lbl_adp_cov_after.text(), "--")

    def test_stages_initial(self):
        self.assertEqual(self.view.lbl_adp_stages.text(), "--")

    def test_build_plan_button_exists(self):
        self.assertTrue(hasattr(self.view, "btn_build_plan"))
        self.assertEqual(self.view.btn_build_plan.text(), "BUILD PLAN")

    def test_execute_stage_button_exists(self):
        self.assertTrue(hasattr(self.view, "btn_execute_stage"))
        self.assertEqual(self.view.btn_execute_stage.text(), "EXECUTE STAGE")

    def test_skip_button_exists(self):
        self.assertTrue(hasattr(self.view, "btn_skip_stage"))
        self.assertEqual(self.view.btn_skip_stage.text(), "SKIP")

    def test_reset_button_exists(self):
        self.assertTrue(hasattr(self.view, "btn_reset_plan"))
        self.assertEqual(self.view.btn_reset_plan.text(), "RESET PLAN")

    def test_update_adaptive_ui_sets_badge(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        gaps = _make_gaps()
        plan = AdaptiveDeploymentEngine.build_plan(gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.view._update_adaptive_ui(plan)
        self.assertIn("STAGE", self.view.lbl_adp_badge.text())
        self.assertIn("1/3", self.view.lbl_adp_badge.text())

    def test_update_adaptive_ui_sets_stage_label(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        gaps = _make_gaps()
        plan = AdaptiveDeploymentEngine.build_plan(gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.view._update_adaptive_ui(plan)
        self.assertIn("S01", self.view.lbl_adp_current_stage.text())

    def test_reset_clears_badge(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        gaps = _make_gaps()
        plan = AdaptiveDeploymentEngine.build_plan(gaps, 37.7749, -122.4194, 78.0, 1.2)
        self.view._update_adaptive_ui(plan)
        self.view._on_adaptive_plan_cleared()
        self.assertEqual(self.view.lbl_adp_badge.text(), "READY")

    def test_complete_plan_shows_complete_badge(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        gaps = _make_gaps()
        plan = AdaptiveDeploymentEngine.build_plan(gaps, 37.7749, -122.4194, 78.0, 1.2)
        for _ in plan.stages:
            AdaptiveDeploymentEngine.advance_stage(plan)
        self.view._update_adaptive_ui(plan)
        self.assertEqual(self.view.lbl_adp_badge.text(), "COMPLETE")


# ─────────────────────────────────────────────────────────────────────────────
# Class 5: AppState Phase 15 signals
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15AppStateSignals(unittest.TestCase):
    """Test Phase 15 signals on AppState."""

    def setUp(self):
        from gcs.state.app_state import AppState
        self.state = AppState()
        self.received_plans = []
        self.cleared_count = 0
        self.state.adaptive_plan_generated.connect(self.received_plans.append)
        self.state.adaptive_plan_updated.connect(self.received_plans.append)
        self.state.adaptive_plan_cleared.connect(lambda: setattr(self, "cleared_count", self.cleared_count + 1))

    def _build_plan(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        return AdaptiveDeploymentEngine.build_plan(_make_gaps(), 37.7749, -122.4194, 78.0, 1.2)

    def test_set_adaptive_plan_emits_signal(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        self.assertEqual(len(self.received_plans), 1)

    def test_set_adaptive_plan_stores_plan(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        self.assertIs(self.state.adaptive_plan, plan)

    def test_advance_adaptive_stage_emits_updated(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        before = len(self.received_plans)
        self.state.advance_adaptive_stage()
        self.assertGreater(len(self.received_plans), before)

    def test_skip_adaptive_stage_emits_updated(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        before = len(self.received_plans)
        self.state.skip_adaptive_stage()
        self.assertGreater(len(self.received_plans), before)

    def test_clear_adaptive_plan_emits_cleared(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        self.state.clear_adaptive_plan()
        self.assertEqual(self.cleared_count, 1)

    def test_clear_adaptive_plan_nulls_plan(self):
        plan = self._build_plan()
        self.state.set_adaptive_plan(plan)
        self.state.clear_adaptive_plan()
        self.assertIsNone(self.state.adaptive_plan)

    def test_advance_without_plan_does_not_crash(self):
        # Should silently return
        try:
            self.state.advance_adaptive_stage()
        except Exception as e:
            self.fail(f"advance_adaptive_stage raised unexpectedly: {e}")

    def test_skip_without_plan_does_not_crash(self):
        try:
            self.state.skip_adaptive_stage()
        except Exception as e:
            self.fail(f"skip_adaptive_stage raised unexpectedly: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Class 6: MapView Phase 15 bridge
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase15MapViewBridge(unittest.TestCase):
    """Test on_adaptive_plan_generated / updated / cleared bridge methods."""

    def setUp(self):
        from gcs.widgets.map_view import MapView
        self.map_view = MapView()
        self._js_calls = []
        # Patch _run_js to capture calls without a real web engine
        self.map_view._run_js = lambda js: self._js_calls.append(js)

    def _build_plan(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentEngine
        return AdaptiveDeploymentEngine.build_plan(_make_gaps(), 37.7749, -122.4194, 78.0, 1.2)

    def test_plan_generated_calls_display_js(self):
        plan = self._build_plan()
        self.map_view.on_adaptive_plan_generated(plan)
        self.assertTrue(any("displayAdaptivePlan" in js for js in self._js_calls))

    def test_plan_updated_calls_update_js(self):
        plan = self._build_plan()
        self.map_view.on_adaptive_plan_updated(plan)
        called = any(
            "updateAdaptiveStage" in js or "displayAdaptivePlan" in js
            for js in self._js_calls
        )
        self.assertTrue(called)

    def test_plan_cleared_calls_clear_js(self):
        self.map_view.on_adaptive_plan_cleared()
        self.assertTrue(any("clearAdaptivePlan" in js for js in self._js_calls))

    def test_none_plan_does_not_crash(self):
        try:
            self.map_view.on_adaptive_plan_generated(None)
        except Exception as e:
            self.fail(f"on_adaptive_plan_generated(None) raised: {e}")

    def test_empty_plan_skips_display(self):
        from gcs.deployment.adaptive_deployment_engine import AdaptiveDeploymentPlan
        empty_plan = AdaptiveDeploymentPlan(plan_id="EMPTY", total_stages=0)
        before = len(self._js_calls)
        self.map_view.on_adaptive_plan_generated(empty_plan)
        self.assertEqual(len(self._js_calls), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
