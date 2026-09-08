"""MAVLink Background Worker Thread.

Handles network & serial connections via pymavlink.mavutil, parsing incoming packets
(HEARTBEAT, GLOBAL_POSITION_INT, ATTITUDE, VFR_HUD, SYS_STATUS, GPS_RAW_INT, STATUSTEXT)
and emitting Qt signals for non-blocking main UI updates.

Phase 3 addition: dispatch() method for safe outbound command sending.
"""

import math
import time
from PySide6.QtCore import QThread, Signal, QMutex
from pymavlink import mavutil
from gcs.mavlink.mock_telemetry import MockTelemetryGenerator
from gcs.state.app_state import app_state


class QMavlinkWorker(QThread):
    """Background worker thread consuming MAVLink packet streams."""

    connected_signal = Signal(int, int, str)   # sys_id, comp_id, vehicle_type
    disconnected_signal = Signal(str)
    connection_error_signal = Signal(str)
    telemetry_updated = Signal(dict)
    statustext_signal = Signal(int, str)
    command_ack_signal = Signal(str)            # feedback string
    mission_ack_signal = Signal(str)            # mission upload/download ACK
    mission_downloaded_signal = Signal(list)    # list of waypoint dicts

    def __init__(self, connection_str="udp:127.0.0.1:14550", baud=57600, parent=None):
        super().__init__(parent)
        self.connection_str = connection_str
        self.baud = baud
        self._running = False
        self._mock_mode = bool(self.connection_str.startswith("mock") or self.connection_str.startswith("sim"))
        self._mav = None
        self._mutex = QMutex()

        # Mock telemetry state cache (mutated by mock commands)
        self._mock_telemetry_state = {}
        self._mock_mission_waypoints = []
        self._mock_active_wp_index = 0
        self._mock_uav_pos = [37.7749, -122.4194]

        self._last_heartbeat_time = 0.0
        self._connected = False
        self._sysid = 1
        self._compid = 1

    # ──────────────────────────────────────────────────────────────────────────
    # Thread Run Method
    # ──────────────────────────────────────────────────────────────────────────
    def run(self):
        self._running = True

        if self.connection_str.startswith("mock") or self.connection_str.startswith("sim"):
            self._mock_mode = True
            self.connected_signal.emit(1, 1, "ArduCopter (Quadrotor)")
            self.statustext_signal.emit(6, "Mock MAVLink Stream Connected [SITL Sim Mode]")
            self.statustext_signal.emit(6, "EKF3 IMU0 is using GPS")
            self.statustext_signal.emit(6, "ArduCopter V4.5.1 (Mock)")

            generator = MockTelemetryGenerator()
            tick = 0
            while self._running:
                tick += 1
                telemetry = generator.generate_packet(tick)

                # Autonomous mission navigation in mock mode
                self._mutex.lock()
                mode = self._mock_telemetry_state.get("mode", "")
                if mode == "AUTO" and self._mock_mission_waypoints:
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
                                self._mock_telemetry_state["mode"] = "LOITER"
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

                telemetry.update(self._mock_telemetry_state)
                self._mutex.unlock()
                self.telemetry_updated.emit(telemetry)
                self.msleep(100)

            self.disconnected_signal.emit("User disconnected mock stream")
            return

        # Real MAVLink connection
        try:
            self._mav = mavutil.mavlink_connection(
                self.connection_str,
                baud=self.baud,
                autoreconnect=True
            )
        except Exception as e:
            self.connection_error_signal.emit(f"Connection failed: {str(e)}")
            self._running = False
            return

        telemetry_cache = {
            "lat": None, "lon": None, "alt_rel": 0.0, "alt_abs": 0.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0, "groundspeed": 0.0,
            "heading": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "battery_pct": 0, "battery_v": 0.0, "gps_fix": "No Fix",
            "satellites": 0, "hdop": 99.0, "armed": False, "mode": "UNKNOWN",
            "system_id": 1, "component_id": 1, "autopilot": "ArduPilot",
            "connection_str": self.connection_str, "timestamp": time.time(),
        }

        last_gcs_heartbeat_send = 0.0

        while self._running:
            try:
                now = time.time()
                # Emit GCS heartbeat every 1.0s to satisfy PX4 / ArduPilot GCS connection preflight check
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

                msg = self._mav.recv_match(blocking=True, timeout=0.2)

                now = time.time()

                if msg is not None:
                    msg_type = msg.get_type()

                    if msg_type == "HEARTBEAT":
                        self._last_heartbeat_time = now
                        self._sysid = msg.get_srcSystem()
                        self._compid = msg.get_srcComponent()
                        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        mode_str = mavutil.mode_string_v10(msg)
                        vehicle_type = (
                            mavutil.mavlink.enums['MAV_TYPE'][msg.type].description
                            if msg.type in mavutil.mavlink.enums['MAV_TYPE']
                            else f"Type {msg.type}"
                        )
                        telemetry_cache.update({
                            "armed": armed, "mode": mode_str,
                            "system_id": self._sysid, "component_id": self._compid,
                            "autopilot": vehicle_type
                        })
                        if not self._connected:
                            self._connected = True
                            self.connected_signal.emit(self._sysid, self._compid, vehicle_type)

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
                        telemetry_cache["groundspeed"] = msg.groundspeed
                        telemetry_cache["heading"] = float(msg.heading)
                    elif msg_type == "SYS_STATUS":
                        telemetry_cache["battery_v"] = msg.voltage_battery / 1000.0
                        telemetry_cache["battery_pct"] = msg.battery_remaining if msg.battery_remaining >= 0 else 0
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
                        self.command_ack_signal.emit(f"CMD ACK: cmd={msg.command} result={msg.result}")
                    elif msg_type == "MISSION_CURRENT":
                        app_state.set_active_waypoint(msg.seq)
                    elif msg_type == "MISSION_ITEM_REACHED":
                        self.command_ack_signal.emit(f"WAYPOINT #{msg.seq} REACHED")

                    telemetry_cache["timestamp"] = now
                    if self._connected:
                        self.telemetry_updated.emit(dict(telemetry_cache))

                if self._connected and (now - self._last_heartbeat_time > 3.5):
                    self._connected = False
                    self.disconnected_signal.emit("MAVLink Heartbeat timeout (>3.5s)")

            except Exception:
                pass

        try:
            self._mav.close()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 3 & 4: Outbound Command & Mission Protocol Dispatch
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
        """Execute a real MAVLink command function on the active connection."""
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

    def upload_mission(self, waypoints: list):
        """Upload waypoints via MAVLink mission protocol."""
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
            app_state.log("INFO", "MAVLINK", msg)
            return

        if self._mav is None:
            self.command_ack_signal.emit("UPLOAD FAILED: NO CONNECTION")
            return

        def _do_upload():
            try:
                self._mutex.lock()
                self._mav.mav.mission_clear_all_send(self._mav.target_system, self._mav.target_component)
                time.sleep(0.1)

                count = len(waypoints)
                self._mav.mav.mission_count_send(self._mav.target_system, self._mav.target_component, count)

                for _ in range(count):
                    req = self._mav.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=3.0)
                    if req is None:
                        raise TimeoutError("Timeout waiting for MISSION_REQUEST")
                    seq = req.seq
                    wp = waypoints[seq]
                    cmd = wp.command if hasattr(wp, "command") else wp.get("command", 16)
                    frame = wp.frame if hasattr(wp, "frame") else wp.get("frame", 3)
                    p1 = wp.param1 if hasattr(wp, "param1") else wp.get("param1", 0.0)
                    p2 = wp.param2 if hasattr(wp, "param2") else wp.get("param2", 2.0)
                    p3 = wp.param3 if hasattr(wp, "param3") else wp.get("param3", 0.0)
                    p4 = wp.param4 if hasattr(wp, "param4") else wp.get("param4", 0.0)
                    lat = wp.lat if hasattr(wp, "lat") else wp.get("lat", 0.0)
                    lon = wp.lon if hasattr(wp, "lon") else wp.get("lon", 0.0)
                    alt = wp.alt if hasattr(wp, "alt") else wp.get("alt", 25.0)

                    if req.get_type() == 'MISSION_REQUEST_INT':
                        self._mav.mav.mission_item_int_send(
                            self._mav.target_system, self._mav.target_component,
                            seq, frame, cmd, 0, 1, p1, p2, p3, p4,
                            int(lat * 1e7), int(lon * 1e7), float(alt)
                        )
                    else:
                        self._mav.mav.mission_item_send(
                            self._mav.target_system, self._mav.target_component,
                            seq, frame, cmd, 0, 1, p1, p2, p3, p4,
                            float(lat), float(lon), float(alt)
                        )

                ack = self._mav.recv_match(type='MISSION_ACK', blocking=True, timeout=3.0)
                self._mutex.unlock()
                if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    success_msg = f"MISSION UPLOAD: SUCCESS ({count} WPs)"
                    self.mission_ack_signal.emit(success_msg)
                    self.command_ack_signal.emit(success_msg)
                    app_state.set_mission_status("UPLOADED")
                    app_state.set_command_feedback(success_msg)
                else:
                    err_msg = f"MISSION UPLOAD REJECTED (type={getattr(ack, 'type', 'timeout')})"
                    self.command_ack_signal.emit(err_msg)
            except Exception as e:
                self._mutex.unlock()
                self.command_ack_signal.emit(f"MISSION UPLOAD ERROR: {str(e)}")

        import threading
        threading.Thread(target=_do_upload, daemon=True).start()

    def download_mission(self):
        """Download waypoints via MAVLink mission protocol."""
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
            app_state.log("INFO", "MAVLINK", msg)
            return

        if self._mav is None:
            self.command_ack_signal.emit("DOWNLOAD FAILED: NO CONNECTION")
            return

        def _do_download():
            try:
                self._mutex.lock()
                self._mav.mav.mission_request_list_send(self._mav.target_system, self._mav.target_component)
                msg_count = self._mav.recv_match(type=['MISSION_COUNT'], blocking=True, timeout=3.0)
                if msg_count is None:
                    raise TimeoutError("Timeout waiting for MISSION_COUNT")

                count = msg_count.count
                downloaded_wps = []
                for seq in range(count):
                    self._mav.mav.mission_request_int_send(self._mav.target_system, self._mav.target_component, seq)
                    item = self._mav.recv_match(type=['MISSION_ITEM_INT', 'MISSION_ITEM'], blocking=True, timeout=3.0)
                    if item is None:
                        raise TimeoutError(f"Timeout waiting for WP #{seq}")
                    if item.get_type() == 'MISSION_ITEM_INT':
                        lat = item.x / 1e7
                        lon = item.y / 1e7
                    else:
                        lat = item.x
                        lon = item.y
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

                self._mav.mav.mission_ack_send(self._mav.target_system, self._mav.target_component, mavutil.mavlink.MAV_MISSION_ACCEPTED)
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

    def release_payload(self, servo_channel: int = 9, pwm: int = 1900):
        """Trigger emergency payload release via MAV_CMD_DO_SET_SERVO."""
        from gcs.mavlink import commands
        if self._mock_mode:
            result = commands.mock_payload_release(servo_channel, pwm)
            self.dispatch_mock(result)
        else:
            self.dispatch_real(commands.send_payload_release, servo_channel, pwm)

    def stop(self):
        self._running = False
        self.quit()
        self.wait(1000)

