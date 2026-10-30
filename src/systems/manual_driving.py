"""Manual driving controller for user-controlled ambulances with automatic dynamic rerouting."""
from __future__ import annotations

import math
from collections.abc import Callable

from src.algorithms.astar import AStarPathfinder
from src.models.ambulance import Ambulance, ControlMode
from src.models.police_unit import PoliceUnit
from src.models.route import Route
from src.simulation.simulation_state import SimulationState
from src.systems.ambulance_movement import _handle_route_destination_reached


class ManualDrivingController:
    """Handles manual keyboard controls (W/A/S/D) with dynamic off-route auto-rerouting."""

    def __init__(
        self,
        on_reroute: Callable[[str, Route], None] | None = None,
        on_destination_reached: Callable[[str], None] | None = None
    ):
        self.inputs: dict[str, bool] = {
            "forward": False,
            "backward": False,
            "left": False,
            "right": False,
        }
        self.acceleration: float = 14.0
        self.turn_rate_deg: float = 95.0
        self.friction: float = 7.0
        self.on_reroute = on_reroute
        self.on_destination_reached = on_destination_reached
        self.last_reroute_time: dict[str, float] = {}

    def set_input(self, control: str, active: bool) -> None:
        if control in self.inputs:
            self.inputs[control] = active

    def update(self, state: SimulationState, dt: float) -> None:
        """Update physics, position, route tracking, and off-route rerouting for manual ambulances and police."""
        # 1. Update player-controlled police units if active
        for p_unit in state.police_units.values():
            if p_unit.is_player_controlled:
                self._update_police_unit(p_unit, state, dt)

        # 2. Update player-controlled ambulance if active
        if not state.selected_ambulance_id or state.selected_ambulance_id not in state.fleet:
            return

        amb = state.fleet[state.selected_ambulance_id]
        if amb.control_mode != ControlMode.MANUAL:
            return

        # 1. Responsive Steering: Allow steering at rest or in motion
        turn_rate = self.turn_rate_deg
        if abs(amb.current_speed) < 0.5:
            # Low-speed / stationary turning so vehicle never gets trapped against a curb
            turn_dir = 1.0
            turn_rate = self.turn_rate_deg * 0.90
        else:
            turn_dir = 1.0 if amb.current_speed >= 0 else -1.0

        if self.inputs["left"]:
            amb.heading = (amb.heading + turn_rate * dt * turn_dir) % 360.0
        if self.inputs["right"]:
            amb.heading = (amb.heading - turn_rate * dt * turn_dir) % 360.0

        # 2. Acceleration / Braking
        if self.inputs["forward"]:
            amb.current_speed = min(amb.speed_mps, amb.current_speed + self.acceleration * dt)
        elif self.inputs["backward"]:
            amb.current_speed = max(-8.0, amb.current_speed - self.acceleration * dt)
        else:
            # Natural road friction deceleration
            if amb.current_speed > 0:
                amb.current_speed = max(0.0, amb.current_speed - self.friction * dt)
            elif amb.current_speed < 0:
                amb.current_speed = min(0.0, amb.current_speed + self.friction * dt)

        # 3. Heading displacement
        rad = math.radians(amb.heading)
        # Panda3D coordinate convention: 0 is (dx=0, dy=1); 90 is (dx=-1, dy=0)
        move_x = -math.sin(rad) * amb.current_speed * dt
        move_y = math.cos(rad) * amb.current_speed * dt

        candidate_x = amb.position[0] + move_x
        candidate_y = amb.position[1] + move_y

        # 4. Road Bounds Validation (with generous 6.5m corridor)
        is_on_road, _ = state.road_graph.is_on_drivable_road(candidate_x, candidate_y, tolerance=6.5)
        if is_on_road:
            amb.position = (candidate_x, candidate_y, 0.0)
        else:
            # Soft bumper containment: slide along nearest road edge rather than freezing vehicle
            edge, dist, nearest_pt = state.road_graph.find_nearest_edge(candidate_x, candidate_y)
            if edge and not edge.is_closed and dist < 9.0:
                amb.position = (nearest_pt[0], nearest_pt[1], 0.0)
                amb.current_speed *= 0.6
            else:
                amb.current_speed = 0.0

        # 5. Active Route Tracking & Dynamic Auto-Reroute on Deviation
        self._track_route_and_handle_deviations(amb, state)

    def _track_route_and_handle_deviations(self, amb: Ambulance, state: SimulationState) -> None:
        """Check waypoint progression, destination arrival, and detect if driver missed planned path."""
        route = state.active_routes.get(amb.id)
        if not route or not route.waypoints:
            return

        # Distance to destination
        dest_wp = route.waypoints[-1]
        dist_to_dest = math.hypot(dest_wp[0] - amb.position[0], dest_wp[1] - amb.position[1])

        # Check destination arrival
        if dist_to_dest < 4.0:
            _handle_route_destination_reached(amb, route, state)
            if self.on_destination_reached:
                self.on_destination_reached(amb.id)
            return

        # Check waypoint progression along planned path
        wp_idx = min(route.current_segment_index, len(route.waypoints) - 1)
        target_wp = route.waypoints[wp_idx]
        dist_to_wp = math.hypot(target_wp[0] - amb.position[0], target_wp[1] - amb.position[1])

        if dist_to_wp < 3.8 and route.current_segment_index + 1 < len(route.waypoints):
            route.current_segment_index += 1
            wp_idx = route.current_segment_index
            target_wp = route.waypoints[wp_idx]

        # Calculate minimum distance from ambulance position to the remaining route waypoints
        remaining_wps = route.waypoints[route.current_segment_index:]
        min_dist_to_route = min(
            (math.hypot(wp[0] - amb.position[0], wp[1] - amb.position[1]) for wp in remaining_wps),
            default=0.0
        )

        # Check if planned route ahead has become blocked by an obstacle or closure
        remaining_segments = route.segments[route.current_segment_index:]
        is_route_blocked = False
        for s in remaining_segments:
            if s.turn_instruction and "U-turn" in s.turn_instruction:
                continue
            edge = state.road_graph.edges.get(s.edge_id)
            if edge and (edge.is_closed or edge.active_incident_id is not None or edge.speed_factor < 0.6):
                is_route_blocked = True
                break

        # Detect deviation: Driver took wrong turn or drifted > 11.5 meters away or path blocked
        now = state.simulation_time
        last_reroute = self.last_reroute_time.get(amb.id, -999.0)

        if (is_route_blocked or min_dist_to_route > 11.5) and (now - last_reroute) >= 1.0:
            from src.algorithms.traffic_recovery import calculate_dynamic_reroute
            new_route = calculate_dynamic_reroute(amb, route, state)
            if not new_route and route.destination_node_id:
                origin_node = state.road_graph.find_nearest_node(amb.position[0], amb.position[1])
                if origin_node:
                    pathfinder = AStarPathfinder(state.road_graph)
                    new_route = pathfinder.find_route(
                        origin_node_id=origin_node.id,
                        destination_node_id=route.destination_node_id,
                        destination_title=route.destination_title,
                        sim_time=now,
                        vehicle_speed_mps=amb.speed_mps
                    )

            if new_route and new_route.id != route.id:
                # Update active route immediately!
                state.active_routes[amb.id] = new_route
                amb.active_route_id = new_route.id
                self.last_reroute_time[amb.id] = now
                state.increment_version()

                if self.on_reroute:
                    self.on_reroute(amb.id, new_route)

    def _update_police_unit(self, p_unit: PoliceUnit, state: SimulationState, dt: float) -> None:
        """Process keyboard driving physics and scene clearance for player-controlled police cruiser."""
        turn_rate = self.turn_rate_deg
        if abs(p_unit.current_speed) < 0.5:
            turn_dir = 1.0
            turn_rate = self.turn_rate_deg * 0.90
        else:
            turn_dir = 1.0 if p_unit.current_speed >= 0 else -1.0

        if self.inputs["left"]:
            p_unit.heading = (p_unit.heading + turn_rate * dt * turn_dir) % 360.0
        if self.inputs["right"]:
            p_unit.heading = (p_unit.heading - turn_rate * dt * turn_dir) % 360.0

        if self.inputs["forward"]:
            p_unit.current_speed = min(p_unit.speed_mps, p_unit.current_speed + self.acceleration * dt)
        elif self.inputs["backward"]:
            p_unit.current_speed = max(-8.0, p_unit.current_speed - self.acceleration * dt)
        else:
            if p_unit.current_speed > 0:
                p_unit.current_speed = max(0.0, p_unit.current_speed - self.friction * dt)
            elif p_unit.current_speed < 0:
                p_unit.current_speed = min(0.0, p_unit.current_speed + self.friction * dt)

        rad = math.radians(p_unit.heading)
        move_x = -math.sin(rad) * p_unit.current_speed * dt
        move_y = math.cos(rad) * p_unit.current_speed * dt

        cand_x = p_unit.position[0] + move_x
        cand_y = p_unit.position[1] + move_y

        is_on_road, _ = state.road_graph.is_on_drivable_road(cand_x, cand_y, tolerance=6.5)
        if is_on_road:
            p_unit.position = (cand_x, cand_y, 0.0)
        else:
            edge, dist, nearest_pt = state.road_graph.find_nearest_edge(cand_x, cand_y)
            if edge and dist < 9.0:
                p_unit.position = (nearest_pt[0], nearest_pt[1], 0.0)
                p_unit.current_speed *= 0.6
            else:
                p_unit.current_speed = 0.0

        # Check proximity to assigned incident for on-scene manual clearance
        if p_unit.assigned_incident_id and p_unit.assigned_incident_id in state.road_incidents:
            inc = state.road_incidents[p_unit.assigned_incident_id]
            dist_inc = math.hypot(p_unit.position[0] - inc.position[0], p_unit.position[1] - inc.position[1])
            if dist_inc < 5.0:
                from src.models.police_unit import PoliceStatus
                p_unit.status = PoliceStatus.CLEARING
                p_unit.clearance_progress += dt / max(1.0, p_unit.clearance_duration)
                if p_unit.clearance_progress >= 1.0:
                    from src.simulation.commands import ClearRoadIncidentCommand
                    ClearRoadIncidentCommand(inc.id).execute(state)
