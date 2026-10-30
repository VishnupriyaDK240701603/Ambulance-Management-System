"""Emergency incident models and state transitions."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EmergencySeverity(str, Enum):
    LOW = "LOW"            # e.g., minor fractures, simple transport
    MEDIUM = "MEDIUM"      # e.g., acute illness, respiratory distress
    HIGH = "HIGH"          # e.g., cardiac arrest, major polytrauma
    CRITICAL = "CRITICAL"  # e.g., multi-organ failure, ICU transfer

class IncidentStatus(str, Enum):
    CREATED = "CREATED"
    WAITING_DISPATCH = "WAITING_DISPATCH"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    PATIENT_ONBOARD = "PATIENT_ONBOARD"
    TRANSPORTING = "TRANSPORTING"
    HOSPITAL_ARRIVAL = "HOSPITAL_ARRIVAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

# Valid state transitions
VALID_TRANSITIONS = {
    IncidentStatus.CREATED: {IncidentStatus.WAITING_DISPATCH, IncidentStatus.CANCELLED},
    IncidentStatus.WAITING_DISPATCH: {IncidentStatus.ASSIGNED, IncidentStatus.CANCELLED, IncidentStatus.FAILED},
    IncidentStatus.ASSIGNED: {IncidentStatus.EN_ROUTE, IncidentStatus.WAITING_DISPATCH, IncidentStatus.CANCELLED},
    IncidentStatus.EN_ROUTE: {IncidentStatus.ON_SCENE, IncidentStatus.WAITING_DISPATCH, IncidentStatus.CANCELLED},
    IncidentStatus.ON_SCENE: {IncidentStatus.PATIENT_ONBOARD, IncidentStatus.CANCELLED},
    IncidentStatus.PATIENT_ONBOARD: {IncidentStatus.TRANSPORTING, IncidentStatus.CANCELLED},
    IncidentStatus.TRANSPORTING: {IncidentStatus.HOSPITAL_ARRIVAL, IncidentStatus.CANCELLED},
    IncidentStatus.HOSPITAL_ARRIVAL: {IncidentStatus.COMPLETED},
    IncidentStatus.COMPLETED: set(),
    IncidentStatus.CANCELLED: set(),
    IncidentStatus.FAILED: {IncidentStatus.WAITING_DISPATCH},
}

@dataclass
class EmergencyIncident:
    id: str
    location: tuple[float, float, float]
    nearest_node_id: str
    severity: EmergencySeverity
    required_capabilities: list[str]
    title: str = "Medical Emergency"
    description: str = ""
    status: IncidentStatus = IncidentStatus.CREATED
    assigned_ambulance_id: str | None = None
    destination_hospital_id: str | None = None
    created_at: float = 0.0
    dispatched_at: float | None = None
    arrived_scene_at: float | None = None
    patient_onboard_at: float | None = None
    arrived_hospital_at: float | None = None
    completed_at: float | None = None
    decision_id: str | None = None
    _last_hosp_eval_time: float = -999.0

    def transition_to(self, new_status: IncidentStatus, sim_time: float) -> tuple[bool, str]:
        """Validate and apply state transition."""
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            return False, f"Illegal transition from {self.status.value} to {new_status.value}"
        
        self.status = new_status
        if new_status == IncidentStatus.ASSIGNED:
            self.dispatched_at = sim_time
        elif new_status == IncidentStatus.ON_SCENE:
            self.arrived_scene_at = sim_time
        elif new_status == IncidentStatus.PATIENT_ONBOARD:
            self.patient_onboard_at = sim_time
        elif new_status == IncidentStatus.HOSPITAL_ARRIVAL:
            self.arrived_hospital_at = sim_time
        elif new_status == IncidentStatus.COMPLETED:
            self.completed_at = sim_time
            
        return True, "Transition successful"
