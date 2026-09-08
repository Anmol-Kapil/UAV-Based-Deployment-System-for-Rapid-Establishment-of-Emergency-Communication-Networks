"""Main Application Entry Point for the UAV Ground Control Station (GCS).

Launch with:
    python -m gcs.main
or
    python gcs/main.py
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure package path is resolved
curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(curr_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from gcs.widgets.main_window import MainWindow


def load_stylesheet(app: QApplication):
    qss_path = os.path.join(curr_dir, "resources", "styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    else:
        print(f"[WARN] QSS stylesheet not found at: {qss_path}")


def main():
    # Configure application
    app = QApplication(sys.argv)
    app.setApplicationName("UAV Emergency Deployment GCS")
    app.setOrganizationName("EngineeringProject")

    # Load custom dark engineering theme
    load_stylesheet(app)

    # Launch main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
