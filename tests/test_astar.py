"""Tests for A* pathfinding algorithm on the road network."""
import pytest

from src.algorithms.astar import AStarPathfinder
from src.world.city_generator import CityGenerator


@pytest.fixture
def pathfinder_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    pathfinder = AStarPathfinder(graph)
    return graph, pathfinder

def test_astar_direct_path(pathfinder_setup):
    _graph, pathfinder = pathfinder_setup
    route = pathfinder.find_route("N_0_0", "N_2_0")
    assert route is not None
    assert route.origin_node_id == "N_0_0"
    assert route.destination_node_id == "N_2_0"
    assert route.node_ids == ["N_0_0", "N_1_0", "N_2_0"]
    assert len(route.segments) == 2
    assert route.total_distance_meters == pytest.approx(56.0)
    assert route.estimated_travel_time_sec > 0.0

def test_astar_respects_road_closure(pathfinder_setup):
    graph, pathfinder = pathfinder_setup
    # Normal route
    route_orig = pathfinder.find_route("N_0_0", "N_2_0")
    assert "N_1_0" in route_orig.node_ids

    # Close the direct edge E_N_0_0_N_1_0
    graph.set_edge_closed("E_N_0_0_N_1_0", True)

    # Re-route should find detour via N_0_1
    detour = pathfinder.find_route("N_0_0", "N_2_0")
    assert detour is not None
    assert "E_N_0_0_N_1_0" not in [s.edge_id for s in detour.segments]
    assert detour.node_ids[1] == "N_0_1"
    assert detour.total_distance_meters > route_orig.total_distance_meters

def test_astar_unreachable_returns_none(pathfinder_setup):
    graph, pathfinder = pathfinder_setup
    # Completely isolate N_0_0 by closing all outgoing edges
    for edge_id in list(graph.adjacency["N_0_0"]):
        graph.set_edge_closed(edge_id, True)

    route = pathfinder.find_route("N_0_0", "N_7_7")
    assert route is None

def test_astar_same_origin_destination(pathfinder_setup):
    _graph, pathfinder = pathfinder_setup
    route = pathfinder.find_route("N_3_3", "N_3_3")
    assert route is not None
    assert route.total_distance_meters == 0.0
    assert route.estimated_travel_time_sec == 0.0
