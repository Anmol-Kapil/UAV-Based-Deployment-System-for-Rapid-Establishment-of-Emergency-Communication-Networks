"""
Phase 5 — Pydantic request/response models for the FastAPI backend.

Kept separate from main.py so the API's data shapes are visible at a
glance, and so main.py itself stays focused on routing/orchestration.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class LatLon(BaseModel):
    lat: float
    lon: float


class NodeOut(BaseModel):
    id: str
    lat: float
    lon: float
    coverage_radius_m: float


class StatusResponse(BaseModel):
    status: str
    phase: int
    mission_state: str
    uav_connected: bool
    area_defined: bool
    last_analysis_available: bool


class AreaRequest(BaseModel):
    polygon: List[LatLon] = Field(..., min_length=3)


class AreaResponse(BaseModel):
    accepted: bool
    point_count: int
    polygon: List[LatLon]


class AnalyzeResponse(BaseModel):
    total_points: int
    covered_points: List[LatLon]
    gap_points: List[LatLon]
    coverage_percentage: float
    gap_percentage: float


class CandidateOut(BaseModel):
    lat: float
    lon: float
    cluster_size: int
    coverage_improvement_pct: float
    distance_to_home_m: float
    boundary_distance_m: float
    coverage_score: float
    distance_score: float
    suitability_score: float
    score: float


class CandidatesResponse(BaseModel):
    candidates: List[CandidateOut]
    top: List[CandidateOut]


class SelectTargetRequest(BaseModel):
    lat: float
    lon: float


class SelectTargetResponse(BaseModel):
    accepted: bool
    lat: float
    lon: float
    matched_candidate: bool


class MissionGenerateRequest(BaseModel):
    lat: float
    lon: float
    altitude_m: Optional[float] = None


class MissionOut(BaseModel):
    id: int
    created_at: str
    target_lat: float
    target_lon: float
    target_alt: float
    score: Optional[float]
    status: str


class DeploymentOut(BaseModel):
    id: int
    mission_id: Optional[int]
    node_id: Optional[str]
    lat: float
    lon: float
    timestamp: str
    status: str


class NotImplementedResponse(BaseModel):
    implemented: bool = False
    phase_required: int
    message: str
