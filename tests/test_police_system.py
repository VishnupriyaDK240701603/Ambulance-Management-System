"""Tests for traffic police notification, operational clearance confirmation, and automated timeout rejection."""
import pytest

from src.algorithms.astar import AStarPathfinder
from src.models.police_unit import PoliceStatus, PoliceUnit
from src.models.road_incident import IncidentType
from src.simulation.commands import (
    AcceptPoliceDispatchCommand,
    PlaceRoadIncidentCommand,
    ReAlertPoliceDispatchCommand,
    RejectPoliceDispatchCommand,
)
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState
from src.systems.police_system import update_police_system
from src.world.city_generator import CityGenerator


@pytest.fixture
def police_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph, is_started=True)
    engine = SimulationEngine(state, fixed_dt=0.05)
    engine.register_subsystem(update_police_system)
    pathfinder = AStarPathfinder(graph)

    # Initial stationing of Traffic Police Department desk
    police = PoliceUnit(
        id="POLICE-01",
        position=graph.nodes["N_1_2"].world_pos,
        status=PoliceStatus.IDLE,
        response_deadline_sec=20.0
    )
    state.police_units[police.id] = police

    return state, engine, graph, pathfinder, police

def test_automatic_police_dispatch_alert_on_road_incident(police_setup):
    """Verify that placing any traffic hazard automatically alerts POLICE-01 without manual sending."""
    _state, engine, graph, _, police = police_setup

    assert police.status == PoliceStatus.IDLE
    assert police.notification_received is False

    # Place a roadblock using authoritative command
    cmd = PlaceRoadIncidentCommand(
        incident_id="HAZ-AUTO-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_2_2_N_3_2",
        position=graph.nodes["N_2_2"].world_pos
    )
    ok, msg = engine.execute_command(cmd)
    assert ok is True

    # Check that Traffic Police received the notification automatically
    assert police.notification_received is True
    assert police.status == PoliceStatus.REQUESTED
    assert police.assigned_incident_id == "HAZ-AUTO-01"
    assert police.response_deadline_sec == 20.0
    assert "Automatically sent dispatch notification to Traffic Police (P-01)!" in msg

def test_police_confirm_cleared_reopens_road_immediately(police_setup):
    """Verify that police confirming 'CLEARED' immediately opens the road and resets status without driving a vehicle."""
    _state, engine, graph, _, police = police_setup

    # Place hazard
    cmd_place = PlaceRoadIncidentCommand(
        incident_id="HAZ-ACCEPT-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_2_2_N_3_2",
        position=graph.nodes["N_2_2"].world_pos
    )
    engine.execute_command(cmd_place)
    assert police.status == PoliceStatus.REQUESTED
    assert graph.edges["E_N_2_2_N_3_2"].is_closed is True

    # Police confirms cleared (Accept)
    cmd_accept = AcceptPoliceDispatchCommand(police_id="POLICE-01")
    ok, msg = engine.execute_command(cmd_accept)
    assert ok is True
    assert "CLEARED! Road reopened." in msg

    # Road is immediately reopened and police is reset to IDLE standing by
    assert graph.edges["E_N_2_2_N_3_2"].is_closed is False
    assert police.status == PoliceStatus.IDLE
    assert police.assigned_incident_id is None
    assert police.notification_received is False

def test_police_cannot_clear_leaves_road_closed(police_setup):
    """Verify that police reporting 'CANNOT CLEAR' (Rejected) leaves the road closed."""
    _state, engine, graph, _, police = police_setup

    cmd_place = PlaceRoadIncidentCommand(
        incident_id="HAZ-REJECT-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_2_2_N_3_2",
        position=graph.nodes["N_2_2"].world_pos
    )
    engine.execute_command(cmd_place)

    # Police reports cannot clear
    cmd_reject = RejectPoliceDispatchCommand(police_id="POLICE-01", reason="Heavy debris requiring municipal crane")
    ok, _msg = engine.execute_command(cmd_reject)
    assert ok is True
    assert police.status == PoliceStatus.REJECTED
    assert police.rejection_reason == "Heavy debris requiring municipal crane"
    # Road MUST remain closed
    assert graph.edges["E_N_2_2_N_3_2"].is_closed is True

def test_police_automatic_rejection_when_time_limit_exceeded(police_setup):
    """Verify that if police does not clear within the 20s time limit, it is automatically REJECTED."""
    _state, engine, graph, _, police = police_setup

    cmd_place = PlaceRoadIncidentCommand(
        incident_id="HAZ-TIMEOUT-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_2_2_N_3_2",
        position=graph.nodes["N_2_2"].world_pos
    )
    engine.execute_command(cmd_place)
    assert police.status == PoliceStatus.REQUESTED

    # Advance time past the 20.0s deadline (21 seconds)
    for _ in range(210):
        engine.update(0.1)

    # Status must automatically become REJECTED with timeout explanation
    assert police.status == PoliceStatus.REJECTED
    assert "exceeded" in police.rejection_reason.lower()
    assert "automatically rejected" in police.rejection_reason.lower()
    # Road MUST remain closed
    assert graph.edges["E_N_2_2_N_3_2"].is_closed is True

def test_police_re_alert_resets_20s_countdown(police_setup):
    """Verify re-alerting police resets status to REQUESTED with a fresh 20-second window."""
    _state, engine, graph, _, police = police_setup

    cmd_place = PlaceRoadIncidentCommand(
        incident_id="HAZ-REALERT-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_2_2_N_3_2",
        position=graph.nodes["N_2_2"].world_pos
    )
    engine.execute_command(cmd_place)

    # Reject first
    engine.execute_command(RejectPoliceDispatchCommand(police_id="POLICE-01"))
    assert police.status == PoliceStatus.REJECTED

    # Re-alert police
    cmd_realert = ReAlertPoliceDispatchCommand(police_id="POLICE-01")
    ok, _msg = engine.execute_command(cmd_realert)
    assert ok is True
    assert police.status == PoliceStatus.REQUESTED
    assert police.notification_received is True
    assert police.rejection_reason is None
    assert police.response_deadline_sec == 20.0
