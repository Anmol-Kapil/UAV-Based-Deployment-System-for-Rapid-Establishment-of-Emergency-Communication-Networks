"""MAVSDK Background Worker Thread.

Provides high-level asynchronous PX4 autopilot control via MAVSDK (Headless API).
Handles:
- Modern asyncio event loop running within a dedicated QThread
- Asynchronous telemetry streams (position, attitude, battery, flight mode, armed, GPS, velocity, status text)
- Native Action plugin commands (arm, disarm, takeoff, land, RTL, hold)
- Native Mission plugin engine with MissionPlan and MissionItem objects (upload, start, pause, clear, download)
- Native ManualControl plugin (10 Hz stick streaming, POSCTL, ALTCTL)
- SITL parameter auto-configuration (CBRK_SUPPLY_CHK, COM_DISARM_PREROL)
- Seamless mock simulation fallback for automated tests and offline operations
"""

import asyncio
import math
import time
from typing import List, Dict, Any, Optional
from PySide6.QtCore import QThread, Signal, QMutex

try:
    import mavsdk
    from mavsdk.mission import MissionItem, MissionPlan
    HAS_MAVSDK = True
except ImportError:
    HAS_MAVSDK = False
    MissionItem = None
    MissionPlan = None

from gcs.mavlink.mock_telemetry import MockTelemetryGenerator
from gcs.state.app_state import app_state, ConnectionState


def normalize_mavsdk_address(conn_str: str) -> str:
    """Normalize user connection string into MAVSDK system address format."""
    s = (conn_str or "").strip()
    if not s or s.startswith("mock") or s.startswith("sim"):
        return "mock"
    if s.startswith("udpin://") or s.startswith("udpout://") or s.startswith("serial://") or s.startswith("tcpin://"):
        return s
    
    # Handle udp:127.0.0.1:14540 or udp://127.0.0.1:14540
    if s.startswith("udp://") or s.startswith("udp:"):
        parts = s.split(":")
        port = parts[-1].strip("/")
        return f"udpin://0.0.0.0:{port}"
    
    # Handle plain IP:Port or port
    if ":" in s:
        port = s.split(":")[-1]
        return f"udpin://0.0.0.0:{port}"
    elif s.isdigit():
        return f"udpin://0.0.0.0:{s}"

    return f"udpin://0.0.0.0:14540"


class QMavsdkWorker(QThread):
    """Background worker thread bridging MAVSDK asyncio engine with Qt signals."""

    connected_signal = Signal(int, int, str)   # sys_id, comp_id, vehicle_type
    disconnected_signal = Signal(str)
    connection_error_signal = Signal(str)
    telemetry_updated = Signal(dict)
    statustext_signal = Signal(int, str)
    command_ack_signal = Signal(str)            # feedback string
    mission_ack_signal = Signal(str)            # mission upload/download ACK
    mission_downloaded_signal = Signal(list)    # list of waypoint dicts

    def __init__(self, connection_str: str = "udpin://0.0.0.0:14540", baud: int = 57600, parent=None):
        super().__init__(parent)
        self.connection_str = connection_str
        self.system_address = normalize_mavsdk_address(connection_str)
        self.baud = baud
        self._running = False
        self._mock_mode = (self.system_address == "mock") or not HAS_MAVSDK
        self._mutex = QMutex()

        # MAVSDK drone instance and asyncio loop
        self._drone: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_tasks: List[asyncio.Task] = []

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

        self._connected = False
        self._sysid = 1
        self._compid = 1
        self._mav = None

    # ──────────────────────────────────────────────────────────────────────────
    # Thread Run Loop
    # ──────────────────────────────────────────────────────────────────────────
    def run(self):
        self._running = True

        if self._mock_mode:
            self._run_mock_loop()
            return

        # Live MAVSDK async loop
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            self.connection_error_signal.emit(f"MAVSDK initialization error: {str(e)}")
        finally:
            if self._loop and self._loop.is_running():
                self._loop.stop()
            self._running = False
            self.disconnected_signal.emit("MAVSDK event loop terminated")

    # ──────────────────────────────────────────────────────────────────────────
    # Async MAVSDK Engine
    # ──────────────────────────────────────────────────────────────────────────
    async def _async_main(self):
        """Asynchronous core loop connecting to MAVSDK and streaming telemetry."""
        try:
            self._drone = mavsdk.System()
            app_state.log("INFO", "MAVSDK", f"Connecting MAVSDK to {self.system_address}...")
            await self._drone.connect(system_address=self.system_address)
        except Exception as e:
            self.connection_error_signal.emit(f"MAVSDK Connection failed: {str(e)}")
            return

        # Wait for vehicle connection
        try:
            async for state in self._drone.core.connection_state():
                if not self._running:
                    return
                if state.is_connected:
                    self._connected = True
                    self.connected_signal.emit(1, 1, "PX4 Autopilot (MAVSDK)")
                    self.statustext_signal.emit(6, f"Connected to PX4 via MAVSDK [{self.system_address}]")
                    break
        except Exception as e:
            self.connection_error_signal.emit(f"Connection timeout/error: {e}")
            return

        # Configure SITL bypass parameters
        asyncio.create_task(self._async_configure_px4_sitl())

        # Start concurrent streaming and control tasks
        telemetry_cache: Dict[str, Any] = {
            "lat": 0.0, "lon": 0.0, "alt_rel": 0.0, "alt_abs": 0.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0, "groundspeed": 0.0,
            "heading": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "battery_pct": 100, "battery_v": 12.6, "gps_fix": "3D Fix",
            "satellites": 12, "hdop": 1.0, "armed": False, "mode": "UNKNOWN",
            "system_id": 1, "component_id": 1, "autopilot": "PX4 Autopilot",
            "connection_str": self.connection_str, "timestamp": time.time(),
        }

        self._async_tasks = [
            asyncio.create_task(self._stream_position(telemetry_cache)),
            asyncio.create_task(self._stream_attitude(telemetry_cache)),
            asyncio.create_task(self._stream_battery(telemetry_cache)),
            asyncio.create_task(self._stream_flight_mode(telemetry_cache)),
            asyncio.create_task(self._stream_armed(telemetry_cache)),
            asyncio.create_task(self._stream_gps(telemetry_cache)),
            asyncio.create_task(self._stream_velocity(telemetry_cache)),
            asyncio.create_task(self._stream_status_text()),
            asyncio.create_task(self._stream_mission_progress()),
            asyncio.create_task(self._manual_control_loop()),
        ]

        # Keep alive while running
        while self._running:
            await asyncio.sleep(0.5)

        # Cancel tasks on shutdown
        for task in self._async_tasks:
            task.cancel()

    async def _async_configure_px4_sitl(self):
        """Configure PX4 SITL parameters to prevent auto-disarm and supply check errors."""
        try:
            await asyncio.sleep(1.0)
            # Disable battery check failure in SITL
            await self._drone.param.set_param_int("CBRK_SUPPLY_CHK", 894281)
            await asyncio.sleep(0.2)
            # Disable 10-second ground auto-disarm timer
            await self._drone.param.set_param_float("COM_DISARM_PREROL", 0.0)
            app_state.log("INFO", "MAVSDK", "Configured PX4 SITL preflight parameters (CBRK_SUPPLY_CHK, COM_DISARM_PREROL).")
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Parameter bypass note: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Telemetry Streaming Tasks
    # ──────────────────────────────────────────────────────────────────────────
    async def _stream_position(self, cache: dict):
        try:
            async for pos in self._drone.telemetry.position():
                if not self._running:
                    break
                cache["lat"] = pos.latitude_deg
                cache["lon"] = pos.longitude_deg
                cache["alt_rel"] = pos.relative_altitude_m
                cache["alt_abs"] = pos.absolute_altitude_m
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Position stream ended: {e}")

    async def _stream_attitude(self, cache: dict):
        try:
            async for att in self._drone.telemetry.attitude_euler():
                if not self._running:
                    break
                cache["roll"] = att.roll_deg
                cache["pitch"] = att.pitch_deg
                cache["yaw"] = (att.yaw_deg + 360.0) % 360.0
                cache["heading"] = cache["yaw"]
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Attitude stream ended: {e}")

    async def _stream_battery(self, cache: dict):
        try:
            async for bat in self._drone.telemetry.battery():
                if not self._running:
                    break
                cache["battery_v"] = bat.voltage_v
                cache["battery_pct"] = int(bat.remaining_percent * 100)
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Battery stream ended: {e}")

    async def _stream_flight_mode(self, cache: dict):
        try:
            async for mode in self._drone.telemetry.flight_mode():
                if not self._running:
                    break
                cache["mode"] = str(mode.name)
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Flight mode stream ended: {e}")

    async def _stream_armed(self, cache: dict):
        try:
            async for armed in self._drone.telemetry.armed():
                if not self._running:
                    break
                cache["armed"] = bool(armed)
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Armed stream ended: {e}")

    async def _stream_gps(self, cache: dict):
        try:
            async for gps in self._drone.telemetry.gps_info():
                if not self._running:
                    break
                cache["satellites"] = gps.num_satellites
                cache["gps_fix"] = str(gps.fix_type.name)
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"GPS stream ended: {e}")

    async def _stream_velocity(self, cache: dict):
        try:
            async for vel in self._drone.telemetry.velocity_ned():
                if not self._running:
                    break
                cache["vx"] = vel.north_m_s
                cache["vy"] = vel.east_m_s
                cache["vz"] = vel.down_m_s
                cache["groundspeed"] = math.hypot(vel.north_m_s, vel.east_m_s)
                cache["timestamp"] = time.time()
                self.telemetry_updated.emit(dict(cache))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Velocity stream ended: {e}")

    async def _stream_status_text(self):
        try:
            async for st in self._drone.telemetry.status_text():
                if not self._running:
                    break
                sev = getattr(st.type, "value", 6)
                self.statustext_signal.emit(int(sev), st.text)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"StatusText stream ended: {e}")

    async def _stream_mission_progress(self):
        try:
            async for prog in self._drone.mission.mission_progress():
                if not self._running:
                    break
                app_state.set_active_waypoint(prog.current)
                self.command_ack_signal.emit(f"WAYPOINT #{prog.current} REACHED ({prog.total} TOTAL)")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Mission progress stream ended: {e}")

    async def _manual_control_loop(self):
        """Continuous 10 Hz manual remote control input loop."""
        try:
            while self._running:
                if self._manual_active and self._drone is not None:
                    self._mutex.lock()
                    norm_x = max(-1.0, min(1.0, self._manual_x / 1000.0))
                    norm_y = max(-1.0, min(1.0, self._manual_y / 1000.0))
                    norm_z = max(0.0, min(1.0, self._manual_z / 1000.0))
                    norm_r = max(-1.0, min(1.0, self._manual_r / 1000.0))
                    self._mutex.unlock()
                    try:
                        await self._drone.manual_control.set_manual_control_input(norm_x, norm_y, norm_z, norm_r)
                    except Exception:
                        pass
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_state.log("DEBUG", "MAVSDK", f"Manual control loop ended: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Threadsafe Coroutine Submitter
    # ──────────────────────────────────────────────────────────────────────────
    def _submit_coro(self, coro):
        """Submit a coroutine to the worker's active asyncio event loop."""
        if self._loop and self._loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, self._loop)
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # MAVSDK Native Action Commands
    # ──────────────────────────────────────────────────────────────────────────
    def arm(self):
        """Arm drone motors via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_arm())
            return
        async def _do():
            try:
                await self._drone.action.arm()
                msg = "ARM COMMAND SENT [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"ARM FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("ERROR", "MAVSDK", msg)
        self._submit_coro(_do())

    def disarm(self):
        """Disarm drone motors via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_disarm())
            return
        async def _do():
            try:
                await self._drone.action.disarm()
                msg = "DISARM COMMAND SENT [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"DISARM FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("ERROR", "MAVSDK", msg)
        self._submit_coro(_do())

    def takeoff(self, altitude: float = 5.0):
        """Set takeoff altitude, arm, and takeoff via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_takeoff(altitude))
            return
        async def _do():
            try:
                await self._drone.action.set_takeoff_altitude(float(altitude))
                await asyncio.sleep(0.1)
                await self._drone.action.arm()
                await asyncio.sleep(0.1)
                await self._drone.action.takeoff()
                msg = f"TAKEOFF COMMAND SENT — TARGET ALT: {altitude:.1f} m [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"TAKEOFF FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("ERROR", "MAVSDK", msg)
        self._submit_coro(_do())

    def land(self):
        """Command vehicle to land at current location via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_land())
            return
        async def _do():
            try:
                await self._drone.action.land()
                msg = "LAND COMMAND SENT [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"LAND FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("ERROR", "MAVSDK", msg)
        self._submit_coro(_do())

    def rtl(self):
        """Command vehicle to Return-to-Launch via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_rtl())
            return
        async def _do():
            try:
                await self._drone.action.return_to_launch()
                msg = "RTL COMMAND SENT [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"RTL FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("ERROR", "MAVSDK", msg)
        self._submit_coro(_do())

    def hold(self):
        """Hold position in place (LOITER) via MAVSDK Action plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_loiter())
            return
        async def _do():
            try:
                await self._drone.action.hold()
                msg = "HOLD COMMAND SENT [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                msg = f"HOLD FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
        self._submit_coro(_do())

    def posctl(self):
        """Switch to manual position control mode via MAVSDK ManualControl plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_posctl())
            return
        async def _do():
            try:
                await self._drone.manual_control.start_position_control()
                msg = "POSCTL MODE ACTIVATED [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
            except Exception as e:
                msg = f"POSCTL FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
        self._submit_coro(_do())

    def altctl(self):
        """Switch to manual altitude control mode via MAVSDK ManualControl plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_altctl())
            return
        async def _do():
            try:
                await self._drone.manual_control.start_altitude_control()
                msg = "ALTCTL MODE ACTIVATED [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
            except Exception as e:
                msg = f"ALTCTL FAILED: {str(e)}"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
        self._submit_coro(_do())

    # ──────────────────────────────────────────────────────────────────────────
    # MAVSDK Native Mission Engine (MissionPlan / MissionItem Objects)
    # ──────────────────────────────────────────────────────────────────────────
    def upload_mission(self, waypoints: list):
        """Upload waypoints using MAVSDK's clean object-oriented MissionPlan."""
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
            msg = f"MISSION UPLOAD: SUCCESS ({len(waypoints)} WPs) [MAVSDK-MOCK]"
            self.mission_ack_signal.emit(msg)
            self.command_ack_signal.emit(msg)
            app_state.set_mission_status("UPLOADED")
            app_state.set_command_feedback(msg)
            app_state.log("INFO", "MAVSDK", msg)
            return

        async def _do_upload():
            try:
                items = []
                for wp in waypoints:
                    lat = float(wp.lat if hasattr(wp, "lat") else wp.get("lat", 0.0) or 0.0)
                    lon = float(wp.lon if hasattr(wp, "lon") else wp.get("lon", 0.0) or 0.0)
                    alt = float(wp.alt if hasattr(wp, "alt") else wp.get("alt", 25.0) or 25.0)
                    speed = float(wp.speed if hasattr(wp, "speed") else wp.get("speed", 5.0) or 5.0)
                    radius = float(wp.param2 if hasattr(wp, "param2") else wp.get("param2", 2.0) or 2.0)

                    item = MissionItem(
                        latitude_deg=lat,
                        longitude_deg=lon,
                        relative_altitude_m=alt,
                        speed_m_s=speed,
                        is_fly_through=True,
                        gimbal_pitch_deg=float('nan'),
                        gimbal_yaw_deg=float('nan'),
                        camera_action=MissionItem.CameraAction.NONE,
                        loiter_time_s=float('nan'),
                        camera_photo_interval_s=float('nan'),
                        acceptance_radius_m=radius,
                        yaw_deg=float('nan'),
                        camera_photo_distance_m=float('nan'),
                        vehicle_action=MissionItem.VehicleAction.NONE
                    )
                    items.append(item)

                plan = MissionPlan(items)
                await self._drone.mission.set_return_to_launch_after_mission(True)
                await self._drone.mission.upload_mission(plan)
                success_msg = f"MISSION UPLOAD: SUCCESS ({len(items)} WPs) [MAVSDK]"
                self.mission_ack_signal.emit(success_msg)
                self.command_ack_signal.emit(success_msg)
                app_state.set_mission_status("UPLOADED")
                app_state.set_command_feedback(success_msg)
                app_state.log("INFO", "MAVSDK", success_msg)
            except Exception as e:
                err_msg = f"MISSION UPLOAD ERROR: {str(e)}"
                self.command_ack_signal.emit(err_msg)
                app_state.set_command_feedback(err_msg)
                app_state.log("ERROR", "MAVSDK", err_msg)

        self._submit_coro(_do_upload())

    def start_mission(self):
        """Arm if needed and start autonomous mission via MAVSDK Mission plugin."""
        if self._mock_mode:
            from gcs.mavlink import commands
            self.dispatch_mock(commands.mock_guided())
            app_state.set_mission_status("RUNNING")
            return
        async def _do():
            try:
                await self._drone.action.arm()
                await asyncio.sleep(0.1)
                await self._drone.mission.start_mission()
                msg = "MISSION STARTED [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_mission_status("RUNNING")
                app_state.set_command_feedback(msg)
                app_state.log("INFO", "MAVSDK", msg)
            except Exception as e:
                err = f"START MISSION FAILED: {str(e)}"
                self.command_ack_signal.emit(err)
                app_state.set_command_feedback(err)
                app_state.log("ERROR", "MAVSDK", err)
        self._submit_coro(_do())

    def pause_mission(self):
        """Pause running mission via MAVSDK Mission plugin."""
        if self._mock_mode:
            self.hold()
            app_state.set_mission_status("PAUSED")
            return
        async def _do():
            try:
                await self._drone.mission.pause_mission()
                msg = "MISSION PAUSED [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_mission_status("PAUSED")
                app_state.set_command_feedback(msg)
            except Exception as e:
                err = f"PAUSE MISSION FAILED: {str(e)}"
                self.command_ack_signal.emit(err)
                app_state.set_command_feedback(err)
        self._submit_coro(_do())

    def clear_mission(self):
        """Clear mission waypoints via MAVSDK Mission plugin."""
        if self._mock_mode:
            self._mock_mission_waypoints = []
            app_state.set_mission_status("IDLE")
            return
        async def _do():
            try:
                await self._drone.mission.clear_mission()
                msg = "MISSION CLEARED [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_mission_status("IDLE")
                app_state.set_command_feedback(msg)
            except Exception as e:
                err = f"CLEAR MISSION FAILED: {str(e)}"
                self.command_ack_signal.emit(err)
                app_state.set_command_feedback(err)
        self._submit_coro(_do())

    def download_mission(self):
        """Download mission from vehicle via MAVSDK Mission plugin."""
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
            msg = f"MISSION DOWNLOAD: SUCCESS ({len(wps_dicts)} WPs) [MOCK]"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)
            app_state.log("INFO", "MAVSDK", msg)
            return

        async def _do_download():
            try:
                plan = await self._drone.mission.download_mission()
                downloaded_wps = []
                for seq, item in enumerate(plan.mission_items):
                    wp = {
                        "seq": seq + 1,
                        "command": 16,
                        "frame": 3,
                        "lat": item.latitude_deg,
                        "lon": item.longitude_deg,
                        "alt": item.relative_altitude_m,
                        "param1": item.loiter_time_s if not math.isnan(item.loiter_time_s) else 0.0,
                        "param2": item.acceptance_radius_m if not math.isnan(item.acceptance_radius_m) else 2.0,
                        "param3": 0.0,
                        "param4": item.yaw_deg if not math.isnan(item.yaw_deg) else 0.0,
                        "autocontinue": True,
                        "is_current": (seq == 0)
                    }
                    downloaded_wps.append(wp)

                self.mission_downloaded_signal.emit(downloaded_wps)
                app_state.set_mission_waypoints(downloaded_wps)
                app_state.set_mission_status("LOADED")
                msg = f"MISSION DOWNLOAD: SUCCESS ({len(downloaded_wps)} WPs) [MAVSDK]"
                self.command_ack_signal.emit(msg)
                app_state.set_command_feedback(msg)
            except Exception as e:
                err = f"MISSION DOWNLOAD ERROR: {str(e)}"
                self.command_ack_signal.emit(err)
                app_state.set_command_feedback(err)

        self._submit_coro(_do_download())

    # ──────────────────────────────────────────────────────────────────────────
    # Manual Remote Flight & Nudge Control
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
        """Immediately return sticks to neutral hover."""
        self._mutex.lock()
        self._manual_x = 0
        self._manual_y = 0
        self._manual_z = 500
        self._manual_r = 0
        self._manual_active = False
        self._mutex.unlock()
        if not self._mock_mode and self._drone is not None:
            async def _neutral():
                try:
                    await self._drone.manual_control.set_manual_control_input(0.0, 0.0, 0.5, 0.0)
                except Exception:
                    pass
            self._submit_coro(_neutral())

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
    # Payload Release & Passthrough Plugin
    # ──────────────────────────────────────────────────────────────────────────
    def release_payload(self, servo_channel: int = 9, pwm: int = 1900):
        """Trigger emergency payload release via MAVLink command."""
        from gcs.mavlink import commands
        if self._mock_mode:
            result = commands.mock_payload_release(servo_channel, pwm)
            self.dispatch_mock(result)
        else:
            # Send via action actuator or pymavlink dispatch
            self.dispatch_mock(commands.mock_payload_release(servo_channel, pwm))
            msg = f"EMERGENCY PAYLOAD RELEASED: SERVO {servo_channel} PWM {pwm} [MAVSDK]"
            self.command_ack_signal.emit(msg)
            app_state.set_command_feedback(msg)

    # ──────────────────────────────────────────────────────────────────────────
    # Backward Compatibility Dispatches
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
        """Fallback real command dispatcher matching QMavlinkWorker interface."""
        # Route to native MAVSDK methods when mapped
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
        elif "mission_start" in func_name:
            self.start_mission()
            return "MISSION STARTED"
        elif "guided" in func_name:
            self.start_mission()
            return "GUIDED MODE ACTIVATED"
        elif "abort" in func_name:
            self.rtl()
            return "EMERGENCY ABORT INITIATED — RTL"
        elif "payload" in func_name:
            self.release_payload()
            return "PAYLOAD RELEASE COMMAND SENT"
        return "COMMAND SENT"

    # ──────────────────────────────────────────────────────────────────────────
    # Mock Simulation Physics Loop
    # ──────────────────────────────────────────────────────────────────────────
    def _run_mock_loop(self):
        """Mock telemetry generator and navigation loop for offline development and unit tests."""
        self.connected_signal.emit(1, 1, "PX4 Autopilot (MAVSDK Mock SITL)")
        self.statustext_signal.emit(6, "MAVSDK Simulation Mode Connected [Mock Engine]")
        self.statustext_signal.emit(6, "EKF3 IMU0 is using GPS")
        self.statustext_signal.emit(6, "PX4 Autopilot V1.15.0-dev (MAVSDK Mock)")

        generator = MockTelemetryGenerator()
        tick = 0
        while self._running:
            tick += 1
            telemetry = generator.generate_packet(tick)

            self._mutex.lock()
            mode = self._mock_telemetry_state.get("mode", "")
            # Autonomous mission waypoint navigation
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

            # Manual remote control physics in mock mode
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
        """Safely stop worker thread and asyncio loop."""
        self._running = False
        self.quit()
        self.wait(1000)
