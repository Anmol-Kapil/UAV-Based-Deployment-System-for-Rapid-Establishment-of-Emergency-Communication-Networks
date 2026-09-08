"""Automated Unit & Integration Tests for Phase 6: Camera Integration & OSD Telemetry."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

# Ensure application exists
app = QApplication.instance() or QApplication(sys.argv)

from gcs.state.app_state import app_state, ConnectionState
from gcs.camera.camera_worker import CameraWorker, CameraSourceType
from gcs.widgets.camera_view import CameraView
from gcs.widgets.camera_dialog import FullscreenCameraDialog


class TestPhase6CameraIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app_state.reset_telemetry()
        app_state.set_connection(ConnectionState.DISCONNECTED)

    def setUp(self):
        app_state.reset_telemetry()

    def test_01_camera_worker_synthetic_stream(self):
        """Test CameraWorker synthetic stream generation, frame sizing, and thread lifecycle."""
        worker = CameraWorker(source_type=CameraSourceType.SYNTHETIC)
        received_frames = []

        def _on_frame(img: QImage):
            received_frames.append(img)

        worker.frame_ready.connect(_on_frame)
        worker.start()

        # Wait up to 1 second for at least 3 frames
        for _ in range(20):
            app.processEvents()
            time.sleep(0.05)
            if len(received_frames) >= 3:
                break

        worker.stop()

        self.assertGreaterEqual(len(received_frames), 1, "CameraWorker should produce synthetic frames")
        frame = received_frames[0]
        self.assertFalse(frame.isNull(), "Generated frame must not be null")
        self.assertEqual(frame.width(), 640)
        self.assertEqual(frame.height(), 360)
        self.assertFalse(worker.isRunning(), "Worker should stop cleanly")

    def test_02_camera_view_ui_state_transitions(self):
        """Test CameraView UI controls, offline/streaming stacked layout, and button gating."""
        view = CameraView()

        # 1. Initial Offline State
        self.assertEqual(view.stack.currentIndex(), 0, "Initial view must be offline placeholder")
        self.assertIn("OFFLINE", view.lbl_cam_status.text())
        self.assertTrue(view.btn_start.isEnabled())
        self.assertFalse(view.btn_stop.isEnabled())
        self.assertFalse(view.btn_snapshot.isEnabled())
        self.assertFalse(view.btn_record.isEnabled())
        self.assertFalse(view.btn_fullscreen.isEnabled())

        # 2. Start Stream
        view.combo_source.setCurrentIndex(0)  # Synthetic
        view.btn_start.click()
        app.processEvents()

        self.assertEqual(view.stack.currentIndex(), 1, "Live canvas must be active when streaming")
        self.assertFalse(view.btn_start.isEnabled())
        self.assertTrue(view.btn_stop.isEnabled())
        self.assertTrue(view.btn_snapshot.isEnabled())
        self.assertTrue(view.btn_record.isEnabled())
        self.assertTrue(view.btn_fullscreen.isEnabled())

        # 3. Stop Stream
        view.btn_stop.click()
        app.processEvents()

        self.assertEqual(view.stack.currentIndex(), 0, "Must return to offline placeholder on stop")
        self.assertIn("OFFLINE", view.lbl_cam_status.text())
        self.assertTrue(view.btn_start.isEnabled())
        self.assertFalse(view.btn_stop.isEnabled())
        self.assertFalse(view.btn_snapshot.isEnabled())

        view.deleteLater()

    def test_03_snapshot_capture_and_watermark(self):
        """Test visual inspection snapshot capture, watermark embedding, and file creation."""
        view = CameraView()
        view.start_stream()

        # Wait for at least one frame
        for _ in range(15):
            app.processEvents()
            time.sleep(0.05)
            if view._worker and view._worker.latest_frame:
                break

        self.assertIsNotNone(view._worker.latest_frame, "Latest frame must be available")

        # Capture snapshot
        snap_path = view.take_snapshot()
        self.assertIsNotNone(snap_path, "Snapshot path should not be None")
        self.assertTrue(os.path.exists(snap_path), f"Snapshot file must exist: {snap_path}")
        self.assertGreater(os.path.getsize(snap_path), 1000, "Snapshot file must have non-trivial size")

        # Verify image integrity
        img = QImage(snap_path)
        self.assertFalse(img.isNull(), "Saved snapshot must load as a valid QImage")
        self.assertEqual(img.width(), 640)
        self.assertEqual(img.height(), 360)

        view.stop_stream()
        view.deleteLater()

    def test_04_recording_and_osd_telemetry_sync(self):
        """Test local video recording toggle, OSD toggle, and live telemetry synchronization."""
        view = CameraView()
        view.start_stream()

        # Telemetry updates
        app_state.flight_mode = "GUIDED"
        app_state.update_telemetry(pitch=5.2, roll=-3.1, alt_rel=32.4, groundspeed=14.2)
        app.processEvents()

        self.assertIn("GUIDED", view.lbl_hud_mode.text())
        self.assertIn("32.4", view.lbl_hud_alt.text())

        # Test Recording Toggle
        self.assertFalse(view._worker.is_recording)
        view.btn_record.click()
        self.assertTrue(view._worker.is_recording)
        self.assertIn("Stop Rec", view.btn_record.text())
        self.assertIn("REC", view.lbl_rec_indicator.text())

        # Toggle recording off
        view.btn_record.click()
        self.assertFalse(view._worker.is_recording)
        self.assertEqual(view.lbl_rec_indicator.text(), "")

        # Test OSD toggle
        self.assertTrue(view._show_osd)
        view.btn_osd.click()
        self.assertFalse(view._show_osd)
        self.assertIn("OFF", view.btn_osd.text())
        view.btn_osd.click()
        self.assertTrue(view._show_osd)

        view.stop_stream()
        view.deleteLater()


if __name__ == "__main__":
    unittest.main()
