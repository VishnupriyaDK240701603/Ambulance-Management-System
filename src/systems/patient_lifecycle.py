"""Patient lifecycle and automated dispatch/hospital transfer subsystem."""
from __future__ import annotations

from src.algorithms.dispatch import DispatchAlgorithm
from src.algorithms.hospital_selection import HospitalSelectionAlgorithm
from src.models.ambulance import AmbulanceStatus
from src.models.emergency import IncidentStatus
from src.simulation.simulation_state import SimulationState

# Global algorithm instances
_dispatch_algo = DispatchAlgorithm()
_hospital_algo = HospitalSelectionAlgorithm()

def update_patient_lifecycle(state: SimulationState, dt: float) -> None:
    """Subsystem update: handle triage progression, automated dispatch, and hospital transfer."""
    sim_time = state.simulation_time

    # 1. Automated Coordinated Dispatch for waiting emergencies
    dispatch_results = _dispatch_algo.dispatch_waiting_emergencies(state)
    for em_id, amb_id, route, dec_record in dispatch_results:
        state.decision_records.append(dec_record)
        em = state.emergencies.get(em_id)
        if not em:
            continue
        em.decision_id = dec_record.id

        if amb_id and route:
            amb = state.fleet.get(amb_id)
            if amb:
                amb.status = AmbulanceStatus.EN_ROUTE
                amb.assigned_emergency_id = em.id
                amb.active_route_id = route.id
                state.active_routes[amb.id] = route

                em.assigned_ambulance_id = amb.id
                em.transition_to(IncidentStatus.ASSIGNED, sim_time)
                em.transition_to(IncidentStatus.EN_ROUTE, sim_time)
                state.increment_version()

    # 2. On-scene triage progression: ON_SCENE -> PATIENT_ONBOARD -> TRANSPORTING
    for em in list(state.emergencies.values()):
        if em.status in (IncidentStatus.ON_SCENE, IncidentStatus.PATIENT_ONBOARD) and em.assigned_ambulance_id:
            amb = state.fleet.get(em.assigned_ambulance_id)
            if not amb:
                continue

            # Check triage time elapsed (2.0 seconds on scene for stabilization)
            time_on_scene = sim_time - (em.arrived_scene_at or sim_time)
            if time_on_scene >= 2.0:
                if em.status == IncidentStatus.ON_SCENE:
                    em.transition_to(IncidentStatus.PATIENT_ONBOARD, sim_time)
                    state.increment_version()

                # Rate-limit re-evaluation if waiting for hospital capacity
                last_eval = em._last_hosp_eval_time
                if sim_time - last_eval < 1.0:
                    continue
                em._last_hosp_eval_time = sim_time

                # Select destination hospital dynamically
                hosp_id, hosp_route, dec_record = _hospital_algo.select_destination(
                    ambulance=amb,
                    emergency=em,
                    state=state
                )
                if dec_record:
                    state.decision_records.append(dec_record)

                if hosp_id and hosp_route:
                    amb.status = AmbulanceStatus.TRANSPORTING
                    amb.assigned_hospital_id = hosp_id
                    amb.active_route_id = hosp_route.id
                    state.active_routes[amb.id] = hosp_route

                    em.destination_hospital_id = hosp_id
                    em.transition_to(IncidentStatus.TRANSPORTING, sim_time)
                    state.increment_version()
