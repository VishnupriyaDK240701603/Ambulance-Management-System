"""Traffic recovery algorithm evaluating detour rerouting versus police clearance waiting."""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.algorithms.astar import AStarPathfinder
from src.models.ambulance import Ambulance
from src.models.decision_record import CandidateEvaluation, DecisionRecord, DecisionType
from src.models.route import Route, RouteSegment
from src.simulation.simulation_state import SimulationState


@dataclass
class TrafficRecoverySettings:
    reroute_improvement_threshold_sec: float = 10.0
    police_dispatch_overhead_sec: float = 5.0
    default_police_clearance_time_sec: float = 8.0

class TrafficRecoveryAlgorithm:
    """Evaluates blocked routes and determines whether to wait for police or take an alternative detour."""

    def __init__(self, settings: TrafficRecoverySettings | None = None):
        self.settings = settings or TrafficRecoverySettings()

    def evaluate_recovery(
        self,
        ambulance: Ambulance,
        active_route: Route,
        state: SimulationState
    ) -> tuple[str, Route | None, DecisionRecord]:
        """Compare waiting for police clearance vs. rerouting.
        
        Returns:
            action_type: 'REROUTE' or 'WAIT_FOR_POLICE' or 'NO_ALTERNATIVE'
            new_route: validated detour route if REROUTE, else None
            decision_record: Explainable AI record
        """
        pathfinder = AStarPathfinder(state.road_graph)
        current_node = state.road_graph.find_nearest_node(ambulance.position[0], ambulance.position[1])
        origin_id = current_node.id if current_node else active_route.origin_node_id
        dest_id = active_route.destination_node_id

        # 1. Inspect obstruction on the active route
        blocked_edge_id = None
        for seg in active_route.segments[active_route.current_segment_index:]:
            edge = state.road_graph.edges.get(seg.edge_id)
            if edge and (edge.is_closed or edge.speed_factor < 0.5):
                blocked_edge_id = seg.edge_id
                break

        # 2. Calculate alternative detour route with the road graph in its current state
        detour_route = pathfinder.find_route(
            origin_node_id=origin_id,
            destination_node_id=dest_id,
            destination_title=active_route.destination_title,
            sim_time=state.simulation_time,
            vehicle_speed_mps=ambulance.speed_mps
        )

        # 3. Calculate waiting cost for police clearance
        police_eta = 15.0  # Estimated police arrival
        police_clear_time = self.settings.default_police_clearance_time_sec
        # Check if police already dispatched or near
        if state.police_units:
            p_unit = next(iter(state.police_units.values()))
            if p_unit.assigned_incident_id:
                police_eta = 8.0
        total_wait_expected_sec = police_eta + police_clear_time + active_route.time_remaining_sec

        detour_eta_sec = detour_route.estimated_travel_time_sec if detour_route else float("inf")

        eligible_evals: list[CandidateEvaluation] = []
        rejected_evals: list[CandidateEvaluation] = []

        # Candidate Option A: Wait for police
        eval_wait = CandidateEvaluation(
            candidate_id="WAIT_POLICE",
            name="Wait for Police Clearance",
            is_eligible=True,
            score=round(total_wait_expected_sec, 1),
            metrics={
                "estimated_wait_sec": total_wait_expected_sec,
                "police_eta_sec": police_eta,
                "clearance_duration_sec": police_clear_time
            }
        )
        eligible_evals.append(eval_wait)

        # Candidate Option B: Detour reroute
        if detour_route:
            eval_detour = CandidateEvaluation(
                candidate_id="DETOUR_REROUTE",
                name="Detour Reroute (Alternative Path)",
                is_eligible=True,
                score=round(detour_eta_sec, 1),
                metrics={
                    "detour_eta_sec": round(detour_eta_sec, 1),
                    "detour_distance_meters": round(detour_route.total_distance_meters, 1),
                    "detour_waypoints": len(detour_route.waypoints)
                }
            )
            eligible_evals.append(eval_detour)
        else:
            rejected_evals.append(
                CandidateEvaluation(
                    candidate_id="DETOUR_REROUTE",
                    name="Detour Reroute",
                    is_eligible=False,
                    rejection_reason="No alternative unblocked path exists to destination"
                )
            )

        # Decision rule: Choose Detour if detour ETA is significantly better than waiting
        dec_id = f"DEC_RECOVERY_{ambulance.id}_{int(state.simulation_time)}"
        action_type = "WAIT_FOR_POLICE"
        chosen_route: Route | None = None
        reasoning = ""

        if detour_route and (total_wait_expected_sec - detour_eta_sec > self.settings.reroute_improvement_threshold_sec):
            action_type = "REROUTE"
            chosen_route = detour_route
            saved_time = total_wait_expected_sec - detour_eta_sec
            reasoning = (
                f"Rerouting selected: Alternative detour saves estimated {saved_time:.1f}s compared to waiting "
                f"for police clearance ({detour_eta_sec:.1f}s vs {total_wait_expected_sec:.1f}s expected wait)."
            )
        else:
            action_type = "WAIT_FOR_POLICE"
            chosen_route = None
            if not detour_route:
                reasoning = (
                    f"No alternative route available. Ambulance must hold position until Traffic Police clears hazard on {blocked_edge_id}."
                )
            else:
                reasoning = (
                    f"Holding position for Police clearance: Detour path ({detour_eta_sec:.1f}s) does not exceed "
                    f"the {self.settings.reroute_improvement_threshold_sec:.1f}s improvement threshold over waiting ({total_wait_expected_sec:.1f}s)."
                )

        dec_record = DecisionRecord(
            id=dec_id,
            decision_type=DecisionType.TRAFFIC_RECOVERY,
            timestamp=state.simulation_time,
            target_entity_id=ambulance.id,
            state_version=state.state_version,
            selected_id=action_type,
            selected_name="Detour Reroute" if action_type == "REROUTE" else "Wait for Police",
            eligible_candidates=eligible_evals,
            rejected_candidates=rejected_evals,
            metrics_used=["detour_eta_sec", "wait_for_police_eta_sec", "threshold_sec"],
            reasoning_summary=reasoning,
            applied=True
        )

        return action_type, chosen_route, dec_record


def calculate_dynamic_reroute(
    ambulance: Ambulance,
    active_route: Route,
    state: SimulationState
) -> Route | None:
    """Calculate a seamless, valid road-network detour for an active ambulance around obstacles.
    
    1. If ambulance is currently driving on the blocked edge, executes a U-turn return segment
       back to cur_seg.from_node_id and detours from that intersection.
    2. If the blockage is downstream on an upcoming edge, preserves the current segment to
       cur_seg.to_node_id and detours from that upcoming intersection so the vehicle never cuts across off-road buildings.
    3. If stationary at a node or starting route, routes from the nearest node.
    """
    if not active_route or not active_route.destination_node_id:
        return None

    pathfinder = AStarPathfinder(state.road_graph)
    cur_seg_idx = active_route.current_segment_index
    remaining_segs = active_route.segments[cur_seg_idx:]

    if not remaining_segs:
        orig = state.road_graph.find_nearest_node(ambulance.position[0], ambulance.position[1])
        if not orig:
            return None
        return pathfinder.find_route(
            origin_node_id=orig.id,
            destination_node_id=active_route.destination_node_id,
            destination_title=active_route.destination_title,
            sim_time=state.simulation_time,
            vehicle_speed_mps=ambulance.speed_mps
        )

    cur_seg = remaining_segs[0]
    cur_edge = state.road_graph.edges.get(cur_seg.edge_id)

    # Check if ambulance is actually near cur_seg
    from_node = state.road_graph.nodes.get(cur_seg.from_node_id)
    to_node = state.road_graph.nodes.get(cur_seg.to_node_id)
    if from_node and to_node:
        _, _, dist_to_cur_seg = state.road_graph._point_to_segment(
            ambulance.position[0], ambulance.position[1],
            from_node.world_pos[0], from_node.world_pos[1],
            to_node.world_pos[0], to_node.world_pos[1]
        )
        if dist_to_cur_seg > 8.0:
            # Ambulance has deviated or is at a different intersection: route from nearest node!
            orig = state.road_graph.find_nearest_node(ambulance.position[0], ambulance.position[1])
            if not orig:
                return None
            return pathfinder.find_route(
                origin_node_id=orig.id,
                destination_node_id=active_route.destination_node_id,
                destination_title=active_route.destination_title,
                sim_time=state.simulation_time,
                vehicle_speed_mps=ambulance.speed_mps
            )

    cur_is_blocked = cur_edge and (
        cur_edge.is_closed or
        cur_edge.active_incident_id is not None or
        cur_edge.speed_factor < 0.6
    )

    if cur_is_blocked:
        # Case A: Block is directly on the current edge the ambulance is driving on.
        # U-turn back to from_node and detour around the obstacle!
        from_node_id = cur_seg.from_node_id
        detour = pathfinder.find_route(
            origin_node_id=from_node_id,
            destination_node_id=active_route.destination_node_id,
            destination_title=active_route.destination_title,
            sim_time=state.simulation_time,
            vehicle_speed_mps=ambulance.speed_mps
        )
        if not detour:
            return None

        from_node = state.road_graph.nodes.get(from_node_id)
        if not from_node:
            return None
        from_node_pos = from_node.world_pos
        dx = from_node_pos[0] - ambulance.position[0]
        dy = from_node_pos[1] - ambulance.position[1]
        dist = max(1.0, math.hypot(dx, dy))
        rev_id = state.road_graph.get_reverse_edge_id(cur_seg.edge_id) or cur_seg.edge_id

        return_seg = RouteSegment(
            edge_id=rev_id,
            from_node_id=cur_seg.to_node_id,
            to_node_id=from_node_id,
            distance_meters=dist,
            base_speed_mps=ambulance.speed_mps,
            effective_speed_mps=ambulance.speed_mps,
            travel_time_sec=dist / max(1.0, ambulance.speed_mps),
            turn_instruction="U-turn away from obstacle"
        )

        combined_segs = [return_seg] + detour.segments
        combined_wps = [ambulance.position, from_node_pos] + detour.waypoints[1:]
        combined_nodes = [from_node_id] + detour.node_ids

        return Route(
            id=f"REROUTE_UTURN_{detour.id}",
            origin_node_id=from_node_id,
            destination_node_id=active_route.destination_node_id,
            destination_title=active_route.destination_title,
            node_ids=combined_nodes,
            segments=combined_segs,
            total_distance_meters=dist + detour.total_distance_meters,
            estimated_travel_time_sec=(dist / max(1.0, ambulance.speed_mps)) + detour.estimated_travel_time_sec,
            waypoints=combined_wps,
            current_segment_index=0
        )
    else:
        # Case B: Current edge is clear; obstacle is downstream on an upcoming road.
        # Finish current segment to upcoming junction (to_node), then take the detour from there!
        to_node_id = cur_seg.to_node_id
        detour = pathfinder.find_route(
            origin_node_id=to_node_id,
            destination_node_id=active_route.destination_node_id,
            destination_title=active_route.destination_title,
            sim_time=state.simulation_time,
            vehicle_speed_mps=ambulance.speed_mps
        )
        if not detour:
            return None

        from_node = state.road_graph.nodes.get(cur_seg.from_node_id)
        to_node = state.road_graph.nodes.get(to_node_id)
        if not from_node or not to_node:
            return None

        combined_segs = [cur_seg] + detour.segments
        combined_wps = [from_node.world_pos, to_node.world_pos] + detour.waypoints[1:]
        combined_nodes = [cur_seg.from_node_id] + detour.node_ids

        return Route(
            id=f"REROUTE_{detour.id}",
            origin_node_id=cur_seg.from_node_id,
            destination_node_id=active_route.destination_node_id,
            destination_title=active_route.destination_title,
            node_ids=combined_nodes,
            segments=combined_segs,
            total_distance_meters=cur_seg.distance_meters + detour.total_distance_meters,
            estimated_travel_time_sec=cur_seg.travel_time_sec + detour.estimated_travel_time_sec,
            waypoints=combined_wps,
            current_segment_index=0
        )

