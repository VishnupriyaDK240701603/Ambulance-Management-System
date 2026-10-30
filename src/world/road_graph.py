"""Navigable road graph representation with edge weights, closures, and congestion."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class RoadNode:
    id: str
    grid_x: int
    grid_y: int
    world_pos: tuple[float, float, float]
    neighbors: set[str] = field(default_factory=set)
    incident_edge_ids: set[str] = field(default_factory=set)

@dataclass
class RoadEdge:
    id: str
    from_node: str
    to_node: str
    length_meters: float
    base_speed_mps: float = 15.0
    speed_factor: float = 1.0       # < 1.0 means congestion (e.g. 0.25)
    obstruction_penalty_sec: float = 0.0
    is_closed: bool = False
    active_incident_id: str | None = None
    waypoints: list[tuple[float, float, float]] = field(default_factory=list)

    @property
    def effective_speed_mps(self) -> float:
        if self.is_closed:
            return 0.001
        return max(1.0, self.base_speed_mps * self.speed_factor)

    @property
    def travel_time_sec(self) -> float:
        if self.is_closed:
            return float("inf")
        base_time = self.length_meters / self.effective_speed_mps
        return base_time + self.obstruction_penalty_sec

class RoadGraph:
    def __init__(self):
        self.nodes: dict[str, RoadNode] = {}
        self.edges: dict[str, RoadEdge] = {}
        self.adjacency: dict[str, list[str]] = {}  # node_id -> list of outgoing edge_ids

    def add_node(self, node_id: str, gx: int, gy: int, world_pos: tuple[float, float, float]) -> RoadNode:
        node = RoadNode(id=node_id, grid_x=gx, grid_y=gy, world_pos=world_pos)
        self.nodes[node_id] = node
        self.adjacency[node_id] = []
        return node

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        base_speed_mps: float = 15.0,
        bidirectional: bool = True
    ) -> list[RoadEdge]:
        created = []
        n1 = self.nodes[from_node_id]
        n2 = self.nodes[to_node_id]
        dx = n2.world_pos[0] - n1.world_pos[0]
        dy = n2.world_pos[1] - n1.world_pos[1]
        dist = math.hypot(dx, dy)

        e1_id = f"E_{from_node_id}_{to_node_id}"
        e1 = RoadEdge(
            id=e1_id,
            from_node=from_node_id,
            to_node=to_node_id,
            length_meters=dist,
            base_speed_mps=base_speed_mps,
            waypoints=[n1.world_pos, n2.world_pos]
        )
        self.edges[e1_id] = e1
        self.adjacency[from_node_id].append(e1_id)
        n1.neighbors.add(to_node_id)
        n1.incident_edge_ids.add(e1_id)
        n2.incident_edge_ids.add(e1_id)
        created.append(e1)

        if bidirectional:
            e2_id = f"E_{to_node_id}_{from_node_id}"
            e2 = RoadEdge(
                id=e2_id,
                from_node=to_node_id,
                to_node=from_node_id,
                length_meters=dist,
                base_speed_mps=base_speed_mps,
                waypoints=[n2.world_pos, n1.world_pos]
            )
            self.edges[e2_id] = e2
            self.adjacency[to_node_id].append(e2_id)
            n2.neighbors.add(from_node_id)
            n2.incident_edge_ids.add(e2_id)
            n1.incident_edge_ids.add(e2_id)
            created.append(e2)

        return created

    def find_nearest_node(self, x: float, y: float) -> RoadNode | None:
        best_node = None
        min_dist = float("inf")
        for node in self.nodes.values():
            d = math.hypot(node.world_pos[0] - x, node.world_pos[1] - y)
            if d < min_dist:
                min_dist = d
                best_node = node
        return best_node

    def find_nearest_edge(self, x: float, y: float) -> tuple[RoadEdge | None, float, tuple[float, float, float]]:
        """Find the nearest edge, distance to it, and projected point on the edge."""
        best_edge = None
        min_dist = float("inf")
        best_pt = (0.0, 0.0, 0.0)

        for edge in self.edges.values():
            p1 = self.nodes[edge.from_node].world_pos
            p2 = self.nodes[edge.to_node].world_pos
            px, py, d = self._point_to_segment(x, y, p1[0], p1[1], p2[0], p2[1])
            if d < min_dist:
                min_dist = d
                best_edge = edge
                best_pt = (px, py, 0.0)

        return best_edge, min_dist, best_pt

    def is_on_drivable_road(self, x: float, y: float, tolerance: float = 3.5) -> tuple[bool, str | None]:
        """Check if (x, y) is on or near a drivable road centerline."""
        edge, dist, _ = self.find_nearest_edge(x, y)
        if edge and dist <= tolerance:
            if edge.is_closed:
                return False, f"Road {edge.id} is closed"
            return True, edge.id
        return False, "Not on a valid road segment"

    def set_edge_closed(self, edge_id: str, closed: bool, incident_id: str | None = None) -> bool:
        if edge_id in self.edges:
            self.edges[edge_id].is_closed = closed
            self.edges[edge_id].active_incident_id = incident_id if closed else None
            # Also close reverse edge if bidirectional
            rev_id = self.get_reverse_edge_id(edge_id)
            if rev_id and rev_id in self.edges:
                self.edges[rev_id].is_closed = closed
                self.edges[rev_id].active_incident_id = incident_id if closed else None
            return True
        return False

    def set_edge_congestion(self, edge_id: str, speed_factor: float, delay_sec: float, incident_id: str | None = None) -> bool:
        if edge_id in self.edges:
            self.edges[edge_id].speed_factor = speed_factor
            self.edges[edge_id].obstruction_penalty_sec = delay_sec
            self.edges[edge_id].active_incident_id = incident_id
            rev_id = self.get_reverse_edge_id(edge_id)
            if rev_id and rev_id in self.edges:
                self.edges[rev_id].speed_factor = speed_factor
                self.edges[rev_id].obstruction_penalty_sec = delay_sec
                self.edges[rev_id].active_incident_id = incident_id
            return True
        return False

    def clear_edge_incident(self, edge_id: str) -> bool:
        if edge_id in self.edges:
            self.edges[edge_id].is_closed = False
            self.edges[edge_id].speed_factor = 1.0
            self.edges[edge_id].obstruction_penalty_sec = 0.0
            self.edges[edge_id].active_incident_id = None
            rev_id = self.get_reverse_edge_id(edge_id)
            if rev_id and rev_id in self.edges:
                self.edges[rev_id].is_closed = False
                self.edges[rev_id].speed_factor = 1.0
                self.edges[rev_id].obstruction_penalty_sec = 0.0
                self.edges[rev_id].active_incident_id = None
            return True
        return False

    def get_reverse_edge_id(self, edge_id: str) -> str | None:
        if edge_id in self.edges:
            edge = self.edges[edge_id]
            rev_id = f"E_{edge.to_node}_{edge.from_node}"
            if rev_id in self.edges:
                return rev_id
        return None

    @staticmethod
    def _point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return x1, y1, math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        dist = math.hypot(px - proj_x, py - proj_y)
        return proj_x, proj_y, dist
