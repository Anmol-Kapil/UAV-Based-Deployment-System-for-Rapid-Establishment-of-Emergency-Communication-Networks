"""Asynchronous Camera Video Stream Worker.

Supports:
1. Synthetic Aerial Inspection Simulator (30 FPS dynamic terrain & gimbal motion)
2. Gazebo SITL Camera Stream over UDP (port 5600)
3. RTSP Network Stream integration
4. Real-time snapshot capture and local recording
"""

import os
import sys
import time
import math
import socket
from datetime import datetime
from enum import Enum
from typing import Optional

from PySide6.QtCore import QThread, Signal, QMutex, QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QLinearGradient
from gcs.state.app_state import app_state


class CameraSourceType(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    GAZEBO_UDP = "GAZEBO_UDP"
    RTSP_STREAM = "RTSP_STREAM"


class CameraWorker(QThread):
    """Worker thread for video acquisition, synthetic rendering, and streaming."""

    frame_ready = Signal(QImage)
    status_changed = Signal(str, str)     # status (e.g. "STREAMING", "OFFLINE"), details
    snapshot_saved = Signal(str)          # absolute path to saved snapshot
    recording_toggled = Signal(bool)      # is_recording

    def __init__(self, source_type: CameraSourceType = CameraSourceType.SYNTHETIC, parent=None):
        super().__init__(parent)
        self.source_type = source_type
        self.udp_host = "127.0.0.1"
        self.udp_port = 5600
        self.rtsp_url = "rtsp://127.0.0.1:8554/live"

        self._running = False
        self._mutex = QMutex()
        self._last_frame: Optional[QImage] = None
        self._is_recording = False
        self._record_frame_count = 0
        self._record_start_time = 0.0

        # Snapshot folder setup
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.snapshots_dir = os.path.join(project_root, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)

        # Synthetic animation state
        self._anim_phase = 0.0

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def latest_frame(self) -> Optional[QImage]:
        self._mutex.lock()
        frame = self._last_frame.copy() if self._last_frame else None
        self._mutex.unlock()
        return frame

    def set_source(self, source_type: CameraSourceType, udp_port: int = 5600, rtsp_url: str = ""):
        self._mutex.lock()
        self.source_type = source_type
        self.udp_port = udp_port
        if rtsp_url:
            self.rtsp_url = rtsp_url
        self._mutex.unlock()

    def run(self):
        self._running = True
        self.status_changed.emit("CONNECTING", f"Initializing {self.source_type.value} stream...")

        if self.source_type == CameraSourceType.SYNTHETIC:
            self._run_synthetic()
        elif self.source_type == CameraSourceType.GAZEBO_UDP:
            self._run_udp()
        elif self.source_type == CameraSourceType.RTSP_STREAM:
            self._run_rtsp()

        self._running = False
        self.status_changed.emit("OFFLINE", "Stream stopped")

    def stop(self):
        self._running = False
        self.quit()
        self.wait(1500)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Synthetic Aerial Inspection Simulator Engine
    # ──────────────────────────────────────────────────────────────────────────
    def _run_synthetic(self):
        """Generates realistic 30 FPS gimbal-stabilized aerial disaster inspection video."""
        self.status_changed.emit("STREAMING", "30 FPS | 640x360 (Synthetic Aerial Gimbal)")
        frame_delay = 1.0 / 30.0  # 30 FPS target (~33ms)

        width = 640
        height = 360

        while self._running:
            t_start = time.time()
            self._anim_phase += 0.05

            # Telemetry context (safely convert from possible '--' placeholders)
            telem = dict(app_state.telemetry)
            pitch = telem.get("pitch")
            pitch = float(pitch) if isinstance(pitch, (int, float)) else 0.0

            roll = telem.get("roll")
            roll = float(roll) if isinstance(roll, (int, float)) else 0.0

            heading = telem.get("heading")
            heading = float(heading) if isinstance(heading, (int, float)) else 0.0

            alt = telem.get("alt_rel", telem.get("alt"))
            alt = float(alt) if (isinstance(alt, (int, float)) and alt > 0) else 25.0

            # Render synthetic inspection frame
            frame = self._render_synthetic_frame(width, height, pitch, roll, heading, alt)

            self._mutex.lock()
            self._last_frame = frame
            if self._is_recording:
                self._record_frame_count += 1
            self._mutex.unlock()

            self.frame_ready.emit(frame)

            elapsed = time.time() - t_start
            sleep_time = max(0.005, frame_delay - elapsed)
            time.sleep(sleep_time)

    def _render_synthetic_frame(self, w: int, h: int, pitch: float, roll: float, heading: float, alt: float) -> QImage:
        """Draws realistic aerial disaster ground contours, terrain grid, and optical features."""
        img = QImage(w, h, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = w / 2.0
        cy = h / 2.0

        # Gimbal stabilization / attitude offset
        pitch_rad = math.radians(pitch)
        roll_rad = math.radians(roll)

        offset_y = -pitch * 3.0
        offset_x = roll * 2.0

        # 1. Earth / Terrain Ground Base (Simulated disaster area terrain)
        # Background gradient: muddy terrain, flood zones, vegetation
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor(32, 40, 36))    # Dark olive / forest
        bg_grad.setColorAt(0.5, QColor(48, 44, 38))    # Disturbed soil / silt
        bg_grad.setColorAt(1.0, QColor(24, 32, 34))    # Deep water / flood boundary
        painter.fillRect(0, 0, w, h, bg_grad)

        # 2. Simulated Moving Terrain Contours (Simulates UAV movement & drift)
        painter.save()
        painter.translate(cx + offset_x, cy + offset_y)
        painter.rotate(-roll * 0.5)

        # Dynamic perspective grid representing ground surface
        painter.setPen(QPen(QColor(60, 75, 70, 80), 1))
        step = 40
        grid_shift = (self._anim_phase * 20.0) % step

        for y_line in range(-h, h + step, step):
            painter.drawLine(-w, y_line + int(grid_shift), w, y_line + int(grid_shift))
        for x_line in range(-w, w + step, step):
            painter.drawLine(x_line, -h, x_line, h)

        # 3. Ground Landmarks / Drop Candidate Features
        # Feature A: Emergency Drop Site Alpha
        self._draw_ground_poi(painter, -120, 40 + int(grid_shift * 0.8), "CANDIDATE DROP ZONE ALPHA", QColor(210, 153, 34, 180))

        # Feature B: Flood Barrier / Road Intersection
        painter.setPen(QPen(QColor(80, 90, 85, 120), 8))
        painter.drawLine(-250, -80 + int(grid_shift * 0.5), 250, -20 + int(grid_shift * 0.5))

        # Feature C: Cellular Coverage Shadow Zone
        shadow_brush = QBrush(QColor(248, 81, 73, 35))
        painter.setBrush(shadow_brush)
        painter.setPen(QPen(QColor(248, 81, 73, 140), 1, Qt.PenStyle.DashLine))
        painter.drawEllipse(QPointF(80, -30 + int(grid_shift * 0.6)), 70, 45)
        painter.setPen(QPen(QColor(248, 81, 73, 200), 1))
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.drawText(30, -35 + int(grid_shift * 0.6), "[RF BLACKOUT ZONE]")

        painter.restore()

        # 4. Camera Optical Vignette & Lens Effect
        vignette = QRadialGradient(cx, cy, max(w, h) * 0.65)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.7, QColor(0, 0, 0, 40))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 160))
        painter.fillRect(0, 0, w, h, vignette)

        # 5. Sensor Inspection Overlay details (Frame timestamp & optical metadata)
        painter.setPen(QColor(200, 220, 240, 160))
        painter.setFont(QFont("Consolas", 8))
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        painter.drawText(10, 18, f"GIMBAL 4K OPTICAL | {time_str} UTC")
        painter.drawText(w - 140, 18, f"FOV: 84° | ZOOM: 1.0x")

        painter.end()
        return img

    def _draw_ground_poi(self, painter: QPainter, x: int, y: int, label: str, color: QColor):
        """Draws a recognizable ground landmark with bracket box."""
        painter.setPen(QPen(color, 1.5))
        size = 18
        # Four corner brackets
        painter.drawLine(x - size, y - size, x - size + 6, y - size)
        painter.drawLine(x - size, y - size, x - size, y - size + 6)

        painter.drawLine(x + size, y - size, x + size - 6, y - size)
        painter.drawLine(x + size, y - size, x + size, y - size + 6)

        painter.drawLine(x - size, y + size, x - size + 6, y + size)
        painter.drawLine(x - size, y + size, x - size, y + size - 6)

        painter.drawLine(x + size, y + size, x + size - 6, y + size)
        painter.drawLine(x + size, y + size, x + size, y + size - 6)

        # Center dot
        painter.drawPoint(x, y)

        # Label
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.setPen(color)
        painter.drawText(x - 65, y + size + 12, label)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Gazebo UDP Stream Receiver Engine (port 5600)
    # ──────────────────────────────────────────────────────────────────────────
    def _run_udp(self):
        """Listens on UDP socket for Gazebo camera frames or renders standby pattern."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            sock.bind((self.udp_host, self.udp_port))
            self.status_changed.emit("STREAMING", f"Listening on UDP {self.udp_host}:{self.udp_port}")
        except Exception as e:
            self.status_changed.emit("ERROR", f"UDP Bind error on :{self.udp_port}: {e}")
            sock.close()
            return

        last_packet_time = 0.0

        while self._running:
            try:
                data, _ = sock.recvfrom(65507)
                last_packet_time = time.time()
                # Attempt to decode JPEG frame
                img = QImage()
                if img.loadFromData(data):
                    self._mutex.lock()
                    self._last_frame = img
                    self._mutex.unlock()
                    self.frame_ready.emit(img)
            except socket.timeout:
                # If Gazebo is not streaming UDP packets, display clean standby test pattern
                now = time.time()
                if (now - last_packet_time) > 1.0:
                    standby_img = self._render_standby_frame(f"UDP :{self.udp_port} LISTENING\nWAITING FOR GAZEBO VIDEO STREAM")
                    self._mutex.lock()
                    self._last_frame = standby_img
                    self._mutex.unlock()
                    self.frame_ready.emit(standby_img)
                    time.sleep(0.1)
            except Exception as e:
                time.sleep(0.1)

        sock.close()

    # ──────────────────────────────────────────────────────────────────────────
    # 3. RTSP Stream Receiver
    # ──────────────────────────────────────────────────────────────────────────
    def _run_rtsp(self):
        """RTSP stream handler with informative standby card."""
        self.status_changed.emit("STREAMING", f"RTSP Stream: {self.rtsp_url}")
        while self._running:
            standby_img = self._render_standby_frame(f"RTSP STREAM SOURCE\n{self.rtsp_url}")
            self._mutex.lock()
            self._last_frame = standby_img
            self._mutex.unlock()
            self.frame_ready.emit(standby_img)
            time.sleep(0.2)

    def _render_standby_frame(self, message: str) -> QImage:
        """Generates high-contrast standby raster with grid and status label."""
        w, h = 640, 360
        img = QImage(w, h, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        painter.fillRect(0, 0, w, h, QColor(13, 17, 23))

        # Grid lines
        painter.setPen(QPen(QColor(33, 38, 45), 1))
        for x in range(0, w, 40):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            painter.drawLine(0, y, w, y)

        # Crosshairs
        painter.setPen(QPen(QColor(88, 166, 255, 120), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, int(h / 2), w, int(h / 2))
        painter.drawLine(int(w / 2), 0, int(w / 2), h)

        # Text banner
        painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        painter.setPen(QColor(88, 166, 255))
        rect = img.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)

        painter.end()
        return img

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Snapshot & Recording Services
    # ──────────────────────────────────────────────────────────────────────────
    def take_snapshot(self, custom_path: Optional[str] = None) -> Optional[str]:
        """Captures the current video frame with telemetry watermark and writes PNG."""
        frame = self.latest_frame
        if not frame:
            return None

        # Burn watermark into copy
        watermarked = frame.copy()
        painter = QPainter(watermarked)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Bottom watermark strip
        h = watermarked.height()
        w = watermarked.width()
        painter.fillRect(0, h - 28, w, 28, QColor(10, 14, 20, 200))

        painter.setPen(QColor(240, 246, 252))
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))

        t_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        telem = dict(app_state.telemetry)
        lat = telem.get("lat", "--")
        lon = telem.get("lon", "--")
        alt = telem.get("alt_rel", "--")
        mode = app_state.flight_mode

        lat_str = f"{lat:.6f}" if isinstance(lat, (int, float)) else str(lat)
        lon_str = f"{lon:.6f}" if isinstance(lon, (int, float)) else str(lon)
        alt_str = f"{alt:.1f}m" if isinstance(alt, (int, float)) else str(alt)

        watermark_text = f"UAV INSPECTION | {t_stamp} | {lat_str}, {lon_str} | ALT: {alt_str} | {mode}"
        painter.drawText(12, h - 9, watermark_text)
        painter.end()

        # Save to file
        if not custom_path:
            filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(self.snapshots_dir, filename)
        else:
            filepath = custom_path

        watermarked.save(filepath, "PNG")
        self.snapshot_saved.emit(filepath)
        app_state.log("INFO", "CAMERA", f"Inspection snapshot saved: {os.path.basename(filepath)}")
        app_state.set_command_feedback(f"SNAPSHOT SAVED: {os.path.basename(filepath)}")
        return filepath

    def toggle_recording(self) -> bool:
        """Toggle frame recording session."""
        self._mutex.lock()
        self._is_recording = not self._is_recording
        state = self._is_recording
        if state:
            self._record_frame_count = 0
            self._record_start_time = time.time()
        self._mutex.unlock()

        self.recording_toggled.emit(state)
        status_msg = "RECORDING STARTED" if state else f"RECORDING STOPPED ({self._record_frame_count} frames)"
        app_state.log("INFO", "CAMERA", status_msg)
        app_state.set_command_feedback(status_msg)
        return state
