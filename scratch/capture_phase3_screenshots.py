"""Capture Phase 3 visual evidence screenshots."""

import os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gcs.widgets.main_window import MainWindow
from gcs.mavlink import commands as cmds
from gcs.state.app_state import app_state

ARTIFACT_DIR = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"

app = QApplication.instance() or QApplication(sys.argv)

window = MainWindow()
window.resize(1380, 880)
window.show()
app.processEvents()

# Connect mock stream
window.start_mavlink_worker("mock://127.0.0.1:14550", 57600)
for _ in range(12):
    app.processEvents(); time.sleep(0.05)

# Save connected+disarmed state
p = window.grab()
p.save(os.path.join(ARTIFACT_DIR, "phase3_connected_disarmed.png"))
print("Saved: phase3_connected_disarmed.png")

# Arm the vehicle
window._mav_worker.dispatch_mock(cmds.mock_arm())
for _ in range(8):
    app.processEvents(); time.sleep(0.05)

# Save armed state (flight controls enabled)
p = window.grab()
p.save(os.path.join(ARTIFACT_DIR, "phase3_armed_controls_active.png"))
print("Saved: phase3_armed_controls_active.png")

window.disconnect_mavlink()
window.close()
print("Phase 3 screenshots done.")
