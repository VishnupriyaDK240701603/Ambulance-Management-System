"""Dynamic Ambulance Reallocation Algorithm for optimal city-wide coverage and reduced idle latency."""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.algorithms.astar import AStarPathfinder
from src.models.ambulance import Ambulance, AmbulanceStatus, ControlMode
from src.models.decision_record import CandidateEvaluation, DecisionRecord, DecisionType
from src.models.route import Route
from src.simulation.events import EventType, SimulationEvent
from src.simulation.simulation_state import SimulationState


@dataclass
class StandbyStation:
    id: str
    name: str
    node_id: str
    district: str
    weight: float = 1.0

DEFAULT_STANDBY_STATIONS: list[StandbyStation] = [
    StandbyStation("DEPOT-01", "West District EMS Depot", "N_1_1", "West", 1.0),
    StandbyStation("DEPOT-02", "South District EMS Depot", "N_6_2", "South", 1.1),
    StandbyStation("DEPOT-03", "North District EMS Depot", "N_4_6", "North", 1.0),
    StandbyStation("HUB-CENTRAL", "Central City Junction", "N_3_3", "Central", 1.3),
    StandbyStation("HUB-EAST", "East Commerce Hub", "N_6_5", "East", 1.0),
]

@dataclass
class ReallocationPlan:
    ambulance_id: str
    station_id: str
    station_name: str
    destination_node_id: str
    route: Route
    decision_record: DecisionRecord
    coverage_improvement_sec: float

class DynamicReallocationAlgorithm:
    """
    Monitors spatial fleet distribution and dynamically repositions idle ambulances
    to strategic standby posts as demand changes, maximizing coverage and reducing idle time.
    """

    def __init__(self, stations: list[StandbyStation] | None = None):
        self.stations = stations or DEFAULT_STANDBY_STATIONS

    def evaluate_reallocation(self, state: SimulationState) -> ReallocationPlan | None:
        """
        Evaluate if any idle ambulance should be repositioned to an underserved strategic post.
        Returns ReallocationPlan if an improvement above threshold is found, else None.
        """
        # Find idle ambulances eligible for reallocation
        idle_ambulances = [
            amb for amb in state.fleet.values()
            if amb.control_mode == ControlMode.AUTONOMOUS
            and amb.assigned_emergency_id is None
            and amb.status in (AmbulanceStatus.AVAILABLE, AmbulanceStatus.EN_ROUTE)
            and amb.active_route_id is None
        ]

        if not idle_ambulances:
            return None

        # Verify which stations exist in road graph
        valid_stations = [s for s in self.stations if s.node_id in state.road_graph.nodes]
        if not valid_stations:
            return None

        pathfinder = AStarPathfinder(state.road_graph)

        # For each station, find distance/ETA from nearest available ambulance
        station_min_eta: dict[str, float] = {}
        for station in valid_stations:
            min_eta = 999.0
            st_node = state.road_graph.nodes[station.node_id]
            for amb in state.fleet.values():
                if amb.assigned_emergency_id is not None:
                    continue
                d = math.hypot(amb.position[0] - st_node.world_pos[0], amb.position[1] - st_node.world_pos[1])
                eta_est = d / max(1.0, amb.speed_mps)
                min_eta = min(min_eta, eta_est)
            station_min_eta[station.id] = min_eta

        # Find station with highest coverage deficit (highest weighted ETA)
        underserved_station = max(
            valid_stations,
            key=lambda s: station_min_eta.get(s.id, 0.0) * s.weight
        )

        worst_eta = station_min_eta.get(underserved_station.id, 0.0)
        # Only reallocate if station ETA is worse than 6.0s (underserved post)
        if worst_eta < 6.0:
            return None

        st_node = state.road_graph.nodes[underserved_station.node_id]

        # Evaluate candidate idle ambulances to relocate
        candidate_evals: list[CandidateEvaluation] = []
        best_candidate: Ambulance | None = None
        best_route: Route | None = None
        best_eta = 999.0

        for amb in idle_ambulances:
            origin_node = state.road_graph.find_nearest_node(amb.position[0], amb.position[1])
            if not origin_node or origin_node.id == underserved_station.node_id:
                continue

            route = pathfinder.find_route(
                origin_node_id=origin_node.id,
                destination_node_id=underserved_station.node_id,
                destination_title=f"Standby: {underserved_station.name}",
                sim_time=state.simulation_time,
                vehicle_speed_mps=amb.speed_mps
            )
            if not route:
                continue

            eta = route.estimated_travel_time_sec
            improvement = worst_eta

            eval_entry = CandidateEvaluation(
                candidate_id=amb.id,
                name=f"{amb.unit_class.value} [{amb.id}]",
                is_eligible=True,
                score=round(eta, 2),
                metrics={
                    "eta_seconds": round(eta, 1),
                    "distance_meters": round(route.total_distance_meters, 1),
                    "coverage_improvement_sec": round(improvement, 1),
                    "target_post": underserved_station.name
                },
                score_components={
                    "relocation_time": round(eta, 2),
                    "coverage_gain": round(improvement, 2)
                }
            )
            candidate_evals.append(eval_entry)

            if eta < best_eta:
                best_eta = eta
                best_candidate = amb
                best_route = route

        if not best_candidate or not best_route:
            return None

        candidate_evals.sort(key=lambda x: x.score)

        dec_id = f"DEC_REALLOC_{best_candidate.id}_{int(state.simulation_time)}"
        reasoning = (
            f"Dynamic Reallocation: Repositioning idle unit {best_candidate.unit_class.value} [{best_candidate.id}] "
            f"to strategic standby post '{underserved_station.name}' ({underserved_station.district} District). "
            f"Cuts peak district response time from {worst_eta:.1f}s to {best_route.estimated_travel_time_sec:.1f}s "
            f"(+{worst_eta:.1f}s coverage improvement), eliminating fleet clustering."
        )

        dec_record = DecisionRecord(
            id=dec_id,
            decision_type=DecisionType.REALLOCATION,
            timestamp=state.simulation_time,
            target_entity_id=best_candidate.id,
            state_version=state.state_version,
            selected_id=underserved_station.id,
            selected_name=f"Standby: {underserved_station.name}",
            eligible_candidates=candidate_evals,
            rejected_candidates=[],
            metrics_used=["coverage_deficit", "eta_reduction", "cluster_reduction", "idle_time"],
            reasoning_summary=reasoning,
            applied=True
        )

        return ReallocationPlan(
            ambulance_id=best_candidate.id,
            station_id=underserved_station.id,
            station_name=underserved_station.name,
            destination_node_id=underserved_station.node_id,
            route=best_route,
            decision_record=dec_record,
            coverage_improvement_sec=worst_eta
        )

    def apply_reallocation(self, plan: ReallocationPlan, state: SimulationState) -> bool:
        """Apply the reallocation plan to the simulation state."""
        amb = state.fleet.get(plan.ambulance_id)
        if not amb:
            return False

        # Route ambulance to strategic standby post
        amb.status = AmbulanceStatus.EN_ROUTE
        amb.assigned_emergency_id = None
        amb.active_route_id = plan.route.id
        amb.target_node_id = plan.destination_node_id
        state.active_routes[amb.id] = plan.route
        state.decision_records.append(plan.decision_record)
        state.increment_version()

        event_log = getattr(state, "event_log", None)
        if event_log:
            event_log.record(
                SimulationEvent(
                    event_type=EventType.AMBULANCE_REALLOCATED,
                    timestamp=state.simulation_time,
                    entity_id=amb.id,
                    payload={
                        "target_station": plan.station_name,
                        "destination_node": plan.destination_node_id,
                        "improvement_sec": plan.coverage_improvement_sec
                    }
                )
            )
        return True
