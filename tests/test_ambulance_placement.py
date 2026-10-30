"""Tests for ambulance placement, initial limits, and capability validation."""
import pytest

from src.models.ambulance import Ambulance, AmbulanceClass, AmbulanceStatus
from src.simulation.commands import DeployAmbulanceCommand
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import CityGenerator
from src.world.world_coordinates import CoordinateConverter


@pytest.fixture
def sim_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    conv = CoordinateConverter(grid_width=8, grid_height=8, block_size=28.0)
    state = SimulationState(road_graph=graph, deployment_limit=2)
    engine = SimulationEngine(state)
    return state, engine, conv, graph

def test_initial_fleet_is_zero(sim_setup):
    state, _engine, _conv, _graph = sim_setup
    assert len(state.fleet) == 0
    assert state.available_ambulances_count == 0

def test_deploy_ambulance_valid(sim_setup):
    state, engine, conv, _graph = sim_setup
    pos1 = conv.grid_to_world(1, 1)

    cmd = DeployAmbulanceCommand(
        unit_id="AMB-BLS-01",
        unit_class=AmbulanceClass.BLS,
        position=pos1,
        capabilities=["cpr", "oxygen", "basic_first_aid"]
    )
    ok, _msg = engine.execute_command(cmd)
    assert ok is True
    assert len(state.fleet) == 1
    assert "AMB-BLS-01" in state.fleet
    assert state.fleet["AMB-BLS-01"].status == AmbulanceStatus.AVAILABLE

def test_enforce_two_unit_deployment_limit(sim_setup):
    state, engine, conv, _graph = sim_setup
    pos1 = conv.grid_to_world(1, 1)
    pos2 = conv.grid_to_world(2, 2)
    pos3 = conv.grid_to_world(3, 3)

    # Unit 1
    ok1, _ = engine.execute_command(DeployAmbulanceCommand("AMB-1", AmbulanceClass.BLS, pos1))
    assert ok1 is True

    # Unit 2
    ok2, _ = engine.execute_command(DeployAmbulanceCommand("AMB-2", AmbulanceClass.ALS, pos2))
    assert ok2 is True

    # Unit 3 should fail due to deployment_limit = 2
    ok3, msg3 = engine.execute_command(DeployAmbulanceCommand("AMB-3", AmbulanceClass.CCT, pos3))
    assert ok3 is False
    assert "limit reached" in msg3.lower()
    assert len(state.fleet) == 2
    assert "AMB-3" not in state.fleet  # No ghost unit created

def test_reject_off_road_deployment(sim_setup):
    state, engine, conv, _graph = sim_setup
    # Inside a building block, not on road
    p1 = conv.grid_to_world(2, 2)
    p2 = conv.grid_to_world(3, 3)
    block_center = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0, 0.0)

    cmd = DeployAmbulanceCommand("AMB-GHOST", AmbulanceClass.BLS, block_center)
    ok, msg = engine.execute_command(cmd)
    assert ok is False
    assert "invalid deployment location" in msg.lower()
    assert len(state.fleet) == 0

def test_reject_overlapping_deployment(sim_setup):
    state, engine, conv, _graph = sim_setup
    pos = conv.grid_to_world(1, 1)

    ok1, _ = engine.execute_command(DeployAmbulanceCommand("AMB-1", AmbulanceClass.BLS, pos))
    assert ok1 is True

    # Same location (overlap < 4.0m)
    overlap_pos = (pos[0] + 1.0, pos[1], pos[2])
    ok2, msg2 = engine.execute_command(DeployAmbulanceCommand("AMB-2", AmbulanceClass.ALS, overlap_pos))
    assert ok2 is False
    assert "overlaps" in msg2.lower()
    assert len(state.fleet) == 1

def test_distinct_capabilities_matrix():
    bls = Ambulance(
        id="B1",
        unit_class=AmbulanceClass.BLS,
        position=(0, 0, 0),
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting"]
    )
    als = Ambulance(
        id="A1",
        unit_class=AmbulanceClass.ALS,
        position=(0, 0, 0),
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting", "iv_access", "intubation", "defibrillator"]
    )
    cct = Ambulance(
        id="C1",
        unit_class=AmbulanceClass.CCT,
        position=(0, 0, 0),
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting", "iv_access", "intubation", "defibrillator", "ventilator", "ecmo"]
    )

    # BLS can handle minor
    ok, _ = bls.is_eligible_for(["cpr", "oxygen"])
    assert ok is True

    # BLS cannot handle cardiac/intubation
    ok, reason = bls.is_eligible_for(["cpr", "defibrillator"])
    assert ok is False
    assert "Missing" in reason

    # ALS can handle defibrillator
    ok, _ = als.is_eligible_for(["cpr", "defibrillator"])
    assert ok is True

    # ALS cannot handle ECMO
    ok, _ = als.is_eligible_for(["ecmo"])
    assert ok is False

    # CCT can handle ECMO
    ok, _ = cct.is_eligible_for(["ecmo", "ventilator"])
    assert ok is True

def test_max_ambulance_limit_eight(sim_setup):
    state, engine, conv, _graph = sim_setup
    state.deployment_limit = 8

    # Deploy 8 ambulances at distinct road nodes
    for i in range(8):
        pos = conv.grid_to_world(i % 8, i // 8)
        ok, msg = engine.execute_command(DeployAmbulanceCommand(f"AMB-LIMIT-{i+1}", AmbulanceClass.BLS, pos))
        assert ok is True, f"Failed at {i}: {msg}"

    assert len(state.fleet) == 8

    # 9th ambulance should fail
    pos9 = conv.grid_to_world(0, 2)
    ok9, msg9 = engine.execute_command(DeployAmbulanceCommand("AMB-LIMIT-9", AmbulanceClass.BLS, pos9))
    assert ok9 is False
    assert "limit reached" in msg9.lower()
    assert len(state.fleet) == 8
