"""Manual Remote Control Widget for UAV GCS.

Phase 17: QGroundControl-Grade Manual Remote Control Interface.
Provides:
- Flight Mode switching (POSCTL, ALTCTL, LOITER, LAND, RTL, STABILIZE)
- 1-Click Takeoff (user-defined target altitude, auto-arms and engages TAKEOFF mode)
- Virtual Directional Pads for Translation (Pitch/Roll) and Vertical/Yaw (Throttle/Heading)
- Continuous MAVLink MANUAL_CONTROL (#69) streaming & discrete step nudging
- Real-time Keyboard WASD / RF / QE controls with safety auto-hover release
- Mini Telemetry HUD strip (Mode, Arm state, Altitude, Speed, Heading)
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QFrame,
    QDialog,
    QSlider,
)
from PySide6.QtCore import Qt, QTimer, Signal
from gcs.state.app_state import app_state, ConnectionState, FlightState


class ManualControlView(QWidget):
    """Interactive Manual Remote Control view modeled after QGroundControl."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("manualControlView")
        self._worker = None
        self._speed_scale = 500  # Default normal speed stick magnitude (range 100..1000)
        self._keyboard_enabled = True

        self._active_keys = set()
        self._key_timer = QTimer(self)
        self._key_timer.setInterval(100)  # 10 Hz keyboard stick update
        self._key_timer.timeout.connect(self._process_active_keys)

        self._init_ui()
        self._connect_signals()
        self._refresh_ui()

    def set_worker(self, worker):
        """Inject active MAVLink worker reference."""
        self._worker = worker
        self._refresh_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # ── 1. Header & Live Mini HUD ──
        header_group = QGroupBox("MANUAL FLIGHT STATUS")
        header_group.setStyleSheet("""
            QGroupBox {
                font-weight: 700;
                font-size: 11px;
                color: #58a6ff;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 6px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        h_layout = QHBoxLayout(header_group)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(8)

        self.lbl_hud_mode = QLabel("MODE: --")
        self.lbl_hud_mode.setStyleSheet("font-weight: bold; color: #79c0ff; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d;")
        h_layout.addWidget(self.lbl_hud_mode)

        self.lbl_hud_arm = QLabel("DISARMED")
        self.lbl_hud_arm.setStyleSheet("font-weight: bold; color: #d29922; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d;")
        h_layout.addWidget(self.lbl_hud_arm)

        self.lbl_hud_alt = QLabel("ALT: 0.0 m")
        self.lbl_hud_alt.setStyleSheet("color: #c9d1d9; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d;")
        h_layout.addWidget(self.lbl_hud_alt)

        self.lbl_hud_spd = QLabel("SPD: 0.0 m/s")
        self.lbl_hud_spd.setStyleSheet("color: #c9d1d9; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d;")
        h_layout.addWidget(self.lbl_hud_spd)

        root_layout.addWidget(header_group)

        # ── 2. Primary Flight Modes ──
        mode_group = QGroupBox("FLIGHT MODES")
        mode_group.setStyleSheet("QGroupBox { font-weight: 700; font-size: 11px; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        mode_layout = QGridLayout(mode_group)
        mode_layout.setSpacing(6)

        self.btn_posctl = QPushButton("POSCTL (Hold)")
        self.btn_posctl.setToolTip("Position Control: primary safe manual flight mode. Rock-solid GPS/altitude hold.")
        self.btn_posctl.setStyleSheet("font-weight: bold; color: #3fb950; background: #21262d; border: 1px solid #238636; padding: 6px;")
        self.btn_posctl.clicked.connect(self._on_posctl)
        mode_layout.addWidget(self.btn_posctl, 0, 0)

        self.btn_loiter = QPushButton("LOITER (Hover)")
        self.btn_loiter.setToolTip("Loiter / Hold position in 3D space")
        self.btn_loiter.clicked.connect(self._on_loiter)
        mode_layout.addWidget(self.btn_loiter, 0, 1)

        self.btn_altctl = QPushButton("ALTCTL")
        self.btn_altctl.setToolTip("Altitude hold mode with manual tilt")
        self.btn_altctl.clicked.connect(self._on_altctl)
        mode_layout.addWidget(self.btn_altctl, 1, 0)

        self.btn_land = QPushButton("LAND")
        self.btn_land.setToolTip("Land immediately at current position")
        self.btn_land.setStyleSheet("color: #f85149;")
        self.btn_land.clicked.connect(self._on_land)
        mode_layout.addWidget(self.btn_land, 1, 1)

        self.btn_rtl = QPushButton("RTL (Home)")
        self.btn_rtl.setToolTip("Return to launch coordinates and land")
        self.btn_rtl.setStyleSheet("color: #e3b341;")
        self.btn_rtl.clicked.connect(self._on_rtl)
        mode_layout.addWidget(self.btn_rtl, 2, 0, 1, 2)

        root_layout.addWidget(mode_group)

        # ── 3. Quick Takeoff Box ──
        takeoff_group = QGroupBox("TAKEOFF & ARMING")
        takeoff_group.setStyleSheet("QGroupBox { font-weight: 700; font-size: 11px; color: #3fb950; border: 1px solid #238636; border-radius: 6px; margin-top: 6px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        t_layout = QHBoxLayout(takeoff_group)
        t_layout.setContentsMargins(8, 8, 8, 8)
        t_layout.setSpacing(6)

        lbl_alt = QLabel("Alt (m):")
        lbl_alt.setStyleSheet("font-size: 11px; font-weight: 600;")
        t_layout.addWidget(lbl_alt)

        self.spin_takeoff_alt = QDoubleSpinBox()
        self.spin_takeoff_alt.setRange(1.0, 100.0)
        self.spin_takeoff_alt.setValue(5.0)
        self.spin_takeoff_alt.setSingleStep(1.0)
        self.spin_takeoff_alt.setSuffix(" m")
        self.spin_takeoff_alt.setStyleSheet("background: #161b22; color: #58a6ff; font-weight: bold; border: 1px solid #30363d; border-radius: 4px; padding: 4px;")
        t_layout.addWidget(self.spin_takeoff_alt)

        self.btn_takeoff = QPushButton("🚀 TAKEOFF")
        self.btn_takeoff.setToolTip("Auto-arms vehicle and commands climb to target altitude")
        self.btn_takeoff.setStyleSheet("font-weight: bold; background: #238636; color: white; border-radius: 4px; padding: 6px 12px;")
        self.btn_takeoff.clicked.connect(self._on_takeoff)
        t_layout.addWidget(self.btn_takeoff)

        self.btn_arm_toggle = QPushButton("ARM")
        self.btn_arm_toggle.setToolTip("Toggle Arm/Disarm")
        self.btn_arm_toggle.setStyleSheet("font-weight: bold; color: #58a6ff; border: 1px solid #30363d; padding: 6px 10px;")
        self.btn_arm_toggle.clicked.connect(self._on_arm_toggle)
        t_layout.addWidget(self.btn_arm_toggle)

        root_layout.addWidget(takeoff_group)

        # ── 4. Directional Flight Controls ──
        pads_layout = QHBoxLayout()
        pads_layout.setSpacing(12)

        # Translation Pad (Pitch / Roll)
        trans_group = QGroupBox("PITCH & ROLL (Motion)")
        trans_group.setStyleSheet("QGroupBox { font-weight: 700; font-size: 11px; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grid_trans = QGridLayout(trans_group)
        grid_trans.setSpacing(4)

        self.btn_forward = self._make_dpad_btn("▲ FORWARD\n(W)", "nudge_forward")
        self.btn_backward = self._make_dpad_btn("▼ BACKWARD\n(S)", "nudge_backward")
        self.btn_left = self._make_dpad_btn("◀ LEFT\n(A)", "nudge_left")
        self.btn_right = self._make_dpad_btn("RIGHT ▶\n(D)", "nudge_right")
        self.btn_brake = QPushButton("🛑 BRAKE\n(Space)")
        self.btn_brake.setStyleSheet("font-weight: bold; color: #f85149; background: #21262d; border: 1px solid #da3633; border-radius: 4px; padding: 8px;")
        self.btn_brake.clicked.connect(self._on_brake)

        grid_trans.addWidget(self.btn_forward, 0, 1)
        grid_trans.addWidget(self.btn_left, 1, 0)
        grid_trans.addWidget(self.btn_brake, 1, 1)
        grid_trans.addWidget(self.btn_right, 1, 2)
        grid_trans.addWidget(self.btn_backward, 2, 1)
        pads_layout.addWidget(trans_group)

        # Altitude & Yaw Pad (Throttle / Heading)
        alt_yaw_group = QGroupBox("ALTITUDE & YAW")
        alt_yaw_group.setStyleSheet("QGroupBox { font-weight: 700; font-size: 11px; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grid_altyaw = QGridLayout(alt_yaw_group)
        grid_altyaw.setSpacing(4)

        self.btn_climb = self._make_dpad_btn("▲ CLIMB\n(R / ↑)", "nudge_climb")
        self.btn_descend = self._make_dpad_btn("▼ DESCEND\n(F / ↓)", "nudge_descend")
        self.btn_yaw_left = self._make_dpad_btn("↺ YAW L\n(Q)", "nudge_yaw_l")
        self.btn_yaw_right = self._make_dpad_btn("↻ YAW R\n(E)", "nudge_yaw_r")
        self.btn_center = QPushButton("⚓ HOVER")
        self.btn_center.setStyleSheet("font-weight: bold; color: #58a6ff; background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 8px;")
        self.btn_center.clicked.connect(self._on_brake)

        grid_altyaw.addWidget(self.btn_climb, 0, 1)
        grid_altyaw.addWidget(self.btn_yaw_left, 1, 0)
        grid_altyaw.addWidget(self.btn_center, 1, 1)
        grid_altyaw.addWidget(self.btn_yaw_right, 1, 2)
        grid_altyaw.addWidget(self.btn_descend, 2, 1)
        pads_layout.addWidget(alt_yaw_group)

        root_layout.addLayout(pads_layout)

        # ── 5. Speed & Keyboard Settings ──
        settings_group = QGroupBox("CONTROL TUNING & HOTKEYS")
        settings_group.setStyleSheet("QGroupBox { font-weight: 700; font-size: 11px; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        s_layout = QVBoxLayout(settings_group)
        s_layout.setSpacing(6)

        speed_row = QHBoxLayout()
        lbl_speed = QLabel("Speed Magnitude:")
        lbl_speed.setStyleSheet("font-size: 11px;")
        speed_row.addWidget(lbl_speed)

        self.btn_spd_slow = QPushButton("Slow (1 m/s)")
        self.btn_spd_slow.setCheckable(True)
        self.btn_spd_slow.clicked.connect(lambda: self._set_speed(300))
        speed_row.addWidget(self.btn_spd_slow)

        self.btn_spd_norm = QPushButton("Normal (3 m/s)")
        self.btn_spd_norm.setCheckable(True)
        self.btn_spd_norm.setChecked(True)
        self.btn_spd_norm.clicked.connect(lambda: self._set_speed(500))
        speed_row.addWidget(self.btn_spd_norm)

        self.btn_spd_fast = QPushButton("Fast (5 m/s)")
        self.btn_spd_fast.setCheckable(True)
        self.btn_spd_fast.clicked.connect(lambda: self._set_speed(800))
        speed_row.addWidget(self.btn_spd_fast)

        s_layout.addLayout(speed_row)

        self.chk_keyboard = QCheckBox("Enable Keyboard Hotkeys (W, A, S, D, Q, E, R, F, Space)")
        self.chk_keyboard.setChecked(True)
        self.chk_keyboard.setStyleSheet("color: #79c0ff; font-weight: 600; font-size: 11px;")
        self.chk_keyboard.toggled.connect(self._on_keyboard_toggle)
        s_layout.addWidget(self.chk_keyboard)

        lbl_hint = QLabel("Tip: Click on this panel to focus keyboard control. Releasing keys immediately holds position.")
        lbl_hint.setStyleSheet("color: #8b949e; font-size: 10px; font-style: italic;")
        s_layout.addWidget(lbl_hint)

        root_layout.addWidget(settings_group)
        root_layout.addStretch()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _make_dpad_btn(self, text: str, action: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet("""
            QPushButton {
                font-weight: 700;
                font-size: 11px;
                color: #c9d1d9;
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px 4px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #30363d;
                color: #58a6ff;
                border-color: #58a6ff;
            }
            QPushButton:pressed {
                background-color: #1f6feb;
                color: white;
            }
        """)
        # Connect pressed and released for continuous motion
        if action == "nudge_forward":
            btn.pressed.connect(lambda: self._start_motion(dx=self._speed_scale))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_backward":
            btn.pressed.connect(lambda: self._start_motion(dx=-self._speed_scale))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_left":
            btn.pressed.connect(lambda: self._start_motion(dy=-self._speed_scale))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_right":
            btn.pressed.connect(lambda: self._start_motion(dy=self._speed_scale))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_climb":
            btn.pressed.connect(lambda: self._start_motion(dz=500 + int(self._speed_scale * 0.5)))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_descend":
            btn.pressed.connect(lambda: self._start_motion(dz=500 - int(self._speed_scale * 0.5)))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_yaw_l":
            btn.pressed.connect(lambda: self._start_motion(dr=-self._speed_scale))
            btn.released.connect(self._stop_motion)
        elif action == "nudge_yaw_r":
            btn.pressed.connect(lambda: self._start_motion(dr=self._speed_scale))
            btn.released.connect(self._stop_motion)
        return btn

    def _set_speed(self, val: int):
        self._speed_scale = val
        self.btn_spd_slow.setChecked(val == 300)
        self.btn_spd_norm.setChecked(val == 500)
        self.btn_spd_fast.setChecked(val == 800)

    def _connect_signals(self):
        app_state.connection_changed.connect(self._on_connection_changed_slot)
        app_state.arm_state_changed.connect(self._on_arm_state_changed_slot)
        app_state.telemetry_updated.connect(self._on_telemetry_updated)
        app_state.flight_mode_changed.connect(self._on_flight_mode_changed_slot)

    def _on_connection_changed_slot(self, _=None):
        self._refresh_ui()

    def _on_arm_state_changed_slot(self, _=None):
        self._refresh_ui()

    def _on_flight_mode_changed_slot(self, m: str):
        try:
            self.lbl_hud_mode.setText(f"MODE: {m}")
        except RuntimeError:
            pass

    def _on_telemetry_updated(self, t: dict):
        try:
            mode = t.get("mode", app_state.flight_mode)
            self.lbl_hud_mode.setText(f"MODE: {mode}")

            armed = t.get("armed", app_state.arm_state == FlightState.ARMED)
            if armed:
                self.lbl_hud_arm.setText("ARMED")
                self.lbl_hud_arm.setStyleSheet("font-weight: bold; color: #3fb950; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #238636;")
                self.btn_arm_toggle.setText("DISARM")
                self.btn_arm_toggle.setStyleSheet("font-weight: bold; color: #d29922; border: 1px solid #30363d; padding: 6px 10px;")
            else:
                self.lbl_hud_arm.setText("DISARMED")
                self.lbl_hud_arm.setStyleSheet("font-weight: bold; color: #d29922; background: #161b22; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d;")
                self.btn_arm_toggle.setText("ARM")
                self.btn_arm_toggle.setStyleSheet("font-weight: bold; color: #3fb950; border: 1px solid #30363d; padding: 6px 10px;")

            alt = t.get("alt_rel", 0.0)
            self.lbl_hud_alt.setText(f"ALT: {alt:.1f} m" if isinstance(alt, (int, float)) else f"ALT: {alt}")

            spd = t.get("groundspeed", 0.0)
            self.lbl_hud_spd.setText(f"SPD: {spd:.1f} m/s" if isinstance(spd, (int, float)) else f"SPD: {spd}")
        except RuntimeError:
            pass

    def _refresh_ui(self):
        try:
            is_conn = (app_state.connection_status == ConnectionState.CONNECTED)
            self.btn_takeoff.setEnabled(is_conn)
            self.btn_arm_toggle.setEnabled(is_conn)
            self.btn_posctl.setEnabled(is_conn)
            self.btn_loiter.setEnabled(is_conn)
            self.btn_altctl.setEnabled(is_conn)
            self.btn_land.setEnabled(is_conn)
            self.btn_rtl.setEnabled(is_conn)
            self.btn_forward.setEnabled(is_conn)
            self.btn_backward.setEnabled(is_conn)
            self.btn_left.setEnabled(is_conn)
            self.btn_right.setEnabled(is_conn)
            self.btn_climb.setEnabled(is_conn)
            self.btn_descend.setEnabled(is_conn)
            self.btn_yaw_left.setEnabled(is_conn)
            self.btn_yaw_right.setEnabled(is_conn)
            self.btn_brake.setEnabled(is_conn)
            self.btn_center.setEnabled(is_conn)
        except RuntimeError:
            pass

    # ── Motion Commands ──
    def _start_motion(self, dx: int = 0, dy: int = 0, dz: int = 500, dr: int = 0):
        if not self._worker:
            return
        if hasattr(self._worker, "set_manual_control"):
            self._worker.set_manual_control(dx, dy, dz, dr, active=True)

    def _stop_motion(self):
        if not self._worker:
            return
        if hasattr(self._worker, "stop_manual_control"):
            self._worker.stop_manual_control()

    def _on_brake(self):
        self._stop_motion()
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                self._worker.dispatch_mock(commands.mock_loiter())
            else:
                self._worker.dispatch_real(commands.send_loiter)
            app_state.set_command_feedback("BRAKE ACTIVATED — VEHICLE IN HOVER")

    def _on_posctl(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_posctl())
        else:
            self._worker.dispatch_real(commands.send_posctl)
        app_state.set_command_feedback("MODE SWITCH: POSCTL (POSITION HOLD)")

    def _on_loiter(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_loiter())
        else:
            self._worker.dispatch_real(commands.send_loiter)
        app_state.set_command_feedback("MODE SWITCH: LOITER")

    def _on_altctl(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_altctl())
        else:
            self._worker.dispatch_real(commands.send_altctl)
        app_state.set_command_feedback("MODE SWITCH: ALTCTL")

    def _on_land(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_land())
        else:
            self._worker.dispatch_real(commands.send_land)
        app_state.set_command_feedback("LANDING COMMAND SENT")

    def _on_rtl(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_rtl())
        else:
            self._worker.dispatch_real(commands.send_rtl)
        app_state.set_command_feedback("RETURN TO LAUNCH COMMAND SENT")

    def _on_takeoff(self):
        if not self._worker:
            return
        alt = self.spin_takeoff_alt.value()
        lat = app_state.uav_latitude
        lon = app_state.uav_longitude
        from gcs.mavlink import commands
        if self._worker._mock_mode:
            self._worker.dispatch_mock(commands.mock_takeoff(alt))
        else:
            self._worker.dispatch_real(commands.send_takeoff, alt, lat, lon)
        app_state.set_command_feedback(f"TAKEOFF INITIATED: TARGET ALTITUDE {alt:.1f} m")

    def _on_arm_toggle(self):
        if not self._worker:
            return
        from gcs.mavlink import commands
        is_armed = (app_state.arm_state == FlightState.ARMED)
        if is_armed:
            if self._worker._mock_mode:
                self._worker.dispatch_mock(commands.mock_disarm())
            else:
                self._worker.dispatch_real(commands.send_disarm)
            app_state.set_command_feedback("DISARM COMMAND SENT")
        else:
            if self._worker._mock_mode:
                self._worker.dispatch_mock(commands.mock_arm())
            else:
                self._worker.dispatch_real(commands.send_arm)
            app_state.set_command_feedback("ARM COMMAND SENT")

    # ── Keyboard Flight Control ──
    def _on_keyboard_toggle(self, enabled: bool):
        self._keyboard_enabled = enabled
        if not enabled:
            self._active_keys.clear()
            self._stop_motion()
            self._key_timer.stop()
        else:
            self.setFocus()

    def keyPressEvent(self, event):
        if not self._keyboard_enabled or event.isAutoRepeat():
            super().keyPressEvent(event)
            return

        key = event.key()
        valid_keys = {
            Qt.Key.Key_W, Qt.Key.Key_S, Qt.Key.Key_A, Qt.Key.Key_D,
            Qt.Key.Key_Q, Qt.Key.Key_E, Qt.Key.Key_R, Qt.Key.Key_F,
            Qt.Key.Key_Space, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right
        }
        if key in valid_keys:
            self._active_keys.add(key)
            if not self._key_timer.isActive():
                self._key_timer.start()
            self._process_active_keys()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not self._keyboard_enabled or event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return

        key = event.key()
        if key in self._active_keys:
            self._active_keys.discard(key)
            if not self._active_keys:
                self._key_timer.stop()
                self._stop_motion()
            else:
                self._process_active_keys()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def _process_active_keys(self):
        if not self._worker or not self._active_keys:
            return

        dx, dy, dz, dr = 0, 0, 500, 0
        spd = self._speed_scale

        if Qt.Key.Key_Space in self._active_keys:
            self._on_brake()
            return

        # Translation
        if Qt.Key.Key_W in self._active_keys:
            dx += spd
        if Qt.Key.Key_S in self._active_keys:
            dx -= spd
        if Qt.Key.Key_A in self._active_keys:
            dy -= spd
        if Qt.Key.Key_D in self._active_keys:
            dy += spd

        # Heading (Yaw)
        if Qt.Key.Key_Q in self._active_keys:
            dr -= spd
        if Qt.Key.Key_E in self._active_keys:
            dr += spd

        # Altitude (Throttle)
        if Qt.Key.Key_R in self._active_keys or Qt.Key.Key_Up in self._active_keys:
            dz = 500 + int(spd * 0.5)
        if Qt.Key.Key_F in self._active_keys or Qt.Key.Key_Down in self._active_keys:
            dz = 500 - int(spd * 0.5)

        self._start_motion(dx=dx, dy=dy, dz=dz, dr=dr)
