"""World coordinate conversion utilities."""
from __future__ import annotations


class CoordinateConverter:
    def __init__(self, grid_width: int = 8, grid_height: int = 8, block_size: float = 28.0):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.block_size = block_size
        self.half_width = (grid_width - 1) * block_size / 2.0
        self.half_height = (grid_height - 1) * block_size / 2.0

    def grid_to_world(self, gx: int, gy: int, z: float = 0.0) -> tuple[float, float, float]:
        """Convert integer grid coordinates to 3D world coordinates (X=right, Y=forward, Z=up)."""
        x = gx * self.block_size - self.half_width
        y = gy * self.block_size - self.half_height
        return (x, y, z)

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert 3D world coordinates to closest integer grid coordinates."""
        gx = round((x + self.half_width) / self.block_size)
        gy = round((y + self.half_height) / self.block_size)
        gx = max(0, min(self.grid_width - 1, gx))
        gy = max(0, min(self.grid_height - 1, gy))
        return (gx, gy)

    def node_id(self, gx: int, gy: int) -> str:
        return f"N_{gx}_{gy}"
