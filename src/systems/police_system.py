"""Traffic police communication, notification monitoring, and automated clearance timeout subsystem."""
from __future__ import annotations

from src.models.police_unit import PoliceStatus
from src.simulation.simulation_state import SimulationState


def update_police_system(state: SimulationState, dt: float) -> None:
    """Subsystem update: manage police notification deadlines and automated timeout rejection."""
    # 1. Automatic Alert: If active uncleared incidents exist and police is IDLE, automatically notify police
    active_incidents = [inc for inc in state.road_incidents.values() if inc.cleared_at is None]
    if active_incidents:
        for p_unit in state.police_units.values():
            if p_unit.status == PoliceStatus.IDLE and not p_unit.assigned_incident_id:
                oldest_inc = active_incidents[0]
                p_unit.notification_received = True
                p_unit.status = PoliceStatus.REQUESTED
                p_unit.assigned_incident_id = oldest_inc.id
                p_unit.notification_time = state.simulation_time
                p_unit.response_deadline_sec = 20.0
                p_unit.rejection_reason = None
                state.increment_version()

    # 2. Process timeout deadline: if not cleared within time limit, automatically REJECT
    for p_unit in list(state.police_units.values()):
        if p_unit.status == PoliceStatus.REQUESTED:
            # If assigned incident was already cleared or removed, reset to IDLE
            if p_unit.assigned_incident_id and (
                p_unit.assigned_incident_id not in state.road_incidents or
                state.road_incidents[p_unit.assigned_incident_id].cleared_at is not None
            ):
                p_unit.status = PoliceStatus.IDLE
                p_unit.assigned_incident_id = None
                p_unit.notification_received = False
                p_unit.rejection_reason = None
                state.increment_version()
                continue

            time_elapsed = state.simulation_time - p_unit.notification_time
            if time_elapsed >= p_unit.response_deadline_sec:
                # Time limit exceeded! Automatically reject
                p_unit.status = PoliceStatus.REJECTED
                p_unit.rejection_reason = (
                    f"Clearance time limit ({p_unit.response_deadline_sec:.0f}s) exceeded! "
                    "Automatically REJECTED. Road remains blocked."
                )
                state.increment_version()
