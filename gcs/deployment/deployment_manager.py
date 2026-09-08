"""Emergency Communication Node Deployment Models and State Machine."""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class DeploymentState(str, Enum):
    IDLE = "IDLE"
    TARGET_SELECTED = "TARGET SELECTED"
    NAVIGATING = "NAVIGATING"
    ON_STATION = "ON STATION"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    RETURNING = "RETURNING"


@dataclass
class DeploymentTarget:
    target_id: str = "TGT-01"
    lat: float = 37.7749
    lon: float = -122.4194
    alt: float = 25.0
    acceptance_radius_m: float = 15.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "alt": round(self.alt, 1),
            "acceptance_radius_m": round(self.acceptance_radius_m, 1),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeploymentTarget":
        return cls(
            target_id=str(data.get("target_id", "TGT-01")),
            lat=float(data.get("lat", 37.7749)),
            lon=float(data.get("lon", -122.4194)),
            alt=float(data.get("alt", 25.0)),
            acceptance_radius_m=float(data.get("acceptance_radius_m", 15.0)),
        )


@dataclass
class DeploymentNode:
    node_id: str
    lat: float
    lon: float
    alt: float = 0.0
    deploy_time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    status: str = "ACTIVE"
    tx_power_dbm: float = 20.0
    coverage_radius_m: float = 250.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "alt": round(self.alt, 1),
            "deploy_time": self.deploy_time,
            "status": self.status,
            "tx_power_dbm": self.tx_power_dbm,
            "coverage_radius_m": self.coverage_radius_m,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeploymentNode":
        return cls(
            node_id=str(data.get("node_id", "NODE-01")),
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            alt=float(data.get("alt", 0.0)),
            deploy_time=str(data.get("deploy_time", "")),
            status=str(data.get("status", "ACTIVE")),
            tx_power_dbm=float(data.get("tx_power_dbm", 20.0)),
            coverage_radius_m=float(data.get("coverage_radius_m", 250.0)),
        )


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate forward azimuth / bearing in degrees from point 1 to point 2."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def calculate_ground_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters between two coordinates."""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c
