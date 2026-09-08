"""Headless / GUI screenshot capture script for Phase 11: Simulated RF Propagation Model.

Captures:
1. phase11_rf_model_configuration.png (RF Configuration Panel, Parameters, and [SIMULATED RF] Badge)
2. phase11_rf_coverage_calculated.png (Theoretical RF Metrics & [APPLY TO VIRTUAL NODES] Synchronization)
3. phase11_uav_live_rf_link_telemetry.png (Real-Time UAV-to-Node RF Link, Distance, RSSI & Quality Badge)
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state, ConnectionState
from gcs.deployment.virtual_node_manager import virtual_node_manager
from gcs.rf.rf_model import rf_engine, RfConfig


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    artifact_dir = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"
    os.makedirs(artifact_dir, exist_ok=True)

    # Switch to RF SURVEY tab (index 4)
    right_panel = window.right_panel
    right_panel.tabs.setCurrentIndex(4)
    rf_view = right_panel.rf_view

    # Adjust layout for right panel visibility
    window.splitter.setSizes([200, 740, 500])

    # Mock connected state
    app_state.set_connection(ConnectionState.CONNECTED)
    app_state.update_telemetry({
        "lat": 37.774929,
        "lon": -122.419416,
        "alt_rel": 25.0,
        "groundspeed": 12.0,
        "mode": "GUIDED",
        "battery_remaining": 92
    })
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 1: RF Configuration Panel
    p1 = os.path.join(artifact_dir, "phase11_rf_model_configuration.png")
    window.grab().save(p1)
    print(f"Captured: {p1}")

    # 2. Configure 5.8 GHz & High-Power RF and Calculate Coverage
    rf_view.combo_band.setCurrentText("5.8 GHz")
    rf_view.spin_tx_pwr.setValue(23.0)
    rf_view.combo_env.setCurrentText("Suburban Disaster (2.5)")
    rf_view.spin_n.setValue(2.5)
    rf_view.spin_rx_sens.setValue(-75.0)
    rf_view._on_calculate_coverage()

    # Deploy two virtual nodes and apply RF coverage
    vnode1 = virtual_node_manager.deploy_node(
        lat=37.7760,
        lon=-122.4180,
        altitude_m=4.5,
        frequency_band="5.8 GHz",
        tx_power_dbm=23.0,
        mission_id="MIS-RF-TEST"
    )
    vnode2 = virtual_node_manager.deploy_node(
        lat=37.7790,
        lon=-122.4150,
        altitude_m=4.5,
        frequency_band="5.8 GHz",
        tx_power_dbm=23.0,
        mission_id="MIS-RF-TEST"
    )
    rf_view._on_apply_to_virtual_nodes()
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 2: Calculated RF Coverage & Applied to Virtual Nodes
    p2 = os.path.join(artifact_dir, "phase11_rf_coverage_calculated.png")
    window.grab().save(p2)
    print(f"Captured: {p2}")

    # 3. Stream UAV position near NODE_001 to demonstrate real-time link estimation
    app_state.update_telemetry({
        "lat": 37.7765,
        "lon": -122.4180,
        "alt_rel": 30.0,
        "groundspeed": 8.5
    })
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 3: Real-Time UAV RF Link Telemetry
    p3 = os.path.join(artifact_dir, "phase11_uav_live_rf_link_telemetry.png")
    window.grab().save(p3)
    print(f"Captured: {p3}")

    window.close()
    print("Phase 11 screenshot capture completed successfully.")


if __name__ == "__main__":
    main()
