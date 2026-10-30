"""Authoritative commands for state mutations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.models.ambulance import Ambulance, AmbulanceClass, AmbulanceStatus, ControlMode
from src.models.emergency import EmergencyIncident, EmergencySeverity, IncidentStatus
from src.models.police_unit import PoliceStatus
from src.models.road_incident import IncidentType, RoadIncident
from src.simulation.events import EventType, SimulationEvent
from src.simulation.simulation_state import SimulationState
from src.simulation.validators import ScenarioValidator


class Command(ABC):
    @abstractmethod
    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        """Execute command atomically on state. Returns (success, message, events_generated)."""

@dataclass
class DeployAmbulanceCommand(Command):
    unit_id: str
    unit_class: AmbulanceClass
    position: tuple[float, float, float]
    heading: float = 0.0
    capabilities: list[str] | None = None
    speed_mps: float = 15.0

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        val = ScenarioValidator.validate_ambulance_deployment(
            unit_id=self.unit_id,
            unit_class=self.unit_class,
            position=self.position,
            current_fleet=state.fleet,
            deployment_limit=state.deployment_limit,
            road_graph=state.road_graph
        )
        if not val.is_valid:
            return False, val.reason, []

        ambulance = Ambulance(
            id=self.unit_id,
            unit_class=self.unit_class,
            position=self.position,
            heading=self.heading,
            capabilities=self.capabilities or [],
            speed_mps=self.speed_mps,
            created_at=state.simulation_time
        )
        state.fleet[self.unit_id] = ambulance
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.AMBULANCE_DEPLOYED,
            timestamp=state.simulation_time,
            entity_id=self.unit_id,
            payload={"unit_class": self.unit_class.value, "position": self.position}
        )
        return True, f"Deployed {self.unit_class.value} ambulance [{self.unit_id}] successfully.", [event]

@dataclass
class RemoveAmbulanceCommand(Command):
    unit_id: str

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.unit_id not in state.fleet:
            return False, f"Ambulance '{self.unit_id}' not found in fleet.", []
        amb = state.fleet[self.unit_id]
        if amb.status in (AmbulanceStatus.EN_ROUTE, AmbulanceStatus.ON_SCENE, AmbulanceStatus.TRANSPORTING):
            return False, f"Cannot remove ambulance {self.unit_id} while actively engaged in mission ({amb.status.value}).", []

        del state.fleet[self.unit_id]
        if state.selected_ambulance_id == self.unit_id:
            state.selected_ambulance_id = None
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.AMBULANCE_REMOVED,
            timestamp=state.simulation_time,
            entity_id=self.unit_id
        )
        return True, f"Recalled ambulance [{self.unit_id}].", [event]

@dataclass
class SetControlModeCommand(Command):
    unit_id: str
    control_mode: ControlMode

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.unit_id not in state.fleet:
            return False, f"Ambulance '{self.unit_id}' not found.", []
        amb = state.fleet[self.unit_id]
        amb.control_mode = self.control_mode
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.AMBULANCE_CONTROL_MODE_CHANGED,
            timestamp=state.simulation_time,
            entity_id=self.unit_id,
            payload={"control_mode": self.control_mode.value}
        )
        return True, f"Ambulance [{self.unit_id}] switched to {self.control_mode.value} control.", [event]

@dataclass
class CreateEmergencyCommand(Command):
    emergency_id: str
    location: tuple[float, float, float]
    severity: EmergencySeverity
    required_capabilities: list[str]
    title: str = "Medical Emergency"
    description: str = ""

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.emergency_id in state.emergencies:
            return False, f"Emergency incident '{self.emergency_id}' already exists.", []

        # Find nearest road node
        nearest_node = state.road_graph.find_nearest_node(self.location[0], self.location[1])
        nearest_id = nearest_node.id if nearest_node else "N_0_0"

        incident = EmergencyIncident(
            id=self.emergency_id,
            location=self.location,
            nearest_node_id=nearest_id,
            severity=self.severity,
            required_capabilities=self.required_capabilities,
            title=self.title,
            description=self.description,
            status=IncidentStatus.WAITING_DISPATCH,
            created_at=state.simulation_time
        )
        state.emergencies[self.emergency_id] = incident
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.EMERGENCY_CREATED,
            timestamp=state.simulation_time,
            entity_id=self.emergency_id,
            payload={"severity": self.severity.value, "location": self.location}
        )
        return True, f"Reported emergency incident [{self.emergency_id}] - {self.title}.", [event]

@dataclass
class UpdateHospitalBedsCommand(Command):
    hospital_id: str
    new_occupied: int
    new_vacant: int

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.hospital_id not in state.hospitals:
            return False, f"Hospital '{self.hospital_id}' not found.", []
        hosp = state.hospitals[self.hospital_id]
        ok, reason = hosp.update_bed_counts(self.new_occupied, self.new_vacant)
        if not ok:
            return False, reason, []
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.HOSPITAL_BEDS_UPDATED,
            timestamp=state.simulation_time,
            entity_id=self.hospital_id,
            payload={"occupied": self.new_occupied, "vacant": self.new_vacant}
        )
        return True, f"Hospital {hosp.name} updated: Occupied={self.new_occupied}, Vacant={self.new_vacant}.", [event]

@dataclass
class PlaceRoadIncidentCommand(Command):
    incident_id: str
    incident_type: IncidentType
    edge_id: str
    position: tuple[float, float, float]
    speed_factor: float = 0.25
    delay_penalty_sec: float = 60.0
    description: str = ""

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.edge_id not in state.road_graph.edges:
            return False, f"Road edge '{self.edge_id}' does not exist.", []

        is_closed = (self.incident_type == IncidentType.ROADBLOCK)
        if is_closed:
            state.road_graph.set_edge_closed(self.edge_id, True, incident_id=self.incident_id)
        else:
            state.road_graph.set_edge_congestion(self.edge_id, self.speed_factor, self.delay_penalty_sec, incident_id=self.incident_id)

        inc = RoadIncident(
            id=self.incident_id,
            incident_type=self.incident_type,
            edge_id=self.edge_id,
            position=self.position,
            speed_factor=0.0 if is_closed else self.speed_factor,
            delay_penalty_sec=self.delay_penalty_sec,
            is_closed=is_closed,
            created_at=state.simulation_time,
            description=self.description or f"{self.incident_type.value} on {self.edge_id}"
        )
        state.road_incidents[self.incident_id] = inc

        # Proactively reroute any active ambulances whose remaining route passes through this obstructed edge
        from src.algorithms.traffic_recovery import calculate_dynamic_reroute
        rerouted_units = []

        rev_edge_id = state.road_graph.get_reverse_edge_id(self.edge_id)
        affected_edges = {self.edge_id}
        if rev_edge_id:
            affected_edges.add(rev_edge_id)

        for amb_id, route in list(state.active_routes.items()):
            amb = state.fleet.get(amb_id)
            if not amb or not route.waypoints:
                continue

            # Check if any remaining segment uses the newly obstructed road
            remaining_segments = route.segments[route.current_segment_index:]
            uses_blocked_road = any(s.edge_id in affected_edges for s in remaining_segments)
            if uses_blocked_road:
                new_route = calculate_dynamic_reroute(amb, route, state)
                if new_route:
                    state.active_routes[amb.id] = new_route
                    amb.active_route_id = new_route.id
                    rerouted_units.append(amb.id)

        # Automatically alert Traffic Police immediately without expecting manual dispatch
        police_alerted = False
        for p_unit in state.police_units.values():
            if p_unit.status in (PoliceStatus.IDLE, PoliceStatus.REJECTED, PoliceStatus.TIMEOUT):
                p_unit.notification_received = True
                p_unit.status = PoliceStatus.REQUESTED
                p_unit.assigned_incident_id = self.incident_id
                p_unit.notification_time = state.simulation_time
                p_unit.response_deadline_sec = 20.0
                p_unit.rejection_reason = None
                police_alerted = True
                break

        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.ROAD_INCIDENT_PLACED,
            timestamp=state.simulation_time,
            entity_id=self.incident_id,
            payload={"incident_type": self.incident_type.value, "edge_id": self.edge_id}
        )
        msg = f"Placed {self.incident_type.value} incident on road {self.edge_id}."
        if police_alerted:
            msg += " Automatically sent dispatch notification to Traffic Police (P-01)!"
        if rerouted_units:
            msg += f" Auto-rerouted {len(rerouted_units)} unit(s) around the obstacle: {', '.join(rerouted_units)}."
        return True, msg, [event]

@dataclass
class ClearRoadIncidentCommand(Command):
    incident_id: str

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.incident_id not in state.road_incidents:
            return False, f"Incident '{self.incident_id}' not found.", []
        inc = state.road_incidents[self.incident_id]
        state.road_graph.clear_edge_incident(inc.edge_id)
        inc.cleared_at = state.simulation_time

        # Reset police unit assigned to this incident
        for p_unit in state.police_units.values():
            if p_unit.assigned_incident_id == self.incident_id:
                p_unit.status = PoliceStatus.IDLE
                p_unit.assigned_incident_id = None
                p_unit.clearance_progress = 0.0
                p_unit.notification_received = False
                p_unit.rejection_reason = None
                if p_unit.id in state.active_routes:
                    del state.active_routes[p_unit.id]
                p_unit.active_route_id = None

        # Check if active ambulances can optimize back to direct roads
        from src.algorithms.astar import AStarPathfinder
        pathfinder = AStarPathfinder(state.road_graph)
        for amb_id, a_route in list(state.active_routes.items()):
            amb = state.fleet.get(amb_id)
            if not amb or not a_route.destination_node_id:
                continue
            orig = state.road_graph.find_nearest_node(amb.position[0], amb.position[1])
            if orig:
                opt_route = pathfinder.find_route(
                    orig.id,
                    a_route.destination_node_id,
                    destination_title=a_route.destination_title,
                    sim_time=state.simulation_time,
                    vehicle_speed_mps=amb.speed_mps
                )
                if opt_route and opt_route.estimated_travel_time_sec < a_route.time_remaining_sec - 1.5:
                    state.active_routes[amb.id] = opt_route
                    amb.active_route_id = opt_route.id

        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.ROAD_INCIDENT_CLEARED,
            timestamp=state.simulation_time,
            entity_id=self.incident_id
        )
        return True, f"Incident [{self.incident_id}] cleared and road reopened.", [event]

@dataclass
class AcceptPoliceDispatchCommand(Command):
    police_id: str

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.police_id not in state.police_units:
            return False, f"Police unit '{self.police_id}' not found.", []
        p_unit = state.police_units[self.police_id]
        if not p_unit.assigned_incident_id or p_unit.assigned_incident_id not in state.road_incidents:
            return False, "No active road incident assigned to police.", []

        inc_id = p_unit.assigned_incident_id

        # Police confirms clearance: immediately reopen road in graph and re-optimize detouring ambulances
        _ok, _msg, events = ClearRoadIncidentCommand(incident_id=inc_id).execute(state)
        p_unit.status = PoliceStatus.IDLE
        p_unit.assigned_incident_id = None
        p_unit.notification_received = False
        p_unit.rejection_reason = None
        state.increment_version()

        return True, f"Traffic Police confirmed: Obstruction [{inc_id}] CLEARED! Road reopened.", events

@dataclass
class RejectPoliceDispatchCommand(Command):
    police_id: str
    reason: str = "Traffic Police confirmed: Unable to clear obstruction / Declined"

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.police_id not in state.police_units:
            return False, f"Police unit '{self.police_id}' not found.", []
        p_unit = state.police_units[self.police_id]
        p_unit.status = PoliceStatus.REJECTED
        p_unit.rejection_reason = self.reason

        state.increment_version()
        event = SimulationEvent(
            event_type=EventType.POLICE_STATUS_CHANGED,
            timestamp=state.simulation_time,
            entity_id=p_unit.id,
            payload={"status": PoliceStatus.REJECTED.value, "reason": self.reason}
        )
        return True, "Traffic Police confirmed: Obstruction NOT cleared (REJECTED). Road remains closed.", [event]

@dataclass
class TimeoutPoliceDispatchCommand(Command):
    police_id: str

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.police_id not in state.police_units:
            return False, f"Police unit '{self.police_id}' not found.", []
        p_unit = state.police_units[self.police_id]
        p_unit.status = PoliceStatus.REJECTED
        p_unit.rejection_reason = f"Clearance time limit ({p_unit.response_deadline_sec:.0f}s) exceeded! Automatically REJECTED."

        state.increment_version()
        event = SimulationEvent(
            event_type=EventType.POLICE_STATUS_CHANGED,
            timestamp=state.simulation_time,
            entity_id=p_unit.id,
            payload={"status": PoliceStatus.REJECTED.value}
        )
        return True, "Clearance time limit exceeded: Automatically REJECTED! Road remains closed.", [event]

@dataclass
class ReAlertPoliceDispatchCommand(Command):
    police_id: str

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.police_id not in state.police_units:
            return False, f"Police unit '{self.police_id}' not found.", []
        p_unit = state.police_units[self.police_id]

        active_inc = [inc for inc in state.road_incidents.values() if inc.cleared_at is None]
        if not active_inc:
            return False, "No active road incidents to alert police for.", []

        target = active_inc[0]
        p_unit.notification_received = True
        p_unit.status = PoliceStatus.REQUESTED
        p_unit.assigned_incident_id = target.id
        p_unit.notification_time = state.simulation_time
        p_unit.response_deadline_sec = 20.0
        p_unit.rejection_reason = None
        state.increment_version()

        event = SimulationEvent(
            event_type=EventType.POLICE_STATUS_CHANGED,
            timestamp=state.simulation_time,
            entity_id=p_unit.id,
            payload={"status": PoliceStatus.REQUESTED.value, "incident_id": target.id}
        )
        return True, f"Re-alert sent to Cruiser [{p_unit.id}] for incident [{target.id}]! Awaiting officer response...", [event]

@dataclass
class SetPoliceControlModeCommand(Command):
    police_id: str
    is_manual: bool = False
    is_player_controlled: bool | None = None

    def __post_init__(self):
        if self.is_player_controlled is not None:
            self.is_manual = self.is_player_controlled

    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if self.police_id not in state.police_units:
            return False, f"Police unit '{self.police_id}' not found.", []
        p_unit = state.police_units[self.police_id]
        p_unit.is_player_controlled = self.is_manual
        state.increment_version()
        mode_str = "MANUAL (WASD Driving)" if self.is_manual else "AUTONOMOUS (AI Patrol)"
        return True, f"Police Cruiser [{p_unit.id}] control mode set to {mode_str}.", []

@dataclass
class StartSimulationCommand(Command):
    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if state.is_started and not state.is_paused:
            return False, "Simulation is already running.", []
        state.is_started = True
        state.is_paused = False
        state.increment_version()
        event = SimulationEvent(EventType.SIM_STARTED, state.simulation_time)
        return True, "LifeLine Dispatch simulation started.", [event]

@dataclass
class PauseSimulationCommand(Command):
    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if not state.is_started:
            return False, "Simulation has not started yet.", []
        if state.is_paused:
            return False, "Simulation is already paused.", []
        state.is_paused = True
        state.increment_version()
        event = SimulationEvent(EventType.SIM_PAUSED, state.simulation_time)
        return True, "Simulation paused.", [event]

@dataclass
class ResumeSimulationCommand(Command):
    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        if not state.is_started:
            return False, "Simulation has not started yet.", []
        if not state.is_paused:
            return False, "Simulation is not paused.", []
        state.is_paused = False
        state.increment_version()
        event = SimulationEvent(EventType.SIM_RESUMED, state.simulation_time)
        return True, "Simulation resumed.", [event]

@dataclass
class ResetSimulationCommand(Command):
    def execute(self, state: SimulationState) -> tuple[bool, str, list[SimulationEvent]]:
        state.simulation_time = 0.0
        state.is_started = False
        state.is_paused = False
        state.fleet.clear()
        state.emergencies.clear()
        state.active_routes.clear()
        state.police_units.clear()
        state.decision_records.clear()
        state.selected_ambulance_id = None
        state.selected_hospital_id = None
        state.selected_incident_id = None
        state.selected_emergency_id = None

        # Reopen all closed or congested edges
        for inc_id in list(state.road_incidents.keys()):
            inc = state.road_incidents[inc_id]
            state.road_graph.clear_edge_incident(inc.edge_id)
        state.road_incidents.clear()

        # Reset hospital beds to default
        for hosp in state.hospitals.values():
            hosp.reserved_patient_ids.clear()
            hosp.occupied_beds = int(hosp.total_beds * 0.5)
            hosp.vacant_beds = hosp.total_beds - hosp.occupied_beds
            hosp.validate_invariants()

        state.increment_version()
        event = SimulationEvent(EventType.SIM_RESET, 0.0)
        return True, "Simulation state reset to default scenario (0 deployed units).", [event]
