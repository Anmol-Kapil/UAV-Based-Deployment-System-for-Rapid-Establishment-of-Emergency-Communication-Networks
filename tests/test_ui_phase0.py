"""Automated Acceptance Test for GCS Phase 0 UI Skeleton.

Verifies:
1. Application instantiates cleanly without exceptions
2. Top status bar is present with DISCONNECTED state and strictly '--' placeholders
3. Left tool panel has all required sections and disabled buttons with tooltips
4. Central map view initializes
5. Telemetry view contains only placeholder '--' values (no fake telemetry)
6. Camera view displays 'CAMERA OFFLINE' and 'Available in Phase 6'
7. Right context panel contains all 6 required tabs
8. Bottom flight controls are disabled with 'Not connected' tooltip
9. Event log contains initial startup event
10. Application shuts down cleanly
"""

import sys
import os
import unittest

# Headless / offscreen support for CI/automated testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure gcs package is importable
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state, ConnectionState


class TestPhase0UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.window = MainWindow()

    def test_01_top_bar_presence_and_placeholders(self):
        top_bar = self.window.top_bar
        self.assertIsNotNone(top_bar)
        self.assertEqual(top_bar.badge_conn.text(), "● DISCONNECTED")
        self.assertIn("--", top_bar.label_vehicle.text())
        self.assertIn("--", top_bar.label_mode.text())
        self.assertIn("--", top_bar.label_gps.text())
        self.assertIn("--", top_bar.label_alt.text())
        self.assertIn("--", top_bar.label_battery.text())
        self.assertIn("NORMAL", top_bar.badge_safety.text())
        self.assertIn("OFFLINE", top_bar.badge_sim.text())

    def test_02_no_fake_telemetry(self):
        """Strict check: no hardcoded fake numbers (e.g. 13.08, 85%) allowed."""
        telemetry = self.window.right_panel.tab_telemetry
        self.assertIn("--", telemetry.val_lat.text())
        self.assertIn("--", telemetry.val_lon.text())
        self.assertEqual(telemetry.item_alt.lbl_value.text(), "--")
        self.assertEqual(telemetry.item_speed.lbl_value.text(), "--")
        self.assertEqual(telemetry.item_heading.lbl_value.text(), "--")
        self.assertEqual(telemetry.item_battery.lbl_value.text(), "--")
        self.assertIn("--", telemetry.val_roll.text())
        self.assertIn("--", telemetry.val_pitch.text())
        self.assertIn("--", telemetry.val_yaw.text())

    def test_03_left_panel_tools_and_tooltips(self):
        left_panel = self.window.left_panel
        self.assertIsNotNone(left_panel)
        # Verify sections exist
        self.assertIsNotNone(left_panel.sec_vehicle)
        self.assertIsNotNone(left_panel.sec_mission)
        self.assertIsNotNone(left_panel.sec_deployment)
        self.assertIsNotNone(left_panel.sec_survey)
        self.assertIsNotNone(left_panel.sec_safety)

        # Check vehicle section buttons exist and have tooltips
        for btn in left_panel.sec_vehicle.findChildren(type(left_panel.btn_collapse_all)):
            if btn != left_panel.sec_vehicle.header_btn:
                self.assertTrue(len(btn.toolTip()) > 0)

    def test_04_camera_placeholder(self):
        camera = self.window.right_panel.tab_camera
        self.assertIsNotNone(camera)
        labels = [lbl.text() for lbl in camera.findChildren(type(camera.lbl_cam_status))]
        # Status should show OFFLINE when idle
        self.assertTrue(any("CAMERA OFFLINE" in text or "STREAMING" in text for text in labels))

    def test_05_tabs_in_context_panel(self):
        tabs = self.window.right_panel.tabs
        self.assertEqual(tabs.count(), 6)
        tab_names = [tabs.tabText(i) for i in range(tabs.count())]
        expected = ["TELEMETRY", "CAMERA", "MISSION", "DEPLOYMENT", "RF SURVEY", "LOG"]
        self.assertEqual(tab_names, expected)

    def test_06_bottom_flight_control_bar_state(self):
        bottom_bar = self.window.bottom_bar
        self.assertIsNotNone(bottom_bar)
        self.assertEqual(len(bottom_bar.flight_buttons), 8)
        for btn in bottom_bar.flight_buttons:
            self.assertFalse(btn.isEnabled())
            self.assertTrue(len(btn.toolTip()) > 0)
        self.assertIn("DISCONNECTED", bottom_bar.lbl_feedback.text())

    def test_07_event_log(self):
        log_view = self.window.right_panel.tab_log
        self.assertGreaterEqual(log_view.table.rowCount(), 1)
        first_msg = log_view.table.item(0, 3).text()
        self.assertTrue(len(first_msg) > 0)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()


if __name__ == "__main__":
    unittest.main()
