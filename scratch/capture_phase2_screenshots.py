"""Capture Phase 2 visual evidence screenshots for GCS walkthrough."""

import os
import sys
import time

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use offscreen platform for reliable rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.state.app_state import app_state

ARTIFACT_DIR = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"


def capture_screenshots():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(1380, 880)
    window.show()
    app.processEvents()
    time.sleep(0.5)

    # 1. Connect Mock Stream and wait for track history generation
    window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)

    start_t = time.time()
    while time.time() - start_t < 1.8:
        app.processEvents()
        time.sleep(0.05)

    pix_map_track = window.grab()
    path_map_track = os.path.join(ARTIFACT_DIR, "phase2_ui_live_map_track.png")
    pix_map_track.save(path_map_track)
    print(f"Saved: {path_map_track}")

    window.disconnect_mavlink()
    window.close()
    print("Phase 2 screenshot capture complete.")


if __name__ == "__main__":
    capture_screenshots()
