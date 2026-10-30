"""Deterministic capability-aware and multi-incident joint ambulance dispatch algorithm with Explainable AI audits."""
from __future__ import annotations

from dataclasses import dataclass

from src.algorithms.astar import AStarPathfinder
from src.models.ambulance import Ambulance, AmbulanceClass, AmbulanceStatus
from src.models.decision_record import CandidateEvaluation, DecisionRecord, DecisionType
from src.models.emergency import EmergencyIncident, EmergencySeverity, IncidentStatus
from src.models.route import Route
from src.simulation.simulation_state import SimulationState

SEVERITY_PRIORITY: dict[EmergencySeverity, int] = {
    EmergencySeverity.CRITICAL: 4,
    EmergencySeverity.HIGH: 3,
    EmergencySeverity.MEDIUM: 2,
    EmergencySeverity.LOW: 1,
}

SEVERITY_URGENCY_MULTIPLIER: dict[EmergencySeverity, float] = {
    EmergencySeverity.CRITICAL: 1.30,
    EmergencySeverity.HIGH: 1.15,
    EmergencySeverity.MEDIUM: 1.00,
    EmergencySeverity.LOW: 0.85,
}

def hungarian_algorithm(cost_matrix: list[list[float]]) -> list[tuple[int, int]]:
    """
    Kuhn-Munkres algorithm (Hungarian method) for minimum weight bipartite matching.
    Returns list of (row_idx, col_idx) matched pairs for the rows and columns.
    """
    n_rows = len(cost_matrix)
    if n_rows == 0:
        return []
    n_cols = len(cost_matrix[0])
    if n_cols == 0:
        return []

    dim = max(n_rows, n_cols)
    BIG = 1e9
    cost = [[0.0] * (dim + 1) for _ in range(dim + 1)]
    for r in range(dim):
        for c in range(dim):
            if r < n_rows and c < n_cols:
                cost[r + 1][c + 1] = cost_matrix[r][c]
            else:
                cost[r + 1][c + 1] = 0.0

    u = [0.0] * (dim + 1)
    v = [0.0] * (dim + 1)
    p = [0] * (dim + 1)
    way = [0] * (dim + 1)

    for i in range(1, dim + 1):
        p[0] = i
        j0 = 0
        minv = [BIG] * (dim + 1)
        used = [False] * (dim + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = BIG
            j1 = 0
            for j in range(1, dim + 1):
                if not used[j]:
                    cur = cost[i0][j] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(dim + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    matches = []
    for j in range(1, dim + 1):
        r = p[j] - 1
        c = j - 1
        if r < n_rows and c < n_cols:
            matches.append((r, c))
    return sorted(matches)

def calculate_tier_match(
    amb: Ambulance,
    emergency: EmergencyIncident,
    has_qualified_in_fleet: bool
) -> tuple[bool, float, str, str | None]:
    """
    Evaluate medical capabilities and tier alignment.
    Returns: (is_eligible, tier_cost, role_desc, rejection_reason)
    """
    missing = [cap for cap in emergency.required_capabilities if cap not in amb.capabilities]
    has_all = (len(missing) == 0)

    if has_all:
        tier_cost = 0.0
        role = "Optimal Tier Match"

        if emergency.severity == EmergencySeverity.LOW:
            if amb.unit_class == AmbulanceClass.BLS:
                tier_cost = 0.0
                role = "Optimal Tier Match (BLS for Low Acuity)"
            elif amb.unit_class == AmbulanceClass.ALS:
                tier_cost = 14.0
                role = "Over-Tier (ALS Conserved for High/Critical)"
            elif amb.unit_class == AmbulanceClass.CCT:
                tier_cost = 28.0
                role = "Over-Tier (CCT Conserved for Critical/ICU)"
        elif emergency.severity == EmergencySeverity.MEDIUM:
            if amb.unit_class == AmbulanceClass.ALS:
                tier_cost = 0.0
                role = "Optimal Tier Match (ALS for Moderate Acuity)"
            elif amb.unit_class == AmbulanceClass.CCT:
                tier_cost = 5.0
                role = "Acceptable Tier (CCT for Moderate Acuity)"
            else:
                tier_cost = 0.0
                role = "Direct Capability Match"
        elif emergency.severity == EmergencySeverity.HIGH:
            if amb.unit_class == AmbulanceClass.ALS:
                tier_cost = 0.0
                role = "Optimal Tier Match (ALS for Severe Trauma)"
            elif amb.unit_class == AmbulanceClass.CCT:
                tier_cost = 3.0
                role = "Acceptable Tier (CCT for Severe Trauma)"
            else:
                tier_cost = 0.0
                role = "Direct Capability Match"
        else: # CRITICAL
            if amb.unit_class == AmbulanceClass.CCT:
                tier_cost = 0.0
                role = "Optimal Tier Match (CCT for Critical ICU)"
            elif amb.unit_class == AmbulanceClass.ALS:
                tier_cost = 10.0
                role = "Sub-Optimal Tier (ALS for Critical Call)"
            else:
                tier_cost = 20.0
                role = "Basic Responder for Critical Call"

        return True, tier_cost, role, None

    else:
        if has_qualified_in_fleet:
            rej_reason = f"Missing required capabilities: {', '.join(missing)}"
            return False, 999.0, "Ineligible (Missing Capabilities)", rej_reason
        else:
            has_basic_life_support = any(
                cap in amb.capabilities for cap in ("cpr", "oxygen", "basic_first_aid", "splinting")
            )
            if has_basic_life_support:
                tier_cost = 40.0 + len(missing) * 10.0
                role = f"Provisional First-Responder (Missing: {', '.join(missing)})"
                return True, tier_cost, role, None
            else:
                rej_reason = f"Missing required capabilities: {', '.join(missing)}"
                return False, 999.0, "Ineligible", rej_reason

@dataclass
class DispatchWeights:
    eta_weight: float = 0.55
    distance_weight: float = 0.25
    capability_bonus: float = 0.10
    workload_penalty: float = 0.10
    tier_preservation_weight: float = 0.25

def compute_candidate_score(
    amb: Ambulance,
    emergency: EmergencyIncident,
    route: Route,
    tier_cost: float,
    weights: DispatchWeights
) -> tuple[float, dict[str, float]]:
    eta = route.estimated_travel_time_sec
    dist = route.total_distance_meters
    workload = amb.total_missions_completed
    extra_caps = max(0, len(amb.capabilities) - len(emergency.required_capabilities))

    urgency_mult = SEVERITY_URGENCY_MULTIPLIER.get(emergency.severity, 1.0)
    time_cost = eta * weights.eta_weight * urgency_mult
    dist_cost = (dist / 10.0) * weights.distance_weight
    workload_cost = (workload * 5.0) * weights.workload_penalty
    cap_bonus = min(10.0, extra_caps * 1.5) * weights.capability_bonus
    tier_preservation_cost = tier_cost * weights.tier_preservation_weight

    total_cost = time_cost + dist_cost + workload_cost + tier_preservation_cost - cap_bonus
    breakdown = {
        "time_cost": round(time_cost, 2),
        "dist_cost": round(dist_cost, 2),
        "workload_penalty": round(workload_cost, 2),
        "tier_preservation_cost": round(tier_preservation_cost, 2),
        "capability_bonus": round(-cap_bonus, 2)
    }
    return total_cost, breakdown

class DispatchAlgorithm:
    """Evaluates deployed ambulances for emergency dispatch with full explainability and multi-incident joint optimization."""

    def __init__(self, weights: DispatchWeights | None = None):
        self.weights = weights or DispatchWeights()

    def evaluate_and_dispatch(
        self,
        emergency: EmergencyIncident,
        state: SimulationState
    ) -> tuple[str | None, Route | None, DecisionRecord]:
        """Evaluate candidates, pick best eligible unit, and generate transparent decision audit record."""
        pathfinder = AStarPathfinder(state.road_graph)
        eligible_evals: list[CandidateEvaluation] = []
        rejected_evals: list[CandidateEvaluation] = []
        candidate_routes: dict[str, Route] = {}

        # Fallback nearest road node for emergency
        dest_node_id = emergency.nearest_node_id
        if dest_node_id not in state.road_graph.nodes:
            dest_node = state.road_graph.find_nearest_node(emergency.location[0], emergency.location[1])
            dest_node_id = dest_node.id if dest_node else "N_0_0"

        # Check if any deployed unit currently has 100% of required capabilities
        has_qualified_in_fleet = any(
            amb.status in (AmbulanceStatus.AVAILABLE, AmbulanceStatus.ASSIGNED) and
            all(cap in amb.capabilities for cap in emergency.required_capabilities)
            for amb in state.fleet.values()
        )

        # Evaluate every deployed ambulance
        for amb in state.fleet.values():
            # 1. Eligibility Check: Status
            if amb.status not in (AmbulanceStatus.AVAILABLE, AmbulanceStatus.ASSIGNED):
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=amb.id,
                        name=f"{amb.unit_class.value} [{amb.id}]",
                        is_eligible=False,
                        rejection_reason=f"Unit operational status is {amb.status.value}"
                    )
                )
                continue

            # 2. Eligibility Check: Medical Capabilities & Tier
            is_elig, tier_cost, role_desc, rej_reason = calculate_tier_match(
                amb, emergency, has_qualified_in_fleet
            )
            if not is_elig:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=amb.id,
                        name=f"{amb.unit_class.value} [{amb.id}]",
                        is_eligible=False,
                        rejection_reason=rej_reason or "Capabilities check failed"
                    )
                )
                continue

            # 3. Eligibility Check: Road Network Reachability via A*
            origin_node = state.road_graph.find_nearest_node(amb.position[0], amb.position[1])
            if not origin_node:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=amb.id,
                        name=f"{amb.unit_class.value} [{amb.id}]",
                        is_eligible=False,
                        rejection_reason="No nearby accessible road node"
                    )
                )
                continue

            route = pathfinder.find_route(
                origin_node_id=origin_node.id,
                destination_node_id=dest_node_id,
                destination_title=emergency.title,
                sim_time=state.simulation_time,
                vehicle_speed_mps=amb.speed_mps
            )
            if not route:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=amb.id,
                        name=f"{amb.unit_class.value} [{amb.id}]",
                        is_eligible=False,
                        rejection_reason="No feasible unblocked road route to scene (roadblocks/closures)"
                    )
                )
                continue

            candidate_routes[amb.id] = route

            # 4. Multi-factor Scoring for eligible candidate
            cost_score, breakdown = compute_candidate_score(
                amb, emergency, route, tier_cost, self.weights
            )

            eval_entry = CandidateEvaluation(
                candidate_id=amb.id,
                name=f"{amb.unit_class.value} [{amb.id}]",
                is_eligible=True,
                score=round(cost_score, 2),
                metrics={
                    "eta_seconds": round(route.estimated_travel_time_sec, 1),
                    "distance_meters": round(route.total_distance_meters, 1),
                    "speed_mps": amb.speed_mps,
                    "missions_completed": amb.total_missions_completed,
                    "capabilities": list(amb.capabilities),
                    "unit_class": amb.unit_class.value,
                    "dispatch_role": role_desc
                },
                score_components=breakdown
            )
            eligible_evals.append(eval_entry)

        # Rank eligible candidates (lowest cost score first)
        eligible_evals.sort(key=lambda x: x.score)

        dec_id = f"DEC_DISPATCH_{emergency.id}_{int(state.simulation_time)}"
        selected_id: str | None = None
        selected_name: str = "None Available"
        chosen_route: Route | None = None
        reasoning = ""

        if eligible_evals:
            winner = eligible_evals[0]
            selected_id = winner.candidate_id
            selected_name = winner.name
            chosen_route = candidate_routes[selected_id]
            role = winner.metrics.get("dispatch_role", "Primary Responder")
            reasoning = (
                f"Assigned {winner.name} as {role}: lowest composite response cost ({winner.score:.2f}) "
                f"with estimated ETA of {winner.metrics['eta_seconds']}s over {winner.metrics['distance_meters']}m."
            )
        else:
            reasoning = (
                f"No eligible ambulance available for incident [{emergency.id}]. "
                f"Rejections: {len(rejected_evals)} candidate(s) failed eligibility criteria."
            )

        dec_record = DecisionRecord(
            id=dec_id,
            decision_type=DecisionType.DISPATCH,
            timestamp=state.simulation_time,
            target_entity_id=emergency.id,
            state_version=state.state_version,
            selected_id=selected_id,
            selected_name=selected_name,
            eligible_candidates=eligible_evals,
            rejected_candidates=rejected_evals,
            metrics_used=["eta_sec", "distance_meters", "capabilities", "tier_preservation", "workload_penalty"],
            reasoning_summary=reasoning,
            applied=(selected_id is not None)
        )

        return selected_id, chosen_route, dec_record

    def dispatch_waiting_emergencies(
        self,
        state: SimulationState
    ) -> list[tuple[str, str | None, Route | None, DecisionRecord]]:
        """
        Coordinated multi-incident global optimal ambulance dispatch.
        Jointly matches all waiting emergencies with available ambulances to prevent
        suboptimal greedy allocations, avoid idle units, and optimize global response time.
        """
        waiting_emergencies = [
            em for em in state.emergencies.values()
            if em.status == IncidentStatus.WAITING_DISPATCH
        ]
        if not waiting_emergencies:
            return []

        # Sort waiting emergencies: highest severity first, then older wait time
        waiting_emergencies.sort(
            key=lambda em: (-SEVERITY_PRIORITY.get(em.severity, 0), em.created_at)
        )

        available_ambulances = [
            amb for amb in state.fleet.values()
            if amb.status == AmbulanceStatus.AVAILABLE and amb.assigned_emergency_id is None
        ]

        # Case A: No ambulances available at all
        if not available_ambulances:
            results = []
            for em in waiting_emergencies:
                dec_id = f"DEC_DISPATCH_{em.id}_{int(state.simulation_time)}"
                dec = DecisionRecord(
                    id=dec_id,
                    decision_type=DecisionType.DISPATCH,
                    timestamp=state.simulation_time,
                    target_entity_id=em.id,
                    state_version=state.state_version,
                    selected_id=None,
                    selected_name="Fleet Fully Committed",
                    eligible_candidates=[],
                    rejected_candidates=[],
                    metrics_used=["fleet_availability"],
                    reasoning_summary="No available ambulances in fleet; queued in WAITING_DISPATCH.",
                    applied=False
                )
                results.append((em.id, None, None, dec))
            return results

        # Case B: Single emergency or single ambulance
        if len(waiting_emergencies) == 1 or len(available_ambulances) == 1:
            results = []
            assigned_ambs = set()
            for em in waiting_emergencies:
                temp_avail = [a for a in available_ambulances if a.id not in assigned_ambs]
                if not temp_avail:
                    dec_id = f"DEC_DISPATCH_{em.id}_{int(state.simulation_time)}"
                    dec = DecisionRecord(
                        id=dec_id,
                        decision_type=DecisionType.DISPATCH,
                        timestamp=state.simulation_time,
                        target_entity_id=em.id,
                        state_version=state.state_version,
                        selected_id=None,
                        selected_name="Fleet Fully Committed",
                        eligible_candidates=[],
                        rejected_candidates=[],
                        metrics_used=["fleet_availability"],
                        reasoning_summary=f"Incident [{em.id}] queued; remaining units deployed to higher-priority calls.",
                        applied=False
                    )
                    results.append((em.id, None, None, dec))
                    continue

                sel_id, route, dec = self.evaluate_and_dispatch(em, state)
                if sel_id and sel_id not in assigned_ambs:
                    assigned_ambs.add(sel_id)
                    results.append((em.id, sel_id, route, dec))
                else:
                    results.append((em.id, None, None, dec))
            return results

        # Case C: Multiple waiting emergencies and multiple available ambulances: Joint Bipartite Optimization
        pathfinder = AStarPathfinder(state.road_graph)
        n_em = len(waiting_emergencies)
        n_amb = len(available_ambulances)

        pair_routes: dict[tuple[int, int], Route] = {}
        pair_evals: dict[tuple[int, int], CandidateEvaluation] = {}
        pair_costs: list[list[float]] = [[1e6] * n_amb for _ in range(n_em)]

        for i, em in enumerate(waiting_emergencies):
            dest_node_id = em.nearest_node_id
            if dest_node_id not in state.road_graph.nodes:
                dest_node = state.road_graph.find_nearest_node(em.location[0], em.location[1])
                dest_node_id = dest_node.id if dest_node else "N_0_0"

            has_qualified = any(
                all(c in a.capabilities for c in em.required_capabilities)
                for a in available_ambulances
            )

            urgency_offset = (4 - SEVERITY_PRIORITY.get(em.severity, 1)) * 50.0

            for j, amb in enumerate(available_ambulances):
                is_elig, tier_cost, role_desc, _rej_reason = calculate_tier_match(
                    amb, em, has_qualified
                )
                if not is_elig:
                    continue

                origin_node = state.road_graph.find_nearest_node(amb.position[0], amb.position[1])
                if not origin_node:
                    continue

                route = pathfinder.find_route(
                    origin_node_id=origin_node.id,
                    destination_node_id=dest_node_id,
                    destination_title=em.title,
                    sim_time=state.simulation_time,
                    vehicle_speed_mps=amb.speed_mps
                )
                if not route:
                    continue

                cost, breakdown = compute_candidate_score(
                    amb, em, route, tier_cost, self.weights
                )
                pair_routes[(i, j)] = route
                pair_costs[i][j] = cost + urgency_offset
                pair_evals[(i, j)] = CandidateEvaluation(
                    candidate_id=amb.id,
                    name=f"{amb.unit_class.value} [{amb.id}]",
                    is_eligible=True,
                    score=round(cost, 2),
                    metrics={
                        "eta_seconds": round(route.estimated_travel_time_sec, 1),
                        "distance_meters": round(route.total_distance_meters, 1),
                        "speed_mps": amb.speed_mps,
                        "missions_completed": amb.total_missions_completed,
                        "capabilities": list(amb.capabilities),
                        "unit_class": amb.unit_class.value,
                        "dispatch_role": role_desc
                    },
                    score_components=breakdown
                )

        optimal_matches = hungarian_algorithm(pair_costs)
        matched_dict = dict(optimal_matches)

        results = []
        for i, em in enumerate(waiting_emergencies):
            j = matched_dict.get(i)
            dec_id = f"DEC_DISPATCH_{em.id}_{int(state.simulation_time)}"

            all_eligible = []
            all_rejected = []
            for k, amb in enumerate(available_ambulances):
                if (i, k) in pair_evals:
                    all_eligible.append(pair_evals[(i, k)])
                else:
                    all_rejected.append(
                        CandidateEvaluation(
                            candidate_id=amb.id,
                            name=f"{amb.unit_class.value} [{amb.id}]",
                            is_eligible=False,
                            rejection_reason="Capabilities tier mismatch or scene unreachable"
                        )
                    )
            all_eligible.sort(key=lambda x: x.score)

            if j is not None and pair_costs[i][j] < 5e5 and (i, j) in pair_routes:
                chosen_amb = available_ambulances[j]
                chosen_route = pair_routes[(i, j)]
                winner_eval = pair_evals[(i, j)]
                role = winner_eval.metrics.get("dispatch_role", "Primary Responder")

                reasoning = (
                    f"Assigned {chosen_amb.unit_class.value} [{chosen_amb.id}] via Joint Multi-Incident Optimizer ({role}): "
                    f"Composite cost {winner_eval.score:.2f}, ETA {winner_eval.metrics['eta_seconds']}s over {winner_eval.metrics['distance_meters']}m. "
                    f"Coordinated across {len(waiting_emergencies)} concurrent emergencies for optimal fleet coverage."
                )

                dec = DecisionRecord(
                    id=dec_id,
                    decision_type=DecisionType.DISPATCH,
                    timestamp=state.simulation_time,
                    target_entity_id=em.id,
                    state_version=state.state_version,
                    selected_id=chosen_amb.id,
                    selected_name=f"{chosen_amb.unit_class.value} [{chosen_amb.id}]",
                    eligible_candidates=all_eligible,
                    rejected_candidates=all_rejected,
                    metrics_used=["eta_sec", "distance_meters", "joint_optimization", "tier_preservation"],
                    reasoning_summary=reasoning,
                    applied=True
                )
                results.append((em.id, chosen_amb.id, chosen_route, dec))
            else:
                reasoning = (
                    f"Incident [{em.id}] queued: fleet capacity committed to higher-priority simultaneous calls, "
                    f"or no feasible road route to scene."
                )
                dec = DecisionRecord(
                    id=dec_id,
                    decision_type=DecisionType.DISPATCH,
                    timestamp=state.simulation_time,
                    target_entity_id=em.id,
                    state_version=state.state_version,
                    selected_id=None,
                    selected_name="Fleet Capacity Reached",
                    eligible_candidates=all_eligible,
                    rejected_candidates=all_rejected,
                    metrics_used=["fleet_availability", "joint_optimization"],
                    reasoning_summary=reasoning,
                    applied=False
                )
                results.append((em.id, None, None, dec))

        return results
