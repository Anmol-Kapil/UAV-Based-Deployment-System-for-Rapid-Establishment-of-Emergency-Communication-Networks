"""Coverage Optimization and Candidate Generation Algorithm for Emergency Networks.

Solves the optimal spatial placement problem:
Given a disaster polygon boundary, hazard exclusion zones, and K available physical
relay nodes, determine the optimal geographical coordinates that maximize aggregate
RF coverage of the disaster area while maintaining mesh backhaul communication
and avoiding hazard zones.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple


class OptimizationStrategy(str, Enum):
    GREEDY_MAX_COVERAGE = "Greedy Max Coverage"
    PRIORITY_HOTSPOT = "Priority Hotspots"
    UNIFORM_MESH = "Uniform Mesh"


@dataclass
class CandidateSite:
    candidate_id: str
    lat: float
    lon: float
    alt: float = 25.0
    coverage_radius_m: float = 250.0
    covered_area_m2: float = 0.0
    coverage_ratio: float = 0.0  # Fraction of disaster area covered
    overlap_ratio: float = 0.0   # Fraction overlapping with already selected nodes
    is_selected: bool = False
    mesh_linked_nodes: List[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "alt": round(self.alt, 1),
            "coverage_radius_m": round(self.coverage_radius_m, 1),
            "covered_area_m2": round(self.covered_area_m2, 1),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "overlap_ratio": round(self.overlap_ratio, 4),
            "is_selected": self.is_selected,
            "mesh_linked_nodes": list(self.mesh_linked_nodes),
            "score": round(self.score, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateSite":
        return cls(
            candidate_id=str(data.get("candidate_id", "C-01")),
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            alt=float(data.get("alt", 25.0)),
            coverage_radius_m=float(data.get("coverage_radius_m", 250.0)),
            covered_area_m2=float(data.get("covered_area_m2", 0.0)),
            coverage_ratio=float(data.get("coverage_ratio", 0.0)),
            overlap_ratio=float(data.get("overlap_ratio", 0.0)),
            is_selected=bool(data.get("is_selected", False)),
            mesh_linked_nodes=list(data.get("mesh_linked_nodes", [])),
            score=float(data.get("score", 0.0)),
        )


@dataclass
class OptimizationConfig:
    num_nodes: int = 3
    coverage_radius_m: float = 250.0
    grid_resolution_m: float = 80.0
    hazard_buffer_m: float = 30.0
    cruise_alt_m: float = 25.0
    strategy: OptimizationStrategy = OptimizationStrategy.GREEDY_MAX_COVERAGE


@dataclass
class OptimizationResult:
    total_area_m2: float
    covered_area_m2: float
    coverage_percent: float
    overlap_percent: float
    candidates: List[CandidateSite] = field(default_factory=list)
    selected_candidates: List[CandidateSite] = field(default_factory=list)
    mesh_connectivity_ok: bool = True
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_area_m2": round(self.total_area_m2, 1),
            "covered_area_m2": round(self.covered_area_m2, 1),
            "coverage_percent": round(self.coverage_percent, 1),
            "overlap_percent": round(self.overlap_percent, 1),
            "candidate_count": len(self.candidates),
            "selected_count": len(self.selected_candidates),
            "selected_ids": [c.candidate_id for c in self.selected_candidates],
            "candidates": [c.to_dict() for c in self.candidates],
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "mesh_connectivity_ok": self.mesh_connectivity_ok,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates geodesic distance in meters between two lat/lon points."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def point_in_polygon(lat: float, lon: float, vertices: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm to determine if a point (lat, lon) is inside polygon vertices [(lat, lon), ...]."""
    if len(vertices) < 3:
        return False
    inside = False
    n = len(vertices)
    p1_lat, p1_lon = vertices[0]
    for i in range(1, n + 1):
        p2_lat, p2_lon = vertices[i % n]
        if min(p1_lat, p2_lat) < lat <= max(p1_lat, p2_lat):
            if lon <= max(p1_lon, p2_lon):
                if p1_lat != p2_lat:
                    x_inters = (lat - p1_lat) * (p2_lon - p1_lon) / (p2_lat - p1_lat) + p1_lon
                else:
                    x_inters = p1_lon
                if p1_lon == p2_lon or lon <= x_inters:
                    inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon
    return inside


def lat_lon_to_meters(lat: float, lon: float, ref_lat: float, ref_lon: float) -> Tuple[float, float]:
    """Projects lat/lon to local tangent plane (X East, Y North in meters) relative to reference origin."""
    r = 6371000.0
    x = math.radians(lon - ref_lon) * r * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * r
    return x, y


def meters_to_lat_lon(x: float, y: float, ref_lat: float, ref_lon: float) -> Tuple[float, float]:
    """Converts local tangent plane coordinates (X East, Y North) back to lat/lon."""
    r = 6371000.0
    lat = ref_lat + math.degrees(y / r)
    lon = ref_lon + math.degrees(x / (r * math.cos(math.radians(ref_lat))))
    return lat, lon


def generate_candidate_grid(
    disaster_area: Any,
    grid_resolution_m: float = 80.0,
    hazard_zones: Optional[List[Any]] = None,
    hazard_buffer_m: float = 30.0,
    cruise_alt_m: float = 25.0
) -> List[CandidateSite]:
    """Generates candidate drop locations within the disaster polygon on a regular lattice,

    strictly pruning points outside the boundary or inside hazard exclusion zones.
    """
    verts = disaster_area.get("vertices", []) if isinstance(disaster_area, dict) else getattr(disaster_area, "vertices", [])
    if len(verts) < 3:
        return []

    poly_coords = [
        (v.get("lat") if isinstance(v, dict) else v.lat,
         v.get("lon") if isinstance(v, dict) else v.lon)
        for v in verts
    ]
    if hasattr(disaster_area, "calculate_centroid"):
        c_lat, c_lon = disaster_area.calculate_centroid()
    elif isinstance(disaster_area, dict) and "centroid" in disaster_area:
        c_lat = disaster_area["centroid"]["lat"]
        c_lon = disaster_area["centroid"]["lon"]
    elif hasattr(disaster_area, "centroid") and disaster_area.centroid:
        c_lat = disaster_area.centroid.lat
        c_lon = disaster_area.centroid.lon
    else:
        c_lat = sum(p[0] for p in poly_coords) / len(poly_coords)
        c_lon = sum(p[1] for p in poly_coords) / len(poly_coords)

    # Convert polygon vertices to local meters
    poly_xy = [lat_lon_to_meters(lat, lon, c_lat, c_lon) for lat, lon in poly_coords]
    min_x = min(p[0] for p in poly_xy)
    max_x = max(p[0] for p in poly_xy)
    min_y = min(p[1] for p in poly_xy)
    max_y = max(p[1] for p in poly_xy)

    step = max(30.0, float(grid_resolution_m))
    candidates: List[CandidateSite] = []
    cand_idx = 1

    curr_y = min_y + step / 2.0
    while curr_y <= max_y:
        curr_x = min_x + step / 2.0
        while curr_x <= max_x:
            lat, lon = meters_to_lat_lon(curr_x, curr_y, c_lat, c_lon)
            # 1. Point in polygon test
            if point_in_polygon(lat, lon, poly_coords):
                # 2. Hazard zone exclusion test
                in_hazard = False
                if hazard_zones:
                    for hz in hazard_zones:
                        dist = haversine_distance_m(lat, lon, hz.lat, hz.lon)
                        if dist < (hz.radius_m + hazard_buffer_m):
                            in_hazard = True
                            break
                if not in_hazard:
                    cand = CandidateSite(
                        candidate_id=f"C-{cand_idx:02d}",
                        lat=lat,
                        lon=lon,
                        alt=cruise_alt_m,
                        coverage_radius_m=250.0
                    )
                    candidates.append(cand)
                    cand_idx += 1
            curr_x += step
        curr_y += step

    return candidates


def optimize_placement(
    candidates: List[CandidateSite],
    disaster_area: Any,
    config: Optional[OptimizationConfig] = None,
    hazard_zones: Optional[List[Any]] = None,
) -> OptimizationResult:
    """Executes Greedy Maximum Coverage placement optimization across candidates.

    Iteratively selects K candidates to maximize aggregate non-overlapping RF coverage
    within the disaster area boundary while maintaining mesh connectivity.
    """
    import time
    t0 = time.perf_counter()

    cfg = config or OptimizationConfig()
    cov_radius = float(cfg.coverage_radius_m)
    num_nodes = max(1, min(int(cfg.num_nodes), len(candidates)))

    verts = disaster_area.get("vertices", []) if isinstance(disaster_area, dict) else getattr(disaster_area, "vertices", [])
    if len(verts) < 3:
        return OptimizationResult(
            total_area_m2=0.0, covered_area_m2=0.0, coverage_percent=0.0,
            overlap_percent=0.0, candidates=[], selected_candidates=[],
            mesh_connectivity_ok=False, execution_time_ms=0.0
        )

    poly_coords = [
        (v.get("lat") if isinstance(v, dict) else v.lat,
         v.get("lon") if isinstance(v, dict) else v.lon)
        for v in verts
    ]
    if hasattr(disaster_area, "calculate_centroid"):
        c_lat, c_lon = disaster_area.calculate_centroid()
    elif isinstance(disaster_area, dict) and "centroid" in disaster_area:
        c_lat = disaster_area["centroid"]["lat"]
        c_lon = disaster_area["centroid"]["lon"]
    elif hasattr(disaster_area, "centroid") and disaster_area.centroid:
        c_lat = disaster_area.centroid.lat
        c_lon = disaster_area.centroid.lon
    else:
        c_lat = sum(p[0] for p in poly_coords) / len(poly_coords)
        c_lon = sum(p[1] for p in poly_coords) / len(poly_coords)

    # 1. Discretize evaluation demand points across disaster area (fine evaluation grid)
    poly_xy = [lat_lon_to_meters(lat, lon, c_lat, c_lon) for lat, lon in poly_coords]
    min_x, max_x = min(p[0] for p in poly_xy), max(p[0] for p in poly_xy)
    min_y, max_y = min(p[1] for p in poly_xy), max(p[1] for p in poly_xy)

    # Adaptive sample resolution: ~40m sample spacing
    eval_step = 40.0
    demand_points: List[Tuple[float, float]] = []  # (x, y) in meters
    ey = min_y + eval_step / 2.0
    while ey <= max_y:
        ex = min_x + eval_step / 2.0
        while ex <= max_x:
            elat, elon = meters_to_lat_lon(ex, ey, c_lat, c_lon)
            if point_in_polygon(elat, elon, poly_coords):
                demand_points.append((ex, ey))
            ex += eval_step
        ey += eval_step

    total_demand_pts = max(1, len(demand_points))
    cell_area_m2 = eval_step * eval_step
    approx_total_area_m2 = total_demand_pts * cell_area_m2
    if hasattr(disaster_area, "calculate_area_sq_meters"):
        real_area_m2 = disaster_area.calculate_area_sq_meters()
    elif isinstance(disaster_area, dict):
        real_area_m2 = disaster_area.get("area_sq_m", approx_total_area_m2)
    elif hasattr(disaster_area, "area_sq_m"):
        real_area_m2 = disaster_area.area_sq_m
    else:
        real_area_m2 = approx_total_area_m2

    if not candidates:
        return OptimizationResult(
            total_area_m2=real_area_m2, covered_area_m2=0.0, coverage_percent=0.0,
            overlap_percent=0.0, candidates=[], selected_candidates=[],
            mesh_connectivity_ok=False, execution_time_ms=(time.perf_counter() - t0) * 1000.0
        )

    # Convert candidates to local meter coords
    cand_xy = [lat_lon_to_meters(c.lat, c.lon, c_lat, c_lon) for c in candidates]

    # Precompute set of covered demand points for each candidate
    candidate_coverage_sets: List[set] = []
    r2 = cov_radius * cov_radius
    for (cx, cy) in cand_xy:
        covered = set()
        for idx, (dx, dy) in enumerate(demand_points):
            dist2 = (cx - dx) ** 2 + (cy - dy) ** 2
            if dist2 <= r2:
                covered.add(idx)
        candidate_coverage_sets.append(covered)

    # Reset candidate selection state
    for c in candidates:
        c.is_selected = False
        c.coverage_radius_m = cov_radius
        c.mesh_linked_nodes = []
        c.score = 0.0

    # 2. Greedy Maximum Coverage with Overlap Penalty
    selected_indices: List[int] = []
    currently_covered_pts: set = set()
    all_selected_coverage_union: set = set()
    sum_individual_pts = 0

    for step in range(num_nodes):
        best_cand_idx = -1
        best_gain = -1.0
        best_uncovered_count = -1

        for idx in range(len(candidates)):
            if idx in selected_indices:
                continue

            cov_set = candidate_coverage_sets[idx]
            new_pts = cov_set - currently_covered_pts
            overlap_pts = cov_set & currently_covered_pts

            # Score = new demand covered - (0.2 * redundant overlap)
            gain = len(new_pts) - 0.25 * len(overlap_pts)

            if gain > best_gain:
                best_gain = gain
                best_cand_idx = idx
                best_uncovered_count = len(new_pts)

        if best_cand_idx != -1 and best_uncovered_count > 0:
            selected_indices.append(best_cand_idx)
            chosen_set = candidate_coverage_sets[best_cand_idx]
            overlap_with_existing = chosen_set & currently_covered_pts
            currently_covered_pts.update(chosen_set)
            sum_individual_pts += len(chosen_set)

            c_obj = candidates[best_cand_idx]
            c_obj.is_selected = True
            c_obj.score = best_gain
            c_obj.covered_area_m2 = len(chosen_set) * cell_area_m2
            c_obj.coverage_ratio = len(chosen_set) / total_demand_pts
            c_obj.overlap_ratio = len(overlap_with_existing) / max(1, len(chosen_set))
        else:
            # If no more candidates add new points, break or pick candidate closest to uncovered area
            break

    # 3. Compute Mesh Backhaul Links (communication range = 2 * cov_radius)
    mesh_comm_range_m = 2.0 * cov_radius * 0.95  # 95% margin for reliable RF link
    selected_objs = [candidates[i] for i in selected_indices]

    for i in range(len(selected_objs)):
        for j in range(i + 1, len(selected_objs)):
            d = haversine_distance_m(selected_objs[i].lat, selected_objs[i].lon,
                                     selected_objs[j].lat, selected_objs[j].lon)
            if d <= mesh_comm_range_m:
                selected_objs[i].mesh_linked_nodes.append(selected_objs[j].candidate_id)
                selected_objs[j].mesh_linked_nodes.append(selected_objs[i].candidate_id)

    # Check mesh connectivity (breadth-first search graph connectivity)
    is_mesh_connected = True
    if len(selected_objs) > 1:
        visited = {selected_objs[0].candidate_id}
        queue = [selected_objs[0].candidate_id]
        id_to_cand = {c.candidate_id: c for c in selected_objs}
        while queue:
            curr_id = queue.pop(0)
            for neighbor_id in id_to_cand[curr_id].mesh_linked_nodes:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(neighbor_id)
        is_mesh_connected = (len(visited) == len(selected_objs))

    # Calculate overall covered area and overlap percentage
    final_covered_ratio = len(currently_covered_pts) / total_demand_pts
    final_covered_m2 = final_covered_ratio * real_area_m2
    coverage_percent = min(100.0, round(final_covered_ratio * 100.0, 1))

    # Overlap = (sum of individual coverage - union of coverage) / max(1, sum of individual coverage)
    overlap_count = max(0, sum_individual_pts - len(currently_covered_pts))
    overlap_percent = round((overlap_count / max(1, sum_individual_pts)) * 100.0, 1) if sum_individual_pts > 0 else 0.0

    t1 = time.perf_counter()
    return OptimizationResult(
        total_area_m2=real_area_m2,
        covered_area_m2=final_covered_m2,
        coverage_percent=coverage_percent,
        overlap_percent=overlap_percent,
        candidates=candidates,
        selected_candidates=selected_objs,
        mesh_connectivity_ok=is_mesh_connected,
        execution_time_ms=(t1 - t0) * 1000.0
    )


def generate_deployment_mission(
    selected_candidates: List[CandidateSite],
    home_lat: float = 37.7749,
    home_lon: float = -122.4194,
    cruise_alt_m: float = 25.0,
    loiter_drop_sec: float = 5.0
) -> List[Dict[str, Any]]:
    """Generates an automated multi-waypoint flight mission from home -> candidate drop stations -> RTL.

    Uses a nearest-neighbor TSP heuristic to sequence drop locations with minimal flight distance.
    Returns list of mission item dictionaries compatible with Phase 4 MissionPlanner.
    """
    if not selected_candidates:
        return []

    # Nearest Neighbor TSP sequence
    unvisited = list(selected_candidates)
    ordered: List[CandidateSite] = []
    curr_lat, curr_lon = home_lat, home_lon

    while unvisited:
        best_idx = 0
        best_dist = float("inf")
        for idx, cand in enumerate(unvisited):
            d = haversine_distance_m(curr_lat, curr_lon, cand.lat, cand.lon)
            if d < best_dist:
                best_dist = d
                best_idx = idx
        chosen = unvisited.pop(best_idx)
        ordered.append(chosen)
        curr_lat, curr_lon = chosen.lat, chosen.lon

    items: List[Dict[str, Any]] = []
    seq = 0

    # 1. Home / Takeoff
    items.append({
        "seq": seq,
        "command": "TAKEOFF",
        "lat": round(home_lat, 7),
        "lon": round(home_lon, 7),
        "alt": round(cruise_alt_m, 1),
        "param1": 0.0,
        "param2": 0.0,
        "param3": 0.0,
        "param4": 0.0,
        "frame": 3,
        "autocontinue": 1,
    })
    seq += 1

    # 2. Sequential Drop Stations
    for cand in ordered:
        # Waypoint to station
        items.append({
            "seq": seq,
            "command": "WAYPOINT",
            "lat": round(cand.lat, 7),
            "lon": round(cand.lon, 7),
            "alt": round(cand.alt if cand.alt > 0 else cruise_alt_m, 1),
            "param1": round(loiter_drop_sec, 1),  # Hold time in seconds
            "param2": cand.coverage_radius_m,     # Target zone radius
            "param3": 0.0,
            "param4": 0.0,
            "frame": 3,
            "autocontinue": 1,
        })
        seq += 1

    # 3. Return to Launch (RTL)
    items.append({
        "seq": seq,
        "command": "RTL",
        "lat": round(home_lat, 7),
        "lon": round(home_lon, 7),
        "alt": round(cruise_alt_m, 1),
        "param1": 0.0,
        "param2": 0.0,
        "param3": 0.0,
        "param4": 0.0,
        "frame": 3,
        "autocontinue": 1,
    })

    return items
