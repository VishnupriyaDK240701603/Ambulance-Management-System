"""Traffic Police unit model and clearance lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PoliceStatus(str, Enum):
    IDLE = "IDLE"
    REQUESTED = "REQUESTED"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    CLEARING = "CLEARING"
    CLEARED = "CLEARED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"

@dataclass
class PoliceUnit:
    id: str
    position: tuple[float, float, float]
    heading: float = 0.0
    status: PoliceStatus = PoliceStatus.IDLE
    assigned_incident_id: str | None = None
    target_node_id: str | None = None
    speed_mps: float = 18.0
    current_speed: float = 0.0
    clearance_progress: float = 0.0
    clearance_duration: float = 8.0
    current_edge_id: str | None = None
    active_route_id: str | None = None
    notification_received: bool = False
    notification_time: float = 0.0
    response_deadline_sec: float = 20.0
    rejection_reason: str | None = None
    is_player_controlled: bool = False
