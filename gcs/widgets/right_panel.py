"""Right-side Context Panel for GCS.

Hosts tabbed interfaces for:
1. TELEMETRY (Active telemetry display)
2. CAMERA (Camera preview & offline placeholder)
3. MISSION (Mission planner & waypoint table placeholder)
4. DEPLOYMENT (Deployment workflow state placeholder)
5. RF SURVEY (RF simulation & survey parameters placeholder)
6. LOG (Event log history)
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QTableWidget,
    QHeaderView,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt
from gcs.widgets.telemetry_view import TelemetryView
from gcs.widgets.camera_view import CameraView
from gcs.widgets.log_view import LogView
from gcs.widgets.mission_view import MissionView
from gcs.widgets.deployment_view import DeploymentView
from gcs.widgets.rf_view import RFView

# Aliases for backwards compatibility
MissionPlaceholder = MissionView
DeploymentPlaceholder = DeploymentView
RFSurveyPlaceholder = RFView


class RightPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rightPanel")
        self.setMinimumWidth(360)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("contextTabs")

        # 1. Telemetry
        self.tab_telemetry = TelemetryView()
        self.tabs.addTab(self.tab_telemetry, "TELEMETRY")

        # 2. Camera
        self.tab_camera = CameraView()
        self.tabs.addTab(self.tab_camera, "CAMERA")

        # 3. Mission
        self.tab_mission = MissionPlaceholder()
        self.tabs.addTab(self.tab_mission, "MISSION")

        # 4. Deployment
        self.tab_deployment = DeploymentPlaceholder()
        self.tabs.addTab(self.tab_deployment, "DEPLOYMENT")

        # 5. RF Survey
        self.tab_rf = RFSurveyPlaceholder()
        self.tabs.addTab(self.tab_rf, "RF SURVEY")

        # 6. Log
        self.tab_log = LogView()
        self.tabs.addTab(self.tab_log, "LOG")

        layout.addWidget(self.tabs)

    @property
    def telemetry_view(self) -> TelemetryView:
        return self.tab_telemetry

    @property
    def mission_view(self) -> MissionView:
        return self.tab_mission

    @property
    def deployment_view(self) -> DeploymentView:
        return self.tab_deployment

    @property
    def camera_view(self) -> CameraView:
        return self.tab_camera

    @property
    def rf_view(self) -> RFView:
        return self.tab_rf

    @property
    def log_view(self) -> LogView:
        return self.tab_log

    def set_worker(self, worker):
        self.tab_mission.set_worker(worker)
        self.tab_deployment.set_worker(worker)
        self.tab_camera.set_worker(worker)
