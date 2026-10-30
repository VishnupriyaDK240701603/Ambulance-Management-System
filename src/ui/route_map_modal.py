"""Tactical Route & GPS Navigation Map Display."""
from __future__ import annotations

import math
from collections.abc import Callable

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import LineSegs, NodePath, TextNode, Vec4

from src.models.ambulance import ControlMode
from src.models.police_unit import PoliceStatus
from src.simulation.simulation_state import SimulationState
from src.world.road_graph import RoadGraph


class RouteMapModal:
    """Tactical GPS View Map: Shows city road grid, active decided path, vehicles, and live turn guidance."""

    def __init__(self, parent, road_graph: RoadGraph, on_toggle_camera_overhead: Callable[[], None] | None = None):
        self.parent = parent
        self.road_graph = road_graph
        self.on_toggle_camera_overhead = on_toggle_camera_overhead
        self.is_visible = False

        # Semi-transparent backdrop frame (centered on screen)
        self.frame = DirectFrame(
            parent=self.parent,
            frameColor=(0.06, 0.08, 0.12, 0.96),
            frameSize=(-0.96, 0.96, -0.72, 0.72),
            pos=(0, 0, 0.02),
            relief=1
        )
        self.frame.hide()

        # Title bar
        self.header_label = DirectLabel(
            parent=self.frame,
            text="TACTICAL GPS NAVIGATION & ROUTE MAP",
            text_scale=0.038,
            text_fg=(0.20, 0.90, 0.95, 1.0),
            pos=(-0.90, 0, 0.65),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.sub_header = DirectLabel(
            parent=self.frame,
            text="Real-time Path Telemetry | Live Deviation Auto-Reroute Active | WASD to Steer",
            text_scale=0.024,
            text_fg=(0.75, 0.82, 0.90, 1.0),
            pos=(-0.90, 0, 0.60),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Map drawing canvas container
        self.map_canvas = DirectFrame(
            parent=self.frame,
            frameColor=(0.04, 0.05, 0.07, 0.95),
            frameSize=(-0.56, 0.56, -0.48, 0.48),
            pos=(-0.35, 0, 0.04),
            relief=1
        )
        self.map_draw_node: NodePath | None = None

        # Right Telemetry Info Panel
        self.info_panel = DirectFrame(
            parent=self.frame,
            frameColor=(0.09, 0.12, 0.17, 0.9),
            frameSize=(-0.33, 0.33, -0.48, 0.48),
            pos=(0.58, 0, 0.04),
            relief=1
        )

        DirectLabel(
            parent=self.info_panel,
            text="MISSION & ROUTE TELEMETRY",
            text_scale=0.026,
            text_fg=(0.3, 0.85, 1.0, 1.0),
            pos=(-0.30, 0, 0.42),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.telemetry_label = DirectLabel(
            parent=self.info_panel,
            text="No active ambulance or route.",
            text_scale=0.022,
            text_fg=(0.92, 0.94, 0.98, 1.0),
            pos=(-0.30, 0, 0.35),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Legend / Guide
        legend_txt = (
            "MAP LEGEND:\n"
            "• [CYAN LINE] Decided Planned Route\n"
            "• [YELLOW ARROW] Selected Driver (WASD)\n"
            "• [H] Hospitals (Green / Teal)\n"
            "• [!] Emergency Incidents (Red/Amber)\n"
            "• [X] Road Hazard / Barricade\n\n"
            "CONTROLS:\n"
            "• W: Accelerate Forward\n"
            "• S: Reverse / Brake\n"
            "• A: Steer Left\n"
            "• D: Steer Right\n"
            "• M: Toggle this Route Map\n"
            "• V: Toggle 3D Overhead Camera"
        )
        DirectLabel(
            parent=self.info_panel,
            text=legend_txt,
            text_scale=0.020,
            text_fg=(0.78, 0.85, 0.92, 1.0),
            pos=(-0.30, 0, 0.08),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Bottom Buttons
        self.btn_overhead = DirectButton(
            parent=self.frame,
            text="Toggle 3D Overhead Cam (V)",
            text_scale=0.026,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.18, 0.45, 0.75, 1.0),
            frameSize=(-0.24, 0.24, -0.035, 0.035),
            pos=(-0.35, 0, -0.58),
            command=self._handle_overhead_click,
            relief=1
        )

        self.btn_close = DirectButton(
            parent=self.frame,
            text="Close Map (M)",
            text_scale=0.028,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.75, 0.25, 0.20, 1.0),
            frameSize=(-0.16, 0.16, -0.035, 0.035),
            pos=(0.70, 0, -0.58),
            command=self.hide,
            relief=1
        )

    def _handle_overhead_click(self):
        if self.on_toggle_camera_overhead:
            self.on_toggle_camera_overhead()

    def toggle(self):
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self.is_visible = True
        self.frame.show()

    def hide(self):
        self.is_visible = False
        self.frame.hide()

    def update_from_state(self, state: SimulationState):
        """Redraw map graphics and update live mission telemetry."""
        if not self.is_visible:
            return

        # 1. Update text telemetry
        amb_id = state.selected_ambulance_id
        if amb_id and amb_id in state.fleet:
            amb = state.fleet[amb_id]
            route = state.active_routes.get(amb.id)
            ctrl_mode = "MANUAL (WASD)" if amb.control_mode == ControlMode.MANUAL else "AUTONOMOUS (AI)"
            txt = (
                f"Active Unit: [{amb.id}] ({amb.unit_class.value})\n"
                f"Control: {ctrl_mode}\n"
                f"Current Speed: {amb.current_speed:.1f} m/s\n"
                f"Heading: {amb.heading:.0f}°\n"
            )
            if route:
                txt += (
                    f"Destination: {route.destination_title}\n"
                    f"Next Guidance: {route.next_turn}\n"
                    f"Distance Remaining: {route.distance_remaining_meters:.1f}m\n"
                    f"Est. Travel Time: {route.time_remaining_sec:.1f}s\n"
                    f"Route Tracking: ON TRACK\n"
                    f"(Auto-Reroutes if off path)"
                )
            else:
                txt += (
                    "Destination: None (Standing by)\n"
                    "Route Tracking: IDLE\n"
                    "Report emergency to dispatch route."
                )
            self.telemetry_label["text"] = txt
        else:
            self.telemetry_label["text"] = "No ambulance selected.\nDeploy a unit in Tab 1 to track navigation."

        # 2. Redraw 2D Map Canvas
        if self.map_draw_node and not self.map_draw_node.isEmpty():
            self.map_draw_node.removeNode()

        self.map_draw_node = self._render_map_mesh(state)

    def _render_map_mesh(self, state: SimulationState) -> NodePath:
        """Procedurally render 2D road lines, decided route, and markers."""
        node = self.map_canvas.attachNewNode("MapCanvasDrawing")

        # Coordinate scale: World coords are roughly -100 to +100
        # Canvas size is -0.52 to +0.52
        scale = 0.52 / 105.0

        lines = LineSegs("RoadGridLines")
        lines.setThickness(2.0)
        lines.setColor(Vec4(0.22, 0.28, 0.38, 0.9)) # Dark slate roads

        # Draw road network edges
        drawn_edges = set()
        for edge in self.road_graph.edges.values():
            pair = tuple(sorted([edge.from_node, edge.to_node]))
            if pair in drawn_edges:
                continue
            drawn_edges.add(pair)

            p1 = self.road_graph.nodes[edge.from_node].world_pos
            p2 = self.road_graph.nodes[edge.to_node].world_pos
            lines.moveTo(p1[0] * scale, 0, p1[1] * scale)
            lines.drawTo(p2[0] * scale, 0, p2[1] * scale)

        node.attachNewNode(lines.create())

        # Draw active road closures / incidents
        for inc in state.road_incidents.values():
            if inc.cleared_at is None:
                ix, iy = inc.position[0] * scale, inc.position[1] * scale
                h_lines = LineSegs("HazMarker")
                h_lines.setColor(Vec4(0.95, 0.2, 0.2, 1.0))
                h_lines.setThickness(3.0)
                h_lines.moveTo(ix - 0.015, 0, iy - 0.015)
                h_lines.drawTo(ix + 0.015, 0, iy + 0.015)
                h_lines.moveTo(ix - 0.015, 0, iy + 0.015)
                h_lines.drawTo(ix + 0.015, 0, iy - 0.015)
                node.attachNewNode(h_lines.create())

        # Draw Hospitals
        for h in state.hospitals.values():
            hx, hy = h.location[0] * scale, h.location[1] * scale
            h_line = LineSegs("HospMarker")
            h_line.setColor(Vec4(0.2, 0.85, 0.5, 1.0))
            h_line.setThickness(4.0)
            # Draw square
            h_line.moveTo(hx - 0.018, 0, hy - 0.018)
            h_line.drawTo(hx + 0.018, 0, hy - 0.018)
            h_line.drawTo(hx + 0.018, 0, hy + 0.018)
            h_line.drawTo(hx - 0.018, 0, hy + 0.018)
            h_line.drawTo(hx - 0.018, 0, hy - 0.018)
            node.attachNewNode(h_line.create())

        # Draw Emergencies
        for em in state.emergencies.values():
            if em.status.value != "COMPLETED":
                ex, ey = em.location[0] * scale, em.location[1] * scale
                em_line = LineSegs("EmergencyMarker")
                em_line.setColor(Vec4(0.95, 0.35, 0.15, 1.0))
                em_line.setThickness(4.0)
                # Diamond
                em_line.moveTo(ex, 0, ey + 0.02)
                em_line.drawTo(ex + 0.02, 0, ey)
                em_line.drawTo(ex, 0, ey - 0.02)
                em_line.drawTo(ex - 0.02, 0, ey)
                em_line.drawTo(ex, 0, ey + 0.02)
                node.attachNewNode(em_line.create())

        # Draw Decided Routes (Cyan neon path)
        for amb_id, route in state.active_routes.items():
            if route.waypoints:
                r_line = LineSegs("RouteLine2D")
                r_line.setColor(Vec4(0.15, 0.98, 0.88, 1.0))
                r_line.setThickness(6.0)

                start_idx = max(0, min(route.current_segment_index, len(route.waypoints) - 1))
                pts = route.waypoints[start_idx:]
                if pts:
                    # Connect directly from current ambulance position to current waypoint!
                    if amb_id in state.fleet:
                        cur_amb = state.fleet[amb_id]
                        r_line.moveTo(cur_amb.position[0] * scale, 0, cur_amb.position[1] * scale)
                        r_line.drawTo(pts[0][0] * scale, 0, pts[0][1] * scale)
                    else:
                        r_line.moveTo(pts[0][0] * scale, 0, pts[0][1] * scale)

                    for pt in pts[1:]:
                        r_line.drawTo(pt[0] * scale, 0, pt[1] * scale)

                node.attachNewNode(r_line.create())

        # Draw Ambulances
        for amb in state.fleet.values():
            ax, ay = amb.position[0] * scale, amb.position[1] * scale
            is_selected = (amb.id == state.selected_ambulance_id)

            a_line = LineSegs("AmbVehicle")
            if is_selected:
                a_line.setColor(Vec4(1.0, 0.92, 0.15, 1.0)) # Bright gold/yellow
                a_line.setThickness(5.0)
            else:
                a_line.setColor(Vec4(0.3, 0.7, 0.9, 0.85))
                a_line.setThickness(3.0)

            # Draw directional pointer triangle according to heading
            rad = math.radians(amb.heading)
            # Front of vehicle
            fx = ax - math.sin(rad) * 0.035
            fy = ay + math.cos(rad) * 0.035
            # Back left
            rad_bl = rad + 2.5
            blx = ax - math.sin(rad_bl) * 0.025
            bly = ay + math.cos(rad_bl) * 0.025
            # Back right
            rad_br = rad - 2.5
            brx = ax - math.sin(rad_br) * 0.025
            bry = ay + math.cos(rad_br) * 0.025

            a_line.moveTo(fx, 0, fy)
            a_line.drawTo(blx, 0, bly)
            a_line.drawTo(brx, 0, bry)
            a_line.drawTo(fx, 0, fy)
            node.attachNewNode(a_line.create())

        # Draw Police Cruiser if active or player-controlled
        for p_unit in state.police_units.values():
            if p_unit.is_player_controlled or p_unit.status not in (PoliceStatus.IDLE, PoliceStatus.REJECTED):
                px, py = p_unit.position[0] * scale, p_unit.position[1] * scale
                p_line = LineSegs("PoliceVehicle")
                p_line.setColor(Vec4(0.2, 0.65, 1.0, 1.0)) # Vibrant police blue
                p_line.setThickness(4.5)

                rad = math.radians(p_unit.heading)
                fx = px - math.sin(rad) * 0.035
                fy = py + math.cos(rad) * 0.035
                rad_bl = rad + 2.5
                blx = px - math.sin(rad_bl) * 0.025
                bly = py + math.cos(rad_bl) * 0.025
                rad_br = rad - 2.5
                brx = px - math.sin(rad_br) * 0.025
                bry = py + math.cos(rad_br) * 0.025

                p_line.moveTo(fx, 0, fy)
                p_line.drawTo(blx, 0, bly)
                p_line.drawTo(brx, 0, bry)
                p_line.drawTo(fx, 0, fy)
                node.attachNewNode(p_line.create())

        return node
