"""
Adaptive UAV Deployment Algorithm Engine
Phase 15: Ground Control Station (GCS)

Implements:
- Multi-criteria gap priority scoring (area weight, RSSI weight, proximity weight)
- Ordered Staged Deployment Plan construction from Phase 14 GapZone objects
- Stage lifecycle management: PENDING -> ACTIVE -> COMPLETED / SKIPPED
- Flight time estimation using Haversine distance + cruise speed assumption
- GeoJSON export for tactical map overlay rendering
"""

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Priority & Status Constants
# ---------------------------------------------------------------------------

class DeploymentPriority:
    """Priority tiers for adaptive deployment staging."""
    CRITICAL = "CRITICAL"   # Gap area > 0.15 km2 or severity CRITICAL
    HIGH     = "HIGH"       # Gap area > 0.05 km2 or severity HIGH
    MODERATE = "MODERATE"   # All other detected gaps

    # Numeric ordering for sort key (lower = higher priority)
    ORDER = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}


class StageStatus:
    """Lifecycle states for a single deployment stage."""
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    COMPLETED = "COMPLETED"
    SKIPPED   = "SKIPPED"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DeploymentStage:
    """A single UAV relay deployment mission within an adaptive plan."""
    stage_id: str                          # e.g. S01, S02
    gap_id: str                            # links back to GapZone.gap_id
    target_lat: float
    target_lon: float
    target_alt_m: float = 15.0
    priority: str = DeploymentPriority.MODERATE
    gap_area_km2: float = 0.0
    gap_severity: str = "MODERATE"
    mean_rssi_dbm: float = -90.0
    estimated_flight_time_s: float = 60.0
    status: str = StageStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "gap_id": self.gap_id,
            "target": {
                "lat": round(self.target_lat, 6),
                "lon": round(self.target_lon, 6),
                "alt_m": round(self.target_alt_m, 1),
            },
            "priority": self.priority,
            "gap_area_km2": round(self.gap_area_km2, 3),
            "gap_severity": self.gap_severity,
            "mean_rssi_dbm": round(self.mean_rssi_dbm, 1),
            "estimated_flight_time_s": round(self.estimated_flight_time_s, 0),
            "status": self.status,
        }

    def to_geojson_feature(self, stage_index: int) -> Dict[str, Any]:
        """GeoJSON Point feature for map rendering."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.target_lon, self.target_lat],
            },
            "properties": {
                **self.to_dict(),
                "stage_index": stage_index,
            },
        }


@dataclass
class AdaptiveDeploymentPlan:
    """Ordered multi-stage adaptive relay deployment plan."""
    plan_id: str
    total_stages: int
    stages: List[DeploymentStage] = field(default_factory=list)
    coverage_before_pct: float = 0.0
    estimated_coverage_after_pct: float = 0.0
    created_at: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))

    @property
    def active_stage(self) -> Optional[DeploymentStage]:
        """Return the currently ACTIVE stage, or None."""
        for s in self.stages:
            if s.status == StageStatus.ACTIVE:
                return s
        return None

    @property
    def next_pending_stage(self) -> Optional[DeploymentStage]:
        """Return the first PENDING stage, or None."""
        for s in self.stages:
            if s.status == StageStatus.PENDING:
                return s
        return None

    @property
    def active_stage_index(self) -> int:
        """1-based index of the ACTIVE stage, 0 if none active."""
        for i, s in enumerate(self.stages, 1):
            if s.status == StageStatus.ACTIVE:
                return i
        return 0

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.stages if s.status == StageStatus.COMPLETED)

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
            for s in self.stages
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "total_stages": self.total_stages,
            "coverage_before_pct": round(self.coverage_before_pct, 1),
            "estimated_coverage_after_pct": round(self.estimated_coverage_after_pct, 1),
            "created_at": self.created_at,
            "stages": [s.to_dict() for s in self.stages],
        }

    def to_geojson(self) -> Dict[str, Any]:
        """GeoJSON FeatureCollection for map overlay rendering."""
        features = [s.to_geojson_feature(i) for i, s in enumerate(self.stages, 1)]

        # Add stage-order route polyline
        if len(self.stages) >= 2:
            coords = [[s.target_lon, s.target_lat] for s in self.stages]
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"type": "route", "plan_id": self.plan_id},
            })

        return {
            "type": "FeatureCollection",
            "properties": self.to_dict(),
            "features": features,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AdaptiveDeploymentEngine:
    """
    Multi-criteria adaptive deployment planner.

    Priority scoring formula (transparent, deterministic -- no ML):

        priority_score = 0.5 * area_norm + 0.3 * rssi_norm + 0.2 * proximity_norm

    Where:
        area_norm      = gap_area_km2 / max_area          [larger gap = more urgent]
        rssi_norm      = (threshold - rssi) / rssi_range  [weaker signal = more urgent]
        proximity_norm = 1 - dist / max_dist              [closer = higher deployability]
    """

    CRUISE_SPEED_MS = 5.0    # m/s assumed cruise speed for flight time estimation
    HOVER_BUFFER_S  = 20.0   # seconds for station-keeping + payload drop
    RSSI_THRESHOLD  = -85.0  # dBm dead zone floor
    RSSI_RANGE      = 30.0   # dBm range from threshold to strongest dead signal

    # ------------------------------------------------------------------

    @classmethod
    def _haversine_m(cls, lat1: float, lon1: float,
                     lat2: float, lon2: float) -> float:
        """Haversine great-circle distance in metres."""
        R = 6_371_000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = phi2 - phi1
        dlam = math.radians(lon2 - lon1)
        a = (math.sin(dphi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @classmethod
    def _classify_priority(cls, gap_area_km2: float, gap_severity: str) -> str:
        """Assign DeploymentPriority tier from GapZone properties."""
        if gap_severity == "CRITICAL" or gap_area_km2 > 0.15:
            return DeploymentPriority.CRITICAL
        if gap_severity == "HIGH" or gap_area_km2 > 0.05:
            return DeploymentPriority.HIGH
        return DeploymentPriority.MODERATE

    @classmethod
    def _estimate_flight_time(cls, home_lat: float, home_lon: float,
                              target_lat: float, target_lon: float) -> float:
        """Round-trip flight time estimate in seconds."""
        dist_m = cls._haversine_m(home_lat, home_lon, target_lat, target_lon)
        one_way_s = dist_m / cls.CRUISE_SPEED_MS
        return round(2 * one_way_s + cls.HOVER_BUFFER_S, 0)

    # ------------------------------------------------------------------

    @classmethod
    def build_plan(
        cls,
        gaps: list,
        home_lat: float = 37.7749,
        home_lon: float = -122.4194,
        coverage_before_pct: float = 0.0,
        total_area_km2: float = 1.2,
    ) -> "AdaptiveDeploymentPlan":
        """
        Construct a prioritised AdaptiveDeploymentPlan from detected GapZones.

        Args:
            gaps:                List of GapZone objects (from CoverageGapAnalyzer).
            home_lat/lon:        UAV launch point for distance calculations.
            coverage_before_pct: Current coverage % (from CoverageAnalysisReport).
            total_area_km2:      Total operational area for coverage improvement estimate.

        Returns:
            AdaptiveDeploymentPlan sorted CRITICAL > HIGH > MODERATE,
            then by priority_score descending within each tier.
        """
        plan_id = "PLAN_" + time.strftime("%H%M%S")

        if not gaps:
            return AdaptiveDeploymentPlan(
                plan_id=plan_id,
                total_stages=0,
                coverage_before_pct=coverage_before_pct,
                estimated_coverage_after_pct=coverage_before_pct,
            )

        # 1. Extract raw metrics
        areas = [getattr(g, "area_sq_km", 0.0) for g in gaps]
        rssis = [getattr(g, "mean_rssi_dbm", -90.0) for g in gaps]
        dists = [
            cls._haversine_m(
                home_lat, home_lon,
                getattr(g, "centroid_lat", home_lat),
                getattr(g, "centroid_lon", home_lon),
            )
            for g in gaps
        ]

        max_area = max(areas) if areas else 1.0
        max_dist = max(dists) if dists else 1.0

        # 2. Score each gap
        scored = []
        for gap, area, rssi, dist in zip(gaps, areas, rssis, dists):
            area_norm  = area / max(max_area, 1e-9)
            rssi_norm  = min(1.0, max(0.0, (cls.RSSI_THRESHOLD - rssi) / cls.RSSI_RANGE))
            prox_norm  = 1.0 - (dist / max(max_dist, 1e-9))
            score      = 0.5 * area_norm + 0.3 * rssi_norm + 0.2 * prox_norm

            # Support both 'gap_severity' and 'severity' attribute names
            severity = getattr(gap, "gap_severity",
                               getattr(gap, "severity", "MODERATE"))
            priority = cls._classify_priority(area, severity)
            scored.append((gap, score, priority, area, rssi, dist, severity))

        # 3. Sort: priority tier first, then score descending within tier
        scored.sort(key=lambda x: (DeploymentPriority.ORDER.get(x[2], 2), -x[1]))

        # 4. Build DeploymentStage objects
        stages: List[DeploymentStage] = []
        total_gap_area = 0.0
        for idx, (gap, score, priority, area, rssi, dist, severity) in enumerate(scored, 1):
            t_lat = getattr(gap, "recommended_relay_lat",
                            getattr(gap, "centroid_lat", home_lat))
            t_lon = getattr(gap, "recommended_relay_lon",
                            getattr(gap, "centroid_lon", home_lon))
            flight_t = cls._estimate_flight_time(home_lat, home_lon, t_lat, t_lon)

            stages.append(DeploymentStage(
                stage_id=f"S{idx:02d}",
                gap_id=getattr(gap, "gap_id", f"GAP_{idx:03d}"),
                target_lat=t_lat,
                target_lon=t_lon,
                target_alt_m=15.0,
                priority=priority,
                gap_area_km2=area,
                gap_severity=severity,
                mean_rssi_dbm=rssi,
                estimated_flight_time_s=flight_t,
                status=StageStatus.PENDING,
            ))
            total_gap_area += area

        # 5. Activate first stage immediately
        if stages:
            stages[0].status = StageStatus.ACTIVE

        # 6. Estimate post-deployment coverage improvement
        gap_fraction = min(1.0, total_gap_area / max(total_area_km2, 1e-9))
        uncovered_pct = 100.0 - coverage_before_pct
        improvement_pct = uncovered_pct * gap_fraction
        estimated_after = min(100.0, coverage_before_pct + improvement_pct)

        return AdaptiveDeploymentPlan(
            plan_id=plan_id,
            total_stages=len(stages),
            stages=stages,
            coverage_before_pct=coverage_before_pct,
            estimated_coverage_after_pct=round(estimated_after, 1),
        )

    @classmethod
    def advance_stage(cls, plan: "AdaptiveDeploymentPlan") -> Optional[DeploymentStage]:
        """
        Mark ACTIVE stage as COMPLETED.
        Promote next PENDING stage to ACTIVE.
        Returns newly activated stage, or None if plan is complete.
        """
        for i, s in enumerate(plan.stages):
            if s.status == StageStatus.ACTIVE:
                s.status = StageStatus.COMPLETED
                for j in range(i + 1, len(plan.stages)):
                    if plan.stages[j].status == StageStatus.PENDING:
                        plan.stages[j].status = StageStatus.ACTIVE
                        return plan.stages[j]
                return None
        return None

    @classmethod
    def skip_stage(cls, plan: "AdaptiveDeploymentPlan") -> Optional[DeploymentStage]:
        """
        Mark ACTIVE stage as SKIPPED.
        Promote next PENDING stage to ACTIVE.
        Returns newly activated stage, or None if plan is complete.
        """
        for i, s in enumerate(plan.stages):
            if s.status == StageStatus.ACTIVE:
                s.status = StageStatus.SKIPPED
                for j in range(i + 1, len(plan.stages)):
                    if plan.stages[j].status == StageStatus.PENDING:
                        plan.stages[j].status = StageStatus.ACTIVE
                        return plan.stages[j]
                return None
        return None

    @classmethod
    def reset_plan(cls, plan: "AdaptiveDeploymentPlan") -> None:
        """Reset all stages to PENDING, reactivate stage 0."""
        for s in plan.stages:
            s.status = StageStatus.PENDING
        if plan.stages:
            plan.stages[0].status = StageStatus.ACTIVE


# Singleton instance
adaptive_deployment_engine = AdaptiveDeploymentEngine()
