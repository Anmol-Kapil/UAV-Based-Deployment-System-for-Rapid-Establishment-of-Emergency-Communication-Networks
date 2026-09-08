"""GPS Deployment Mission Controller for Autonomous Multi-Node Communication Payload Drop.

Manages autonomous multi-target mission execution:
- Coordinates waypoint sequencing with drop target locations
- Geofenced proximity detection (acceptance radius & drop altitude)
- Physical & simulated payload release via MAVLink servo command (MAV_CMD_DO_SET_SERVO)
- Step-by-step node state progression (IDLE -> ARMING -> TAKEOFF -> TRANSIT -> ON_STATION -> RELEASING -> DEPLOYED -> NEXT_TARGET -> RTL -> COMPLETED)
- Supports Autonomous Auto-Release and Supervised Operator Confirmation modes
- Auto-registers deployed nodes into AppState and updates Tactical Map in real time
"""

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Callable
from PySide6.QtCore import QObject, Signal

from gcs.state.app_state import app_state, ConnectionState, FlightState
from gcs.deployment.deployment_manager import (
    DeploymentNode,
    calculate_bearing,
    calculate_ground_distance,
)
from gcs.mavlink.mission_manager import Waypoint, MissionPlan, MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_TAKEOFF, MAV_CMD_NAV_RETURN_TO_LAUNCH, MAV_CMD_NAV_LOITER_TIME


class GpsMissionState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    ARMING = "ARMING"
    TAKEOFF = "TAKEOFF"
    TRANSITING = "TRANSITING"
    ON_STATION = "ON_STATION"
    RELEASING = "RELEASING"
    NODE_DEPLOYED = "NODE_DEPLOYED"
    PAUSED = "PAUSED"
    RETURNING = "RETURNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


@dataclass
class GpsMissionConfig:
    acceptance_radius_m: float = 15.0
    drop_altitude_m: float = 20.0
    auto_release: bool = True  # True: auto release on arrival; False: wait for operator confirm
    settle_delay_sec: float = 2.0  # Time to hold over target before release
    servo_channel: int = 9
    servo_pwm_release: int = 1900
    servo_pwm_neutral: int = 1100
    rf_coverage_radius_m: float = 250.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acceptance_radius_m": self.acceptance_radius_m,
            "drop_altitude_m": self.drop_altitude_m,
            "auto_release": self.auto_release,
            "settle_delay_sec": self.settle_delay_sec,
            "servo_channel": self.servo_channel,
            "servo_pwm_release": self.servo_pwm_release,
            "servo_pwm_neutral": self.servo_pwm_neutral,
            "rf_coverage_radius_m": self.rf_coverage_radius_m,
        }


@dataclass
class GpsDropTarget:
    target_id: str
    lat: float
    lon: float
    alt: float = 20.0
    wp_seq: int = 0
    candidate_id: str = ""
    deployed: bool = False
    deploy_time: Optional[str] = None
    node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "candidate_id": self.candidate_id,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "alt": round(self.alt, 1),
            "wp_seq": self.wp_seq,
            "deployed": self.deployed,
            "deploy_time": self.deploy_time,
            "node_id": self.node_id,
        }


class GpsMissionController(QObject):
    """Orchestrates autonomous GPS multi-target deployment missions."""

    mission_state_changed = Signal(str)
    progress_updated = Signal(dict)
    node_deployed = Signal(object)
    awaiting_confirmation = Signal(str)  # Target ID waiting for manual drop confirmation
    mission_completed = Signal(str)

    def __init__(self, config: Optional[GpsMissionConfig] = None, parent=None):
        super().__init__(parent)
        self.config = config or GpsMissionConfig()
        self.state: GpsMissionState = GpsMissionState.IDLE
        self.targets: List[GpsDropTarget] = []
        self.active_target_index: int = 0
        self._worker = None
        self._settle_timer_start: Optional[float] = None
        self._is_releasing: bool = False

    def set_worker(self, worker):
        """Set MAVLink worker to dispatch commands."""
        self._worker = worker

    def load_from_candidates(self, candidates: List[Any], drop_alt_m: float = 20.0):
        """Build target list from selected candidate sites."""
        self.reset()
        self.targets = []
        for i, c in enumerate(candidates):
            cid = c.candidate_id if hasattr(c, "candidate_id") else c.get("candidate_id", f"C-{i+1}")
            lat = c.lat if hasattr(c, "lat") else c.get("lat", 0.0)
            lon = c.lon if hasattr(c, "lon") else c.get("lon", 0.0)
            target = GpsDropTarget(
                target_id=f"DROP-{i+1:02d}",
                candidate_id=cid,
                lat=lat,
                lon=lon,
                alt=drop_alt_m,
                wp_seq=i + 2  # Assuming WP 1 is takeoff
            )
            self.targets.append(target)

        self.active_target_index = 0
        self._set_state(GpsMissionState.READY if self.targets else GpsMissionState.IDLE)
        self._emit_progress()

    def load_from_waypoints(self, waypoints: List[Any], drop_alt_m: float = 20.0):
        """Build target list by extracting drop stations (e.g. LOITER_TIME or intermediate waypoints)."""
        self.reset()
        self.targets = []
        drop_idx = 0
        for wp in waypoints:
            cmd = wp.command if hasattr(wp, "command") else wp.get("command", MAV_CMD_NAV_WAYPOINT)
            seq = wp.seq if hasattr(wp, "seq") else wp.get("seq", 0)
            # Takeoff, land, rtl are excluded from drop targets
            if cmd in (MAV_CMD_NAV_TAKEOFF, MAV_CMD_NAV_RETURN_TO_LAUNCH, 21):
                continue
            lat = wp.lat if hasattr(wp, "lat") else wp.get("lat", 0.0)
            lon = wp.lon if hasattr(wp, "lon") else wp.get("lon", 0.0)
            alt = wp.alt if hasattr(wp, "alt") else wp.get("alt", drop_alt_m)
            drop_idx += 1
            target = GpsDropTarget(
                target_id=f"DROP-{drop_idx:02d}",
                candidate_id=f"WP-{seq}",
                lat=lat,
                lon=lon,
                alt=alt,
                wp_seq=seq
            )
            self.targets.append(target)

        self.active_target_index = 0
        self._set_state(GpsMissionState.READY if self.targets else GpsMissionState.IDLE)
        self._emit_progress()

    def start_mission(self) -> bool:
        """Start or initiate the autonomous GPS deployment flight."""
        if not self.targets:
            app_state.set_command_feedback("GPS MISSION ERROR: NO TARGETS LOADED")
            return False

        self._set_state(GpsMissionState.TRANSITING)
        app_state.set_command_feedback(f"GPS DEPLOYMENT MISSION STARTED: {len(self.targets)} NODES EN ROUTE")
        app_state.log("INFO", "GPS_MISSION", f"Started GPS Deployment Mission ({len(self.targets)} nodes to deploy)")

        # Dispatch vehicle to AUTO mode
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                self._worker._mock_telemetry_state["mode"] = "AUTO"
                self._worker._mock_telemetry_state["armed"] = True
            else:
                commands.send_mission_start(self._worker._mav)

        self._emit_progress()
        return True

    def pause_mission(self):
        """Pause mission by commanding station hold / LOITER."""
        if self.state in (GpsMissionState.TRANSITING, GpsMissionState.ON_STATION, GpsMissionState.RELEASING):
            self._set_state(GpsMissionState.PAUSED)
            app_state.set_command_feedback("GPS DEPLOYMENT MISSION PAUSED (LOITER)")
            app_state.log("WARN", "GPS_MISSION", "GPS Deployment Mission paused by operator")
            if self._worker:
                from gcs.mavlink import commands
                if self._worker._mock_mode:
                    self._worker._mock_telemetry_state["mode"] = "LOITER"
                else:
                    commands.send_loiter(self._worker._mav)
            self._emit_progress()

    def resume_mission(self):
        """Resume autonomous mission execution."""
        if self.state == GpsMissionState.PAUSED:
            self._set_state(GpsMissionState.TRANSITING)
            app_state.set_command_feedback("GPS DEPLOYMENT MISSION RESUMED (AUTO)")
            app_state.log("INFO", "GPS_MISSION", "GPS Deployment Mission resumed by operator")
            if self._worker:
                from gcs.mavlink import commands
                if self._worker._mock_mode:
                    self._worker._mock_telemetry_state["mode"] = "AUTO"
                else:
                    commands.send_mission_start(self._worker._mav)
            self._emit_progress()

    def abort_mission(self):
        """Emergency abort and return to launch."""
        self._set_state(GpsMissionState.ABORTED)
        app_state.set_command_feedback("GPS DEPLOYMENT MISSION ABORTED — COMMANDING RTL")
        app_state.log("ALERT", "GPS_MISSION", "GPS Deployment Mission ABORTED by operator. Vehicle returning to launch.")
        if self._worker:
            from gcs.mavlink import commands
            if self._worker._mock_mode:
                self._worker._mock_telemetry_state["mode"] = "RTL"
            else:
                commands.send_rtl(self._worker._mav)
        self._emit_progress()

    def process_telemetry(self, telemetry: Dict[str, Any]):
        """Evaluate vehicle GPS position relative to active drop target."""
        if self.state not in (GpsMissionState.TRANSITING, GpsMissionState.ON_STATION, GpsMissionState.RELEASING):
            return

        cur_target = self.get_active_target()
        if not cur_target:
            return

        uav_lat = telemetry.get("lat")
        uav_lon = telemetry.get("lon")
        uav_alt = telemetry.get("alt_rel", telemetry.get("alt", 0.0))

        if not isinstance(uav_lat, (int, float)) or not isinstance(uav_lon, (int, float)):
            return

        dist_m = calculate_ground_distance(uav_lat, uav_lon, cur_target.lat, cur_target.lon)
        bearing_deg = calculate_bearing(uav_lat, uav_lon, cur_target.lat, cur_target.lon)

        progress_data = {
            "state": self.state.value,
            "target_index": self.active_target_index,
            "total_targets": len(self.targets),
            "target_id": cur_target.target_id,
            "candidate_id": cur_target.candidate_id,
            "target_lat": cur_target.lat,
            "target_lon": cur_target.lon,
            "distance_m": round(dist_m, 1),
            "bearing_deg": round(bearing_deg, 1),
            "auto_release": self.config.auto_release,
        }
        self.progress_updated.emit(progress_data)
        app_state.set_gps_mission_progress(progress_data)

        # Arrival detection: within acceptance radius
        if dist_m <= self.config.acceptance_radius_m:
            if self.state == GpsMissionState.TRANSITING:
                self._set_state(GpsMissionState.ON_STATION)
                self._settle_timer_start = time.time()
                app_state.set_command_feedback(f"UAV ON STATION OVER {cur_target.target_id} (DIST: {dist_m:.1f}m)")
                app_state.log("INFO", "GPS_MISSION", f"UAV arrived on station over {cur_target.target_id} ({cur_target.candidate_id})")

            if self.state == GpsMissionState.ON_STATION:
                now = time.time()
                elapsed = now - (self._settle_timer_start or now)

                if self.config.auto_release:
                    # Auto release after settling delay
                    if elapsed >= self.config.settle_delay_sec and not self._is_releasing:
                        self.trigger_payload_release()
                else:
                    # Supervised mode: emit awaiting confirmation
                    self.awaiting_confirmation.emit(cur_target.target_id)
        else:
            if self.state == GpsMissionState.ON_STATION and not self._is_releasing:
                # Drifted outside acceptance radius
                self._set_state(GpsMissionState.TRANSITING)

    def trigger_payload_release(self):
        """Execute payload release for active target."""
        cur_target = self.get_active_target()
        if not cur_target or cur_target.deployed or self._is_releasing:
            return

        self._is_releasing = True
        self._set_state(GpsMissionState.RELEASING)
        app_state.set_command_feedback(f"RELEASING PAYLOAD AT {cur_target.target_id}...")
        app_state.log("INFO", "GPS_MISSION", f"Actuating payload release mechanism for target {cur_target.target_id}")

        # Send MAVLink servo command
        if self._worker:
            if hasattr(self._worker, "release_payload"):
                self._worker.release_payload(self.config.servo_channel, self.config.servo_pwm_release)
            else:
                from gcs.mavlink import commands
                if not self._worker._mock_mode:
                    commands.send_payload_release(self._worker._mav, self.config.servo_channel, self.config.servo_pwm_release)

        # Mark target deployed
        node_num = len(app_state.deployed_nodes) + 1
        node_id = f"NODE_{node_num:03d}"
        now_str = time.strftime("%H:%M:%S")

        cur_target.deployed = True
        cur_target.deploy_time = now_str
        cur_target.node_id = node_id

        # Register deployed virtual node (automatically syncs to app_state.deployed_nodes)
        from gcs.deployment.virtual_node_manager import virtual_node_manager
        node = virtual_node_manager.deploy_node(
            node_id=node_id,
            lat=cur_target.lat,
            lon=cur_target.lon,
            altitude_m=4.5,
            mission_id=f"MIS-{cur_target.target_id}",
            coverage_radius_m=self.config.rf_coverage_radius_m
        )
        self.node_deployed.emit(node)


        self._set_state(GpsMissionState.NODE_DEPLOYED)
        success_msg = f"NODE {node.node_id} DEPLOYED AT {cur_target.lat:.6f}, {cur_target.lon:.6f}"
        app_state.set_command_feedback(success_msg)
        app_state.log("INFO", "DEPLOYMENT", success_msg)

        # Advance to next target or complete
        self._advance_target()
        return node

    def _advance_target(self):
        """Move pointer to next drop site or transition to RTL / COMPLETED."""
        self._is_releasing = False
        self.active_target_index += 1

        if self.active_target_index < len(self.targets):
            next_tgt = self.targets[self.active_target_index]
            self._set_state(GpsMissionState.TRANSITING)
            app_state.set_command_feedback(f"TRANSIT TO NEXT DROP: {next_tgt.target_id} ({self.active_target_index + 1}/{len(self.targets)})")
            app_state.log("INFO", "GPS_MISSION", f"Advancing to target {next_tgt.target_id} ({next_tgt.candidate_id})")
        else:
            # All drop targets deployed
            self._set_state(GpsMissionState.RETURNING)
            complete_msg = f"ALL {len(self.targets)} PAYLOADS DEPLOYED — MISSION RETURNING (RTL)"
            app_state.set_command_feedback(complete_msg)
            app_state.log("INFO", "GPS_MISSION", complete_msg)

            if self._worker:
                from gcs.mavlink import commands
                if self._worker._mock_mode:
                    self._worker._mock_telemetry_state["mode"] = "RTL"
                else:
                    commands.send_rtl(self._worker._mav)

            self.mission_completed.emit(complete_msg)
            self._set_state(GpsMissionState.COMPLETED)

        self._emit_progress()

    def get_active_target(self) -> Optional[GpsDropTarget]:
        if 0 <= self.active_target_index < len(self.targets):
            return self.targets[self.active_target_index]
        return None

    def reset(self):
        self.state = GpsMissionState.IDLE
        self.targets = []
        self.active_target_index = 0
        self._settle_timer_start = None
        self._is_releasing = False
        self._emit_progress()

    def _set_state(self, new_state: GpsMissionState):
        self.state = new_state
        self.mission_state_changed.emit(new_state.value)
        app_state.set_gps_mission_state(new_state.value)

    def _emit_progress(self):
        cur_target = self.get_active_target()
        progress = {
            "state": self.state.value,
            "target_index": self.active_target_index,
            "total_targets": len(self.targets),
            "target_id": cur_target.target_id if cur_target else "",
            "candidate_id": cur_target.candidate_id if cur_target else "",
            "target_lat": cur_target.lat if cur_target else 0.0,
            "target_lon": cur_target.lon if cur_target else 0.0,
            "distance_m": 0.0,
            "bearing_deg": 0.0,
            "auto_release": self.config.auto_release,
        }
        self.progress_updated.emit(progress)
        app_state.set_gps_mission_progress(progress)


# Global singleton instance for app-wide coordination
gps_mission_controller = GpsMissionController()
