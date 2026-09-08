"""MAVLink Mission Protocol Manager and Waypoint Data Models.

Provides:
- Waypoint dataclass (sequence, command, coordinates, parameters)
- MissionPlan model (list of Waypoints, distance/ETA calculations)
- File I/O for QGC .plan JSON and standard ArduPilot .waypoints WPL 110 format
- Helpers for MAVLink mission command definitions and conversions
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# Common MAVLink command IDs
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_UNLIM = 17
MAV_CMD_NAV_LOITER_TURNS = 18
MAV_CMD_NAV_LOITER_TIME = 19
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_NAV_SPLINE_WAYPOINT = 82
MAV_CMD_MISSION_START = 300

# Mapping command IDs to human-readable labels
COMMAND_NAMES = {
    MAV_CMD_NAV_WAYPOINT: "WAYPOINT",
    MAV_CMD_NAV_TAKEOFF: "TAKEOFF",
    MAV_CMD_NAV_LOITER_UNLIM: "LOITER",
    MAV_CMD_NAV_LOITER_TIME: "LOITER_TIME",
    MAV_CMD_NAV_LAND: "LAND",
    MAV_CMD_NAV_RETURN_TO_LAUNCH: "RTL",
    MAV_CMD_NAV_SPLINE_WAYPOINT: "SPLINE_WP",
}

NAME_TO_COMMAND = {v: k for k, v in COMMAND_NAMES.items()}


@dataclass
class Waypoint:
    seq: int = 0
    command: int = MAV_CMD_NAV_WAYPOINT
    frame: int = 3  # MAV_FRAME_GLOBAL_RELATIVE_ALT
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 25.0  # meters relative
    param1: float = 0.0  # Hold time (seconds)
    param2: float = 2.0  # Acceptance radius (meters)
    param3: float = 0.0  # Pass through radius (0 for standard)
    param4: float = 0.0  # Yaw angle (degrees)
    autocontinue: bool = True
    is_current: bool = False

    @property
    def command_name(self) -> str:
        return COMMAND_NAMES.get(self.command, f"CMD_{self.command}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "command": self.command,
            "command_name": self.command_name,
            "frame": self.frame,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "alt": round(self.alt, 1),
            "param1": round(self.param1, 1),
            "param2": round(self.param2, 1),
            "param3": round(self.param3, 1),
            "param4": round(self.param4, 1),
            "autocontinue": self.autocontinue,
            "is_current": self.is_current,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Waypoint":
        cmd = data.get("command", MAV_CMD_NAV_WAYPOINT)
        if isinstance(cmd, str):
            cmd = NAME_TO_COMMAND.get(cmd.upper(), MAV_CMD_NAV_WAYPOINT)
        return cls(
            seq=int(data.get("seq", 0)),
            command=int(cmd),
            frame=int(data.get("frame", 3)),
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            alt=float(data.get("alt", 25.0)),
            param1=float(data.get("param1", 0.0)),
            param2=float(data.get("param2", 2.0)),
            param3=float(data.get("param3", 0.0)),
            param4=float(data.get("param4", 0.0)),
            autocontinue=bool(data.get("autocontinue", True)),
            is_current=bool(data.get("is_current", False)),
        )


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class MissionPlan:
    """Represents a full multi-waypoint flight mission."""

    def __init__(self, waypoints: Optional[List[Waypoint]] = None):
        self.waypoints: List[Waypoint] = []
        if waypoints:
            for i, wp in enumerate(waypoints):
                wp.seq = i + 1
                self.waypoints.append(wp)

    def add_waypoint(self, lat: float, lon: float, alt: float = 25.0, command: int = MAV_CMD_NAV_WAYPOINT, param1: float = 0.0) -> Waypoint:
        seq = len(self.waypoints) + 1
        wp = Waypoint(seq=seq, command=command, lat=lat, lon=lon, alt=alt, param1=param1)
        self.waypoints.append(wp)
        return wp

    def remove_waypoint(self, index: int) -> Optional[Waypoint]:
        if 0 <= index < len(self.waypoints):
            removed = self.waypoints.pop(index)
            self._reindex()
            return removed
        return None

    def move_waypoint(self, from_idx: int, to_idx: int):
        if 0 <= from_idx < len(self.waypoints) and 0 <= to_idx < len(self.waypoints):
            wp = self.waypoints.pop(from_idx)
            self.waypoints.insert(to_idx, wp)
            self._reindex()

    def clear(self):
        self.waypoints.clear()

    def _reindex(self):
        for i, wp in enumerate(self.waypoints):
            wp.seq = i + 1

    def calculate_total_distance(self) -> float:
        """Calculate total mission path length in meters."""
        if len(self.waypoints) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.waypoints) - 1):
            wp1 = self.waypoints[i]
            wp2 = self.waypoints[i + 1]
            total += haversine_distance(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
        return total

    def calculate_eta_seconds(self, cruise_speed_mps: float = 12.0) -> float:
        """Estimate flight duration in seconds given cruise speed."""
        if cruise_speed_mps <= 0:
            return 0.0
        dist = self.calculate_total_distance()
        flight_sec = dist / cruise_speed_mps
        # Add hold times
        hold_sec = sum(wp.param1 for wp in self.waypoints)
        return flight_sec + hold_sec

    def to_list_of_dicts(self) -> List[Dict[str, Any]]:
        return [wp.to_dict() for wp in self.waypoints]

    def to_qgc_json(self) -> str:
        """Export mission to QGroundControl .plan JSON format."""
        items = []
        for wp in self.waypoints:
            items.append({
                "AMSLAltAboveTerrain": None,
                "Altitude": wp.alt,
                "AltitudeMode": 1,
                "autoContinue": wp.autocontinue,
                "command": wp.command,
                "doJumpId": 1,
                "frame": wp.frame,
                "params": [wp.param1, wp.param2, wp.param3, wp.param4, wp.lat, wp.lon, wp.alt],
                "type": "SimpleItem"
            })
        data = {
            "fileType": "Plan",
            "version": 1,
            "groundStation": "UAV Emergency Deployment GCS",
            "mission": {
                "cruiseSpeed": 12.0,
                "hoverSpeed": 5.0,
                "items": items,
                "plannedHomePosition": [
                    self.waypoints[0].lat if self.waypoints else 37.7749,
                    self.waypoints[0].lon if self.waypoints else -122.4194,
                    0.0
                ],
                "vehicleType": 2,
                "version": 2
            }
        }
        return json.dumps(data, indent=2)

    def to_waypoints_text(self) -> str:
        """Export mission to standard ArduPilot/QGC WPL 110 format."""
        lines = ["QGC WPL 110"]
        # Line 0 is usually home position
        if self.waypoints:
            home = self.waypoints[0]
            lines.append(f"0\t1\t0\t16\t0\t0\t0\t0\t{home.lat:.7f}\t{home.lon:.7f}\t{home.alt:.2f}\t1")
        for i, wp in enumerate(self.waypoints):
            seq = i + 1
            cur = 1 if wp.is_current else 0
            lines.append(
                f"{seq}\t{cur}\t{wp.frame}\t{wp.command}\t"
                f"{wp.param1:.2f}\t{wp.param2:.2f}\t{wp.param3:.2f}\t{wp.param4:.2f}\t"
                f"{wp.lat:.7f}\t{wp.lon:.7f}\t{wp.alt:.2f}\t{1 if wp.autocontinue else 0}"
            )
        return "\n".join(lines) + "\n"

    @classmethod
    def from_qgc_json(cls, json_str: str) -> "MissionPlan":
        """Parse mission from QGroundControl .plan JSON string."""
        data = json.loads(json_str)
        plan = cls()
        mission_obj = data.get("mission", {})
        items = mission_obj.get("items", [])
        for i, item in enumerate(items):
            params = item.get("params", [0, 0, 0, 0, 0, 0, 0])
            cmd = item.get("command", MAV_CMD_NAV_WAYPOINT)
            lat = params[4] if len(params) > 4 else 0.0
            lon = params[5] if len(params) > 5 else 0.0
            alt = params[6] if len(params) > 6 else item.get("Altitude", 25.0)
            p1 = params[0] if len(params) > 0 else 0.0
            p2 = params[1] if len(params) > 1 else 2.0
            p3 = params[2] if len(params) > 2 else 0.0
            p4 = params[3] if len(params) > 3 else 0.0
            wp = Waypoint(
                seq=i + 1,
                command=cmd,
                lat=lat,
                lon=lon,
                alt=alt,
                param1=p1,
                param2=p2,
                param3=p3,
                param4=p4,
                autocontinue=item.get("autoContinue", True)
            )
            plan.waypoints.append(wp)
        return plan

    @classmethod
    def from_waypoints_text(cls, text: str) -> "MissionPlan":
        """Parse mission from standard ArduPilot/QGC WPL 110 format."""
        plan = cls()
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            return plan

        for line in lines:
            if line.startswith("QGC WPL"):
                continue
            parts = line.split()
            if len(parts) >= 12:
                seq = int(parts[0])
                if seq == 0:
                    # Home position line in WPL 110, skip from waypoint list
                    continue
                cur = bool(int(parts[1]))
                frame = int(parts[2])
                cmd = int(parts[3])
                p1, p2, p3, p4 = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                lat, lon, alt = float(parts[8]), float(parts[9]), float(parts[10])
                autocontinue = bool(int(parts[11]))
                wp = Waypoint(
                    seq=len(plan.waypoints) + 1,
                    command=cmd,
                    frame=frame,
                    lat=lat,
                    lon=lon,
                    alt=alt,
                    param1=p1,
                    param2=p2,
                    param3=p3,
                    param4=p4,
                    autocontinue=autocontinue,
                    is_current=cur,
                )
                plan.waypoints.append(wp)
        return plan
