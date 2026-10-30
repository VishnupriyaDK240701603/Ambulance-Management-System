"""Road incidents: Roadblocks, Congestion, Accidents."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IncidentType(str, Enum):
    ROADBLOCK = "ROADBLOCK"       # Fully closed edge (impassable)
    CONGESTION = "CONGESTION"     # High delay / low speed edge
    ACCIDENT = "ACCIDENT"         # Severe delay or partial block

@dataclass
class RoadIncident:
    id: str
    incident_type: IncidentType
    edge_id: str
    position: tuple[float, float, float]
    speed_factor: float = 0.2     # Factor multiplying normal speed (0.0 = blocked)
    delay_penalty_sec: float = 60.0
    is_closed: bool = False
    police_requested: bool = False
    assigned_police_id: str | None = None
    created_at: float = 0.0
    cleared_at: float | None = None
    description: str = ""
