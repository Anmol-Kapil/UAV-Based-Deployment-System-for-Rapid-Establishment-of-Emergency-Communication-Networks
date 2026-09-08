"""Phase 1 Automated Test Suite for UAV GCS MAVLink Connection & UI integration."""

import os
import sys
import unittest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure offscreen Qt platform for CI / headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication


class TestGCSPhase1(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_01_pymavlink_and_mock_telemetry(self):
        """Verify pymavlink module and MockTelemetryGenerator."""
        from pymavlink import mavutil
        from gcs.mavlink.mock_telemetry import MockTelemetryGenerator

        generator = MockTelemetryGenerator()
        packet1 = generator.generate_packet(1)
        packet2 = generator.generate_packet(2)

        self.assertIn("lat", packet1)
        self.assertIn("lon", packet1)
        self.assertIn("alt_rel", packet1)
        self.assertIn("battery_pct", packet1)
        self.assertEqual(packet1["system_id"], 1)
        self.assertNotEqual(packet1["lat"], packet2["lat"], "Mock packet coordinates did not update with tick")

    def test_02_connection_dialog_instantiation(self):
        """Verify ConnectionDialog instantiates properly."""
        from gcs.widgets.connection_dialog import ConnectionDialog

        dialog = ConnectionDialog()
        self.assertIsNotNone(dialog)
        conn_str, baud = dialog.get_connection_string()
        self.assertTrue(conn_str.startswith("mock://"), f"Unexpected default conn string: {conn_str}")
        dialog.deleteLater()

    def test_03_mavlink_worker_mock_flow(self):
        """Verify QMavlinkWorker connects in mock mode and emits signals."""
        from gcs.mavlink.mavlink_worker import QMavlinkWorker

        worker = QMavlinkWorker(connection_str="mock://127.0.0.1:14550")
        connected_events = []
        telemetry_events = []

        worker.connected_signal.connect(lambda sysid, compid, vtype: connected_events.append((sysid, compid, vtype)))
        worker.telemetry_updated.connect(lambda d: telemetry_events.append(d))

        worker.start()

        # Wait up to 500ms
        import time
        start_t = time.time()
        while time.time() - start_t < 0.5:
            self.app.processEvents()
            time.sleep(0.05)

        worker.stop()

        self.assertGreater(len(connected_events), 0, "QMavlinkWorker did not emit connected_signal")
        self.assertGreater(len(telemetry_events), 0, "QMavlinkWorker did not emit telemetry_updated")

    def test_04_full_ui_connection_cycle(self):
        """Verify MainWindow connects, updates telemetry readouts, and disconnects cleanly."""
        from gcs.widgets.main_window import MainWindow
        from gcs.state.app_state import app_state, ConnectionState

        window = MainWindow()
        window.show()
        self.app.processEvents()

        # Verify initial DISCONNECTED state
        self.assertEqual(app_state.connection_status, ConnectionState.DISCONNECTED)
        self.assertEqual(window.top_bar.badge_conn.text(), "● DISCONNECTED")
        self.assertEqual(window.right_panel.telemetry_view.val_lat.text(), "LAT: --")

        # Trigger mock connection
        window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)

        import time
        start_t = time.time()
        while time.time() - start_t < 0.6:
            self.app.processEvents()
            time.sleep(0.05)

        # Verify CONNECTED state
        self.assertEqual(app_state.connection_status, ConnectionState.CONNECTED)
        self.assertEqual(window.top_bar.badge_conn.text(), "● CONNECTED")
        self.assertNotEqual(window.right_panel.telemetry_view.val_lat.text(), "LAT: --")
        self.assertTrue(window.left_panel.btn_disconnect.isEnabled())
        self.assertFalse(window.left_panel.btn_connect.isEnabled())

        # Trigger disconnect
        window.disconnect_mavlink()
        self.app.processEvents()

        # Verify DISCONNECTED state and reset placeholders
        self.assertEqual(app_state.connection_status, ConnectionState.DISCONNECTED)
        self.assertEqual(window.top_bar.badge_conn.text(), "● DISCONNECTED")
        self.assertEqual(window.right_panel.telemetry_view.val_lat.text(), "LAT: --")
        self.assertEqual(window.right_panel.telemetry_view.item_alt.lbl_value.text(), "--")

        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
