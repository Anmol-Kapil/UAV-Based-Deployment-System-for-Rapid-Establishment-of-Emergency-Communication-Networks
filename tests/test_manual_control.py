"""Phase 17 Automated Test Suite for Manual Remote Control & Flight Operations."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from gcs.state.app_state import app_state, ConnectionState, FlightState


class TestManualControl(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)
        cls._reset_state()

    @classmethod
    def tearDownClass(cls):
        cls._reset_state()

    def setUp(self):
        self._reset_state()

    def tearDown(self):
        self._reset_state()

    @classmethod
    def _reset_state(cls):
        app_state.reset_telemetry()
        app_state.set_connection(ConnectionState.DISCONNECTED)
        app_state.arm_state = FlightState.DISARMED

    def test_01_commands_manual_control(self):
        """Verify send_manual_control and mock_manual_control."""
        from gcs.mavlink import commands

        mock_res = commands.mock_manual_control(500, -500, 700, 200)
        self.assertIn("MANUAL CONTROL", mock_res["result"])
        self.assertEqual(mock_res["telemetry_patch"]["mode"], "POSCTL")

        mock_posctl = commands.mock_posctl()
        self.assertEqual(mock_posctl["telemetry_patch"]["mode"], "POSCTL")

        mock_altctl = commands.mock_altctl()
        self.assertEqual(mock_altctl["telemetry_patch"]["mode"], "ALTCTL")

        # Test send_manual_control with mock mav
        mock_mav = MagicMock()
        res = commands.send_manual_control(mock_mav, 400, -200, 600, 0)
        self.assertIn("MANUAL_CONTROL", res)
        mock_mav.mav.manual_control_send.assert_called_once()

    def test_02_send_takeoff_with_coordinates(self):
        """Verify send_takeoff passes coordinates or NaN appropriately."""
        from gcs.mavlink import commands

        mock_mav = MagicMock()
        mock_mav.target_system = 1
        mock_mav.target_component = 1

        res = commands.send_takeoff(mock_mav, altitude=10.0, lat=37.7749, lon=-122.4194)
        self.assertIn("TARGET ALT: 10.0 m", res)
        # Verify MAV_CMD_NAV_TAKEOFF was sent
        calls = mock_mav.mav.command_long_send.call_args_list
        self.assertGreaterEqual(len(calls), 2)
        takeoff_call = calls[1]
        self.assertEqual(takeoff_call[0][2], 22)  # MAV_CMD_NAV_TAKEOFF = 22
        self.assertEqual(takeoff_call[0][8], 37.7749)
        self.assertEqual(takeoff_call[0][9], -122.4194)
        self.assertEqual(takeoff_call[0][10], 10.0)

    def test_03_worker_manual_control_methods(self):
        """Verify QMavlinkWorker manual control state methods."""
        from gcs.mavlink.mavlink_worker import QMavlinkWorker

        worker = QMavlinkWorker("mock://127.0.0.1:14550")
        self.assertEqual(worker._manual_z, 500)
        self.assertFalse(worker._manual_active)

        worker.set_manual_control(x=600, y=-300, z=750, r=400, active=True)
        self.assertEqual(worker._manual_x, 600)
        self.assertEqual(worker._manual_y, -300)
        self.assertEqual(worker._manual_z, 750)
        self.assertEqual(worker._manual_r, 400)
        self.assertTrue(worker._manual_active)

        worker.stop_manual_control()
        self.assertEqual(worker._manual_x, 0)
        self.assertEqual(worker._manual_y, 0)
        self.assertEqual(worker._manual_z, 500)
        self.assertEqual(worker._manual_r, 0)
        self.assertFalse(worker._manual_active)

    def test_04_manual_control_view_widget(self):
        """Verify ManualControlView widget initialization and interactions."""
        from gcs.widgets.manual_control_view import ManualControlView
        from gcs.mavlink.mavlink_worker import QMavlinkWorker

        view = ManualControlView()
        self.assertIsNotNone(view)

        # Initial disconnected state
        app_state.set_connection(ConnectionState.DISCONNECTED)
        self.assertFalse(view.btn_takeoff.isEnabled())
        self.assertFalse(view.btn_forward.isEnabled())

        # Connected state
        app_state.set_connection(ConnectionState.CONNECTED)
        self.assertTrue(view.btn_takeoff.isEnabled())
        self.assertTrue(view.btn_forward.isEnabled())
        self.assertTrue(view.btn_posctl.isEnabled())
        self.assertTrue(view.btn_loiter.isEnabled())

        # Worker injection
        worker = QMavlinkWorker("mock://127.0.0.1:14550")
        view.set_worker(worker)

        # Simulate D-pad press and release
        view._start_motion(dx=500)
        self.assertTrue(worker._manual_active)
        self.assertEqual(worker._manual_x, 500)

        view._stop_motion()
        self.assertFalse(worker._manual_active)
        self.assertEqual(worker._manual_x, 0)

        # Telemetry updates
        view._on_telemetry_updated({"mode": "POSCTL", "armed": True, "alt_rel": 5.2, "groundspeed": 3.1})
        self.assertIn("POSCTL", view.lbl_hud_mode.text())
        self.assertIn("ARMED", view.lbl_hud_arm.text())
        self.assertIn("5.2", view.lbl_hud_alt.text())
        self.assertIn("3.1", view.lbl_hud_spd.text())

        view.deleteLater()

    def test_05_keyboard_flight_events(self):
        """Verify keyboard key presses map to directional motion."""
        from gcs.widgets.manual_control_view import ManualControlView
        from gcs.mavlink.mavlink_worker import QMavlinkWorker

        view = ManualControlView()
        worker = QMavlinkWorker("mock://127.0.0.1:14550")
        view.set_worker(worker)

        # Press 'W' for forward
        press_w = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_W, Qt.KeyboardModifier.NoModifier)
        view.keyPressEvent(press_w)
        self.assertIn(Qt.Key.Key_W, view._active_keys)
        self.assertEqual(worker._manual_x, 500)

        # Release 'W'
        rel_w = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_W, Qt.KeyboardModifier.NoModifier)
        view.keyReleaseEvent(rel_w)
        self.assertNotIn(Qt.Key.Key_W, view._active_keys)
        self.assertFalse(worker._manual_active)

        view.deleteLater()

    def test_06_left_panel_manual_flight_integration(self):
        """Verify MANUAL REMOTE FLIGHT section is present in LeftPanel."""
        from gcs.widgets.left_panel import LeftPanel

        panel = LeftPanel()
        self.assertIsNotNone(panel.sec_manual)
        self.assertIsNotNone(panel.manual_control_view)

        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
