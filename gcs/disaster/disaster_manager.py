"""Disaster Area Planning Data Models and Spherical Geodesic Calculations.

Provides:
- Disaster area polygon vertices and boundary definition
- Spherical polygon area (m², km², hectares) and perimeter calculations
- Hazard / No-Fly exclusion zones (NFZ, Fire, Flood, Structural Collapse)
- GeoJSON export and import capabilities
- Emergency disaster scenario presets
"""

import math
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from gcs.deployment.deployment_manager import calculate_ground_distance


@dataclass
class DisasterVertex:
    lat: float
    lon: float
    seq: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "seq": self.seq,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisasterVertex":
        return cls(
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            seq=int(data.get("seq", 1)),
        )


@dataclass
class HazardZone:
    zone_id: str = "HZ-01"
    name: str = "Hazard Exclusion Zone"
    lat: float = 37.7760
    lon: float = -122.4180
    radius_m: float = 120.0
    hazard_type: str = "NO_FLY"  # NO_FLY, FIRE, COLLAPSE, FLOOD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "radius_m": round(self.radius_m, 1),
            "hazard_type": self.hazard_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HazardZone":
        return cls(
            zone_id=str(data.get("zone_id", "HZ-01")),
            name=str(data.get("name", "Hazard Zone")),
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            radius_m=float(data.get("radius_m", 100.0)),
            hazard_type=str(data.get("hazard_type", "NO_FLY")),
        )


@dataclass
class DisasterArea:
    name: str = "Disaster Incident Area"
    description: str = "Emergency response communication recovery operational zone"
    vertices: List[DisasterVertex] = field(default_factory=list)
    hazard_zones: List[HazardZone] = field(default_factory=list)

    def calculate_perimeter_meters(self) -> float:
        """Calculate total perimeter in meters around closed polygon."""
        if len(self.vertices) < 3:
            return 0.0
        total_m = 0.0
        n = len(self.vertices)
        for i in range(n):
            v1 = self.vertices[i]
            v2 = self.vertices[(i + 1) % n]
            total_m += calculate_ground_distance(v1.lat, v1.lon, v2.lat, v2.lon)
        return total_m

    def calculate_area_sq_meters(self) -> float:
        """Calculate spherical geodesic polygon area in square meters using spherical surveyor's excess."""
        if len(self.vertices) < 3:
            return 0.0

        R = 6371000.0  # Earth radius in meters
        total = 0.0
        n = len(self.vertices)

        for i in range(n):
            v_prev = self.vertices[(i - 1 + n) % n]
            v_curr = self.vertices[i]
            v_next = self.vertices[(i + 1) % n]

            phi = math.radians(v_curr.lat)
            lambda_next = math.radians(v_next.lon)
            lambda_prev = math.radians(v_prev.lon)

            # Difference with wrap-around check
            delta_lambda = lambda_next - lambda_prev
            if delta_lambda > math.pi:
                delta_lambda -= 2.0 * math.pi
            elif delta_lambda < -math.pi:
                delta_lambda += 2.0 * math.pi

            total += delta_lambda * math.sin(phi)

        area = abs(total) * (R * R) / 2.0
        return area

    def calculate_centroid(self) -> Tuple[float, float]:
        """Calculate average latitude and longitude centroid of polygon."""
        if not self.vertices:
            return (37.7749, -122.4194)
        avg_lat = sum(v.lat for v in self.vertices) / len(self.vertices)
        avg_lon = sum(v.lon for v in self.vertices) / len(self.vertices)
        return (round(avg_lat, 7), round(avg_lon, 7))

    @property
    def centroid(self) -> Any:
        class _Centroid:
            def __init__(self, lat, lon):
                self.lat = lat
                self.lon = lon
        c_lat, c_lon = self.calculate_centroid()
        return _Centroid(c_lat, c_lon)

    @property
    def area_sq_m(self) -> float:
        return self.calculate_area_sq_meters()


    def to_dict(self) -> Dict[str, Any]:
        area_m2 = self.calculate_area_sq_meters()
        perim_m = self.calculate_perimeter_meters()
        cent_lat, cent_lon = self.calculate_centroid()

        return {
            "name": self.name,
            "description": self.description,
            "vertices": [v.to_dict() for v in self.vertices],
            "hazard_zones": [h.to_dict() for h in self.hazard_zones],
            "area_sq_m": round(area_m2, 1),
            "area_sq_km": round(area_m2 / 1e6, 3),
            "area_hectares": round(area_m2 / 1e4, 2),
            "perimeter_m": round(perim_m, 1),
            "perimeter_km": round(perim_m / 1000.0, 3),
            "centroid": {"lat": cent_lat, "lon": cent_lon},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisasterArea":
        verts = [DisasterVertex.from_dict(v) for v in data.get("vertices", [])]
        hazards = [HazardZone.from_dict(h) for h in data.get("hazard_zones", [])]
        return cls(
            name=str(data.get("name", "Disaster Incident Area")),
            description=str(data.get("description", "")),
            vertices=verts,
            hazard_zones=hazards,
        )

    def to_geojson(self) -> Dict[str, Any]:
        """Convert disaster boundary and hazard zones to standard GeoJSON FeatureCollection."""
        features = []

        if len(self.vertices) >= 3:
            # Polygon coordinates: [ [ [lon, lat], ... , [lon0, lat0] ] ]
            ring = [[v.lon, v.lat] for v in self.vertices]
            ring.append([self.vertices[0].lon, self.vertices[0].lat])  # Close ring

            features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "disaster_boundary",
                    "name": self.name,
                    "description": self.description,
                    "area_sq_m": round(self.calculate_area_sq_meters(), 1),
                    "perimeter_m": round(self.calculate_perimeter_meters(), 1),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring]
                }
            })

        for h in self.hazard_zones:
            features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "hazard_zone",
                    "zone_id": h.zone_id,
                    "name": h.name,
                    "hazard_type": h.hazard_type,
                    "radius_m": h.radius_m,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [h.lon, h.lat]
                }
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    @classmethod
    def from_geojson(cls, geojson: Dict[str, Any]) -> "DisasterArea":
        """Parse standard GeoJSON FeatureCollection into DisasterArea."""
        area = cls()
        features = geojson.get("features", [])

        for f in features:
            props = f.get("properties", {})
            geom = f.get("geometry", {})
            f_type = props.get("feature_type", "")
            g_type = geom.get("type", "")

            if f_type == "disaster_boundary" or g_type == "Polygon":
                coords = geom.get("coordinates", [[]])[0]
                area.name = props.get("name", "Imported Disaster Area")
                area.description = props.get("description", "")
                verts = []
                # Drop closing duplicate vertex if present
                pts = coords[:-1] if (len(coords) > 1 and coords[0] == coords[-1]) else coords
                for idx, pt in enumerate(pts, start=1):
                    verts.append(DisasterVertex(lon=pt[0], lat=pt[1], seq=idx))
                area.vertices = verts

            elif f_type == "hazard_zone" or (g_type == "Point" and "radius_m" in props):
                pt = geom.get("coordinates", [0.0, 0.0])
                hz = HazardZone(
                    zone_id=props.get("zone_id", "HZ"),
                    name=props.get("name", "Hazard Zone"),
                    lat=pt[1],
                    lon=pt[0],
                    radius_m=float(props.get("radius_m", 100.0)),
                    hazard_type=props.get("hazard_type", "NO_FLY"),
                )
                area.hazard_zones.append(hz)

        return area


def get_preset_scenarios() -> Dict[str, DisasterArea]:
    """Returns realistic emergency disaster scenario presets for instant evaluation."""
    presets = {}

    # Scenario 1: San Francisco Flash Flood Plain (1.2 km²)
    sf_flood = DisasterArea(
        name="Sector Alpha — Flash Flood Zone",
        description="Lowland river plain inundation requiring emergency cellular relay deployment",
        vertices=[
            DisasterVertex(lat=37.7785, lon=-122.4230, seq=1),
            DisasterVertex(lat=37.7810, lon=-122.4170, seq=2),
            DisasterVertex(lat=37.7790, lon=-122.4130, seq=3),
            DisasterVertex(lat=37.7735, lon=-122.4140, seq=4),
            DisasterVertex(lat=37.7720, lon=-122.4205, seq=5),
            DisasterVertex(lat=37.7750, lon=-122.4245, seq=6),
        ],
        hazard_zones=[
            HazardZone(zone_id="HZ-01", name="Submerged Power Substation", lat=37.7770, lon=-122.4175, radius_m=90.0, hazard_type="NO_FLY"),
        ]
    )
    presets["SF Flash Flood (1.2 km²)"] = sf_flood

    # Scenario 2: Urban Earthquake Sector Alpha (0.85 km²)
    quake = DisasterArea(
        name="Urban Earthquake Collapse Zone",
        description="High-density commercial collapse zone with base station infrastructure failure",
        vertices=[
            DisasterVertex(lat=37.7800, lon=-122.4240, seq=1),
            DisasterVertex(lat=37.7815, lon=-122.4140, seq=2),
            DisasterVertex(lat=37.7725, lon=-122.4130, seq=3),
            DisasterVertex(lat=37.7710, lon=-122.4230, seq=4),
        ],
        hazard_zones=[
            HazardZone(zone_id="HZ-01", name="Tower Crane Collapse Hazard", lat=37.7765, lon=-122.4185, radius_m=75.0, hazard_type="COLLAPSE"),
            HazardZone(zone_id="HZ-02", name="Gas Pipeline Rupture Zone", lat=37.7745, lon=-122.4170, radius_m=60.0, hazard_type="FIRE"),
        ]
    )
    presets["Urban Earthquake (0.85 km²)"] = quake

    # Scenario 3: Wildfire Rapid Defense Perimeter (2.5 km²)
    wildfire = DisasterArea(
        name="Wildfire Rapid Defense Perimeter",
        description="Advancing wildland-urban interface fire front with severed fiber backhaul",
        vertices=[
            DisasterVertex(lat=37.7830, lon=-122.4260, seq=1),
            DisasterVertex(lat=37.7850, lon=-122.4160, seq=2),
            DisasterVertex(lat=37.7800, lon=-122.4100, seq=3),
            DisasterVertex(lat=37.7720, lon=-122.4120, seq=4),
            DisasterVertex(lat=37.7690, lon=-122.4200, seq=5),
            DisasterVertex(lat=37.7740, lon=-122.4280, seq=6),
        ],
        hazard_zones=[
            HazardZone(zone_id="HZ-01", name="Active Fire Thermal Updraft NFZ", lat=37.7815, lon=-122.4150, radius_m=180.0, hazard_type="FIRE"),
        ]
    )
    presets["Wildfire Defense (2.5 km²)"] = wildfire

    return presets
