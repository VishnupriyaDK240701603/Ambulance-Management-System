"""Tests for patient lifecycle state machine and end-to-end mission transitions."""
import pytest

from src.models.ambulance import Ambulance, AmbulanceClass, AmbulanceStatus
from src.models.emergency import EmergencyIncident, EmergencySeverity, IncidentStatus
from src.models.hospital import Hospital
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState
from src.systems.ambulance_movement import update_ambulance_movement
from src.systems.patient_lifecycle import update_patient_lifecycle
from src.world.city_generator import CityGenerator


@pytest.fixture
def lifecycle_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph, is_started=True, deployment_limit=2)
    engine = SimulationEngine(state, fixed_dt=0.05)

    engine.register_subsystem(update_ambulance_movement)
    engine.register_subsystem(update_patient_lifecycle)

    # Add hospital at N_2_2
    hosp = Hospital(
        id="HOSP-01",
        name="City Hospital",
        node_id="N_2_2",
        location=graph.nodes["N_2_2"].world_pos,
        total_beds=8,
        occupied_beds=4,
        vacant_beds=4,
        capabilities=["cpr", "trauma", "icu"]
    )
    state.hospitals[hosp.id] = hosp

    # Deploy ALS ambulance at N_1_1
    amb = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_1_1"].world_pos,
        capabilities=["cpr", "oxygen", "trauma", "defibrillator"],
        speed_mps=20.0
    )
    state.fleet[amb.id] = amb

    return state, engine, graph

def test_full_mission_lifecycle(lifecycle_setup):
    state, engine, graph = lifecycle_setup
    amb = state.fleet["AMB-01"]
    hosp = state.hospitals["HOSP-01"]

    # 1. Report Emergency incident at N_1_2
    incident = EmergencyIncident(
        id="INC-555",
        location=graph.nodes["N_1_2"].world_pos,
        nearest_node_id="N_1_2",
        severity=EmergencySeverity.MEDIUM,
        required_capabilities=["cpr", "trauma"],
        status=IncidentStatus.WAITING_DISPATCH
    )
    state.emergencies[incident.id] = incident

    # Step simulation: PatientLifecycle should dispatch AMB-01
    engine.update(0.1)
    assert incident.status == IncidentStatus.EN_ROUTE
    assert amb.status == AmbulanceStatus.EN_ROUTE
    assert amb.assigned_emergency_id == "INC-555"
    assert amb.id in state.active_routes

    # Step simulation until ambulance arrives on scene at N_1_2
    for _ in range(60):
        engine.update(0.1)
        if amb.status == AmbulanceStatus.ON_SCENE:
            break

    assert amb.status == AmbulanceStatus.ON_SCENE
    assert incident.status == IncidentStatus.ON_SCENE

    # Step simulation through triage delay (~2.5s) to reach PATIENT_ONBOARD & hospital routing
    for _ in range(40):
        engine.update(0.1)
        if amb.status == AmbulanceStatus.TRANSPORTING:
            break

    assert amb.status == AmbulanceStatus.TRANSPORTING
    assert incident.status == IncidentStatus.TRANSPORTING
    assert amb.assigned_hospital_id == "HOSP-01"
    # Bed was reserved
    assert "INC-555" in hosp.reserved_patient_ids

    # Step simulation until ambulance reaches hospital N_2_2
    for _ in range(80):
        engine.update(0.1)
        if amb.status == AmbulanceStatus.AVAILABLE:
            break

    # Final state: mission completed, patient admitted, bed count updated
    assert amb.status == AmbulanceStatus.AVAILABLE
    assert incident.status == IncidentStatus.COMPLETED
    assert amb.total_missions_completed == 1
    # Check patient admission
    assert "INC-555" not in hosp.reserved_patient_ids
    assert hosp.occupied_beds == 5
    assert hosp.vacant_beds == 3
    assert hosp.total_beds == 8

def test_single_waypoint_route_no_index_error(lifecycle_setup):
    """Verify that when origin == destination (1 waypoint), no list index out of range occurs."""
    from src.models.route import Route
    state, engine, graph = lifecycle_setup
    amb = state.fleet["AMB-01"]
    amb.status = AmbulanceStatus.EN_ROUTE

    # Single-waypoint route
    single_route = Route(
        id="R_SINGLE",
        origin_node_id="N_1_1",
        destination_node_id="N_1_1",
        destination_title="Target",
        waypoints=[graph.nodes["N_1_1"].world_pos]
    )
    state.active_routes[amb.id] = single_route
    amb.active_route_id = single_route.id

    # Must step cleanly without IndexError
    update_ambulance_movement(state, 0.05)
    engine.update(0.05)

