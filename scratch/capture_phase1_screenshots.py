"""Capture Phase 1 visual evidence screenshots for GCS walkthrough."""

import os
import sys
import time

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use offscreen platform for reliable rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.widgets.connection_dialog import ConnectionDialog
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

    # 1. Capture Disconnected state
    pix_disconnected = window.grab()
    path_disconnected = os.path.join(ARTIFACT_DIR, "phase1_ui_disconnected.png")
    pix_disconnected.save(path_disconnected)
    print(f"Saved: {path_disconnected}")

    # 2. Capture Connection Dialog
    dialog = ConnectionDialog(window)
    dialog.show()
    app.processEvents()
    time.sleep(0.3)
    pix_dialog = dialog.grab()
    path_dialog = os.path.join(ARTIFACT_DIR, "phase1_ui_connection_dialog.png")
    pix_dialog.save(path_dialog)
    print(f"Saved: {path_dialog}")
    dialog.close()

    # 3. Connect Mock Stream and capture Live Telemetry
    window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)

    start_t = time.time()
    while time.time() - start_t < 1.0:
        app.processEvents()
        time.sleep(0.05)

    pix_connected = window.grab()
    path_connected = os.path.join(ARTIFACT_DIR, "phase1_ui_connected.png")
    pix_connected.save(path_connected)
    print(f"Saved: {path_connected}")

    window.disconnect_mavlink()
    window.close()
    print("Screenshot capture complete.")


if __name__ == "__main__":
    capture_screenshots()
