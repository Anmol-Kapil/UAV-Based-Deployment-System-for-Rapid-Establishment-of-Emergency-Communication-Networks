"""Camera Panel for UAV Ground Control Station.

Dedicated inspection video console featuring:
- Real-time video viewport with aspect-ratio scaling
- Multi-source streaming: Synthetic Aerial Feed (30 FPS), Gazebo UDP (:5600), RTSP
- On-Screen Display (OSD) overlay: Reticle crosshair, Artificial Horizon pitch/roll ladder, telemetry bars
- Visual inspection snapshot capture with telemetry watermark
- Local video recording session toggle with OSD REC timer
- Fullscreen modal inspection window
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QComboBox,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from gcs.camera.camera_worker import CameraWorker, CameraSourceType
from gcs.widgets.camera_dialog import CameraCanvas, FullscreenCameraDialog
from gcs.state.app_state import app_state, ConnectionState


class CameraView(QWidget):
    """Operational Visual Inspection and Camera Stream Console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cameraView")
        self._worker: Optional[CameraWorker] = None
        self._is_streaming = False
        self._show_osd = True
        self._rec_timer = QTimer(self)
        self._rec_seconds = 0

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Video Viewport Stack (Page 0: Offline Card, Page 1: Live Video Canvas)
        self.stack = QStackedWidget()

        # Offline placeholder
        self.offline_viewport = QFrame()
        self.offline_viewport.setObjectName("cameraPlaceholder")
        self.offline_viewport.setMinimumHeight(240)
        off_layout = QVBoxLayout(self.offline_viewport)
        off_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        off_layout.setSpacing(6)

        icon_label = QLabel("📹")
        icon_label.setStyleSheet("font-size: 36px; color: #484f58;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        off_layout.addWidget(icon_label)

        self.lbl_offline_title = QLabel("CAMERA OFFLINE")
        self.lbl_offline_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ff7b72; letter-spacing: 1px;")
        self.lbl_offline_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        off_layout.addWidget(self.lbl_offline_title)

        sub_label = QLabel("Select stream source and click 'Start Stream'\nSupports Gazebo SITL UDP (:5600), RTSP, or Synthetic Aerial Feed")
        sub_label.setStyleSheet("font-size: 10px; color: #8b949e; text-align: center;")
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        off_layout.addWidget(sub_label)

        self.stack.addWidget(self.offline_viewport)

        # Live Canvas Viewport
        self.live_canvas = CameraCanvas()
        self.live_canvas.setMinimumHeight(240)
        self.stack.addWidget(self.live_canvas)

        layout.addWidget(self.stack, stretch=1)

        # Alias for backward compatibility
        self.viewport = self.offline_viewport

        # 2. Video HUD Status Bar
        hud_bar = QFrame()
        hud_bar.setProperty("class", "telemetry-card")
        hud_layout = QHBoxLayout(hud_bar)
        hud_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_cam_status = QLabel("STATUS: OFFLINE")
        self.lbl_cam_status.setStyleSheet("font-weight: 700; color: #8b949e; font-size: 10px;")
        hud_layout.addWidget(self.lbl_cam_status)

        self.lbl_rec_indicator = QLabel("")
        self.lbl_rec_indicator.setStyleSheet("font-weight: 700; color: #f85149; font-size: 10px; margin-left: 6px;")
        hud_layout.addWidget(self.lbl_rec_indicator)

        hud_layout.addStretch()

        self.lbl_hud_mode = QLabel("MODE: --")
        self.lbl_hud_mode.setStyleSheet("font-weight: 600; color: #79c0ff; font-size: 10px;")
        hud_layout.addWidget(self.lbl_hud_mode)

        self.lbl_hud_alt = QLabel("ALT: -- m")
        self.lbl_hud_alt.setStyleSheet("font-weight: 600; color: #f0f6fc; font-size: 10px; margin-left: 8px;")
        hud_layout.addWidget(self.lbl_hud_alt)

        layout.addWidget(hud_bar)

        # 3. Stream Configuration Bar
        src_bar = QHBoxLayout()
        src_bar.setSpacing(4)

        lbl_src = QLabel("SRC:")
        lbl_src.setStyleSheet("font-size: 9px; font-weight: 700; color: #8b949e;")
        src_bar.addWidget(lbl_src)

        self.combo_source = QComboBox()
        self.combo_source.addItems([
            "Synthetic Aerial Feed (30 FPS)",
            "Gazebo SITL Camera (UDP :5600)",
            "RTSP Stream (:8554/live)"
        ])
        self.combo_source.setStyleSheet("""
            QComboBox {
                background-color: #161b22;
                border: 1px solid #30363d;
                color: #c9d1d9;
                font-size: 9px;
                padding: 2px 4px;
                border-radius: 3px;
            }
        """)
        src_bar.addWidget(self.combo_source, stretch=1)

        self.btn_start = QPushButton("Start Stream")
        self.btn_start.setStyleSheet("color: #3fb950; font-weight: 700; font-size: 9px; padding: 2px 8px;")
        self.btn_start.clicked.connect(self.start_stream)
        src_bar.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Stream")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("color: #f85149; font-weight: 700; font-size: 9px; padding: 2px 8px;")
        self.btn_stop.clicked.connect(self.stop_stream)
        src_bar.addWidget(self.btn_stop)

        layout.addLayout(src_bar)

        # 4. Action Controls Bar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(4)

        self.btn_snapshot = QPushButton("📸 Snapshot")
        self.btn_snapshot.setToolTip("Capture high-resolution frame with telemetry watermark")
        self.btn_snapshot.setEnabled(False)
        self.btn_snapshot.setStyleSheet("font-size: 9px; font-weight: 600;")
        self.btn_snapshot.clicked.connect(self.take_snapshot)
        btn_bar.addWidget(self.btn_snapshot)

        self.btn_record = QPushButton("⏺ Record")
        self.btn_record.setToolTip("Toggle video recording session")
        self.btn_record.setEnabled(False)
        self.btn_record.setStyleSheet("font-size: 9px; font-weight: 600;")
        self.btn_record.clicked.connect(self.toggle_recording)
        btn_bar.addWidget(self.btn_record)

        self.btn_osd = QPushButton("OSD: ON")
        self.btn_osd.setToolTip("Toggle On-Screen Display HUD overlay")
        self.btn_osd.setEnabled(False)
        self.btn_osd.setStyleSheet("font-size: 9px; font-weight: 600;")
        self.btn_osd.clicked.connect(self.toggle_osd)
        btn_bar.addWidget(self.btn_osd)

        self.btn_fullscreen = QPushButton("⛶ Fullscreen")
        self.btn_fullscreen.setToolTip("Open expanded high-resolution inspection modal")
        self.btn_fullscreen.setEnabled(False)
        self.btn_fullscreen.setStyleSheet("font-size: 9px; font-weight: 600;")
        self.btn_fullscreen.clicked.connect(self.open_fullscreen)
        btn_bar.addWidget(self.btn_fullscreen)

        layout.addLayout(btn_bar)

    def _connect_signals(self):
        app_state.telemetry_updated.connect(self._on_telemetry_updated)
        app_state.connection_changed.connect(self._on_connection_changed)
        self._rec_timer.timeout.connect(self._on_rec_tick)

    def set_worker(self, worker):
        """Optionally receive external MAVLink worker reference."""
        pass

    # ──────────────────────────────────────────────────────────────────────────
    # Stream Lifecycle
    # ──────────────────────────────────────────────────────────────────────────
    def start_stream(self):
        """Start acquisition worker for selected source."""
        if self._worker and self._worker.isRunning():
            self._worker.stop()

        idx = self.combo_source.currentIndex()
        if idx == 0:
            source = CameraSourceType.SYNTHETIC
        elif idx == 1:
            source = CameraSourceType.GAZEBO_UDP
        else:
            source = CameraSourceType.RTSP_STREAM

        self._worker = CameraWorker(source_type=source, parent=self)
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.recording_toggled.connect(self._on_recording_toggled)

        self._worker.start()
        self._is_streaming = True

        self.stack.setCurrentIndex(1)  # Show live canvas
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.combo_source.setEnabled(False)
        self.btn_snapshot.setEnabled(True)
        self.btn_record.setEnabled(True)
        self.btn_osd.setEnabled(True)
        self.btn_fullscreen.setEnabled(True)

        app_state.log("INFO", "CAMERA", f"Started {source.value} video stream")

    def stop_stream(self):
        """Halt acquisition and reset to offline state."""
        if self._worker:
            if self._worker.is_recording:
                self._worker.toggle_recording()
            self._worker.stop()
            self._worker = None

        self._is_streaming = False
        self._rec_timer.stop()
        self.lbl_rec_indicator.setText("")

        self.stack.setCurrentIndex(0)  # Show offline card
        self.lbl_cam_status.setText("STATUS: OFFLINE")
        self.lbl_cam_status.setStyleSheet("font-weight: 700; color: #8b949e; font-size: 10px;")

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.combo_source.setEnabled(True)
        self.btn_snapshot.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_osd.setEnabled(False)
        self.btn_fullscreen.setEnabled(False)

        app_state.log("INFO", "CAMERA", "Camera stream stopped")

    def take_snapshot(self) -> Optional[str]:
        """Capture current frame with watermark."""
        if self._worker and self._is_streaming:
            path = self._worker.take_snapshot()
            return path
        return None

    def toggle_recording(self):
        """Toggle local recording session."""
        if self._worker and self._is_streaming:
            self._worker.toggle_recording()

    def toggle_osd(self):
        """Toggle OSD overlay on video viewport."""
        self._show_osd = not self._show_osd
        self.btn_osd.setText(f"OSD: {'ON' if self._show_osd else 'OFF'}")
        if self._worker and self._worker.latest_frame:
            self.live_canvas.set_frame(self._worker.latest_frame, self._show_osd)

    def open_fullscreen(self):
        """Open high-resolution modal inspection view."""
        dlg = FullscreenCameraDialog(worker=self._worker, parent=self)
        dlg.exec()

    # ──────────────────────────────────────────────────────────────────────────
    # Callbacks & Synchronization
    # ──────────────────────────────────────────────────────────────────────────
    def _on_frame_ready(self, frame: QImage):
        if self._is_streaming:
            self.live_canvas.set_frame(frame, self._show_osd)

    def _on_status_changed(self, status: str, details: str):
        self.lbl_cam_status.setText(f"STATUS: {status}")
        if status == "STREAMING":
            self.lbl_cam_status.setStyleSheet("font-weight: 700; color: #3fb950; font-size: 10px;")
        elif status == "CONNECTING":
            self.lbl_cam_status.setStyleSheet("font-weight: 700; color: #d29922; font-size: 10px;")
        else:
            self.lbl_cam_status.setStyleSheet("font-weight: 700; color: #8b949e; font-size: 10px;")

    def _on_recording_toggled(self, is_rec: bool):
        if is_rec:
            self._rec_seconds = 0
            self._rec_timer.start(1000)
            self.lbl_rec_indicator.setText("● REC 00:00")
            self.btn_record.setText("⏹ Stop Rec")
            self.btn_record.setStyleSheet("color: #f85149; font-weight: bold; font-size: 9px;")
        else:
            self._rec_timer.stop()
            self.lbl_rec_indicator.setText("")
            self.btn_record.setText("⏺ Record")
            self.btn_record.setStyleSheet("font-size: 9px; font-weight: 600;")

    def _on_rec_tick(self):
        self._rec_seconds += 1
        m = self._rec_seconds // 60
        s = self._rec_seconds % 60
        self.lbl_rec_indicator.setText(f"● REC {m:02d}:{s:02d}")

    def _on_telemetry_updated(self, data: dict):
        mode = app_state.flight_mode
        self.lbl_hud_mode.setText(f"MODE: {mode}")

        alt = data.get("alt_rel", data.get("alt"))
        if isinstance(alt, (int, float)):
            self.lbl_hud_alt.setText(f"ALT: {alt:.1f} m")
        else:
            self.lbl_hud_alt.setText("ALT: -- m")

        # Repaint canvas to refresh OSD telemetry if streaming
        if self._is_streaming and self._worker and self._worker.latest_frame:
            self.live_canvas.set_frame(self._worker.latest_frame, self._show_osd)

    def _on_connection_changed(self, status: str):
        if status == ConnectionState.DISCONNECTED:
            self.lbl_hud_mode.setText("MODE: --")
            self.lbl_hud_alt.setText("ALT: -- m")
