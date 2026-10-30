"""Tests for simulation lifecycle: Start, Pause, Resume, Reset."""
import pytest

from src.models.ambulance import AmbulanceClass
from src.simulation.commands import (
    DeployAmbulanceCommand,
    PauseSimulationCommand,
    ResetSimulationCommand,
    ResumeSimulationCommand,
    StartSimulationCommand,
)
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
    return state, engine, conv

def test_start_pause_resume_lifecycle(sim_setup):
    state, engine, _conv = sim_setup
    assert not state.is_started
    assert not state.is_paused

    # Cannot pause before starting
    ok_pause_early, _ = engine.execute_command(PauseSimulationCommand())
    assert ok_pause_early is False

    # Start simulation
    ok_start, _ = engine.execute_command(StartSimulationCommand())
    assert ok_start is True
    assert state.is_started is True
    assert state.is_paused is False

    # Pause
    ok_pause, _ = engine.execute_command(PauseSimulationCommand())
    assert ok_pause is True
    assert state.is_paused is True

    # Advance time while paused: simulation_time must NOT advance
    engine.update(1.0)
    assert state.simulation_time == 0.0

    # Resume
    ok_resume, _ = engine.execute_command(ResumeSimulationCommand())
    assert ok_resume is True
    assert state.is_paused is False

    # Advance time while running: simulation_time advances
    engine.update(0.1)
    assert state.simulation_time > 0.0

def test_reset_lifecycle(sim_setup):
    state, engine, conv = sim_setup
    pos = conv.grid_to_world(1, 1)

    # Deploy ambulance and start
    engine.execute_command(DeployAmbulanceCommand("AMB-1", AmbulanceClass.BLS, pos))
    engine.execute_command(StartSimulationCommand())
    engine.update(1.0)

    assert len(state.fleet) == 1
    assert state.simulation_time > 0.0

    # Reset
    ok_reset, _ = engine.execute_command(ResetSimulationCommand())
    assert ok_reset is True
    assert len(state.fleet) == 0
    assert state.simulation_time == 0.0
    assert not state.is_started
    assert not state.is_paused
