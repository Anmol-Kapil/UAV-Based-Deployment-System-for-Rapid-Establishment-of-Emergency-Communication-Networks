"""Autonomous RF Survey Controller for Phase 12.

Provides:
- SurveyStatus enum (IDLE, READY, RUNNING, PAUSED, COMPLETED, STOPPED)
- SurveySample dataclass (index, lat, lon, altitude_m, rssi_dbm, timestamp, quality)
- SurveyMetrics dataclass (total_points, visited_points, progress_pct, current_rssi_dbm,
  coverage_pct, mean_rssi_dbm, min_rssi_dbm, max_rssi_dbm, elapsed_seconds)
- RfSurveyController QObject singleton:
  - Generates lawnmower survey flight patterns using LawnmowerSurveyGenerator.
  - Controls autonomous or supervised survey mission flight.
  - Dynamically calculates simulated RF RSSI at each survey waypoint using
    RfPropagationEngine calibrated against active deployed VirtualNodes.
  - Computes real-time progress, coverage percentage, and RSSI statistics
    matching Section 23 specification:
    Progress: 32 / 64
    Current RSSI: -62 dBm
    Coverage: 73%
"""

import math
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from PySide6.QtCore import QObject, Signal, QTimer

from gcs.state.app_state import app_state
from gcs.rf.rf_model import rf_engine, RfConfig
from gcs.rf.survey_generator import SurveyPlan, SurveyWaypoint, survey_generator
from gcs.deployment.virtual_node_manager import virtual_node_manager


class SurveyStatus(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


@dataclass
class SurveySample:
    """RF measurement sample collected at a survey waypoint."""
    index: int
    lat: float
    lon: float
    altitude_m: float = 20.0
    rssi_dbm: float = -62.0
    timestamp: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    quality: str = "GOOD"  # EXCELLENT, GOOD, WEAK, NO COVERAGE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "altitude_m": round(self.altitude_m, 1),
            "rssi_dbm": round(self.rssi_dbm, 1),
            "timestamp": self.timestamp,
            "quality": self.quality,
        }


@dataclass
class SurveyMetrics:
    """Real-time survey execution and RF coverage statistics."""
    total_points: int = 0
    visited_points: int = 0
    progress_pct: float = 0.0
    current_rssi_dbm: Optional[float] = None
    coverage_pct: float = 0.0
    mean_rssi_dbm: Optional[float] = None
    min_rssi_dbm: Optional[float] = None
    max_rssi_dbm: Optional[float] = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_points": self.total_points,
            "visited_points": self.visited_points,
            "progress_pct": round(self.progress_pct, 1),
            "current_rssi_dbm": round(self.current_rssi_dbm, 1) if self.current_rssi_dbm is not None else None,
            "coverage_pct": round(self.coverage_pct, 1),
            "mean_rssi_dbm": round(self.mean_rssi_dbm, 1) if self.mean_rssi_dbm is not None else None,
            "min_rssi_dbm": round(self.min_rssi_dbm, 1) if self.min_rssi_dbm is not None else None,
            "max_rssi_dbm": round(self.max_rssi_dbm, 1) if self.max_rssi_dbm is not None else None,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
        }


class RfSurveyController(QObject):
    """Singleton controller managing autonomous RF survey flights and data acquisition."""

    plan_generated = Signal(object)      # SurveyPlan
    state_changed = Signal(str)          # SurveyStatus
    progress_updated = Signal(object)    # SurveyMetrics
    sample_acquired = Signal(object)     # SurveySample
    survey_completed = Signal(object)    # SurveyMetrics
    survey_cleared = Signal()

    def __init__(self):
        super().__init__()
        self.status = SurveyStatus.IDLE
        self.plan: Optional[SurveyPlan] = None
        self.samples: List[SurveySample] = []
        self.current_waypoint_idx = 0
        self.metrics = SurveyMetrics()
        self.start_timestamp: Optional[float] = None

        # Simulation step timer for autonomous survey simulation / stepping
        self._sim_timer = QTimer()
        self._sim_timer.setInterval(400)  # Advance waypoint every 400ms during simulated survey
        self._sim_timer.timeout.connect(self._on_sim_step)

        # Hook into live UAV telemetry to advance based on proximity if connected
        app_state.telemetry_updated.connect(self._on_telemetry_updated)

    def generate_survey(
        self,
        altitude_m: float = 20.0,
        line_spacing_m: float = 20.0,
        target_points: Optional[int] = 64,
        target_area_km2: Optional[float] = 1.2,
    ) -> SurveyPlan:
        """Generate a lawnmower flight pattern matching operator parameters and boundaries."""
        self.stop_survey()

        # Determine center and polygon
        polygon = app_state.disaster_polygon if (app_state.disaster_polygon and len(app_state.disaster_polygon) >= 3) else None

        center_lat = 37.7749
        center_lon = -122.4194
        u_lat = app_state.telemetry.get("lat")
        u_lon = app_state.telemetry.get("lon")
        if isinstance(u_lat, (int, float)) and isinstance(u_lon, (int, float)):
            center_lat = float(u_lat)
            center_lon = float(u_lon)
        elif hasattr(app_state, "home_lat") and app_state.home_lat:
            center_lat = app_state.home_lat
            center_lon = app_state.home_lon
        elif polygon:
            center_lat = sum(p[0] for p in polygon) / len(polygon)
            center_lon = sum(p[1] for p in polygon) / len(polygon)

        # Generate plan
        self.plan = survey_generator.generate(
            polygon=polygon,
            center_lat=center_lat,
            center_lon=center_lon,
            altitude_m=altitude_m,
            line_spacing_m=line_spacing_m,
            target_points=target_points,
            target_area_km2=target_area_km2,
        )

        self.samples.clear()
        self.current_waypoint_idx = 0
        self.status = SurveyStatus.READY
        self.metrics = SurveyMetrics(
            total_points=len(self.plan.waypoints),
            visited_points=0,
            progress_pct=0.0,
            current_rssi_dbm=None,
            coverage_pct=0.0,
        )

        app_state.survey_plan = self.plan
        app_state.survey_samples = self.samples
        app_state.survey_status = self.status.value
        app_state.survey_metrics = self.metrics

        self.plan_generated.emit(self.plan)
        self.state_changed.emit(self.status.value)
        self.progress_updated.emit(self.metrics)

        app_state.set_command_feedback(
            f"RF SURVEY GENERATED: {len(self.plan.waypoints)} pts, {self.plan.area_km2:.2f} km², Spacing {self.plan.line_spacing_m:.0f}m"
        )
        return self.plan

    def start_survey(self) -> bool:
        """Start or resume survey mission execution."""
        if not self.plan or not self.plan.waypoints:
            # Generate default plan if none exists
            self.generate_survey()

        self.status = SurveyStatus.RUNNING
        app_state.survey_status = self.status.value
        if not self.start_timestamp:
            self.start_timestamp = time.time()

        self.state_changed.emit(self.status.value)
        self._sim_timer.start()

        app_state.set_command_feedback(f"RF SURVEY STARTED: Pattern {self.plan.pattern_type} ({len(self.plan.waypoints)} waypoints)")
        return True

    def pause_survey(self):
        """Pause active survey."""
        if self.status == SurveyStatus.RUNNING:
            self.status = SurveyStatus.PAUSED
            app_state.survey_status = self.status.value
            self._sim_timer.stop()
            self.state_changed.emit(self.status.value)
            app_state.set_command_feedback("RF SURVEY PAUSED")

    def resume_survey(self):
        """Resume paused survey."""
        if self.status == SurveyStatus.PAUSED:
            self.status = SurveyStatus.RUNNING
            app_state.survey_status = self.status.value
            self._sim_timer.start()
            self.state_changed.emit(self.status.value)
            app_state.set_command_feedback("RF SURVEY RESUMED")

    def stop_survey(self):
        """Stop active survey."""
        if self.status in (SurveyStatus.RUNNING, SurveyStatus.PAUSED):
            self.status = SurveyStatus.STOPPED
            app_state.survey_status = self.status.value
            self._sim_timer.stop()
            self.state_changed.emit(self.status.value)
            app_state.set_command_feedback("RF SURVEY STOPPED")

    def clear_survey(self):
        """Reset survey state and clear waypoints."""
        self._sim_timer.stop()
        self.status = SurveyStatus.IDLE
        self.plan = None
        self.samples.clear()
        self.current_waypoint_idx = 0
        self.metrics = SurveyMetrics()
        self.start_timestamp = None

        app_state.survey_plan = None
        app_state.survey_samples = []
        app_state.survey_status = self.status.value
        app_state.survey_metrics = self.metrics

        self.survey_cleared.emit()
        self.state_changed.emit(self.status.value)
        self.progress_updated.emit(self.metrics)
        app_state.set_command_feedback("RF SURVEY CLEARED")

    def step_progress(self, target_idx: Optional[int] = None) -> Optional[SurveySample]:
        """Advance survey by sampling the current/specified waypoint."""
        if not self.plan or not self.plan.waypoints:
            return None

        idx = target_idx if target_idx is not None else self.current_waypoint_idx
        if idx >= len(self.plan.waypoints):
            # All points completed
            self.status = SurveyStatus.COMPLETED
            app_state.survey_status = self.status.value
            self._sim_timer.stop()
            self.state_changed.emit(self.status.value)
            self.survey_completed.emit(self.metrics)
            app_state.set_command_feedback(
                f"RF SURVEY COMPLETED: {len(self.samples)} points sampled, Coverage: {self.metrics.coverage_pct:.1f}%"
            )
            return None

        wp = self.plan.waypoints[idx]
        wp.visited = True

        # Calculate simulated RSSI at this waypoint
        rssi = self._calculate_simulated_rssi_at(wp.lat, wp.lon, wp.altitude_m)
        wp.rssi_dbm = rssi
        wp.timestamp = time.strftime("%H:%M:%S")

        # Determine signal quality
        threshold = self._get_threshold()
        if rssi >= -65.0:
            quality = "EXCELLENT"
        elif rssi >= threshold:
            quality = "GOOD"
        elif rssi >= threshold - 10.0:
            quality = "WEAK"
        else:
            quality = "NO COVERAGE"

        sample = SurveySample(
            index=wp.index,
            lat=wp.lat,
            lon=wp.lon,
            altitude_m=wp.altitude_m,
            rssi_dbm=rssi,
            timestamp=wp.timestamp,
            quality=quality,
        )
        self.samples.append(sample)
        app_state.survey_samples = self.samples

        self.current_waypoint_idx = idx + 1
        self._recalculate_metrics(sample.rssi_dbm)

        self.sample_acquired.emit(sample)
        self.progress_updated.emit(self.metrics)
        return sample

    def _get_threshold(self) -> float:
        """Extract receiver sensitivity threshold from app_state config."""
        cfg = app_state.rf_config
        if isinstance(cfg, dict):
            return float(cfg.get("rx_sensitivity_dbm", -75.0))
        elif hasattr(cfg, "rx_sensitivity_dbm"):
            return float(cfg.rx_sensitivity_dbm)
        return -75.0

    def _calculate_simulated_rssi_at(self, lat: float, lon: float, alt_m: float) -> float:
        """Calculate simulated RSSI at given 3D coordinates based on active virtual nodes."""
        nodes = virtual_node_manager.get_all_nodes()
        if isinstance(app_state.rf_config, dict):
            cfg = RfConfig.from_dict(app_state.rf_config)
        else:
            cfg = app_state.rf_config or RfConfig()

        if nodes:
            best_rssi = -120.0
            for node in nodes:
                # 3D distance between waypoint and node
                d_lat_m = (lat - node.lat) * 111139.0
                m_lon = 111139.0 * math.cos(math.radians((lat + node.lat) / 2.0))
                d_lon_m = (lon - node.lon) * m_lon
                d_alt_m = alt_m - node.altitude_m
                dist_3d = math.sqrt(d_lat_m**2 + d_lon_m**2 + d_alt_m**2)

                rssi_node = rf_engine.calculate_rssi(
                    distance_m=dist_3d,
                    config=cfg,
                    custom_tx_pwr_dbm=node.tx_power_dbm,
                    with_shadowing=False,
                )
                if rssi_node > best_rssi:
                    best_rssi = rssi_node
            return round(best_rssi, 1)
        else:
            # If no virtual nodes are deployed yet, compute relative to center coordinates
            # with standard baseline matching Section 23 specification (~ -62 dBm nominal)
            center_lat = self.plan.bounding_box[0] + (self.plan.bounding_box[2] - self.plan.bounding_box[0]) / 2.0
            center_lon = self.plan.bounding_box[1] + (self.plan.bounding_box[3] - self.plan.bounding_box[1]) / 2.0
            d_lat_m = (lat - center_lat) * 111139.0
            d_lon_m = (lon - center_lon) * 111139.0 * math.cos(math.radians(center_lat))
            dist_center = math.sqrt(d_lat_m**2 + d_lon_m**2 + alt_m**2)

            rssi_nom = rf_engine.calculate_rssi(
                distance_m=max(1.0, dist_center),
                config=cfg,
                with_shadowing=False,
            )
            return round(rssi_nom, 1)

    def _recalculate_metrics(self, latest_rssi: float):
        """Update live running metrics matching Section 23 specification."""
        if not self.plan or not self.plan.waypoints:
            return

        total = len(self.plan.waypoints)
        visited = len(self.samples)
        progress = (visited / total * 100.0) if total > 0 else 0.0

        threshold = self._get_threshold()
        covered_pts = sum(1 for s in self.samples if s.rssi_dbm >= threshold)
        coverage_pct = (covered_pts / visited * 100.0) if visited > 0 else 0.0

        rssi_vals = [s.rssi_dbm for s in self.samples]
        mean_rssi = sum(rssi_vals) / len(rssi_vals) if rssi_vals else None
        min_rssi = min(rssi_vals) if rssi_vals else None
        max_rssi = max(rssi_vals) if rssi_vals else None

        elapsed = (time.time() - self.start_timestamp) if self.start_timestamp else 0.0

        self.metrics = SurveyMetrics(
            total_points=total,
            visited_points=visited,
            progress_pct=progress,
            current_rssi_dbm=latest_rssi,
            coverage_pct=coverage_pct,
            mean_rssi_dbm=mean_rssi,
            min_rssi_dbm=min_rssi,
            max_rssi_dbm=max_rssi,
            elapsed_seconds=elapsed,
        )
        app_state.survey_metrics = self.metrics

    def _on_sim_step(self):
        """Advance survey simulated step on timer tick."""
        if self.status == SurveyStatus.RUNNING:
            self.step_progress()

    def _on_telemetry_updated(self):
        """Proximity-based survey progression when connected to live SITL/Gazebo."""
        if self.status != SurveyStatus.RUNNING or not self.plan:
            return

        u_lat = app_state.telemetry.get("lat")
        u_lon = app_state.telemetry.get("lon")
        if not isinstance(u_lat, (int, float)) or not isinstance(u_lon, (int, float)):
            return

        if self.current_waypoint_idx < len(self.plan.waypoints):
            target_wp = self.plan.waypoints[self.current_waypoint_idx]
            d_lat_m = (u_lat - target_wp.lat) * 111139.0
            m_lon = 111139.0 * math.cos(math.radians(target_wp.lat))
            d_lon_m = (u_lon - target_wp.lon) * m_lon
            dist_2d = math.sqrt(d_lat_m**2 + d_lon_m**2)

            # Within 15m acceptance radius -> sample and advance
            if dist_2d <= 15.0:
                self.step_progress()


rf_survey_controller = RfSurveyController()
