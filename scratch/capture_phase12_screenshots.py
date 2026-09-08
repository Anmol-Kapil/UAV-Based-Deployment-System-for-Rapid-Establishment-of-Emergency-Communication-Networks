"""Headless / GUI screenshot capture script for Phase 12: RF Survey.

Captures:
1. phase12_survey_plan_generated.png (Lawnmower parameters, 20m alt, 20m spacing, 1.2 km², 64 points, READY)
2. phase12_survey_in_progress.png (Survey RUNNING, Progress 32 / 64, Current RSSI -62 dBm, Coverage 73%)
3. phase12_survey_completed.png (Survey COMPLETED, 64/64 points, Full survey metrics & Left Panel actions)
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


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    window.resize(1440, 980)
    window.right_panel.setMinimumWidth(380)
    window.show()
    app.processEvents()

    artifact_dir = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"
    os.makedirs(artifact_dir, exist_ok=True)

    # Deploy an emergency communication node as RF source
    vnode = virtual_node_manager.deploy_node(
        lat=37.7749,
        lon=-122.4194,
        altitude_m=4.5,
        frequency_band="2.4 GHz",
        tx_power_dbm=20.0,
        coverage_radius_m=250.0,
        mission_id="MIS-SURVEY-01"
    )

    # Switch to RF SURVEY tab (index 4)
    right_panel = window.right_panel
    right_panel.tabs.setCurrentIndex(4)
    rf_view = right_panel.rf_view

    # Adjust layout for right panel visibility
    window.splitter.setSizes([220, 720, 500])

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

    # 1. Generate Survey Plan (Section 23 parameters: 20m alt, 20m spacing, 1.2 km², 64 points)
    rf_view.spin_survey_alt.setValue(20.0)
    rf_view.spin_survey_spacing.setValue(20.0)
    rf_view._on_generate_survey()
    app.processEvents()

    # Scroll down to make RF SURVEY card and telemetry progress card front and center
    rf_view.scroll_area.verticalScrollBar().setValue(380)
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 1: Survey Plan Generated (READY)
    p1 = os.path.join(artifact_dir, "phase12_survey_plan_generated.png")
    window.grab().save(p1)
    print(f"Captured: {p1}")

    # 2. Start Survey and Advance to 32/64 points (Section 23: Progress 32 / 64, Current RSSI -62 dBm, Coverage 73%)
    rf_survey_controller.start_survey()
    for _ in range(32):
        rf_survey_controller.step_progress()
    rf_view.scroll_area.verticalScrollBar().setValue(380)
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 2: Survey in Progress (RUNNING, 32/64, RSSI, Coverage)
    p2 = os.path.join(artifact_dir, "phase12_survey_in_progress.png")
    window.grab().save(p2)
    print(f"Captured: {p2}")

    # 3. Advance to 64/64 (COMPLETED)
    for _ in range(32):
        rf_survey_controller.step_progress()
    # Trigger completion
    rf_survey_controller.step_progress()
    rf_view.scroll_area.verticalScrollBar().setValue(380)
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 3: Survey Completed
    p3 = os.path.join(artifact_dir, "phase12_survey_completed.png")
    window.grab().save(p3)
    print(f"Captured: {p3}")

    window.close()
    print("Phase 12 screenshot capture complete!")


if __name__ == "__main__":
    main()
