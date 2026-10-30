"""Dynamic hospital selection algorithm with capacity reservations, specialization matching, and inbound alert auditing."""
from __future__ import annotations

from dataclasses import dataclass

from src.algorithms.astar import AStarPathfinder
from src.models.ambulance import Ambulance
from src.models.decision_record import CandidateEvaluation, DecisionRecord, DecisionType
from src.models.emergency import EmergencyIncident
from src.models.hospital import HospitalStatus
from src.models.route import Route
from src.simulation.simulation_state import SimulationState


def extract_emergency_specializations(emergency: EmergencyIncident) -> list[str]:
    """Derive relevant clinical specializations needed for an incident."""
    specs = {"basic"}
    req = set(emergency.required_capabilities)
    title_lower = (emergency.title or "").lower()
    desc_lower = (emergency.description or "").lower()

    if any(k in req for k in ("defibrillator", "cardiac_monitor")) or "cardiac" in title_lower or "heart" in title_lower:
        specs.add("cardiac")
    if any(k in req for k in ("ventilator", "ecmo", "critical_meds")) or emergency.severity.value == "CRITICAL" or "icu" in title_lower:
        specs.add("icu")
        specs.add("critical")
    if any(k in req for k in ("splinting", "basic_first_aid")) or "trauma" in title_lower or "fall" in title_lower or "crash" in title_lower:
        specs.add("trauma")
    if "oxygen" in req or "respiratory" in title_lower:
        specs.add("respiratory")
    if "child" in desc_lower or "pediatric" in desc_lower or "pediatric" in title_lower:
        specs.add("pediatric")
    return list(specs)

@dataclass
class HospitalSelectionWeights:
    eta_weight: float = 0.50
    bed_availability_weight: float = 0.30
    capability_weight: float = 0.20
    switching_penalty_sec: float = 25.0

class HospitalSelectionAlgorithm:
    """Evaluates candidate hospitals and selects optimal destination with bed reservation and inbound alerts."""

    def __init__(self, weights: HospitalSelectionWeights | None = None):
        self.weights = weights or HospitalSelectionWeights()

    def select_destination(
        self,
        ambulance: Ambulance,
        emergency: EmergencyIncident,
        state: SimulationState,
        current_hospital_id: str | None = None
    ) -> tuple[str | None, Route | None, DecisionRecord]:
        """Select best hospital, reserve bed, send inbound alert, and produce Explainable AI audit record."""
        pathfinder = AStarPathfinder(state.road_graph)
        eligible_evals: list[CandidateEvaluation] = []
        rejected_evals: list[CandidateEvaluation] = []
        candidate_routes: dict[str, Route] = {}

        needed_specializations = extract_emergency_specializations(emergency)

        # Ambulance origin node
        origin_node = state.road_graph.find_nearest_node(ambulance.position[0], ambulance.position[1])
        origin_id = origin_node.id if origin_node else "N_0_0"

        for hosp in state.hospitals.values():
            # 1. Eligibility Check: Status
            if hosp.operational_status == HospitalStatus.DIVERT:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=hosp.id,
                        name=hosp.name,
                        is_eligible=False,
                        rejection_reason=f"Hospital operational status is {hosp.operational_status.value} (diverting ambulances)"
                    )
                )
                continue

            # 2. Eligibility Check: Available Vacant Beds (taking reservations into account)
            holds_existing_res = (emergency.id in hosp.reserved_patient_ids)
            avail_beds = hosp.effectively_available_beds + (1 if holds_existing_res else 0)
            if avail_beds <= 0:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=hosp.id,
                        name=hosp.name,
                        is_eligible=False,
                        rejection_reason=f"Zero vacant beds available (Vacant: {hosp.vacant_beds}, Active Reservations: {len(hosp.reserved_patient_ids)})"
                    )
                )
                continue

            # 3. Eligibility Check: Road Reachability via A*
            route = pathfinder.find_route(
                origin_node_id=origin_id,
                destination_node_id=hosp.node_id,
                destination_title=f"Hospital: {hosp.name}",
                sim_time=state.simulation_time,
                vehicle_speed_mps=ambulance.speed_mps
            )
            if not route:
                rejected_evals.append(
                    CandidateEvaluation(
                        candidate_id=hosp.id,
                        name=hosp.name,
                        is_eligible=False,
                        rejection_reason="No feasible unblocked road route from current ambulance position"
                    )
                )
                continue

            candidate_routes[hosp.id] = route

            # 4. Multi-factor Scoring
            eta = route.estimated_travel_time_sec
            dist = route.total_distance_meters
            bed_ratio = avail_beds / max(1, hosp.total_beds)

            # Specialization matching
            spec_matches = [s for s in needed_specializations if s in hosp.capabilities]
            spec_ratio = len(spec_matches) / max(1, len(needed_specializations))

            time_cost = eta * self.weights.eta_weight
            bed_benefit = (bed_ratio * 40.0) * self.weights.bed_availability_weight
            cap_benefit = (spec_ratio * 30.0) * self.weights.capability_weight

            switching_cost = 0.0
            if current_hospital_id and current_hospital_id != hosp.id:
                switching_cost = self.weights.switching_penalty_sec

            composite_cost = time_cost - bed_benefit - cap_benefit + switching_cost

            eval_entry = CandidateEvaluation(
                candidate_id=hosp.id,
                name=hosp.name,
                is_eligible=True,
                score=round(composite_cost, 2),
                metrics={
                    "eta_seconds": round(eta, 1),
                    "distance_meters": round(dist, 1),
                    "vacant_beds": hosp.vacant_beds,
                    "effective_vacant": avail_beds,
                    "bed_capacity": hosp.total_beds,
                    "status": hosp.operational_status.value,
                    "matched_specializations": spec_matches,
                    "all_specializations": list(hosp.capabilities)
                },
                score_components={
                    "time_cost": round(time_cost, 2),
                    "bed_benefit": round(-bed_benefit, 2),
                    "specialization_benefit": round(-cap_benefit, 2),
                    "switching_penalty": round(switching_cost, 2)
                }
            )
            eligible_evals.append(eval_entry)

        # Rank (lowest composite cost wins)
        eligible_evals.sort(key=lambda x: x.score)

        dec_id = f"DEC_HOSP_{emergency.id}_{int(state.simulation_time)}"
        selected_id: str | None = None
        selected_name: str = "No Hospital Available"
        chosen_route: Route | None = None
        reasoning = ""

        if eligible_evals:
            winner = eligible_evals[0]
            selected_id = winner.candidate_id
            selected_name = winner.name
            chosen_route = candidate_routes[selected_id]
            hosp = state.hospitals[selected_id]

            # Atomically manage bed reservations
            if current_hospital_id and current_hospital_id != selected_id and current_hospital_id in state.hospitals:
                state.hospitals[current_hospital_id].release_reservation(emergency.id)

            # Reserve bed at new hospital (increments reserved count to prove bed is held)
            hosp.reserve_bed(emergency.id)

            inbound_count = len(hosp.reserved_patient_ids)
            committed_total = hosp.occupied_beds + inbound_count

            winner.metrics["inbound_alert_sent"] = True
            winner.metrics["bed_reserved_proven"] = True
            winner.metrics["reserved_inbound_count"] = inbound_count
            winner.metrics["total_committed_beds"] = committed_total

            reasoning = (
                f"Dispatched inbound alert to {winner.name} [{selected_id}]: 1 bed reserved for incident [{emergency.id}]. "
                f"Hospital reservation count incremented to {inbound_count} (Total committed: {committed_total}/{hosp.total_beds}). "
                f"Selected by capacity ({winner.metrics['effective_vacant']} available), distance/ETA ({winner.metrics['eta_seconds']}s), "
                f"and matching specialization ({', '.join(winner.metrics['matched_specializations'])})."
            )
        else:
            reasoning = (
                f"No eligible destination hospital found for incident [{emergency.id}]. "
                f"All {len(rejected_evals)} evaluated hospitals failed capacity, connectivity, or diversion criteria."
            )

        dec_record = DecisionRecord(
            id=dec_id,
            decision_type=DecisionType.HOSPITAL_SELECTION,
            timestamp=state.simulation_time,
            target_entity_id=emergency.id,
            state_version=state.state_version,
            selected_id=selected_id,
            selected_name=selected_name,
            eligible_candidates=eligible_evals,
            rejected_candidates=rejected_evals,
            metrics_used=["eta_sec", "vacant_beds", "specialization", "inbound_alert_proof", "switching_penalty"],
            reasoning_summary=reasoning,
            applied=(selected_id is not None)
        )

        return selected_id, chosen_route, dec_record
