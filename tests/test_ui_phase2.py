"""Phase 2 Automated Test Suite for UAV GCS Functional Map Integration."""

import os
import sys
import time
import unittest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure offscreen Qt platform for CI / headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state, ConnectionState


class TestGCSPhase2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_01_map_view_toolbar_initialization(self):
        """Verify MapView toolbar buttons initialize with expected default states."""
        from gcs.widgets.map_view import MapView

        map_widget = MapView()
        self.assertFalse(map_widget.btn_center_uav.isEnabled(), "Center UAV button should be disabled when disconnected")
        self.assertTrue(map_widget.btn_center_home.isEnabled(), "Center Home button should be enabled by default")
        self.assertEqual(map_widget.btn_follow.text(), "FOLLOW: ON")
        map_widget.deleteLater()

    def test_02_map_follow_mode_toggle(self):
        """Verify follow mode toggling updates AppState and button label."""
        from gcs.widgets.map_view import MapView

        map_widget = MapView()
        self.assertTrue(app_state.map_follow_uav)

        map_widget.toggle_follow_mode()
        self.assertFalse(app_state.map_follow_uav)
        self.assertEqual(map_widget.btn_follow.text(), "FOLLOW: OFF")

        map_widget.toggle_follow_mode()
        self.assertTrue(app_state.map_follow_uav)
        self.assertEqual(map_widget.btn_follow.text(), "FOLLOW: ON")

        map_widget.deleteLater()

    def test_03_telemetry_updates_map_view_state(self):
        """Verify receiving valid coordinates enables Center UAV button."""
        from gcs.widgets.map_view import MapView

        map_widget = MapView()
        self.assertFalse(map_widget.btn_center_uav.isEnabled())

        # Simulate incoming MAVLink telemetry
        telemetry = {
            "lat": 37.7749,
            "lon": -122.4194,
            "alt_rel": 15.5,
            "heading": 45.0,
            "armed": False,
            "mode": "GUIDED"
        }
        map_widget.on_telemetry_updated(telemetry)
        self.app.processEvents()

        self.assertTrue(map_widget.btn_center_uav.isEnabled(), "Center UAV button should enable upon receiving telemetry")

        # Simulate disconnect
        map_widget.on_connection_changed(ConnectionState.DISCONNECTED)
        self.assertFalse(map_widget.btn_center_uav.isEnabled(), "Center UAV button should disable upon disconnect")

        map_widget.deleteLater()

    def test_04_full_ui_map_stream_cycle(self):
        """Verify full integration: Connect mock stream -> map receives position -> Disconnect."""
        window = MainWindow()
        window.show()
        self.app.processEvents()

        # Connect mock stream
        window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)

        start_t = time.time()
        while time.time() - start_t < 0.6:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertEqual(app_state.connection_status, ConnectionState.CONNECTED)
        self.assertTrue(window.map_view.btn_center_uav.isEnabled())

        # Disconnect
        window.disconnect_mavlink()
        self.app.processEvents()

        self.assertEqual(app_state.connection_status, ConnectionState.DISCONNECTED)
        self.assertFalse(window.map_view.btn_center_uav.isEnabled())

        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
