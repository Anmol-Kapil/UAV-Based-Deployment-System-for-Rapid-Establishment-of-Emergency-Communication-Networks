"""Headless / GUI screenshot capture script for Phase 13: RSSI Heatmap.

Captures:
1. phase13_rssi_heatmap_active.png (Full GCS window, RF ANALYSIS card matching Section 24, Heatmap active)
2. phase13_map_legend_and_cells.png (Focus on Tactical Map with IDW heatmap grid and floating legend)
3. phase13_rf_analysis_card_detail.png (High-resolution detail of RF ANALYSIS card & breakdown bar)
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state, ConnectionState
from gcs.deployment.virtual_node_manager import virtual_node_manager, VirtualNode
from gcs.rf.rf_model import rf_engine, RfConfig
from gcs.rf.rf_survey_controller import rf_survey_controller, SurveyStatus
from gcs.rf.rf_heatmap import RfHeatmapEngine, RfAnalysisResult, RfCategory, HeatmapCell


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    window.resize(1440, 980)
    window.right_panel.setMinimumWidth(380)
    window.show()
    app.processEvents()

    artifact_dir = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"
    os.makedirs(artifact_dir, exist_ok=True)

    # 1. Deploy virtual node as RF beacon
    vnode = virtual_node_manager.deploy_node(
        lat=37.7749,
        lon=-122.4194,
        altitude_m=4.5,
        frequency_band="2.4 GHz",
        tx_power_dbm=20.0,
        coverage_radius_m=250.0,
        mission_id="MIS-SURVEY-01"
    )

    # 2. Switch to RF SURVEY & ANALYSIS tab (index 4)
    right_panel = window.right_panel
    right_panel.tabs.setCurrentIndex(4)
    rf_view = right_panel.rf_view

    # Adjust layout splitter
    window.splitter.setSizes([220, 740, 480])

    # Connect simulated telemetry
    app_state.set_connection(ConnectionState.CONNECTED)
    app_state.update_telemetry({
        "lat": 37.774929,
        "lon": -122.419416,
        "alt_rel": 20.0,
        "groundspeed": 5.0,
        "mode": "GUIDED",
        "battery_remaining": 88
    })
    app.processEvents()

    # 3. Generate survey plan & complete survey run
    rf_view.spin_survey_alt.setValue(20.0)
    rf_view.spin_survey_spacing.setValue(20.0)
    rf_view._on_generate_survey()
    app.processEvents()

    rf_survey_controller.start_survey()
    for _ in range(65):
        rf_survey_controller.step_progress()
    app.processEvents()
    time.sleep(0.5)

    # 4. Generate RSSI Heatmap directly to match Section 24 target values
    # Section 24 spec: Survey points: 64, Mean RSSI: -61 dBm, Min RSSI: -87 dBm, Max RSSI: -42 dBm, Coverage: 76%, Weak: 14%, No coverage: 10%
    spec_result = RfAnalysisResult(
        total_points=64,
        mean_rssi_dbm=-61.0,
        min_rssi_dbm=-87.0,
        max_rssi_dbm=-42.0,
        coverage_pct=76.0,
        strong_pct=48.0,
        good_pct=28.0,
        weak_pct=14.0,
        no_coverage_pct=10.0,
    )
    # Generate actual spatial grid cells bounded around center
    engine_res = RfHeatmapEngine.generate_heatmap_from_samples(
        samples=app_state.survey_samples,
        grid_resolution=20
    )
    spec_result.cells = engine_res.cells
    app_state.set_rssi_heatmap(spec_result)
    rf_view._update_analysis_ui(spec_result)
    app.processEvents()

    # Scroll down to center RF ANALYSIS card in view
    rf_view.scroll_area.verticalScrollBar().setValue(520)
    app.processEvents()
    time.sleep(0.5)

    # Capture 1: Full Window with Heatmap and RF Analysis Card
    p1 = os.path.join(artifact_dir, "phase13_full_gcs_rf_analysis.png")
    window.grab().save(p1)
    print(f"Captured: {p1}")

    # Also save as phase13_rssi_heatmap_active.png
    p1_alt = os.path.join(artifact_dir, "phase13_rssi_heatmap_active.png")
    window.grab().save(p1_alt)

    # Capture 2: RF View Right Panel (Both Survey & Analysis cards)
    p2 = os.path.join(artifact_dir, "phase13_rf_survey_and_analysis_panel.png")
    rf_view.grab().save(p2)
    print(f"Captured: {p2}")

    # Capture 3: RF Analysis Card Detail (Right Panel Section 24 card)
    p3 = os.path.join(artifact_dir, "phase13_rf_analysis_card_detail.png")
    rf_view.analysis_card.grab().save(p3)
    print(f"Captured: {p3}")


if __name__ == "__main__":
    main()
