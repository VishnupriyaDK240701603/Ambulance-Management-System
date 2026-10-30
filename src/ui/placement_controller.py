"""Interactive 3D Mouse Raycasting and Click-to-Place Controller."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from direct.showbase.DirectObject import DirectObject  # type: ignore
from panda3d.core import (  # type: ignore
    NodePath,
    Point3,
    TextNode,
    Vec4,
)

from src.world.city_generator import make_box
from src.world.road_graph import RoadEdge, RoadGraph


class PlacementController(DirectObject):
    """Handles 3D mouse raycasting, interactive placement preview, and click-to-place."""

    def __init__(
        self,
        base,
        road_graph: RoadGraph,
        on_confirm_placement: Callable[[str, dict[str, Any], tuple[float, float, float]], None],
        on_cancel_placement: Callable[[], None] | None = None
    ):
        super().__init__()
        self.base = base
        self.road_graph = road_graph
        self.on_confirm_placement = on_confirm_placement
        self.on_cancel_placement = on_cancel_placement

        self.active_tool: str | None = None
        self.tool_payload: dict[str, Any] = {}
        self.selected_edge: RoadEdge | None = None
        self.is_valid_location: bool = False
        self.hovered_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.snapped_road_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # 3D Ghost Preview Node
        self.preview_root = self.base.render.attachNewNode("PlacementPreviewRoot")
        self.preview_root.hide()

        # Ghost box reticle
        self.reticle_box = make_box("Reticle", 3.0, 3.0, 0.15, Vec4(0.2, 0.9, 0.4, 0.8), center_bottom=True)
        self.reticle_box.reparentTo(self.preview_root)

        # Ghost vehicle / beacon representation inside preview
        self.ghost_model: NodePath | None = None

        # Floating prompt text billboard
        self.prompt_text = TextNode("PlacementPrompt")
        self.prompt_text.setText("Click road to place (ESC to cancel)")
        self.prompt_text.setAlign(TextNode.ACenter)
        self.prompt_text.setTextColor(1.0, 1.0, 1.0, 1.0)
        self.prompt_np = self.preview_root.attachNewNode(self.prompt_text)
        self.prompt_np.setScale(1.2)
        self.prompt_np.setPos(0, 0, 4.2)
        self.prompt_np.setBillboardPointEye()

        # Bind mouse click and cancel
        self.accept("mouse1", self._on_mouse_click)
        self.accept("mouse3", self.cancel_placement)
        self.accept("escape", self.cancel_placement)

        # Per-frame raycast update task
        self.base.taskMgr.add(self._update_task, "PlacementControllerUpdate")

    def start_placement(self, tool_type: str, payload: dict[str, Any] | None = None) -> None:
        """Activate interactive click-to-place mode for specified tool."""
        self.active_tool = tool_type
        self.tool_payload = payload or {}
        self.selected_edge = None
        self.is_valid_location = False
        self.preview_root.show()

        # Update prompt text
        display_name = tool_type.replace("_", " ").title()
        self.prompt_text.setText(f"Click anywhere on a road to place {display_name}\n(Right-Click or ESC to cancel)")

        # Rebuild ghost model
        if self.ghost_model and not self.ghost_model.isEmpty():
            self.ghost_model.removeNode()

        ghost = None
        if "DEPLOY_" in tool_type or "AMBULANCE" in tool_type:
            col = Vec4(0.2, 0.8, 1.0, 0.75) if "BLS" in tool_type else (
                Vec4(1.0, 0.55, 0.15, 0.75) if "ALS" in tool_type else Vec4(0.9, 0.15, 0.25, 0.75)
            )
            ghost = make_box("GhostAmb", 2.2, 4.6, 2.0, col, center_bottom=True)
            ghost.setPos(0, 0, 0.1)
            ghost.reparentTo(self.preview_root)
        elif "EMERGENCY" in tool_type:
            ghost = make_box("GhostEm", 1.8, 1.8, 1.8, Vec4(0.95, 0.35, 0.15, 0.75), center_bottom=False)
            ghost.setPos(0, 0, 2.0)
            ghost.setHpr(45, 45, 0)
            ghost.reparentTo(self.preview_root)
        elif "HAZARD" in tool_type:
            ghost = make_box("GhostHaz", 4.4, 0.4, 0.9, Vec4(0.95, 0.2, 0.2, 0.75), center_bottom=True)
            ghost.setPos(0, 0, 0.1)
            ghost.reparentTo(self.preview_root)
        self.ghost_model = ghost

    def cancel_placement(self) -> None:
        """Exit placement mode without placing."""
        self.active_tool = None
        self.tool_payload = {}
        self.selected_edge = None
        self.is_valid_location = False
        self.preview_root.hide()
        if self.on_cancel_placement:
            self.on_cancel_placement()

    def destroy(self) -> None:
        """Clean up resources and event handlers."""
        self.ignoreAll()
        if hasattr(self.base, "taskMgr") and self.base.taskMgr and hasattr(self.base.taskMgr, "remove"):
            self.base.taskMgr.remove("PlacementControllerUpdate")
        if hasattr(self, "preview_root") and not self.preview_root.isEmpty():
            self.preview_root.removeNode()

    def _get_mouse_ground_intersection(self) -> tuple[float, float, float] | None:
        """Cast camera ray through 2D mouse cursor onto ground plane Z = 0."""
        if not hasattr(self.base, "mouseWatcherNode") or not self.base.mouseWatcherNode:
            return None
        if not self.base.mouseWatcherNode.hasMouse():
            return None

        mpos = self.base.mouseWatcherNode.getMouse()
        # Ignore mouse if over UI areas (bottom dashboard is Z < -0.48, top bar is Z > 0.88)
        if mpos.getY() < -0.48 or mpos.getY() > 0.88:
            return None

        if not hasattr(self.base, "camNode") or not self.base.camNode:
            return None
        lens = self.base.camNode.getLens()
        if not lens or not hasattr(self.base, "cam") or not self.base.cam:
            return None

        p_from = Point3()
        p_to = Point3()
        if not lens.extrude(mpos, p_from, p_to):
            return None

        # Convert to render coordinates
        p_from_w = self.base.render.getRelativePoint(self.base.cam, p_from)
        p_to_w = self.base.render.getRelativePoint(self.base.cam, p_to)

        dz = p_to_w.getZ() - p_from_w.getZ()
        if abs(dz) < 1e-6:
            return None

        t = -p_from_w.getZ() / dz
        if t <= 0:
            return None

        hit_x = p_from_w.getX() + t * (p_to_w.getX() - p_from_w.getX())
        hit_y = p_from_w.getY() + t * (p_to_w.getY() - p_from_w.getY())
        return (hit_x, hit_y, 0.0)

    def _update_task(self, task):
        if not self.active_tool:
            return task.cont

        hit = self._get_mouse_ground_intersection()
        if not hit:
            return task.cont

        self.hovered_pos = hit
        # Check proximity to nearest drivable road edge
        edge, dist, snapped_pt = self.road_graph.find_nearest_edge(hit[0], hit[1])

        # If within 4.5m of a road centerline, consider it valid and snap to the road!
        if edge and dist <= 4.5:
            is_hazard = "HAZARD" in self.active_tool if self.active_tool else False
            self.is_valid_location = True if is_hazard else not edge.is_closed
            self.snapped_road_pos = snapped_pt
            self.selected_edge = edge
            self.preview_root.setPos(snapped_pt[0], snapped_pt[1], snapped_pt[2] + 0.05)
            # Align reticle orientation with road edge direction
            p1 = self.road_graph.nodes[edge.from_node].world_pos
            p2 = self.road_graph.nodes[edge.to_node].world_pos
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            angle = math.degrees(math.atan2(-dx, dy))
            self.preview_root.setH(angle)

            # Color reticle green for valid
            if self.is_valid_location:
                self.reticle_box.setColor(Vec4(0.2, 0.9, 0.4, 0.85))
                self.prompt_text.setText(f"Place on Road {edge.id} (Click to Confirm)")
                self.prompt_text.setTextColor(0.3, 1.0, 0.5, 1.0)
            else:
                self.reticle_box.setColor(Vec4(0.9, 0.2, 0.2, 0.85))
                self.prompt_text.setText("Road is Closed / Blocked")
                self.prompt_text.setTextColor(1.0, 0.3, 0.3, 1.0)
        else:
            # Over building block or off-road
            self.is_valid_location = False
            self.selected_edge = None
            self.snapped_road_pos = hit
            self.preview_root.setPos(hit[0], hit[1], hit[2] + 0.05)
            self.preview_root.setH(0)
            self.reticle_box.setColor(Vec4(0.95, 0.2, 0.2, 0.85))
            self.prompt_text.setText("Cannot place off-road / inside building (Move mouse to a road)")
            self.prompt_text.setTextColor(1.0, 0.35, 0.35, 1.0)

        return task.cont

    def _on_mouse_click(self):
        """User clicked left mouse button."""
        tool = self.active_tool
        if not tool or not self.is_valid_location:
            return

        hit = self._get_mouse_ground_intersection()
        if not hit:
            return

        # Confirm placement at snapped road position
        payload = dict(self.tool_payload)
        pos = self.snapped_road_pos
        if self.selected_edge:
            payload["edge_id"] = self.selected_edge.id

        self.cancel_placement()
        self.on_confirm_placement(tool, payload, pos)
