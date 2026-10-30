"""Route representation and navigation waypoint data."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RouteSegment:
    edge_id: str
    from_node_id: str
    to_node_id: str
    distance_meters: float
    base_speed_mps: float
    effective_speed_mps: float
    travel_time_sec: float
    is_closed: bool = False
    turn_instruction: str = "Continue straight"

@dataclass
class Route:
    id: str
    origin_node_id: str
    destination_node_id: str
    destination_title: str
    node_ids: list[str] = field(default_factory=list)
    segments: list[RouteSegment] = field(default_factory=list)
    total_distance_meters: float = 0.0
    estimated_travel_time_sec: float = 0.0
    waypoints: list[tuple[float, float, float]] = field(default_factory=list)
    current_segment_index: int = 0
    created_at: float = 0.0

    @property
    def distance_remaining_meters(self) -> float:
        """Calculate remaining distance from current segment."""
        if not self.segments or self.current_segment_index >= len(self.segments):
            return 0.0
        return sum(s.distance_meters for s in self.segments[self.current_segment_index:])

    @property
    def time_remaining_sec(self) -> float:
        """Calculate remaining travel time from current segment."""
        if not self.segments or self.current_segment_index >= len(self.segments):
            return 0.0
        return sum(s.travel_time_sec for s in self.segments[self.current_segment_index:])

    @property
    def next_turn(self) -> str:
        """Turn instruction for the next intersection."""
        if not self.segments or self.current_segment_index >= len(self.segments):
            return "Arrived at destination"
        return self.segments[self.current_segment_index].turn_instruction

    @property
    def current_edge_id(self) -> str | None:
        if not self.segments or self.current_segment_index >= len(self.segments):
            return None
        return self.segments[self.current_segment_index].edge_id
