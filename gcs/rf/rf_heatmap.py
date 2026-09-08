"""
RF Heatmap Engine & Spatial Statistical RF Analysis
Phase 13: Ground Control Station (GCS)

Implements 2D spatial interpolation (Inverse Distance Weighting - IDW)
and statistical RF coverage analytics (Strong, Good, Weak, No Coverage)
over surveyed or simulated virtual node RF fields.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import math


class RfCategory:
    """RF Signal quality classification categories with tactical color codes."""
    STRONG = "STRONG"          # >= -65 dBm (Green)
    GOOD = "GOOD"              # -75 to -65 dBm (Lime / Yellow-Green)
    WEAK = "WEAK"              # -85 to -75 dBm (Orange)
    NO_COVERAGE = "NO_COVERAGE"# < -85 dBm (Red / Crimson)


# UI Color palette matching tactical dark theme
CATEGORY_COLORS = {
    RfCategory.STRONG: "#2ecc71",       # Bright Emerald Green
    RfCategory.GOOD: "#a3e635",         # Lime Green / Yellow-Green
    RfCategory.WEAK: "#f39c12",         # Vibrant Amber / Orange
    RfCategory.NO_COVERAGE: "#e74c3c",   # Crimson Red
}

CATEGORY_FILL_OPACITY = {
    RfCategory.STRONG: 0.55,
    RfCategory.GOOD: 0.50,
    RfCategory.WEAK: 0.45,
    RfCategory.NO_COVERAGE: 0.35,
}


@dataclass
class HeatmapCell:
    """Represents a discrete spatial grid cell in the RF heatmap."""
    row: int
    col: int
    lat: float
    lon: float
    rssi_dbm: float
    category: str
    color: str
    opacity: float
    bounds: Tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)

    def to_geojson_feature(self) -> Dict[str, Any]:
        """Convert grid cell to a GeoJSON Polygon feature."""
        min_lat, min_lon, max_lat, max_lon = self.bounds
        coordinates = [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]]
        return {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": coordinates,
            },
            "properties": {
                "row": self.row,
                "col": self.col,
                "center": [self.lat, self.lon],
                "rssi_dbm": round(self.rssi_dbm, 1),
                "category": self.category,
                "color": self.color,
                "fillOpacity": self.opacity,
            }
        }


@dataclass
class RfAnalysisResult:
    """Statistical summary of RF coverage across the operational area."""
    total_points: int = 0
    mean_rssi_dbm: float = -100.0
    min_rssi_dbm: float = -100.0
    max_rssi_dbm: float = -100.0
    coverage_pct: float = 0.0     # Percentage >= -85 dBm (Strong + Good + Weak)
    strong_pct: float = 0.0       # Percentage >= -65 dBm
    good_pct: float = 0.0         # Percentage -75 to -65 dBm
    weak_pct: float = 0.0         # Percentage -85 to -75 dBm
    no_coverage_pct: float = 0.0  # Percentage < -85 dBm
    cells: List[HeatmapCell] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_points": self.total_points,
            "mean_rssi_dbm": round(self.mean_rssi_dbm, 1),
            "min_rssi_dbm": round(self.min_rssi_dbm, 1),
            "max_rssi_dbm": round(self.max_rssi_dbm, 1),
            "coverage_pct": round(self.coverage_pct, 1),
            "strong_pct": round(self.strong_pct, 1),
            "good_pct": round(self.good_pct, 1),
            "weak_pct": round(self.weak_pct, 1),
            "no_coverage_pct": round(self.no_coverage_pct, 1),
        }

    def to_geojson(self) -> Dict[str, Any]:
        """Convert full heatmap cell collection to a GeoJSON FeatureCollection."""
        return {
            "type": "FeatureCollection",
            "properties": self.to_dict(),
            "features": [cell.to_geojson_feature() for cell in self.cells]
        }


def classify_rssi(rssi_dbm: float) -> Tuple[str, str, float]:
    """
    Classify RSSI value into Section 24 UI categories:
    - Strong: >= -65 dBm
    - Good: -75 to -65 dBm
    - Weak: -85 to -75 dBm
    - No coverage: < -85 dBm
    Returns (category, hex_color, opacity).
    """
    if rssi_dbm >= -65.0:
        cat = RfCategory.STRONG
    elif rssi_dbm >= -75.0:
        cat = RfCategory.GOOD
    elif rssi_dbm >= -85.0:
        cat = RfCategory.WEAK
    else:
        cat = RfCategory.NO_COVERAGE
    
    return cat, CATEGORY_COLORS[cat], CATEGORY_FILL_OPACITY[cat]


class RfHeatmapEngine:
    """
    Computes spatial RF heatmap grids and statistical coverage analysis.
    Uses Inverse Distance Weighting (IDW) interpolation from survey samples,
    or direct RF propagation modeling from active virtual nodes.
    """

    DEFAULT_GRID_RESOLUTION = 24  # 24x24 = 576 discrete spatial bins
    IDW_POWER = 2.0               # Standard inverse square weight

    @classmethod
    def generate_heatmap_from_samples(
        cls,
        samples: List[Any],  # List of SurveySample or objects with lat, lon, rssi_dbm
        grid_resolution: int = DEFAULT_GRID_RESOLUTION,
        boundary_polygon: Optional[List[Tuple[float, float]]] = None,
    ) -> RfAnalysisResult:
        """
        Interpolate RSSI values across a spatial grid bounded by survey samples
        using Inverse Distance Weighting (IDW).
        """
        valid_samples = [s for s in samples if getattr(s, "rssi_dbm", None) is not None]
        if not valid_samples:
            return RfAnalysisResult()

        lats = [s.lat for s in valid_samples]
        lons = [s.lon for s in valid_samples]

        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Apply a 5% margin around the bounding box for continuous visual edges
        lat_span = max(max_lat - min_lat, 0.001)
        lon_span = max(max_lon - min_lon, 0.001)
        margin = 0.04
        min_lat -= lat_span * margin
        max_lat += lat_span * margin
        min_lon -= lon_span * margin
        max_lon += lon_span * margin

        d_lat = (max_lat - min_lat) / grid_resolution
        d_lon = (max_lon - min_lon) / grid_resolution

        cells: List[HeatmapCell] = []
        all_rssi: List[float] = []

        strong_count = 0
        good_count = 0
        weak_count = 0
        no_cov_count = 0

        for r in range(grid_resolution):
            c_lat = min_lat + (r + 0.5) * d_lat
            cell_min_lat = min_lat + r * d_lat
            cell_max_lat = min_lat + (r + 1) * d_lat

            for c in range(grid_resolution):
                c_lon = min_lon + (c + 0.5) * d_lon
                cell_min_lon = min_lon + c * d_lon
                cell_max_lon = min_lon + (c + 1) * d_lon

                # Compute IDW from survey samples
                rssi = cls._interpolate_idw(c_lat, c_lon, valid_samples)
                category, color, opacity = classify_rssi(rssi)

                bounds = (cell_min_lat, cell_min_lon, cell_max_lat, cell_max_lon)
                cell = HeatmapCell(
                    row=r,
                    col=c,
                    lat=c_lat,
                    lon=c_lon,
                    rssi_dbm=rssi,
                    category=category,
                    color=color,
                    opacity=opacity,
                    bounds=bounds,
                )
                cells.append(cell)
                all_rssi.append(rssi)

                if category == RfCategory.STRONG:
                    strong_count += 1
                elif category == RfCategory.GOOD:
                    good_count += 1
                elif category == RfCategory.WEAK:
                    weak_count += 1
                else:
                    no_cov_count += 1

        total = len(cells)
        if total == 0:
            return RfAnalysisResult()

        coverage_count = strong_count + good_count + weak_count

        return RfAnalysisResult(
            total_points=len(valid_samples),
            mean_rssi_dbm=sum(all_rssi) / total,
            min_rssi_dbm=min(all_rssi),
            max_rssi_dbm=max(all_rssi),
            coverage_pct=(coverage_count / total) * 100.0,
            strong_pct=(strong_count / total) * 100.0,
            good_pct=(good_count / total) * 100.0,
            weak_pct=(weak_count / total) * 100.0,
            no_coverage_pct=(no_cov_count / total) * 100.0,
            cells=cells,
        )

    @classmethod
    def generate_heatmap_from_nodes(
        cls,
        nodes: List[Any],
        center_lat: float,
        center_lon: float,
        radius_m: float = 650.0,
        grid_resolution: int = DEFAULT_GRID_RESOLUTION,
        rf_engine: Optional[Any] = None,
    ) -> RfAnalysisResult:
        """
        Generate spatial RF heatmap directly from active virtual nodes
        using RF propagation calculations.
        """
        # Convert radius in meters to approx lat/lon degrees
        meters_per_deg_lat = 111320.0
        meters_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))

        d_lat_deg = radius_m / meters_per_deg_lat
        d_lon_deg = radius_m / meters_per_deg_lon

        min_lat = center_lat - d_lat_deg
        max_lat = center_lat + d_lat_deg
        min_lon = center_lon - d_lon_deg
        max_lon = center_lon + d_lon_deg

        step_lat = (max_lat - min_lat) / grid_resolution
        step_lon = (max_lon - min_lon) / grid_resolution

        # Node filtering: include ACTIVE, DEPLOYED, or READY nodes
        active_nodes = [
            n for n in nodes 
            if getattr(n, "status", None) is not None and getattr(n.status, "value", str(n.status)).upper() in ("ACTIVE", "DEGRADED", "READY", "DEPLOYED")
        ]
        if not active_nodes and nodes:
            active_nodes = list(nodes)

        cells: List[HeatmapCell] = []
        all_rssi: List[float] = []

        strong_count = 0
        good_count = 0
        weak_count = 0
        no_cov_count = 0

        # Import local rf model if engine not provided
        if rf_engine is None:
            from gcs.rf.rf_model import rf_engine

        for r in range(grid_resolution):
            c_lat = min_lat + (r + 0.5) * step_lat
            cell_min_lat = min_lat + r * step_lat
            cell_max_lat = min_lat + (r + 1) * step_lat

            for c in range(grid_resolution):
                c_lon = min_lon + (c + 0.5) * step_lon
                cell_min_lon = min_lon + c * step_lon
                cell_max_lon = min_lon + (c + 1) * step_lon

                # Compute strongest signal received at this ground coordinate from any active node
                best_rssi = -115.0
                if active_nodes:
                    for node in active_nodes:
                        n_lat = getattr(node, "lat", getattr(node, "latitude", 0.0))
                        n_lon = getattr(node, "lon", getattr(node, "longitude", 0.0))
                        n_alt = getattr(node, "altitude_m", getattr(node, "altitude", 0.0)) or 0.0

                        # 2D distance
                        d_m = cls._haversine_distance(c_lat, c_lon, n_lat, n_lon)
                        slant_dist_m = math.sqrt(d_m**2 + n_alt**2)
                        slant_dist_m = max(1.0, slant_dist_m)
                        
                        tx_power = getattr(node, "tx_power_dbm", 20.0)
                        rssi = rf_engine.calculate_rssi(slant_dist_m, tx_power_dbm=tx_power)
                        if rssi > best_rssi:
                            best_rssi = rssi
                else:
                    best_rssi = -115.0

                category, color, opacity = classify_rssi(best_rssi)
                bounds = (cell_min_lat, cell_min_lon, cell_max_lat, cell_max_lon)
                cell = HeatmapCell(
                    row=r,
                    col=c,
                    lat=c_lat,
                    lon=c_lon,
                    rssi_dbm=best_rssi,
                    category=category,
                    color=color,
                    opacity=opacity,
                    bounds=bounds,
                )
                cells.append(cell)
                all_rssi.append(best_rssi)

                if category == RfCategory.STRONG:
                    strong_count += 1
                elif category == RfCategory.GOOD:
                    good_count += 1
                elif category == RfCategory.WEAK:
                    weak_count += 1
                else:
                    no_cov_count += 1

        total = len(cells)
        coverage_count = strong_count + good_count + weak_count

        return RfAnalysisResult(
            total_points=len(active_nodes),
            mean_rssi_dbm=sum(all_rssi) / total if total > 0 else -100.0,
            min_rssi_dbm=min(all_rssi) if all_rssi else -100.0,
            max_rssi_dbm=max(all_rssi) if all_rssi else -100.0,
            coverage_pct=(coverage_count / total) * 100.0 if total > 0 else 0.0,
            strong_pct=(strong_count / total) * 100.0 if total > 0 else 0.0,
            good_pct=(good_count / total) * 100.0 if total > 0 else 0.0,
            weak_pct=(weak_count / total) * 100.0 if total > 0 else 0.0,
            no_coverage_pct=(no_cov_count / total) * 100.0 if total > 0 else 0.0,
            cells=cells,
        )

    @classmethod
    def _interpolate_idw(cls, lat: float, lon: float, samples: List[Any]) -> float:
        """
        Inverse Distance Weighting (IDW) calculation for a point (lat, lon).
        """
        numerator = 0.0
        denominator = 0.0

        for s in samples:
            dist = cls._haversine_distance(lat, lon, s.lat, s.lon)
            if dist < 1.0:  # Coincident or extremely close
                return float(s.rssi_dbm)

            w = 1.0 / (dist ** cls.IDW_POWER)
            numerator += w * float(s.rssi_dbm)
            denominator += w

        if denominator == 0.0:
            return -100.0
        return numerator / denominator

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in meters between two lat/lon points."""
        R = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = (math.sin(dphi / 2.0) ** 2 +
             math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2))
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c
