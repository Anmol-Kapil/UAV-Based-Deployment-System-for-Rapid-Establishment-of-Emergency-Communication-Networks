"""Fullscreen / Popout Modal Dialog for High-Resolution Camera Inspection."""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen
from gcs.camera.camera_worker import CameraWorker
from gcs.state.app_state import app_state


class FullscreenCameraDialog(QDialog):
    """Expanded High-Resolution Inspection Dialog."""

    def __init__(self, worker: Optional[CameraWorker] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("UAV HIGH-RESOLUTION VISUAL INSPECTION CONSOLE")
        self.resize(1024, 640)
        self.setMinimumSize(800, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #c9d1d9;
            }
        """)

        self._worker = worker
        self._current_frame: Optional[QImage] = None
        self._show_osd = True

        self._init_ui()
        if self._worker:
            self._worker.frame_ready.connect(self._on_frame_ready)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("PRIMARY OPTICAL INSPECTION STREAM — EXPANDED VIEW")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #58a6ff; letter-spacing: 0.5px;")
        header.addWidget(title)
        header.addStretch()

        self.lbl_fps = QLabel("30 FPS | 1080p EXPANDED")
        self.lbl_fps.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 600;")
        header.addWidget(self.lbl_fps)

        layout.addLayout(header)

        # Video viewport canvas
        self.canvas = CameraCanvas(self)
        layout.addWidget(self.canvas, stretch=1)

        # Bottom Toolbar
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_osd = QPushButton("OSD: ON")
        self.btn_osd.setStyleSheet("background-color: #21262d; color: #58a6ff; font-weight: 600; padding: 4px 10px;")
        self.btn_osd.clicked.connect(self._toggle_osd)
        bar.addWidget(self.btn_osd)

        self.btn_snap = QPushButton("📸 Capture Snapshot")
        self.btn_snap.setStyleSheet("background-color: #21262d; color: #f0f6fc; font-weight: 600; padding: 4px 12px;")
        self.btn_snap.clicked.connect(self._take_snapshot)
        bar.addWidget(self.btn_snap)

        bar.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #30363d; color: #ffffff; padding: 4px 16px;")
        btn_close.clicked.connect(self.accept)
        bar.addWidget(btn_close)

        layout.addLayout(bar)

    def _on_frame_ready(self, frame: QImage):
        self._current_frame = frame
        self.canvas.set_frame(frame, self._show_osd)

    def _toggle_osd(self):
        self._show_osd = not self._show_osd
        self.btn_osd.setText(f"OSD: {'ON' if self._show_osd else 'OFF'}")
        if self._current_frame:
            self.canvas.set_frame(self._current_frame, self._show_osd)

    def _take_snapshot(self):
        if self._worker:
            self._worker.take_snapshot()

    def closeEvent(self, event):
        if self._worker:
            try:
                self._worker.frame_ready.disconnect(self._on_frame_ready)
            except Exception:
                pass
        super().closeEvent(event)


class CameraCanvas(QFrame):
    """Custom paint widget rendering scaled frame with high-fidelity OSD."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cameraCanvas")
        self.setStyleSheet("background-color: #05070a; border: 1px solid #30363d; border-radius: 4px;")
        self._frame: Optional[QImage] = None
        self._show_osd = True

    def set_frame(self, frame: QImage, show_osd: bool = True):
        self._frame = frame
        self._show_osd = show_osd
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()

        if not self._frame or self._frame.isNull():
            # Offline background
            painter.fillRect(0, 0, w, h, QColor(10, 14, 20))
            painter.setPen(QColor(139, 148, 158))
            painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "NO ACTIVE VIDEO FEED")
            painter.end()
            return

        # 1. Scale video frame keeping aspect ratio
        scaled = self._frame.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x_off = int((w - scaled.width()) / 2)
        y_off = int((h - scaled.height()) / 2)

        # Draw black bars for pillarbox/letterbox
        painter.fillRect(0, 0, w, h, QColor(5, 7, 10))
        painter.drawImage(x_off, y_off, scaled)

        # 2. OSD Overlay
        if self._show_osd:
            self._paint_osd(painter, x_off, y_off, scaled.width(), scaled.height())

        painter.end()

    def _paint_osd(self, painter: QPainter, vx: int, vy: int, vw: int, vh: int):
        cx = vx + vw / 2.0
        cy = vy + vh / 2.0

        telem = dict(app_state.telemetry)
        p = telem.get("pitch")
        pitch = float(p) if isinstance(p, (int, float)) else 0.0

        r = telem.get("roll")
        roll = float(r) if isinstance(r, (int, float)) else 0.0

        a = telem.get("alt_rel", telem.get("alt"))
        alt = float(a) if isinstance(a, (int, float)) else 0.0

        s = telem.get("groundspeed")
        speed = float(s) if isinstance(s, (int, float)) else 0.0

        hd = telem.get("heading")
        heading = float(hd) if isinstance(hd, (int, float)) else 0.0

        mode = app_state.flight_mode
        lat = telem.get("lat", 0.0)
        lon = telem.get("lon", 0.0)

        # Reticle Crosshairs
        painter.setPen(QPen(QColor(88, 166, 255, 180), 1.5))
        # Center circle & crosshair
        painter.drawEllipse(QPointF(cx, cy), 16, 16)
        painter.drawLine(int(cx - 30), int(cy), int(cx - 18), int(cy))
        painter.drawLine(int(cx + 18), int(cy), int(cx + 30), int(cy))
        painter.drawLine(int(cx), int(cy - 30), int(cx), int(cy - 18))
        painter.drawLine(int(cx), int(cy + 18), int(cx), int(cy + 30))

        # Artificial horizon pitch ladder
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-roll)

        p_offset = -pitch * 2.5
        painter.setPen(QPen(QColor(63, 185, 80, 160), 1.5))
        # Horizon zero line
        painter.drawLine(-70, int(p_offset), -25, int(p_offset))
        painter.drawLine(25, int(p_offset), 70, int(p_offset))

        # +10 and -10 deg pitch rungs
        painter.setPen(QPen(QColor(63, 185, 80, 100), 1, Qt.PenStyle.DashLine))
        painter.drawLine(-40, int(p_offset - 25), 40, int(p_offset - 25))
        painter.drawLine(-40, int(p_offset + 25), 40, int(p_offset + 25))
        painter.restore()

        # Top OSD Bar
        painter.fillRect(vx, vy, vw, 24, QColor(10, 14, 20, 180))
        painter.setPen(QColor(240, 246, 252))
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        lat_str = f"{lat:.6f}" if isinstance(lat, (int, float)) else str(lat)
        lon_str = f"{lon:.6f}" if isinstance(lon, (int, float)) else str(lon)
        painter.drawText(vx + 10, vy + 16, f"POS: {lat_str}, {lon_str}")
        painter.drawText(vx + vw - 160, vy + 16, f"HDG: {heading:.0f}° | GIMBAL STAB")

        # Bottom OSD Bar
        painter.fillRect(vx, vy + vh - 24, vw, 24, QColor(10, 14, 20, 180))
        alt_str = f"{alt:.1f} m" if isinstance(alt, (int, float)) else str(alt)
        spd_str = f"{speed:.1f} m/s" if isinstance(speed, (int, float)) else str(speed)
        painter.drawText(vx + 10, vy + vh - 8, f"MODE: {mode} | ALT: {alt_str} | SPD: {spd_str}")
        painter.drawText(vx + vw - 130, vy + vh - 8, f"SATS: {app_state.satellites}")
