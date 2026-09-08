"""Phase 18 Automated Test Suite for MAVSDK Engine Integration."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.mavlink.mavsdk_worker import QMavsdkWorker, normalize_mavsdk_address
from gcs.mavlink.mission_manager import Waypoint, MissionPlan as LocalMissionPlan


class TestMavsdkIntegration(unittest.TestCase):

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
        app_state.set_mission_waypoints([])
        app_state.set_mission_status("IDLE")

    def test_01_address_normalizer(self):
        """Verify URL and endpoint normalization for MAVSDK addresses."""
        self.assertEqual(normalize_mavsdk_address("mock"), "mock")
        self.assertEqual(normalize_mavsdk_address("mock://127.0.0.1:14550"), "mock")
        self.assertEqual(normalize_mavsdk_address("sim:test"), "mock")
        self.assertEqual(normalize_mavsdk_address(""), "mock")

        # Port 14540 (PX4 SITL default companion/MAVSDK port)
        self.assertEqual(normalize_mavsdk_address("14540"), "udpin:0.0.0.0:14540")
        self.assertEqual(normalize_mavsdk_address("udp:127.0.0.1:14540"), "udp:127.0.0.1:14540")
        self.assertEqual(normalize_mavsdk_address("udp://127.0.0.1:14540"), "udp:127.0.0.1:14540")

        # Port 14550 (PX4 SITL GCS port)
        self.assertEqual(normalize_mavsdk_address("udp:127.0.0.1:14550"), "udp:127.0.0.1:14550")
        self.assertEqual(normalize_mavsdk_address("udpin://0.0.0.0:14550"), "udpin:0.0.0.0:14550")

        # Serial / custom URLs
        self.assertEqual(normalize_mavsdk_address("serial://COM3:57600"), "serial:COM3:57600")

    def test_02_mavsdk_worker_lifecycle_and_signals(self):
        """Verify QMavsdkWorker lifecycle, mock stream, and Qt signal emissions."""
        worker = QMavsdkWorker("mock://127.0.0.1:14550")
        self.assertTrue(worker._mock_mode)
        self.assertEqual(worker._manual_z, 500)
        self.assertFalse(worker._manual_active)

        connected_signals = []
        telemetry_signals = []
        feedback_signals = []

        worker.connected_signal.connect(lambda s, c, v: connected_signals.append((s, c, v)))
        worker.telemetry_updated.connect(lambda d: telemetry_signals.append(d))
        worker.command_ack_signal.connect(lambda msg: feedback_signals.append(msg))

        worker.start()

        # Allow worker thread to spin and emit initial packets
        start_t = time.time()
        while time.time() - start_t < 0.4:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertGreater(len(connected_signals), 0, "Connected signal was not emitted")
        self.assertGreater(len(telemetry_signals), 0, "Telemetry updated signal was not emitted")

        # Test flight commands
        worker.arm()
        worker.takeoff(15.0)
        worker.posctl()
        worker.hold()
        worker.land()
        worker.rtl()
        worker.disarm()

        self.assertGreater(len(feedback_signals), 0)

        # Test manual remote flight inputs
        worker.set_manual_control(x=500, y=-500, z=700, r=200, active=True)
        self.assertEqual(worker._manual_x, 500)
        self.assertEqual(worker._manual_y, -500)
        self.assertEqual(worker._manual_z, 700)
        self.assertEqual(worker._manual_r, 200)
        self.assertTrue(worker._manual_active)

        worker.stop_manual_control()
        self.assertEqual(worker._manual_x, 0)
        self.assertEqual(worker._manual_y, 0)
        self.assertEqual(worker._manual_z, 500)
        self.assertFalse(worker._manual_active)

        worker.stop()
        self.assertFalse(worker.isRunning())

    def test_03_mavsdk_mission_plan_integration(self):
        """Verify conversion to/from local mission waypoints and MAVSDK MissionPlan."""
        from mavsdk.mission import MissionItem, MissionPlan

        plan = LocalMissionPlan()
        plan.add_waypoint(lat=37.7749, lon=-122.4194, alt=25.0)
        plan.add_waypoint(lat=37.7760, lon=-122.4180, alt=30.0)

        worker = QMavsdkWorker("mock")
        mission_acks = []
        worker.mission_ack_signal.connect(lambda ack: mission_acks.append(ack))

        # Upload local mission plan
        worker.upload_mission(plan)
        self.assertGreater(len(mission_acks), 0)
        self.assertEqual(app_state.mission_status, "UPLOADED")

        # Download mission
        downloaded = []
        worker.mission_downloaded_signal.connect(lambda wps: downloaded.append(wps))
        worker.download_mission()
        self.assertGreater(len(downloaded), 0)
        self.assertEqual(app_state.mission_status, "LOADED")

        # Verify MAVSDK native objects can be constructed directly
        item = MissionItem(
            latitude_deg=37.7749,
            longitude_deg=-122.4194,
            relative_altitude_m=25.0,
            speed_m_s=5.0,
            is_fly_through=True,
            gimbal_pitch_deg=float('nan'),
            gimbal_yaw_deg=float('nan'),
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=float('nan'),
            camera_photo_interval_s=float('nan'),
            acceptance_radius_m=2.0,
            yaw_deg=float('nan'),
            camera_photo_distance_m=float('nan'),
            vehicle_action=MissionItem.VehicleAction.NONE
        )
        native_plan = MissionPlan([item])
        self.assertEqual(len(native_plan.mission_items), 1)
        self.assertAlmostEqual(native_plan.mission_items[0].latitude_deg, 37.7749)

    def test_04_connection_dialog_mavsdk_presets(self):
        """Verify ConnectionDialog presents MAVSDK ports 14540 and 14550."""
        from gcs.widgets.connection_dialog import ConnectionDialog
        dlg = ConnectionDialog()

        # Select PX4 SITL 14550 GCS (index 1)
        dlg.combo_type.setCurrentIndex(1)
        conn_str, _ = dlg.get_connection_string()
        self.assertEqual(conn_str, "udpin:0.0.0.0:14550")

        # Select PX4 SITL 14540 Companion (index 2)
        dlg.combo_type.setCurrentIndex(2)
        conn_str, _ = dlg.get_connection_string()
        self.assertEqual(conn_str, "udpin:0.0.0.0:14540")

        # Select Mock (index 0)
        dlg.combo_type.setCurrentIndex(0)
        conn_str, _ = dlg.get_connection_string()
        self.assertTrue(conn_str.startswith("mock://"))

        dlg.deleteLater()
