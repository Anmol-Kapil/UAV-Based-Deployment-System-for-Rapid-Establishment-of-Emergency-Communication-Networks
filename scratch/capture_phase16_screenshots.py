"""
scratch/capture_phase16_screenshots.py

Generates UI screenshots for Phase 16: Backend FastAPI Integration & Async REST Client.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt

app = QApplication.instance() or QApplication(sys.argv)

from gcs.state.app_state import app_state
from gcs.widgets.main_window import MainWindow

artifacts_dir = r"C:\Users\Anmol kapil\.gemini\antigravity-ide\brain\48cfa310-6a41-4274-8520-88c16e061083"

win = MainWindow()
win.resize(1380, 880)
win.show()

QApplication.processEvents()

# 1. Full GCS Phase 16 Default View (Offline Local Engine mode)
pix1 = win.grab()
path1 = os.path.join(artifacts_dir, "phase16_full_gcs_rest_offline.png")
pix1.save(path1)
print(f"Saved {path1}")

# 2. Set REST API connected state
app_state.set_backend_connected(True)
QApplication.processEvents()

pix2 = win.grab()
path2 = os.path.join(artifacts_dir, "phase16_full_gcs_rest_online.png")
pix2.save(path2)
print(f"Saved {path2}")

# 3. Left Panel Detail screenshot
pix3 = win.left_panel.grab()
path3 = os.path.join(artifacts_dir, "phase16_left_panel_rest_badge.png")
pix3.save(path3)
print(f"Saved {path3}")

win.close()
