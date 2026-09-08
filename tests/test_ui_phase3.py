"""Phase 3 Automated Test Suite for UAV GCS Functional Flight Controls."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.state.app_state import app_state, ConnectionState, FlightState


class TestGCSPhase3(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)
        # Reset singleton state before tests
        app_state.reset_telemetry()
        app_state.connection_status = ConnectionState.DISCONNECTED

    def test_01_commands_module_mock_functions(self):
        """Verify all mock command functions return proper result/patch dicts."""
        from gcs.mavlink import commands

        arm = commands.mock_arm()
        self.assertIn("result", arm)
        self.assertEqual(arm["telemetry_patch"]["armed"], True)

        disarm = commands.mock_disarm()
        self.assertEqual(disarm["telemetry_patch"]["armed"], False)

        takeoff = commands.mock_takeoff(10.0)
        self.assertIn("10.0", takeoff["result"])
        self.assertEqual(takeoff["telemetry_patch"]["mode"], "TAKEOFF")

        rtl = commands.mock_rtl()
        self.assertEqual(rtl["telemetry_patch"]["mode"], "RTL")

        land = commands.mock_land()
        self.assertEqual(land["telemetry_patch"]["mode"], "LAND")

        loiter = commands.mock_loiter()
        self.assertEqual(loiter["telemetry_patch"]["mode"], "LOITER")

        guided = commands.mock_guided()
        self.assertEqual(guided["telemetry_patch"]["mode"], "GUIDED")

        manual = commands.mock_manual()
        self.assertEqual(manual["telemetry_patch"]["mode"], "STABILIZE")

        abort = commands.mock_abort()
        self.assertIn("RTL", abort["result"])

    def test_02_confirm_dialog_instantiation(self):
        """Verify ConfirmDialog instantiates with correct defaults."""
        from gcs.widgets.confirm_dialog import ConfirmDialog
        dlg = ConfirmDialog("TEST COMMAND", "Test description text.")
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.get_altitude(), 5.0)  # default when ask_altitude=False

        dlg_alt = ConfirmDialog("TAKEOFF", "Climb.", ask_altitude=True, default_altitude=8.0)
        self.assertAlmostEqual(dlg_alt.get_altitude(), 8.0)
        dlg_alt.deleteLater()
        dlg.deleteLater()

    def test_03_bottom_bar_state_gating(self):
        """Verify bottom bar button states across disconnect → connect → arm → disarm."""
        from gcs.widgets.bottom_bar import BottomBar

        bar = BottomBar()

        # Initial disconnected state
        self.assertFalse(bar.btn_arm.isEnabled())
        self.assertFalse(bar.btn_takeoff.isEnabled())
        self.assertFalse(bar.btn_abort.isEnabled())

        # Simulate connection
        app_state.connection_status = ConnectionState.CONNECTED
        bar._on_connection_changed(ConnectionState.CONNECTED)
        self.app.processEvents()

        self.assertTrue(bar.btn_arm.isEnabled(), "ARM should enable when connected+DISARMED")
        self.assertFalse(bar.btn_takeoff.isEnabled(), "TAKEOFF should remain disabled until ARMED")
        self.assertTrue(bar.btn_abort.isEnabled(), "ABORT always enabled when connected")

        # Simulate armed state
        bar._on_arm_state_changed(FlightState.ARMED)
        self.app.processEvents()

        self.assertTrue(bar.btn_takeoff.isEnabled(), "TAKEOFF should enable after ARM")
        self.assertTrue(bar.btn_rtl.isEnabled(), "RTL should enable after ARM")
        self.assertTrue(bar.btn_land.isEnabled(), "LAND should enable after ARM")
        self.assertEqual(bar.btn_arm.text(), "DISARM")

        # Simulate disarm
        bar._on_arm_state_changed(FlightState.DISARMED)
        self.app.processEvents()
        self.assertFalse(bar.btn_takeoff.isEnabled())
        self.assertEqual(bar.btn_arm.text(), "ARM")

        # Simulate disconnect
        bar._on_connection_changed(ConnectionState.DISCONNECTED)
        self.assertFalse(bar.btn_arm.isEnabled())
        self.assertFalse(bar.btn_abort.isEnabled())

        bar.deleteLater()

    def test_04_full_ui_arm_disarm_cycle(self):
        """Verify complete UI arm/disarm command cycle via mock stream."""
        from gcs.widgets.main_window import MainWindow

        window = MainWindow()
        window.show()
        self.app.processEvents()

        # Connect mock stream
        window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)

        start_t = time.time()
        while time.time() - start_t < 0.5:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertEqual(app_state.connection_status, ConnectionState.CONNECTED)
        self.assertTrue(window.bottom_bar.btn_arm.isEnabled())
        self.assertFalse(window.bottom_bar.btn_takeoff.isEnabled())

        # Simulate arm command dispatch (bypass dialog)
        from gcs.mavlink import commands as cmds
        window._mav_worker.dispatch_mock(cmds.mock_arm())

        start_t = time.time()
        while time.time() - start_t < 0.3:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertEqual(app_state.arm_state, FlightState.ARMED)
        self.assertTrue(window.bottom_bar.btn_takeoff.isEnabled())
        self.assertEqual(window.bottom_bar.btn_arm.text(), "DISARM")

        # Simulate disarm
        window._mav_worker.dispatch_mock(cmds.mock_disarm())

        start_t = time.time()
        while time.time() - start_t < 0.3:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertEqual(app_state.arm_state, FlightState.DISARMED)
        self.assertFalse(window.bottom_bar.btn_takeoff.isEnabled())

        window.disconnect_mavlink()
        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
