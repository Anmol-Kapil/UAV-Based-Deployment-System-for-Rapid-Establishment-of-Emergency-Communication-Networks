"""Headless / GUI screenshot capture script for Phase 10: Virtual Nodes & Communication Node Lifecycle Management.
Captures:
1. phase10_node_deployment_ready.png (Deployment tab with Node Deployment card in READY state)
2. phase10_virtual_node_deployed_inspector.png (NODE_001 deployed, Telemetry & Radio Inspector active)
3. phase10_multi_node_network_telemetry.png (Multi-node emergency mesh network registered, node inspection)
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state, ConnectionState
from gcs.deployment.virtual_node_manager import virtual_node_manager, VirtualNode

def main():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    artifact_dir = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"
    os.makedirs(artifact_dir, exist_ok=True)

    # 1. Switch to DEPLOYMENT tab
    right_panel = window.right_panel
    # Find DEPLOY tab (index 3)
    right_panel.tabs.setCurrentIndex(3)
    deploy_view = right_panel.deployment_view

    # Optimize layout for right panel inspector visibility
    window.splitter.setSizes([200, 740, 500])

    # Mock connected state
    app_state.set_connection(ConnectionState.CONNECTED)
    app_state.update_telemetry({
        "lat": 37.774929,
        "lon": -122.419416,
        "alt_rel": 25.0,
        "groundspeed": 12.5,
        "mode": "GUIDED",
        "battery_remaining": 88
    })
    app.processEvents()
    time.sleep(0.2)

    # Scroll down to Node Inspector card
    if hasattr(deploy_view, "scroll_area"):
        deploy_view.scroll_area.verticalScrollBar().setValue(deploy_view.scroll_area.verticalScrollBar().maximum())
    app.processEvents()
    time.sleep(0.3)

    # Screenshot 1: Ready to Deploy
    p1 = os.path.join(artifact_dir, "phase10_node_deployment_ready.png")
    window.grab().save(p1)
    print(f"Captured: {p1}")

    # 2. Deploy First Node NODE_001
    vnode1 = virtual_node_manager.deploy_node(
        lat=37.7760,
        lon=-122.4180,
        altitude_m=4.5,
        frequency_band="2.4 GHz",
        tx_power_dbm=20.0,
        mission_id="MIS-EMERGENCY-ALPHA",
        coverage_radius_m=250.0
    )
    virtual_node_manager.update_telemetry("NODE_001", battery_pct=98.5, packets_tx=124, packets_rx=118, connected_clients=4)
    virtual_node_manager.select_node("NODE_001")
    app.processEvents()
    time.sleep(0.4)

    # Screenshot 2: NODE_001 Deployed & Inspected
    p2 = os.path.join(artifact_dir, "phase10_virtual_node_deployed_inspector.png")
    window.grab().save(p2)
    print(f"Captured: {p2}")

    # 3. Deploy Multiple Nodes (NODE_002, NODE_003) to build network
    vnode2 = virtual_node_manager.deploy_node(
        lat=37.7790,
        lon=-122.4150,
        altitude_m=5.0,
        frequency_band="5.8 GHz",
        tx_power_dbm=23.0,
        mission_id="MIS-EMERGENCY-ALPHA",
        coverage_radius_m=300.0
    )
    virtual_node_manager.update_telemetry("NODE_002", battery_pct=100.0, packets_tx=312, packets_rx=298, connected_clients=7)

    vnode3 = virtual_node_manager.deploy_node(
        lat=37.7820,
        lon=-122.4120,
        altitude_m=4.5,
        frequency_band="915 MHz",
        tx_power_dbm=27.0,
        mission_id="MIS-EMERGENCY-ALPHA",
        coverage_radius_m=450.0
    )
    virtual_node_manager.update_telemetry("NODE_003", battery_pct=96.0, packets_tx=89, packets_rx=76, connected_clients=2)

    # Select NODE_002 for inspection
    virtual_node_manager.select_node("NODE_002")
    app.processEvents()
    time.sleep(0.4)

    # Screenshot 3: Multi-node network & Inspector
    p3 = os.path.join(artifact_dir, "phase10_multi_node_network_telemetry.png")
    window.grab().save(p3)
    print(f"Captured: {p3}")

    window.close()
    print("Screenshot capture sequence completed successfully.")

if __name__ == "__main__":
    main()
