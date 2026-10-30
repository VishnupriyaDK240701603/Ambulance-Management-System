"""Tests for traffic recovery and Can't Proceed algorithmic decision making."""
import pytest

from src.algorithms.astar import AStarPathfinder
from src.algorithms.traffic_recovery import TrafficRecoveryAlgorithm
from src.models.ambulance import Ambulance, AmbulanceClass
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import CityGenerator


@pytest.fixture
def recovery_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph)
    algo = TrafficRecoveryAlgorithm()
    pathfinder = AStarPathfinder(graph)
    return state, algo, graph, pathfinder

def test_cant_proceed_triggers_reroute_when_beneficial(recovery_setup):
    state, algo, graph, pathfinder = recovery_setup

    amb = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_0_0"].world_pos
    )
    state.fleet[amb.id] = amb

    # Initial route from N_0_0 to N_4_0
    route = pathfinder.find_route("N_0_0", "N_4_0")
    state.active_routes[amb.id] = route

    # Block direct road ahead E_N_1_0_N_2_0
    graph.set_edge_closed("E_N_1_0_N_2_0", True)

    action, new_route, dec = algo.evaluate_recovery(amb, route, state)

    # Detour is fast and unblocked: algorithm should choose REROUTE
    assert action == "REROUTE"
    assert new_route is not None
    assert "E_N_1_0_N_2_0" not in [s.edge_id for s in new_route.segments]
    assert dec.decision_type.value == "TRAFFIC_RECOVERY"
    assert "Rerouting selected" in dec.reasoning_summary

def test_recovery_handles_no_alternative(recovery_setup):
    state, algo, graph, pathfinder = recovery_setup

    amb = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_0_0"].world_pos
    )
    state.fleet[amb.id] = amb
    route = pathfinder.find_route("N_0_0", "N_2_0")
    state.active_routes[amb.id] = route

    # Close all edges leaving N_0_0 so no detour exists
    for e_id in list(graph.adjacency["N_0_0"]):
        graph.set_edge_closed(e_id, True)

    action, new_route, dec = algo.evaluate_recovery(amb, route, state)
    assert action == "WAIT_FOR_POLICE"
    assert new_route is None
    assert "No alternative route" in dec.reasoning_summary

def test_dynamic_roadblock_placement_automatically_reroutes_active_ambulance(recovery_setup):
    """Verify that placing a dynamic obstacle immediately auto-reroutes active ambulances."""
    from src.models.road_incident import IncidentType
    from src.simulation.commands import PlaceRoadIncidentCommand
    from src.systems.ambulance_movement import update_ambulance_movement

    state, _algo, graph, pathfinder = recovery_setup
    state.is_started = True

    # Ambulance at N_0_0 dispatched to N_3_0 along horizontal edge
    amb = Ambulance(
        id="AMB-AUTO-REROUTE",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_0_0"].world_pos,
        speed_mps=15.0
    )
    state.fleet[amb.id] = amb
    initial_route = pathfinder.find_route("N_0_0", "N_3_0", destination_title="Target Scene")
    assert initial_route is not None
    state.active_routes[amb.id] = initial_route
    amb.active_route_id = initial_route.id

    # Place a ROADBLOCK obstacle right on edge E_N_1_0_N_2_0
    cmd = PlaceRoadIncidentCommand(
        incident_id="HAZ-TEST-01",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_1_0_N_2_0",
        position=graph.nodes["N_1_0"].world_pos
    )
    ok, _msg, _ = cmd.execute(state)
    assert ok is True

    # Verify that the ambulance's active route was IMMEDIATELY auto-rerouted!
    updated_route = state.active_routes[amb.id]
    assert updated_route.id != initial_route.id
    assert "E_N_1_0_N_2_0" not in [s.edge_id for s in updated_route.segments]

    # Verify movement proceeds along the new detour
    from src.models.ambulance import AmbulanceStatus
    amb.status = AmbulanceStatus.EN_ROUTE
    update_ambulance_movement(state, 0.1)
    assert amb.current_speed > 0.0

def test_multi_ambulance_deadlock_prevention(recovery_setup):
    """Verify that two ambulances close to each other do not mutually freeze each other."""
    from src.models.ambulance import AmbulanceStatus
    from src.systems.ambulance_movement import update_ambulance_movement

    state, _algo, graph, pathfinder = recovery_setup
    state.is_started = True

    # Amb 1 parked on scene at N_1_1
    amb1 = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_1_1"].world_pos,
        status=AmbulanceStatus.ON_SCENE,
        speed_mps=15.0
    )
    # Amb 2 driving past N_1_1 en route to N_1_3
    amb2 = Ambulance(
        id="AMB-02",
        unit_class=AmbulanceClass.BLS,
        position=(amb1.position[0], amb1.position[1] - 1.5, 0.0), # 1.5m away
        status=AmbulanceStatus.EN_ROUTE,
        speed_mps=14.0
    )
    route2 = pathfinder.find_route("N_1_1", "N_1_3")
    assert route2 is not None
    state.active_routes[amb2.id] = route2
    amb2.active_route_id = route2.id

    state.fleet[amb1.id] = amb1
    state.fleet[amb2.id] = amb2

    # Step movement
    update_ambulance_movement(state, 0.1)

    # Amb 2 should NOT be frozen at 0 speed; it slows to caution speed and continues passing!
    assert amb2.current_speed > 0.0
    assert amb2.current_speed <= 4.5

def test_roadblock_on_current_segment_triggers_uturn_reroute(recovery_setup):
    """Verify that placing a roadblock on the ambulance's active road causes a safe U-turn reroute."""
    from src.models.ambulance import AmbulanceStatus
    from src.models.road_incident import IncidentType
    from src.simulation.commands import PlaceRoadIncidentCommand
    from src.systems.ambulance_movement import update_ambulance_movement

    state, _algo, graph, pathfinder = recovery_setup
    state.is_started = True

    route = pathfinder.find_route("N_1_1", "N_1_5", destination_title="North Hospital")
    assert route is not None
    # Ambulance is halfway between N_1_1 and N_1_2 on edge E_N_1_1_N_1_2
    mid_y = (graph.nodes["N_1_1"].world_pos[1] + graph.nodes["N_1_2"].world_pos[1]) / 2.0
    amb = Ambulance(
        id="AMB-CURR-BLOCK",
        unit_class=AmbulanceClass.ALS,
        position=(graph.nodes["N_1_1"].world_pos[0], mid_y, 0.0),
        status=AmbulanceStatus.EN_ROUTE,
        speed_mps=15.0
    )
    state.fleet[amb.id] = amb
    state.active_routes[amb.id] = route
    amb.active_route_id = route.id

    # Place complete roadblock on the ambulance's CURRENT road
    cmd = PlaceRoadIncidentCommand(
        incident_id="HAZ-BLOCK-ACTIVE",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_1_1_N_1_2",
        position=amb.position
    )
    ok, _msg, _ = cmd.execute(state)
    assert ok is True

    # The ambulance active route should be immediately rerouted with a U-turn
    new_route = state.active_routes[amb.id]
    assert "U-turn" in new_route.segments[0].turn_instruction
    assert "E_N_1_1_N_1_2" not in [s.edge_id for s in new_route.segments[1:]]

    # Verify that moving advances toward the U-turn junction (N_1_1)
    target_wp = new_route.waypoints[1]
    assert target_wp == graph.nodes["N_1_1"].world_pos
    update_ambulance_movement(state, 0.1)
    assert amb.current_speed > 0.0

def test_roadblock_on_upcoming_segment_preserves_road_and_detours_at_junction(recovery_setup):
    """Verify that placing a roadblock on an upcoming road ahead detours cleanly at the junction."""
    from src.models.ambulance import AmbulanceStatus
    from src.models.road_incident import IncidentType
    from src.simulation.commands import PlaceRoadIncidentCommand
    from src.systems.ambulance_movement import update_ambulance_movement

    state, _algo, graph, pathfinder = recovery_setup
    state.is_started = True

    route = pathfinder.find_route("N_1_1", "N_1_5", destination_title="North Hospital")
    assert route is not None
    # Ambulance on segment 0 (E_N_1_1_N_1_2)
    p_from = graph.nodes["N_1_1"].world_pos
    amb = Ambulance(
        id="AMB-AHEAD-BLOCK",
        unit_class=AmbulanceClass.ALS,
        position=(p_from[0], p_from[1] + 5.0, 0.0),
        status=AmbulanceStatus.EN_ROUTE,
        speed_mps=15.0
    )
    state.fleet[amb.id] = amb
    state.active_routes[amb.id] = route
    amb.active_route_id = route.id

    # Place roadblock on edge E_N_1_2_N_1_3 (the road ahead after N_1_2)
    cmd = PlaceRoadIncidentCommand(
        incident_id="HAZ-BLOCK-AHEAD",
        incident_type=IncidentType.ROADBLOCK,
        edge_id="E_N_1_2_N_1_3",
        position=graph.nodes["N_1_2"].world_pos
    )
    ok, _msg, _ = cmd.execute(state)
    assert ok is True

    new_route = state.active_routes[amb.id]
    # Current segment E_N_1_1_N_1_2 is preserved to reach the junction
    assert new_route.segments[0].edge_id == "E_N_1_1_N_1_2"
    # The blocked road is completely excluded from the rest of the detour
    assert "E_N_1_2_N_1_3" not in [s.edge_id for s in new_route.segments]
    # Target waypoint 1 is the junction N_1_2
    assert new_route.waypoints[1] == graph.nodes["N_1_2"].world_pos

    update_ambulance_movement(state, 0.1)
    assert amb.current_speed > 0.0

def test_intersection_cross_traffic_collision_prevention(recovery_setup):
    """Verify that two ambulances crossing perpendicularly at a 4-way intersection yield safely and never collide."""
    import math

    from src.models.ambulance import AmbulanceStatus
    from src.systems.ambulance_movement import update_ambulance_movement

    state, _algo, graph, pathfinder = recovery_setup
    state.is_started = True

    # Amb 1 travels East from N_1_2 to N_3_2 (crosses through junction N_2_2)
    amb1 = Ambulance(
        id="AMB-CROSS-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_1_2"].world_pos,
        status=AmbulanceStatus.EN_ROUTE,
        speed_mps=15.0
    )
    route1 = pathfinder.find_route("N_1_2", "N_3_2")
    assert route1 is not None
    state.active_routes[amb1.id] = route1
    amb1.active_route_id = route1.id

    # Amb 2 travels North from N_2_1 to N_2_3 (crosses through junction N_2_2 perpendicularly!)
    amb2 = Ambulance(
        id="AMB-CROSS-02",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_2_1"].world_pos,
        status=AmbulanceStatus.EN_ROUTE,
        speed_mps=14.0
    )
    route2 = pathfinder.find_route("N_2_1", "N_2_3")
    assert route2 is not None
    state.active_routes[amb2.id] = route2
    amb2.active_route_id = route2.id

    state.fleet[amb1.id] = amb1
    state.fleet[amb2.id] = amb2

    min_separation = 999.0

    # Step simulation through intersection traversal (80 steps = 4.0 seconds)
    for _ in range(80):
        update_ambulance_movement(state, 0.05)
        d = math.hypot(amb1.position[0] - amb2.position[0], amb1.position[1] - amb2.position[1])
        min_separation = min(min_separation, d)

    # Minimum separation must NEVER breach vehicle collision boundary (4.0m)
    assert min_separation >= 4.0
    # Both vehicles should successfully progress without being permanently deadlocked
    assert amb1.position != graph.nodes["N_1_2"].world_pos
    assert amb2.position != graph.nodes["N_2_1"].world_pos


