"""Tests for manual driving physics, WASD inputs, and road constraints."""
import pytest

from src.models.ambulance import Ambulance, AmbulanceClass, ControlMode
from src.simulation.simulation_state import SimulationState
from src.systems.manual_driving import ManualDrivingController
from src.world.city_generator import CityGenerator


@pytest.fixture
def manual_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph, is_started=True)
    driver = ManualDrivingController()

    # Place ambulance on road at center of node N_2_2
    pos = graph.nodes["N_2_2"].world_pos
    amb = Ambulance(
        id="AMB-MANUAL",
        unit_class=AmbulanceClass.ALS,
        position=pos,
        heading=0.0,
        control_mode=ControlMode.MANUAL,
        speed_mps=15.0
    )
    state.fleet[amb.id] = amb
    state.selected_ambulance_id = amb.id

    return state, driver, graph

def test_manual_forward_acceleration(manual_setup):
    state, driver, _graph = manual_setup
    amb = state.fleet["AMB-MANUAL"]
    initial_y = amb.position[1]

    # Press forward (W)
    driver.set_input("forward", True)
    for _ in range(10):
        driver.update(state, 0.05)

    assert amb.current_speed > 0.0
    assert amb.position[1] > initial_y  # Moved forward in +Y direction

def test_manual_steering(manual_setup):
    state, driver, _graph = manual_setup
    amb = state.fleet["AMB-MANUAL"]
    amb.current_speed = 5.0  # Moving vehicle
    initial_heading = amb.heading

    # Steer left (A)
    driver.set_input("left", True)
    driver.update(state, 0.1)

    assert amb.heading != initial_heading

def test_manual_stationary_steering(manual_setup):
    """Ensure vehicle can turn its wheels / heading even when stopped at 0 speed."""
    state, driver, _graph = manual_setup
    amb = state.fleet["AMB-MANUAL"]
    amb.current_speed = 0.0
    initial_heading = amb.heading

    # Steer right (D) while stopped
    driver.set_input("right", True)
    driver.update(state, 0.1)

    assert amb.heading != initial_heading

def test_manual_auto_reroute_on_path_deviation(manual_setup):
    """Ensure that if the driver deviates / fails to follow the planned path, it auto-reroutes."""
    from src.algorithms.astar import AStarPathfinder
    state, driver, graph = manual_setup
    amb = state.fleet["AMB-MANUAL"]

    reroutes_recorded = []
    driver.on_reroute = lambda amb_id, rt: reroutes_recorded.append((amb_id, rt))

    # Create initial route from N_2_2 to N_2_5 (straight North)
    pathfinder = AStarPathfinder(graph)
    initial_route = pathfinder.find_route("N_2_2", "N_2_5", destination_title="North Clinic")
    assert initial_route is not None

    state.active_routes[amb.id] = initial_route
    amb.active_route_id = initial_route.id

    # Simulate driver turning East instead of following North path
    # Move ambulance east towards N_3_2 (> 15m away from N_2_2->N_2_5 path)
    east_pos = graph.nodes["N_3_2"].world_pos
    amb.position = east_pos
    state.simulation_time = 2.0

    # Call driver update
    driver.update(state, 0.1)

    # Verify that an automatic reroute was triggered!
    assert len(reroutes_recorded) > 0
    new_amb_id, new_route = reroutes_recorded[0]
    assert new_amb_id == amb.id
    assert new_route.destination_node_id == "N_2_5"
    assert new_route.origin_node_id == "N_3_2"  # New route recalculated from current position!
