"""Autonomous AI ambulance movement subsystem with dynamic obstacle avoidance and anti-deadlock traffic rules."""
from __future__ import annotations

import math

from src.models.ambulance import Ambulance, AmbulanceStatus, ControlMode
from src.models.emergency import IncidentStatus
from src.models.route import Route
from src.simulation.simulation_state import SimulationState


def update_ambulance_movement(state: SimulationState, dt: float) -> None:
    """Subsystem update: advance autonomous ambulances along their active routes with automatic obstacle avoidance."""
    for amb in list(state.fleet.values()):
        if amb.control_mode == ControlMode.MANUAL:
            continue  # Handled by manual driving system

        route = state.active_routes.get(amb.id)
        if not route or not route.waypoints:
            amb.current_speed = 0.0
            continue

        # If vehicle is already at destination node (single waypoint route)
        if len(route.waypoints) <= 1:
            _handle_route_destination_reached(amb, route, state)
            continue

        # Check if the ambulance is in a moving operational state
        if amb.status not in (AmbulanceStatus.EN_ROUTE, AmbulanceStatus.TRANSPORTING):
            amb.current_speed = 0.0
            continue

        # Current waypoint target (index 1 to len(waypoints)-1)
        # Segment i connects waypoints[i] to waypoints[i+1]
        target_wp_idx = min(max(1, route.current_segment_index + 1), len(route.waypoints) - 1)
        target_wp_raw = route.waypoints[target_wp_idx]

        # Calculate right-lane lateral offset (+1.6m normal) so opposite traffic never collides
        raw_dx = target_wp_raw[0] - amb.position[0]
        raw_dy = target_wp_raw[1] - amb.position[1]
        raw_dist = math.hypot(raw_dx, raw_dy)

        if raw_dist > 1e-4:
            ux = raw_dx / raw_dist
            uy = raw_dy / raw_dist
            # Perpendicular normal to the right of travel direction
            nx = uy
            ny = -ux
            target_wp = (target_wp_raw[0] + nx * 1.6, target_wp_raw[1] + ny * 1.6, target_wp_raw[2])
        else:
            target_wp = target_wp_raw

        dx = target_wp[0] - amb.position[0]
        dy = target_wp[1] - amb.position[1]
        dist_to_wp = math.hypot(dx, dy)

        # Check if reached waypoint
        if dist_to_wp < 2.5:
            # Advance to next waypoint
            if target_wp_idx + 1 < len(route.waypoints):
                route.current_segment_index = target_wp_idx
                target_wp_idx = route.current_segment_index + 1
                target_wp = route.waypoints[target_wp_idx]
                dx = target_wp[0] - amb.position[0]
                dy = target_wp[1] - amb.position[1]
                dist_to_wp = math.hypot(dx, dy)
            else:
                # Reached final destination of the active route
                _handle_route_destination_reached(amb, route, state)
                continue

        # ---------------- PROACTIVE OBSTACLE & DYNAMIC TRAFFIC REROUTING ----------------
        # Check if upcoming road or any road ahead on the route is closed, has an accident, or heavy traffic
        remaining_segments = route.segments[route.current_segment_index:]
        is_blocked_ahead = False
        for s in remaining_segments:
            # If executing a U-turn return segment away from obstacle, do not re-trigger on it
            if s.turn_instruction and "U-turn" in s.turn_instruction:
                continue
            edge = state.road_graph.edges.get(s.edge_id)
            if edge and (edge.is_closed or edge.active_incident_id is not None or edge.speed_factor < 0.6):
                is_blocked_ahead = True
                break

        if is_blocked_ahead:
            from src.algorithms.traffic_recovery import calculate_dynamic_reroute
            new_route = calculate_dynamic_reroute(amb, route, state)
            if new_route and new_route.id != route.id:
                state.active_routes[amb.id] = new_route
                amb.active_route_id = new_route.id
                state.increment_version()
                route = new_route
                target_wp_idx = min(max(1, route.current_segment_index + 1), len(route.waypoints) - 1)
                target_wp = route.waypoints[target_wp_idx]
                dx = target_wp[0] - amb.position[0]
                dy = target_wp[1] - amb.position[1]
                dist_to_wp = math.hypot(dx, dy)
            elif not new_route:
                # No alternative path exists around obstacle: halt vehicle safely
                amb.current_speed = 0.0
                continue

        # ---------------- MULTI-VEHICLE COLLISION AVOIDANCE & INTERSECTION MANAGEMENT ----------------
        target_speed = amb.speed_mps

        # Direction unit vector towards target waypoint
        norm_dir_x = (dx / dist_to_wp) if dist_to_wp > 1e-4 else 0.0
        norm_dir_y = (dy / dist_to_wp) if dist_to_wp > 1e-4 else 0.0

        # Distance to upcoming raw road junction / node
        dist_to_raw_node = math.hypot(target_wp_raw[0] - amb.position[0], target_wp_raw[1] - amb.position[1])

        for other in state.fleet.values():
            if other.id == amb.id:
                continue

            dist_other = math.hypot(other.position[0] - amb.position[0], other.position[1] - amb.position[1])
            is_other_active = (
                other.status in (AmbulanceStatus.EN_ROUTE, AmbulanceStatus.TRANSPORTING)
                and (other.current_speed > 0.1 or getattr(other, "active_route_id", None) is not None)
            )

            # --- A. Stationary Vehicle / Scene Handling ---
            if not is_other_active:
                if dist_other < 5.0:
                    # Slow to safe caution speed for passing parked/scene units
                    target_speed = min(target_speed, 4.0)
                continue

            # --- B. Intersection Conflict Management ---
            # If approaching an intersection / junction node
            if dist_to_raw_node < 10.0:
                dist_other_to_same_node = math.hypot(
                    target_wp_raw[0] - other.position[0],
                    target_wp_raw[1] - other.position[1]
                )
                # If other vehicle is also inside or approaching this same junction
                if dist_other_to_same_node < 9.5:
                    amb_prio = (2 if amb.status == AmbulanceStatus.TRANSPORTING else 1, -dist_to_raw_node, amb.id)
                    other_prio = (2 if other.status == AmbulanceStatus.TRANSPORTING else 1, -dist_other_to_same_node, other.id)

                    # If other vehicle is already inside the junction box (< 3.8m), it has right-of-way
                    if dist_other_to_same_node < 3.8 and dist_to_raw_node >= 3.8:
                        target_speed = 0.0  # Hold before junction
                    elif amb_prio < other_prio:
                        # Yield to higher-priority / closer vehicle
                        if dist_to_raw_node > 4.2:
                            target_speed = 0.0  # Hold at stop line before junction
                        elif dist_other < 6.0:
                            target_speed = 0.0
                        else:
                            target_speed = min(target_speed, 2.0)

            # --- C. Dynamic Collision & Safe Following Distance ---
            if dist_other > 1e-4:
                # Vector to other vehicle
                to_other_x = (other.position[0] - amb.position[0]) / dist_other
                to_other_y = (other.position[1] - amb.position[1]) / dist_other

                # Heading alignment: is other in front of amb along amb's travel direction?
                dot_in_front = norm_dir_x * to_other_x + norm_dir_y * to_other_y

                # If other vehicle is in front along path of travel
                if dot_in_front > 0.25:
                    if dist_other < 5.5:
                        target_speed = 0.0  # Full stop to avoid collision/rear-end
                    elif dist_other < 9.5:
                        # Smooth deceleration envelope
                        decel_speed = max(1.5, (dist_other - 5.0) * 1.8)
                        target_speed = min(target_speed, decel_speed)

                # Cross-traffic / merging close proximity
                if dist_other < 5.2:
                    amb_prio = (2 if amb.status == AmbulanceStatus.TRANSPORTING else 1, amb.id)
                    other_prio = (2 if other.status == AmbulanceStatus.TRANSPORTING else 1, other.id)
                    if amb_prio < other_prio:
                        target_speed = 0.0
                    else:
                        if dist_other < 3.8:
                            target_speed = 0.0  # Never penetrate another vehicle even with right of way
                        else:
                            target_speed = min(target_speed, 2.5)

        step_dist = target_speed * dt
        amb.current_speed = target_speed

        if dist_to_wp > 1e-4 and target_speed > 0.0:
            move_x = (dx / dist_to_wp) * min(step_dist, dist_to_wp)
            move_y = (dy / dist_to_wp) * min(step_dist, dist_to_wp)
            cand_x = amb.position[0] + move_x
            cand_y = amb.position[1] + move_y

            # Absolute Physical Collision Barrier:
            # Under no circumstances allow movement that decreases center-to-center distance below 4.2m
            can_advance = True
            for other in state.fleet.values():
                if other.id != amb.id:
                    is_other_active = (
                        other.status in (AmbulanceStatus.EN_ROUTE, AmbulanceStatus.TRANSPORTING)
                        and (other.current_speed > 0.1 or getattr(other, "active_route_id", None) is not None)
                    )
                    if is_other_active:
                        cand_d = math.hypot(other.position[0] - cand_x, other.position[1] - cand_y)
                        curr_d = math.hypot(other.position[0] - amb.position[0], other.position[1] - amb.position[1])
                        if cand_d < 4.2 and cand_d < curr_d:
                            can_advance = False
                            break

            if can_advance:
                amb.position = (cand_x, cand_y, 0.0)
                angle_rad = math.atan2(-dx, dy)
                amb.heading = math.degrees(angle_rad)
            else:
                amb.current_speed = 0.0


def _handle_route_destination_reached(amb: Ambulance, route: Route, state: SimulationState) -> None:
    """Process arrival when ambulance reaches the end of its active route."""
    sim_time = state.simulation_time

    # Case A: Arrived on scene at emergency location
    if amb.status == AmbulanceStatus.EN_ROUTE and amb.assigned_emergency_id:
        em_id = amb.assigned_emergency_id
        if em_id in state.emergencies:
            em = state.emergencies[em_id]
            em.transition_to(IncidentStatus.ON_SCENE, sim_time)
            amb.status = AmbulanceStatus.ON_SCENE
            amb.current_speed = 0.0
            state.active_routes.pop(amb.id, None)
            amb.active_route_id = None
            state.increment_version()

    # Case B: Arrived at destination hospital with patient onboard
    elif amb.status == AmbulanceStatus.TRANSPORTING and amb.assigned_emergency_id:
        em_id = amb.assigned_emergency_id
        if em_id in state.emergencies:
            em = state.emergencies[em_id]
            em.transition_to(IncidentStatus.HOSPITAL_ARRIVAL, sim_time)
            em.transition_to(IncidentStatus.COMPLETED, sim_time)

            # Hospital admits patient atomically
            hosp_id = amb.assigned_hospital_id or em.destination_hospital_id
            if hosp_id and hosp_id in state.hospitals:
                hosp = state.hospitals[hosp_id]
                hosp.admit_patient(em_id)

            # Return ambulance to available status
            amb.status = AmbulanceStatus.AVAILABLE
            amb.assigned_emergency_id = None
            amb.assigned_hospital_id = None
            amb.total_missions_completed += 1
            amb.current_speed = 0.0
            if amb.id in state.active_routes:
                del state.active_routes[amb.id]
            amb.active_route_id = None
            state.increment_version()

    # Case C: Arrived at standby station / depot via dynamic reallocation
    elif amb.assigned_emergency_id is None:
        amb.status = AmbulanceStatus.AVAILABLE
        amb.current_speed = 0.0
        amb.target_node_id = None
        if amb.id in state.active_routes:
            del state.active_routes[amb.id]
        amb.active_route_id = None
        state.increment_version()
