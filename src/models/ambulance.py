"""Ambulance model and state representations."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AmbulanceClass(str, Enum):
    BLS = "BLS"  # Basic Life Support
    ALS = "ALS"  # Advanced Life Support
    CCT = "CCT"  # Critical Care Transport

class AmbulanceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    TRANSPORTING = "TRANSPORTING"
    UNAVAILABLE = "UNAVAILABLE"

class ControlMode(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    MANUAL = "MANUAL"

@dataclass
class Ambulance:
    id: str
    unit_class: AmbulanceClass
    position: tuple[float, float, float]  # (x, y, z) in world coords
    heading: float = 0.0                  # Heading in degrees
    status: AmbulanceStatus = AmbulanceStatus.AVAILABLE
    control_mode: ControlMode = ControlMode.AUTONOMOUS
    capabilities: list[str] = field(default_factory=list)
    speed_mps: float = 15.0
    current_speed: float = 0.0
    current_edge_id: str | None = None
    target_node_id: str | None = None
    assigned_emergency_id: str | None = None
    assigned_hospital_id: str | None = None
    active_route_id: str | None = None
    total_missions_completed: int = 0
    created_at: float = 0.0

    def is_eligible_for(self, required_capabilities: list[str]) -> tuple[bool, str]:
        """Check if ambulance has all required capabilities."""
        if self.status not in (AmbulanceStatus.AVAILABLE, AmbulanceStatus.ASSIGNED):
            return False, f"Ambulance {self.id} is {self.status.value}"
        missing = [cap for cap in required_capabilities if cap not in self.capabilities]
        if missing:
            return False, f"Missing required capabilities: {', '.join(missing)}"
        return True, "Eligible"
