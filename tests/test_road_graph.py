"""Tests for RoadGraph generation, connectivity, and coordinate alignment."""
import pytest

from src.world.city_generator import CityGenerator
from src.world.world_coordinates import CoordinateConverter


def test_coordinate_converter():
    conv = CoordinateConverter(grid_width=8, grid_height=8, block_size=28.0)
    # Check node id naming
    assert conv.node_id(2, 3) == "N_2_3"
    
    # Check roundtrip
    world_pos = conv.grid_to_world(4, 4)
    gx, gy = conv.world_to_grid(world_pos[0], world_pos[1])
    assert gx == 4
    assert gy == 4

def test_road_graph_generation():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()

    # 8x8 grid has 64 intersection nodes
    assert len(graph.nodes) == 64
    assert "N_0_0" in graph.nodes
    assert "N_7_7" in graph.nodes

    # Check bidirectional connectivity
    edge_id = "E_N_0_0_N_1_0"
    rev_edge_id = "E_N_1_0_N_0_0"
    assert edge_id in graph.edges
    assert rev_edge_id in graph.edges
    assert graph.edges[edge_id].length_meters == pytest.approx(28.0)

def test_road_closures_and_congestion():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    edge_id = "E_N_2_2_N_3_2"

    # Close edge
    ok = graph.set_edge_closed(edge_id, True, incident_id="INC-01")
    assert ok is True
    assert graph.edges[edge_id].is_closed is True
    assert graph.edges["E_N_3_2_N_2_2"].is_closed is True
    assert graph.edges[edge_id].travel_time_sec == float("inf")

    # Clear edge
    graph.clear_edge_incident(edge_id)
    assert graph.edges[edge_id].is_closed is False
    assert graph.edges["E_N_3_2_N_2_2"].is_closed is False
    assert graph.edges[edge_id].travel_time_sec < float("inf")

def test_is_on_drivable_road():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    conv = CoordinateConverter(grid_width=8, grid_height=8, block_size=28.0)

    # Center of node N_2_2 is on drivable road
    pos = conv.grid_to_world(2, 2)
    on_road, _ = graph.is_on_drivable_road(pos[0], pos[1], tolerance=4.0)
    assert on_road is True

    # Center of a city block (far off road) is NOT drivable
    p1 = conv.grid_to_world(2, 2)
    p2 = conv.grid_to_world(3, 3)
    block_center_x = (p1[0] + p2[0]) / 2.0
    block_center_y = (p1[1] + p2[1]) / 2.0
    on_road_far, _ = graph.is_on_drivable_road(block_center_x, block_center_y, tolerance=3.5)
    assert on_road_far is False
