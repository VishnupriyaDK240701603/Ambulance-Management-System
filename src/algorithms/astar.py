"""A* Pathfinding implementation over the navigable RoadGraph."""
from __future__ import annotations

import heapq
import math

from src.models.route import Route, RouteSegment
from src.world.road_graph import RoadGraph


class AStarPathfinder:
    """A* algorithm tailored to the road network with travel time, closures, and turning rules."""

    _route_seq: int = 0

    def __init__(self, road_graph: RoadGraph):
        self.road_graph = road_graph

    def find_route(
        self,
        origin_node_id: str,
        destination_node_id: str,
        destination_title: str = "Destination",
        sim_time: float = 0.0,
        vehicle_speed_mps: float | None = None
    ) -> Route | None:
        """Find the optimal route from origin to destination based on travel time."""
        if origin_node_id not in self.road_graph.nodes:
            return None
        if destination_node_id not in self.road_graph.nodes:
            return None

        if origin_node_id == destination_node_id:
            node = self.road_graph.nodes[origin_node_id]
            return Route(
                id=f"RT_{origin_node_id}_{destination_node_id}",
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                destination_title=destination_title,
                node_ids=[origin_node_id],
                segments=[],
                total_distance_meters=0.0,
                estimated_travel_time_sec=0.0,
                waypoints=[node.world_pos],
                created_at=sim_time
            )

        dest_node = self.road_graph.nodes[destination_node_id]

        # Priority queue entries: (f_score, current_time_cost, current_node_id)
        open_set: list[tuple[float, float, str]] = []
        heapq.heappush(open_set, (0.0, 0.0, origin_node_id))

        came_from: dict[str, tuple[str, str]] = {}  # node_id -> (prev_node_id, edge_id)
        g_score: dict[str, float] = {origin_node_id: 0.0}

        def heuristic(node_id: str) -> float:
            n = self.road_graph.nodes[node_id]
            dx = dest_node.world_pos[0] - n.world_pos[0]
            dy = dest_node.world_pos[1] - n.world_pos[1]
            dist = math.hypot(dx, dy)
            # Admissible heuristic: Euclidean distance divided by max possible road speed (e.g. 25 m/s)
            return dist / 25.0

        while open_set:
            _, current_cost, current_id = heapq.heappop(open_set)

            if current_id == destination_node_id:
                return self._reconstruct_route(
                    origin_node_id=origin_node_id,
                    destination_node_id=destination_node_id,
                    destination_title=destination_title,
                    came_from=came_from,
                    sim_time=sim_time,
                    vehicle_speed_mps=vehicle_speed_mps
                )

            if current_cost > g_score.get(current_id, float("inf")):
                continue

            # Explore outgoing edges
            outgoing_edge_ids = self.road_graph.adjacency.get(current_id, [])
            for edge_id in outgoing_edge_ids:
                edge = self.road_graph.edges.get(edge_id)
                if not edge or edge.is_closed:
                    continue  # Closed / impassable road

                neighbor_id = edge.to_node
                # Calculate travel time for this edge
                effective_speed = edge.effective_speed_mps
                if vehicle_speed_mps is not None:
                    effective_speed = min(effective_speed, vehicle_speed_mps)

                edge_travel_time = (edge.length_meters / max(1.0, effective_speed)) + edge.obstruction_penalty_sec
                tentative_g = current_cost + edge_travel_time

                if tentative_g < g_score.get(neighbor_id, float("inf")):
                    came_from[neighbor_id] = (current_id, edge_id)
                    g_score[neighbor_id] = tentative_g
                    f_score = tentative_g + heuristic(neighbor_id)
                    heapq.heappush(open_set, (f_score, tentative_g, neighbor_id))

        return None  # No valid path found (unreachable)

    def _reconstruct_route(
        self,
        origin_node_id: str,
        destination_node_id: str,
        destination_title: str,
        came_from: dict[str, tuple[str, str]],
        sim_time: float,
        vehicle_speed_mps: float | None
    ) -> Route:
        node_path: list[str] = [destination_node_id]
        edge_path: list[str] = []

        curr = destination_node_id
        while curr != origin_node_id:
            prev_node, edge_id = came_from[curr]
            edge_path.append(edge_id)
            node_path.append(prev_node)
            curr = prev_node

        node_path.reverse()
        edge_path.reverse()

        segments: list[RouteSegment] = []
        waypoints: list[tuple[float, float, float]] = []
        total_dist = 0.0
        total_time = 0.0

        for idx, edge_id in enumerate(edge_path):
            edge = self.road_graph.edges[edge_id]
            eff_speed = edge.effective_speed_mps
            if vehicle_speed_mps is not None:
                eff_speed = min(eff_speed, vehicle_speed_mps)

            travel_time = (edge.length_meters / max(1.0, eff_speed)) + edge.obstruction_penalty_sec
            total_dist += edge.length_meters
            total_time += travel_time

            # Compute turn instruction
            turn = self._compute_turn_instruction(idx, edge_path)

            segments.append(
                RouteSegment(
                    edge_id=edge_id,
                    from_node_id=edge.from_node,
                    to_node_id=edge.to_node,
                    distance_meters=edge.length_meters,
                    base_speed_mps=edge.base_speed_mps,
                    effective_speed_mps=eff_speed,
                    travel_time_sec=travel_time,
                    is_closed=edge.is_closed,
                    turn_instruction=turn
                )
            )

        # Collect waypoints along nodes
        for n_id in node_path:
            waypoints.append(self.road_graph.nodes[n_id].world_pos)

        AStarPathfinder._route_seq += 1
        route_id = f"ROUTE_{origin_node_id}_{destination_node_id}_{AStarPathfinder._route_seq}"
        return Route(
            id=route_id,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            destination_title=destination_title,
            node_ids=node_path,
            segments=segments,
            total_distance_meters=total_dist,
            estimated_travel_time_sec=total_time,
            waypoints=waypoints,
            created_at=sim_time
        )

    def _compute_turn_instruction(self, current_idx: int, edge_path: list[str]) -> str:
        """Calculate turn instruction (left, right, straight) relative to road bearings."""
        if current_idx + 1 >= len(edge_path):
            return "Arrive at destination on road"

        curr_edge = self.road_graph.edges[edge_path[current_idx]]
        next_edge = self.road_graph.edges[edge_path[current_idx + 1]]

        n1 = self.road_graph.nodes[curr_edge.from_node].world_pos
        n2 = self.road_graph.nodes[curr_edge.to_node].world_pos
        n3 = self.road_graph.nodes[next_edge.to_node].world_pos

        v1 = (n2[0] - n1[0], n2[1] - n1[1])
        v2 = (n3[0] - n2[0], n3[1] - n2[1])

        # 2D cross product for turn direction
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]

        if cross > 5.0:
            return "Turn left at intersection"
        elif cross < -5.0:
            return "Turn right at intersection"
        elif dot < -5.0:
            return "Make a U-turn at intersection"
        else:
            return "Continue straight through intersection"
