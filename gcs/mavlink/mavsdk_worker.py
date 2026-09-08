"""MAVLink & MAVSDK Background Worker Thread.

Direct, reliable MAVLink communications engine for PX4 SITL (Gazebo) and ArduPilot.
Provides:
- Direct UDP socket listener on port 14550 (PX4 GCS default) & port 14540 (PX4 companion)
- Zero subprocess overhead, zero gRPC dependencies, zero noisy terminal log spam
- 1 Hz GCS Heartbeat responder ensuring PX4 maintains active connection state
- Preflight parameter auto-bypass: CBRK_SUPPLY_CHK (power check) & COM_DISARM_PREROL (auto-disarm)
- Atomic Takeoff, Arm, Disarm, Land, RTL, and Hold flight operations
- High-rate 10 Hz MANUAL_CONTROL (#69) streaming for Virtual D-Pads & Keyboard WASD
- Object-oriented mission upload & execution (MissionPlan / MissionItem)
- Mock simulation mode for offline test isolation
"""

import math
import time
import socket
from typing import List, Dict, Any, Optional
from PySide6.QtCore import QThread, Signal, QMutex
from pymavlink import mavutil

from gcs.mavlink.mock_telemetry import MockTelemetryGenerator
from gcs.state.app_state import app_state, ConnectionState


def normalize_mavsdk_address(conn_str: str) -> str:
    """Normalize any user connection string into a standard pymavlink UDP/Serial URI."""
    s = (conn_str or "").strip()
    if not s or s.startswith("mock") or s.startswith("sim"):
        return "mock"
    # Strip any double slashes (e.g., udpin://0.0.0.0:14550 -> udpin:0.0.0.0:14550)
    s = s.replace("://", ":")
    if s.startswith("udpin:") or s.startswith("udpout:") or s.startswith("udp:") or s.startswith("tcp:") or s.startswith("serial:"):
        return s
    if ":" in s:
        host, port = s.split(":")
        return f"udpin:{host}:{port}"
    if s.isdigit():
        return f"udpin:0.0.0.0:{s}"
    return "udpin:0.0.0.0:14550"


class QMavsdkWorker(QThread):
    """Background worker thread consuming MAVLink packet streams with zero terminal spam."""

    connected_signal = Signal(int, int, str)   # sys_id, comp_id, vehicle_type
    disconnected_signal = Signal(str)
    connection_error_signal = Signal(str)
    telemetry_updated = Signal(dict)
    statustext_signal = Signal(int, str)
    command_ack_signal = Signal(str)            # feedback string
    mission_ack_signal = Signal(str)            # mission upload/download ACK
    mission_downloaded_signal = Signal(list)    # list of waypoint dicts

    def __init__(self, connection_str: str = "udpin:0.0.0.0:14550", baud: int = 57600, parent=None):
        super().__init__(parent)
        self.connection_str = connection_str
        self.normalized_address = normalize_mavsdk_address(connection_str)
        self.baud = baud
        self._running = False
        self._mock_mode = (self.normalized_address == "mock")
        self._mav = None
        self._mutex = QMutex()

        # Mock telemetry state cache (for simulation and test isolation)
        self._mock_telemetry_state = {}
        self._mock_mission_waypoints = []
        self._mock_active_wp_index = 0
        self._mock_uav_pos = [37.7749, -122.4194]

        # Manual control stick states (-1000..1000, throttle 0..1000 with 500 center)
        self._manual_x = 0
        self._manual_y = 0
        self._manual_z = 500
        self._manual_r = 0
        self._manual_active = False
        self._last_manual_send = 0.0

        self._connected = False
        self._sysid = 1
        self._compid = 1
        self._last_heartbeat_time = 0.0
        self._px4_configured = False

    # ──────────────────────────────────────────────────────────────────────────
    # Thread Run Loop
    # ──────────────────────────────────────────────────────────────────────────
    def run(self):
        self._running = True

        if self._mock_mode:
            self._run_mock_loop()
            return

        # Connect to live MAVLink stream (PX4 SITL Gazebo or hardware)
        try:
            # pymavlink connection
            conn_target = self.normalized_address
            # If udp:127.0.0.1:14550 or udpin:0.0.0.0:14550, handle bind gracefully
            self._mav = mavutil.mavlink_connection(
                conn_target,
                baud=self.baud,
                autoreconnect=True
            )
        except Exception as e:
            self.connection_error_signal.emit(f"Connection failed to {self.normalized_address}: {str(e)}")
            self._running = False
            return

        telemetry_cache: Dict[str, Any] = {
            "lat": 0.0, "lon": 0.0, "alt_rel": 0.0, "alt_abs": 0.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0, "groundspeed": 0.0,
            "heading": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "battery_pct": 100, "battery_v": 12.6, "gps_fix": "No Fix",
            "satellites": 0, "hdop": 99.0, "armed": False, "mode": "UNKNOWN",
            "system_id": 1, "component_id": 1, "autopilot": "PX4 Autopilot",
            "connection_str": self.connection_str, "timestamp": time.time(),
        }

        last_gcs_heartbeat_send = 0.0

        while self._running:
            try:
                now = time.time()

                # Send 1 Hz GCS Heartbeat so PX4 knows an operator GCS is active
                if now - last_gcs_heartbeat_send >= 1.0:
                    last_gcs_heartbeat_send = now
                    try:
                        self._mav.mav.heartbeat_send(
                            mavutil.mavlink.MAV_TYPE_GCS,
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                            0, 0, 0
                        )
                    except Exception:
                        pass

                # Stream 10 Hz MANUAL_CONTROL (#69) message if manual control is active
                if now - self._last_manual_send >= 0.1:
                    self._last_manual_send = now
                    if self._manual_active and self._mav is not None:
                        try:
                            self._mutex.lock()
                            mx = self._manual_x
                            my = self._manual_y
                            mz = self._manual_z
                            mr = self._manual_r
                            self._mutex.unlock()
                            self._mav.mav.manual_control_send(
                                self._sysid, mx, my, mz, mr, 0
                            )
                        except Exception:
                            self._mutex.unlock()

                # Read incoming MAVLink packet
                msg = self._mav.recv_match(blocking=True, timeout=0.15)
                now = time.time()

                if msg is not None:
                    msg_type = msg.get_type()

                    if msg_type == "HEARTBEAT":
                        self._last_heartbeat_time = now
                        self._sysid = msg.get_srcSystem()
                        self._compid = msg.get_srcComponent()
                        self._mav.target_system = self._sysid
                        self._mav.target_component = self._compid
                        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        mode_str = mavutil.mode_string_v10(msg)

                        vehicle_type = (
                            mavutil.mavlink.enums['MAV_TYPE'][msg.type].description
                            if msg.type in mavutil.mavlink.enums['MAV_TYPE']
                            else "PX4 Multicopter"
                        )

                        telemetry_cache.update({
                            "armed": armed, "mode": mode_str,
                            "system_id": self._sysid, "component_id": self._compid,
                            "autopilot": vehicle_type
                        })

                        if not self._connected:
                            self._connected = True
                            self.connected_signal.emit(self._sysid, self._compid, vehicle_type)
                            self._configure_px4_sitl()

                    elif msg_type == "GLOBAL_POSITION_INT":
                        telemetry_cache.update({
                            "lat": msg.lat / 1e7, "lon": msg.lon / 1e7,
                            "alt_rel": msg.relative_alt / 1000.0, "alt_abs": msg.alt / 1000.0,
                            "vx": msg.vx / 100.0, "vy": msg.vy / 100.0, "vz": msg.vz / 100.0,
                            "heading": msg.hdg / 100.0 if msg.hdg != 65535 else 0.0,
                        })
                    elif msg_type == "ATTITUDE":
                        telemetry_cache.update({
                            "roll": math.degrees(msg.roll),
                            "pitch": math.degrees(msg.pitch),
                            "yaw": (math.degrees(msg.yaw) + 360.0) % 360.0,
                        })
                    elif msg_type == "VFR_HUD":
                        telemetry_cache["groundspeed"] = float(msg.groundspeed)
                        telemetry_cache["heading"] = float(msg.heading)
                    elif msg_type == "SYS_STATUS":
                        telemetry_cache["battery_v"] = msg.voltage_battery / 1000.0
                        telemetry_cache["battery_pct"] = msg.battery_remaining if msg.battery_remaining >= 0 else 100
                    elif msg_type == "GPS_RAW_INT":
                        fix_map = {0: "No Fix", 1: "No Fix", 2: "2D Fix", 3: "3D Fix",
                                   4: "DGPS", 5: "RTK Float", 6: "RTK Fixed"}
                        telemetry_cache["gps_fix"] = fix_map.get(msg.fix_type, f"Fix {msg.fix_type}")
                        telemetry_cache["satellites"] = msg.satellites_visible
                        telemetry_cache["hdop"] = msg.eph / 100.0
                    elif msg_type == "STATUSTEXT":
                        text = msg.text
                        if isinstance(text, bytes):
                            text = text.decode('utf-8', errors='ignore')
                        self.statustext_signal.emit(msg.severity, text)
                    elif msg_type == "COMMAND_ACK":
                        res_str = self._describe_command_ack(msg.command, msg.result)
                        self.command_ack_signal.emit(res_str)
                    elif msg_type == "MISSION_CURRENT":
                        app_state.set_active_waypoint(msg.seq)
                    elif msg_type == "MISSION_ITEM_REACHED":
                        self.command_ack_signal.emit(f"WAYPOINT #{msg.seq} REACHED")

                    telemetry_cache["timestamp"] = now
                    if self._connected:
                        self.telemetry_updated.emit(dict(telemetry_cache))

                # Heartbeat timeout check (4.0s)
                if self._connected and (now - self._last_heartbeat_time > 4.0):
                    self._connected = False
                    self.disconnected_signal.emit("Vehicle heartbeat timeout (>4.0s)")

            except Exception:
                pass

        try:
            if self._mav:
                self._mav.close()
        except Exception:
            pass

        self._connected = False
        self.disconnected_signal.emit("MAVLink stream disconnected")

    def _describe_command_ack(self, cmd: int, result: int) -> str:
        """Convert MAV_RESULT code to friendly string."""
        results = {
            0: "ACCEPTED",
            1: "TEMPORARILY REJECTED",
            2: "DENIED",
            3: "UNSUPPORTED",
            4: "FAILED",
            5: "IN PROGRESS",
            6: "CANCELLED"
        }
        res_name = results.get(result, f"RESULT_{result}")
        if cmd == 400:  # ARM_DISARM
            return f"ARM/DISARM: {res_name}"
        elif cmd == 22:  # NAV_TAKEOFF
            return f"TAKEOFF: {res_name}"
        elif cmd == 21:  # NAV_LAND
            return f"LAND: {res_name}"
        elif cmd == 20:  # NAV_RETURN_TO_LAUNCH
            return f"RTL: {res_name}"
        elif cmd == 176: # DO_SET_MODE
            return f"MODE SWITCH: {res_name}"
        return f"CMD ACK ({cmd}): {res_name}"

    # ──────────────────────────────────────────────────────────────────────────
    # PX4 Preflight Parameter Configuration (Circuit Breakers)
    # ──────────────────────────────────────────────────────────────────────────
    def _set_param_int(self, param_name: str, value: int):
        """Send an INT32 parameter to PX4 using raw 4-byte IEEE 754 float packing."""
        import struct
        if self._mav is None:
            return
        try:
            param_bytes = param_name.encode('ascii')[:16]
            packed_float = struct.unpack('<f', struct.pack('<i', int(value)))[0]
            self._mav.mav.param_set_send(
                self._sysid, self._compid,
                param_bytes,
                packed_float,
                mavutil.mavlink.MAV_PARAM_TYPE_INT32
            )
        except Exception:
            pass

    def _set_param_float(self, param_name: str, value: float):
        """Send a REAL32 parameter to PX4."""
        if self._mav is None:
            return
        try:
            param_bytes = param_name.encode('ascii')[:16]
            self._mav.mav.param_set_send(
                self._sysid, self._compid,
                param_bytes,
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32
            )
        except Exception:
            pass

    def configure_px4_sitl(self):
        """Public trigger to apply all PX4 SITL circuit breakers and arming bypasses."""
        self._configure_px4_sitl()

    def _configure_px4_sitl(self):
        """Auto-configure all PX4 SITL circuit breakers so health checks pass cleanly."""
        if self._mock_mode or self._mav is None:
            return
        def _do_config():
            try:
                time.sleep(0.2)
                # Comprehensive INT32 Circuit Breakers & Pre-Arm Overrides
                # Packed as IEEE 754 float bytes so PX4's memcpy recovers the exact int32
                params_int = {
                    "CBRK_SUPPLY_CHK": 894281,  # Bypass battery / power module check
                    "CBRK_USB_CHK": 197848,     # Bypass USB connection check
                    "CBRK_IO_SAFETY": 22027,    # Bypass hardware safety switch
                    "CBRK_AIRSPD_CHK": 162128,  # Bypass airspeed sensor check
                    "CBRK_ENGINEPROC": 284953,  # Bypass engine failure check
                    "CBRK_FLIGHTTERM": 121212,  # Bypass flight termination check
                    "CBRK_VTOLARMING": 15987,   # Bypass VTOL arming check
                    "COM_RC_IN_MODE": 1,        # Joystick mode (disables RC transmitter requirement & checks)
                    "NAV_RCL_ACT": 0,           # Disable RC Loss failsafe
                    "NAV_DLL_ACT": 0,           # Disable DataLink Loss failsafe
                    "COM_RCL_EXCEPT": 7,        # Ignore RC loss in Mission(1) + Hold(2) + Offboard(4)
                    "COM_ARM_WO_GPS": 1,        # Allow arming without 3D GPS fix
                    "COM_ARM_MAG_STR": 0,       # Disable magnetic anomaly lock
                    "COM_ARM_EKF_POS": 0,       # Bypass EKF horizontal position lock
                    "COM_ARM_EKF_VEL": 0,       # Bypass EKF velocity lock
                    "COM_ARM_EKF_HGT": 0,       # Bypass EKF height lock
                    "COM_ARM_EKF_YAW": 0,       # Bypass EKF yaw lock
                    "COM_ARM_MIS_REQ": 0,       # Do not require mission to arm
                    "COM_ARM_AUTH_REQ": 0,      # Do not require arm authorization
                    "COM_PREARM_MODE": 0,       # Disable restrictive pre-arm checks
                }
                for name, val in params_int.items():
                    self._set_param_int(name, val)
                    time.sleep(0.02)

                # Float parameters: disable auto-disarm timers
                self._set_param_float("COM_DISARM_PREROL", 0.0)
                self._set_param_float("COM_DISARM_LAND", 0.0)
                time.sleep(0.05)

                # Disengage safety switch via MAVLink command (SAFETY_SWITCH_STATE_DANGEROUS = 1)
                try:
                    self._mav.mav.command_long_send(
                        self._sysid, self._compid,
                        5300,  # MAV_CMD_DO_SET_SAFETY_SWITCH_STATE
                        0,
                        1, 0, 0, 0, 0, 0, 0  # 1 = Safety Off / Armed
                    )
                except Exception:
                    pass

                # Request high-rate data streams
                self._mav.mav.request_data_stream_send(
                    self._sysid, self._compid,
                    mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1
                )
                app_state.log("INFO", "PX4", "Bypassed all SITL health checks (CBRK_SUPPLY_CHK, CBRK_USB_CHK, CBRK_IO_SAFETY, COM_RC_IN_MODE, COM_ARM_WO_GPS, COM_DISARM_PREROL).")
            except Exception as e:
                app_state.log("DEBUG", "PX4", f"SITL config note: {e}")
        import threading
        threading.Thread(target=_do_config, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    # Flight Operations (ARM, TAKEOFF, LAND, RTL, POSCTL)
    # ──────────────────────────────────────────────────────────────────────────
    def arm(self):
        """Arm vehicle motors in PX4 / ArduPilot with preflight bypasses."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_arm())
            return
        if self._mav is None:
            self.command_ack_signal.emit("ARM FAILED: NO CONNECTION")
            return
        def _do_arm():
            try:
                # 1. Re-assert key circuit breakers immediately before arming
                self._set_param_int("CBRK_SUPPLY_CHK", 894281)
                self._set_param_int("CBRK_USB_CHK", 197848)
                self._set_param_int("CBRK_IO_SAFETY", 22027)
                self._set_param_int("COM_RC_IN_MODE", 1)
                self._set_param_int("COM_ARM_WO_GPS", 1)
                self._set_param_float("COM_DISARM_PREROL", 0.0)
                time.sleep(0.05)

                # Disengage safety switch
                try:
                    self._mav.mav.command_long_send(
                        self._sysid, self._compid,
                        5300,  # MAV_CMD_DO_SET_SAFETY_SWITCH_STATE
                        0,
                        1, 0, 0, 0, 0, 0, 0
                    )
                except Exception:
                    pass
                time.sleep(0.05)

                self._mutex.lock()
                # 2. Send MAV_CMD_COMPONENT_ARM_DISARM with force=21196.0 (bypass preflight checks)
                self._mav.mav.command_long_send(
                    self._sysid, self._compid,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0,
                    1,        # 1 = Arm
                    21196.0,  # Force arm bypass
                    0, 0, 0, 0, 0
                )
                self._mutex.unlock()
                msg = "ARM COMMAND SENT (PREFLIGHT BYPASS ACTIVE)"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
            except Exception as e:
                self._mutex.unlock()
                self.command_ack_signal.emit(f"ARM ERROR: {e}")
        import threading
        threading.Thread(target=_do_arm, daemon=True).start()

    def disarm(self):
        """Disarm vehicle motors."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_disarm())
            return
        if self._mav is None:
            self.command_ack_signal.emit("DISARM FAILED: NO CONNECTION")
            return
        try:
            self._mutex.lock()
            self._mav.mav.command_long_send(
                self._sysid, self._compid,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 0, 21196.0, 0, 0, 0, 0, 0
            )
            self._mutex.unlock()
            msg = "DISARM COMMAND SENT"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"DISARM ERROR: {e}")

    def takeoff(self, altitude: float = 5.0):
        """Execute atomic takeoff to target altitude in Gazebo/PX4 with preflight bypass."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_takeoff(altitude))
            return
        if self._mav is None:
            self.command_ack_signal.emit("TAKEOFF FAILED: NO CONNECTION")
            return

        def _do_takeoff():
            try:
                # 0. Re-assert circuit breakers immediately before takeoff
                self._set_param_int("CBRK_SUPPLY_CHK", 894281)
                self._set_param_int("CBRK_USB_CHK", 197848)
                self._set_param_int("CBRK_IO_SAFETY", 22027)
                self._set_param_int("COM_RC_IN_MODE", 1)
                self._set_param_int("COM_ARM_WO_GPS", 1)
                self._set_param_float("COM_DISARM_PREROL", 0.0)
                try:
                    self._mav.mav.command_long_send(
                        self._sysid, self._compid,
                        5300,  # MAV_CMD_DO_SET_SAFETY_SWITCH_STATE
                        0,
                        1, 0, 0, 0, 0, 0, 0
                    )
                except Exception:
                    pass
                time.sleep(0.05)

                # 1. Arm vehicle
                self._mutex.lock()
                self._mav.mav.command_long_send(
                    self._sysid, self._compid,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, 1, 21196.0, 0, 0, 0, 0, 0
                )
                self._mutex.unlock()
                time.sleep(0.15)

                # 2. Send MAV_CMD_NAV_TAKEOFF with altitude
                self._mutex.lock()
                self._mav.mav.command_long_send(
                    self._sysid, self._compid,
                    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                    0,
                    0, 0, 0, float('nan'), float('nan'), float('nan'), float(altitude)
                )
                self._mutex.unlock()
                time.sleep(0.1)

                # 3. Switch to PX4 AUTO_TAKEOFF mode (custom_mode = (4 << 16) | (2 << 24) = 33816576)
                self._mutex.lock()
                try:
                    self._mav.mav.set_mode_send(
                        self._sysid,
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                        33816576
                    )
                except Exception:
                    pass
                try:
                    self._mav.mav.command_long_send(
                        self._sysid, self._compid,
                        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                        0, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 2, 0, 0, 0, 0
                    )
                except Exception:
                    pass
                self._mutex.unlock()

                msg = f"TAKEOFF COMMAND SENT — TARGET ALT: {altitude:.1f} m"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
            except Exception as e:
                self._mutex.unlock()
                self.command_ack_signal.emit(f"TAKEOFF ERROR: {e}")

        import threading
        threading.Thread(target=_do_takeoff, daemon=True).start()

    def land(self):
        """Command vehicle to land at current location."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_land())
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            # PX4 AUTO_LAND mode: (4, 6) = 100925440
            try:
                self._mav.mav.set_mode_send(
                    self._sysid,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    100925440
                )
            except Exception:
                pass
            self._mav.mav.command_long_send(
                self._sysid, self._compid,
                mavutil.mavlink.MAV_CMD_NAV_LAND,
                0, 0, 0, 0, 0, float('nan'), float('nan'), 0.0
            )
            self._mutex.unlock()
            msg = "LAND COMMAND SENT"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"LAND ERROR: {e}")

    def rtl(self):
        """Command vehicle to Return-to-Launch."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_rtl())
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            # PX4 AUTO_RTL mode: (4, 5) = 84148224
            try:
                self._mav.mav.set_mode_send(
                    self._sysid,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    84148224
                )
            except Exception:
                pass
            self._mav.mav.command_long_send(
                self._sysid, self._compid,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0, 0, 0, 0, 0, 0, 0, 0
            )
            self._mutex.unlock()
            msg = "RTL COMMAND SENT"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"RTL ERROR: {e}")

    def hold(self):
        """Command vehicle to hold position (LOITER)."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_loiter())
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            # PX4 AUTO_LOITER mode: (4, 3) = 50593792
            self._mav.mav.set_mode_send(
                self._sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                50593792
            )
            self._mutex.unlock()
            msg = "HOLD / LOITER COMMAND SENT"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"HOLD ERROR: {e}")

    def posctl(self):
        """Switch to POSCTL (Position Control) manual flight mode."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_posctl())
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            # PX4 POSCTL mode: (3, 0) = 196608
            self._mav.mav.set_mode_send(
                self._sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                196608
            )
            self._mutex.unlock()
            msg = "POSCTL MODE ACTIVATED"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"POSCTL ERROR: {e}")

    def altctl(self):
        """Switch to ALTCTL (Altitude Control) mode."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_altctl())
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            # PX4 ALTCTL mode: (2, 0) = 131072
            self._mav.mav.set_mode_send(
                self._sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                131072
            )
            self._mutex.unlock()
            msg = "ALTCTL MODE ACTIVATED"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"ALTCTL ERROR: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Manual Remote Control Inputs
    # ──────────────────────────────────────────────────────────────────────────
    def set_manual_control(self, x: int = 0, y: int = 0, z: int = 500, r: int = 0, active: bool = True):
        """Update stick inputs for 10Hz manual remote flight.
        
        x: pitch (-1000..1000, forward/back)
        y: roll (-1000..1000, right/left)
        z: throttle (0..1000, 500=hover)
        r: yaw (-1000..1000, clockwise/counter-clockwise)
        """
        self._mutex.lock()
        self._manual_x = int(max(-1000, min(1000, x)))
        self._manual_y = int(max(-1000, min(1000, y)))
        self._manual_z = int(max(0, min(1000, z)))
        self._manual_r = int(max(-1000, min(1000, r)))
        self._manual_active = active
        self._mutex.unlock()

    def stop_manual_control(self):
        """Immediately reset manual sticks to neutral hover."""
        self._mutex.lock()
        self._manual_x = 0
        self._manual_y = 0
        self._manual_z = 500
        self._manual_r = 0
        self._manual_active = False
        self._mutex.unlock()
        if not self._mock_mode and self._mav is not None:
            try:
                self._mav.mav.manual_control_send(self._sysid, 0, 0, 500, 0, 0)
            except Exception:
                pass

    def nudge(self, direction: str, duration_sec: float = 0.8, speed: int = 500):
        """Issue a timed directional pulse in POSCTL mode."""
        dx, dy, dz, dr = 0, 0, 500, 0
        dir_upper = direction.upper()
        if dir_upper in ("FORWARD", "UP_PAD"):
            dx = speed
        elif dir_upper in ("BACKWARD", "DOWN_PAD"):
            dx = -speed
        elif dir_upper == "LEFT":
            dy = -speed
        elif dir_upper == "RIGHT":
            dy = speed
        elif dir_upper in ("UP", "CLIMB"):
            dz = 500 + int(speed * 0.5)
        elif dir_upper in ("DOWN", "DESCEND"):
            dz = 500 - int(speed * 0.5)
        elif dir_upper in ("YAW_LEFT", "TURN_LEFT"):
            dr = -speed
        elif dir_upper in ("YAW_RIGHT", "TURN_RIGHT"):
            dr = speed

        self.set_manual_control(dx, dy, dz, dr, active=True)
        import threading
        def _reset_after():
            time.sleep(duration_sec)
            self.stop_manual_control()
        threading.Thread(target=_reset_after, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    # Object-Oriented Mission Protocol Engine
    # ──────────────────────────────────────────────────────────────────────────
    def upload_mission(self, waypoints: list):
        """Upload waypoints via MAVLink mission protocol."""
        if hasattr(waypoints, "waypoints"):
            waypoints = waypoints.waypoints

        if self._mock_mode:
            self._mock_mission_waypoints = list(waypoints)
            self._mock_active_wp_index = 0
            if waypoints:
                first_wp = waypoints[0]
                lat = first_wp.lat if hasattr(first_wp, "lat") else first_wp.get("lat", 37.7749)
                lon = first_wp.lon if hasattr(first_wp, "lon") else first_wp.get("lon", -122.4194)
                self._mock_uav_pos = [lat, lon]
            msg = f"MISSION UPLOAD: SUCCESS ({len(waypoints)} WPs)"
            self.mission_ack_signal.emit(msg)
            self.command_ack_signal.emit(msg)
            app_state.set_mission_status("UPLOADED")
            app_state.set_command_feedback(msg)
            return

        if self._mav is None:
            self.command_ack_signal.emit("UPLOAD FAILED: NO CONNECTION")
            return

        def _do_upload():
            try:
                self._mutex.lock()
                target_sys = self._sysid
                target_comp = self._compid

                self._mav.mav.mission_clear_all_send(target_sys, target_comp)
                time.sleep(0.1)

                count = len(waypoints)
                self._mav.mav.mission_count_send(target_sys, target_comp, count)

                for _ in range(count):
                    req = self._mav.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5.0)
                    if req is None:
                        raise TimeoutError("Timeout waiting for MISSION_REQUEST from vehicle")
                    seq = req.seq
                    wp = waypoints[seq]
                    cmd = int(wp.command if hasattr(wp, "command") else wp.get("command", 16))
                    frame = int(wp.frame if hasattr(wp, "frame") else wp.get("frame", 3))
                    p1 = float(wp.param1 if hasattr(wp, "param1") else wp.get("param1", 0.0) or 0.0)
                    p2 = float(wp.param2 if hasattr(wp, "param2") else wp.get("param2", 2.0) or 2.0)
                    p3 = float(wp.param3 if hasattr(wp, "param3") else wp.get("param3", 0.0) or 0.0)
                    p4 = float(wp.param4 if hasattr(wp, "param4") else wp.get("param4", 0.0) or 0.0)
                    lat = float(wp.lat if hasattr(wp, "lat") else wp.get("lat", 0.0) or 0.0)
                    lon = float(wp.lon if hasattr(wp, "lon") else wp.get("lon", 0.0) or 0.0)
                    alt = float(wp.alt if hasattr(wp, "alt") else wp.get("alt", 25.0) or 25.0)

                    is_current = 1 if seq == 0 else 0
                    autocontinue = 1

                    if req.get_type() == 'MISSION_REQUEST_INT':
                        self._mav.mav.mission_item_int_send(
                            target_sys, target_comp,
                            seq, frame, cmd, is_current, autocontinue, p1, p2, p3, p4,
                            int(lat * 1e7), int(lon * 1e7), float(alt)
                        )
                    else:
                        self._mav.mav.mission_item_send(
                            target_sys, target_comp,
                            seq, frame, cmd, is_current, autocontinue, p1, p2, p3, p4,
                            float(lat), float(lon), float(alt)
                        )

                ack = self._mav.recv_match(type='MISSION_ACK', blocking=True, timeout=5.0)
                if ack and getattr(ack, 'type', None) == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    try:
                        self._mav.mav.mission_set_current_send(target_sys, target_comp, 0)
                    except Exception:
                        pass

                self._mutex.unlock()
                if ack and getattr(ack, 'type', None) == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    success_msg = f"MISSION UPLOAD: SUCCESS ({count} WPs)"
                    self.mission_ack_signal.emit(success_msg)
                    self.command_ack_signal.emit(success_msg)
                    app_state.set_mission_status("UPLOADED")
                    app_state.set_command_feedback(success_msg)
                else:
                    ack_type = getattr(ack, 'type', 'timeout')
                    err_msg = f"MISSION UPLOAD REJECTED (ACK type={ack_type})"
                    self.command_ack_signal.emit(err_msg)
                    app_state.set_command_feedback(err_msg)
            except Exception as e:
                self._mutex.unlock()
                err_msg = f"MISSION UPLOAD ERROR: {str(e)}"
                self.command_ack_signal.emit(err_msg)
                app_state.set_command_feedback(err_msg)

        import threading
        threading.Thread(target=_do_upload, daemon=True).start()

    def start_mission(self):
        """Start autonomous mission flight in PX4 / Gazebo."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_guided())
            app_state.set_mission_status("RUNNING")
            return
        if self._mav is None:
            return
        try:
            # 1. Arm
            self.arm()
            time.sleep(0.1)
            self._mutex.lock()
            # 2. Switch to PX4 AUTO_MISSION mode: (4, 4) = 67371008
            self._mav.mav.set_mode_send(
                self._sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                67371008
            )
            # 3. Send MAV_CMD_MISSION_START
            self._mav.mav.command_long_send(
                self._sysid, self._compid,
                mavutil.mavlink.MAV_CMD_MISSION_START,
                0, 0, 0, 0, 0, 0, 0, 0
            )
            self._mutex.unlock()
            msg = "MISSION STARTED"
            self.command_ack_signal.emit(msg)
            app_state.set_mission_status("RUNNING")
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"START MISSION ERROR: {e}")

    def pause_mission(self):
        """Pause mission and hold position (LOITER)."""
        self.hold()
        app_state.set_mission_status("PAUSED")

    def clear_mission(self):
        """Clear mission waypoints."""
        if self._mock_mode:
            self._mock_mission_waypoints = []
            app_state.set_mission_status("IDLE")
            return
        if self._mav is None:
            return
        try:
            self._mutex.lock()
            self._mav.mav.mission_clear_all_send(self._sysid, self._compid)
            self._mutex.unlock()
            msg = "MISSION CLEARED"
            self.command_ack_signal.emit(msg)
            app_state.set_mission_status("IDLE")
            app_state.set_command_feedback(msg)
        except Exception as e:
            self._mutex.unlock()
            self.command_ack_signal.emit(f"CLEAR ERROR: {e}")

    def download_mission(self):
        """Download waypoints from vehicle."""
        if self._mock_mode:
            if not self._mock_mission_waypoints:
                from gcs.mavlink.mission_manager import Waypoint
                self._mock_mission_waypoints = [
                    Waypoint(seq=1, command=16, lat=37.7758, lon=-122.4184, alt=25.0, param1=3.0),
                    Waypoint(seq=2, command=16, lat=37.7765, lon=-122.4205, alt=30.0, param1=5.0),
                    Waypoint(seq=3, command=16, lat=37.7745, lon=-122.4215, alt=25.0, param1=2.0),
                ]
            wps_dicts = [wp.to_dict() if hasattr(wp, "to_dict") else wp for wp in self._mock_mission_waypoints]
            self.mission_downloaded_signal.emit(wps_dicts)
            app_state.set_mission_waypoints(wps_dicts)
            app_state.set_mission_status("LOADED")
            msg = f"MISSION DOWNLOAD: SUCCESS ({len(wps_dicts)} WPs)"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
            return

        if self._mav is None:
            self.command_ack_signal.emit("DOWNLOAD FAILED: NO CONNECTION")
            return

        def _do_download():
            try:
                self._mutex.lock()
                self._mav.mav.mission_request_list_send(self._sysid, self._compid)
                msg_count = self._mav.recv_match(type=['MISSION_COUNT'], blocking=True, timeout=3.0)
                if msg_count is None:
                    raise TimeoutError("Timeout waiting for MISSION_COUNT")

                count = msg_count.count
                downloaded_wps = []
                for seq in range(count):
                    self._mav.mav.mission_request_int_send(self._sysid, self._compid, seq)
                    item = self._mav.recv_match(type=['MISSION_ITEM_INT', 'MISSION_ITEM'], blocking=True, timeout=3.0)
                    if item is None:
                        raise TimeoutError(f"Timeout waiting for WP #{seq}")
                    lat = item.x / 1e7 if item.get_type() == 'MISSION_ITEM_INT' else item.x
                    lon = item.y / 1e7 if item.get_type() == 'MISSION_ITEM_INT' else item.y
                    wp = {
                        "seq": seq + 1,
                        "command": item.command,
                        "frame": item.frame,
                        "lat": lat,
                        "lon": lon,
                        "alt": item.z,
                        "param1": item.param1,
                        "param2": item.param2,
                        "param3": item.param3,
                        "param4": item.param4,
                        "autocontinue": bool(item.autocontinue),
                        "is_current": bool(item.current)
                    }
                    downloaded_wps.append(wp)

                self._mav.mav.mission_ack_send(self._sysid, self._compid, mavutil.mavlink.MAV_MISSION_ACCEPTED)
                self._mutex.unlock()

                self.mission_downloaded_signal.emit(downloaded_wps)
                app_state.set_mission_waypoints(downloaded_wps)
                app_state.set_mission_status("LOADED")
                success_msg = f"MISSION DOWNLOAD: SUCCESS ({len(downloaded_wps)} WPs)"
                self.command_ack_signal.emit(success_msg)
                app_state.set_command_feedback(success_msg)
            except Exception as e:
                self._mutex.unlock()
                self.command_ack_signal.emit(f"MISSION DOWNLOAD ERROR: {str(e)}")

        import threading
        threading.Thread(target=_do_download, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    # Payload Release
    # ──────────────────────────────────────────────────────────────────────────
    def release_payload(self, servo_channel: int = 9, pwm: int = 1900):
        """Trigger emergency payload release via MAV_CMD_DO_SET_SERVO."""
        from gcs.mavlink import commands
        if self._mock_mode:
            result = commands.mock_payload_release(servo_channel, pwm)
            self.dispatch_mock(result)
        else:
            self.dispatch_real(commands.send_payload_release, servo_channel, pwm)

    # ──────────────────────────────────────────────────────────────────────────
    # Dispatchers
    # ──────────────────────────────────────────────────────────────────────────
    def dispatch_mock(self, mock_result: dict):
        """Apply a mock command result (patches telemetry state & emits feedback)."""
        self._mutex.lock()
        patch = mock_result.get("telemetry_patch", {})
        self._mock_telemetry_state.update(patch)
        self._mutex.unlock()
        feedback = mock_result.get("result", "COMMAND SENT [MOCK]")
        self.command_ack_signal.emit(feedback)

    def dispatch_real(self, cmd_func, *args) -> str:
        """Route to appropriate high-level command or execute direct helper."""
        func_name = getattr(cmd_func, "__name__", "")
        if "arm" in func_name and "disarm" not in func_name:
            self.arm()
            return "ARM COMMAND SENT"
        elif "disarm" in func_name:
            self.disarm()
            return "DISARM COMMAND SENT"
        elif "takeoff" in func_name:
            alt = args[0] if args else 5.0
            self.takeoff(alt)
            return f"TAKEOFF COMMAND SENT — TARGET ALT: {alt:.1f} m"
        elif "land" in func_name:
            self.land()
            return "LAND COMMAND SENT"
        elif "rtl" in func_name:
            self.rtl()
            return "RTL COMMAND SENT"
        elif "loiter" in func_name or "hold" in func_name:
            self.hold()
            return "HOLD COMMAND SENT"
        elif "posctl" in func_name:
            self.posctl()
            return "POSCTL MODE ACTIVATED"
        elif "altctl" in func_name:
            self.altctl()
            return "ALTCTL MODE ACTIVATED"
        elif "mission_start" in func_name:
            self.start_mission()
            return "MISSION STARTED"
        elif "guided" in func_name:
            self.start_mission()
            return "GUIDED MODE ACTIVATED"
        elif "abort" in func_name:
            self.rtl()
            return "EMERGENCY ABORT INITIATED — RTL"

        if self._mav is None:
            return "NO ACTIVE CONNECTION"
        try:
            self._mutex.lock()
            result = cmd_func(self._mav, *args)
            self._mutex.unlock()
            self.command_ack_signal.emit(result)
            return result
        except Exception as e:
            self._mutex.unlock()
            err = f"COMMAND ERROR: {str(e)}"
            self.command_ack_signal.emit(err)
            return err

    # ──────────────────────────────────────────────────────────────────────────
    # Mock Simulation Loop
    # ──────────────────────────────────────────────────────────────────────────
    def _run_mock_loop(self):
        self.connected_signal.emit(1, 1, "PX4 Autopilot (Simulation Mode)")
        self.statustext_signal.emit(6, "Simulation Mode Connected [Direct Engine]")
        self.statustext_signal.emit(6, "EKF3 IMU0 is using GPS")
        self.statustext_signal.emit(6, "PX4 Autopilot V1.15.0 (Simulation)")

        generator = MockTelemetryGenerator()
        tick = 0
        while self._running:
            tick += 1
            telemetry = generator.generate_packet(tick)

            self._mutex.lock()
            mode = self._mock_telemetry_state.get("mode", "")
            if mode in ("AUTO", "GUIDED", "MISSION") and self._mock_mission_waypoints:
                if self._mock_active_wp_index < len(self._mock_mission_waypoints):
                    target = self._mock_mission_waypoints[self._mock_active_wp_index]
                    target_lat = target.lat if hasattr(target, "lat") else target.get("lat", 37.7749)
                    target_lon = target.lon if hasattr(target, "lon") else target.get("lon", -122.4194)
                    target_alt = target.alt if hasattr(target, "alt") else target.get("alt", 25.0)

                    cur_lat = self._mock_uav_pos[0]
                    cur_lon = self._mock_uav_pos[1]
                    d_lat = target_lat - cur_lat
                    d_lon = target_lon - cur_lon
                    dist = math.hypot(d_lat, d_lon)

                    if dist < 0.00015:
                        seq = self._mock_active_wp_index + 1
                        self._mock_active_wp_index += 1
                        if self._mock_active_wp_index >= len(self._mock_mission_waypoints):
                            self._mock_telemetry_state["mode"] = "HOLD"
                            app_state.set_mission_status("IDLE")
                            self.command_ack_signal.emit("MISSION COMPLETE: ALL WAYPOINTS VISITED")
                        else:
                            app_state.set_active_waypoint(self._mock_active_wp_index + 1)
                            self.command_ack_signal.emit(f"WAYPOINT #{seq} REACHED")
                    else:
                        step = 0.00008
                        ratio = step / dist
                        self._mock_uav_pos[0] += d_lat * ratio
                        self._mock_uav_pos[1] += d_lon * ratio
                        heading = (math.degrees(math.atan2(d_lon, d_lat)) + 360) % 360
                        self._mock_telemetry_state.update({
                            "lat": self._mock_uav_pos[0],
                            "lon": self._mock_uav_pos[1],
                            "alt_rel": target_alt,
                            "heading": heading,
                            "groundspeed": 12.0,
                        })

            if self._manual_active:
                vx = (self._manual_x / 1000.0) * 0.00008
                vy = (self._manual_y / 1000.0) * 0.00008
                vz = ((self._manual_z - 500) / 500.0) * 0.4
                vr = (self._manual_r / 1000.0) * 4.0
                self._mock_uav_pos[0] += vx
                self._mock_uav_pos[1] += vy
                cur_alt = self._mock_telemetry_state.get("alt_rel", 5.0)
                new_alt = max(0.0, cur_alt + vz)
                cur_hdg = self._mock_telemetry_state.get("heading", 0.0)
                new_hdg = (cur_hdg + vr + 360) % 360
                self._mock_telemetry_state.update({
                    "lat": self._mock_uav_pos[0],
                    "lon": self._mock_uav_pos[1],
                    "alt_rel": new_alt,
                    "heading": new_hdg,
                    "mode": "POSCTL"
                })

            telemetry.update(self._mock_telemetry_state)
            self._mutex.unlock()
            self.telemetry_updated.emit(telemetry)
            self.msleep(100)

        self.disconnected_signal.emit("Simulation stopped")

    def stop(self):
        """Stop worker thread safely."""
        self._running = False
        self.quit()
        self.wait(1000)
