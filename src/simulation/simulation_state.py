"""Authoritative Single Source of Truth for LifeLine Dispatch."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.models.ambulance import Ambulance
from src.models.decision_record import DecisionRecord
from src.models.emergency import EmergencyIncident
from src.models.hospital import Hospital
from src.models.police_unit import PoliceUnit
from src.models.road_incident import RoadIncident
from src.models.route import Route
from src.world.road_graph import RoadGraph


@dataclass
class SimulationState:
    """The central authoritative state container."""
    simulation_time: float = 0.0
    state_version: int = 1
    is_started: bool = False
    is_paused: bool = False
    deployment_limit: int = 8

    # Entities
    fleet: dict[str, Ambulance] = field(default_factory=dict)
    hospitals: dict[str, Hospital] = field(default_factory=dict)
    emergencies: dict[str, EmergencyIncident] = field(default_factory=dict)
    road_incidents: dict[str, RoadIncident] = field(default_factory=dict)
    police_units: dict[str, PoliceUnit] = field(default_factory=dict)
    active_routes: dict[str, Route] = field(default_factory=dict)
    decision_records: list[DecisionRecord] = field(default_factory=list)

    # Road Network
    road_graph: RoadGraph = field(default_factory=RoadGraph)

    # UI selection state
    selected_ambulance_id: str | None = None
    selected_hospital_id: str | None = None
    selected_incident_id: str | None = None
    selected_emergency_id: str | None = None

    def increment_version(self) -> int:
        self.state_version += 1
        return self.state_version

    @property
    def available_ambulances_count(self) -> int:
        from src.models.ambulance import AmbulanceStatus
        return sum(1 for a in self.fleet.values() if a.status == AmbulanceStatus.AVAILABLE)

    @property
    def active_emergencies_count(self) -> int:
        from src.models.emergency import IncidentStatus
        return sum(1 for e in self.emergencies.values() if e.status not in (IncidentStatus.COMPLETED, IncidentStatus.CANCELLED))

    @property
    def total_vacant_beds(self) -> int:
        return sum(h.vacant_beds for h in self.hospitals.values())

    @property
    def total_hospital_beds(self) -> int:
        return sum(h.total_beds for h in self.hospitals.values())

    @property
    def active_road_incidents_count(self) -> int:
        return sum(1 for inc in self.road_incidents.values() if inc.cleared_at is None)
