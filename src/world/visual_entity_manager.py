"""Visual Entity Manager: Render and synchronize 3D vehicles, markers, and route ribbons."""
from __future__ import annotations

import math

from panda3d.core import (
    LineSegs,
    NodePath,
    Vec4,
)

from src.models.ambulance import Ambulance, AmbulanceClass
from src.models.emergency import EmergencyIncident, IncidentStatus
from src.models.police_unit import PoliceStatus, PoliceUnit
from src.models.road_incident import RoadIncident
from src.models.route import Route
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import make_box


class VisualEntityManager:
    """Manages procedural 3D models for ambulances, emergencies, police, incidents, and routes."""

    def __init__(self, render_root: NodePath):
        self.root = render_root.attachNewNode("VisualEntityManagerRoot")
        self.ambulance_nodes: dict[str, NodePath] = {}
        self.emergency_nodes: dict[str, NodePath] = {}
        self.incident_nodes: dict[str, NodePath] = {}
        self.police_nodes: dict[str, NodePath] = {}
        self.route_line_nodes: dict[str, NodePath] = {}
        self.beacon_time: float = 0.0

    def sync_with_state(self, state: SimulationState, dt: float) -> None:
        """Synchronize all 3D visual representations with authoritative simulation state."""
        self.beacon_time += dt

        # 1. Sync Ambulances
        current_amb_ids = set(state.fleet.keys())
        for amb_id in list(self.ambulance_nodes.keys()):
            if amb_id not in current_amb_ids:
                self.ambulance_nodes[amb_id].removeNode()
                del self.ambulance_nodes[amb_id]

        for amb in state.fleet.values():
            if amb.id not in self.ambulance_nodes:
                self.ambulance_nodes[amb.id] = self._create_ambulance_model(amb)
            node = self.ambulance_nodes[amb.id]
            node.setPos(amb.position[0], amb.position[1], amb.position[2] + 0.1)
            node.setH(amb.heading)

            # Animate roof lightbar and floating overhead beacon
            lightbar = node.find("**/Lightbar")
            if not lightbar.isEmpty():
                if amb.status.value in ("EN_ROUTE", "TRANSPORTING"):
                    phase = math.sin(self.beacon_time * 12.0)
                    if phase > 0:
                        lightbar.setColor(Vec4(1.0, 0.1, 0.1, 1.0))
                    else:
                        lightbar.setColor(Vec4(0.1, 0.3, 1.0, 1.0))
                else:
                    lightbar.setColor(Vec4(0.7, 0.7, 0.7, 1.0))

            beacon = node.find("**/UnitBeacon")
            if not beacon.isEmpty():
                bounce = 0.25 * math.sin(self.beacon_time * 4.0)
                beacon.setPos(0, 0, 4.8 + bounce)
                beacon.setH((self.beacon_time * 80.0) % 360)

        # 2. Sync Emergencies (Hide marker once patient is picked up onboard)
        active_emergencies = {
            e.id: e for e in state.emergencies.values()
            if e.status not in (IncidentStatus.COMPLETED, IncidentStatus.CANCELLED, IncidentStatus.PATIENT_ONBOARD, IncidentStatus.TRANSPORTING)
        }
        for em_id in list(self.emergency_nodes.keys()):
            if em_id not in active_emergencies:
                self.emergency_nodes[em_id].removeNode()
                del self.emergency_nodes[em_id]

        for em in active_emergencies.values():
            if em.id not in self.emergency_nodes:
                self.emergency_nodes[em.id] = self._create_emergency_marker(em)
            node = self.emergency_nodes[em.id]
            # Pulsing hover effect floating high above the street
            bounce = 0.3 * math.sin(self.beacon_time * 4.0)
            node.setPos(em.location[0], em.location[1], em.location[2] + 3.0 + bounce)
            node.setH((self.beacon_time * 60.0) % 360)

        # 3. Sync Road Incidents
        active_inc = {inc.id: inc for inc in state.road_incidents.values() if inc.cleared_at is None}
        for inc_id in list(self.incident_nodes.keys()):
            if inc_id not in active_inc:
                self.incident_nodes[inc_id].removeNode()
                del self.incident_nodes[inc_id]

        for inc in active_inc.values():
            if inc.id not in self.incident_nodes:
                self.incident_nodes[inc.id] = self._create_incident_barricade(inc)

        # 4. Sync Police (Render when player-controlled or active)
        active_police = {
            p_id: p for p_id, p in state.police_units.items()
            if p.is_player_controlled or p.status not in (PoliceStatus.IDLE, PoliceStatus.REJECTED)
        }
        for p_id in list(self.police_nodes.keys()):
            if p_id not in active_police:
                self.police_nodes[p_id].removeNode()
                del self.police_nodes[p_id]

        for p_unit in active_police.values():
            if p_unit.id not in self.police_nodes:
                self.police_nodes[p_unit.id] = self._create_police_model(p_unit)
            node = self.police_nodes[p_unit.id]
            node.setPos(p_unit.position[0], p_unit.position[1], p_unit.position[2] + 0.1)
            node.setH(p_unit.heading)

            # Animate roof lightbar
            lightbar = node.find("**/PoliceLightbar")
            if not lightbar.isEmpty():
                phase = math.sin(self.beacon_time * 14.0)
                if phase > 0:
                    lightbar.setColor(Vec4(0.1, 0.3, 1.0, 1.0))
                else:
                    lightbar.setColor(Vec4(1.0, 0.1, 0.1, 1.0))

            beacon = node.find("**/PoliceBeacon")
            if not beacon.isEmpty():
                bounce = 0.25 * math.sin(self.beacon_time * 4.0)
                beacon.setPos(0, 0, 4.5 + bounce)
                beacon.setH((self.beacon_time * 80.0) % 360)

        # 5. Sync Route Lines (Only for active emergency ambulances)
        active_ambulance_route_ids = {r_id for r_id in state.active_routes if not r_id.startswith("POLICE")}
        for r_id in list(self.route_line_nodes.keys()):
            if r_id not in active_ambulance_route_ids:
                self.route_line_nodes[r_id].removeNode()
                del self.route_line_nodes[r_id]

        for amb_id, route in state.active_routes.items():
            if amb_id.startswith("POLICE"):
                continue
            # Redraw or update route line
            if amb_id in self.route_line_nodes:
                self.route_line_nodes[amb_id].removeNode()
            if route.waypoints:
                self.route_line_nodes[amb_id] = self._create_route_line(route)

    def _create_ambulance_model(self, amb: Ambulance) -> NodePath:
        """Create a procedural ambulance 3D model with headlights, cabin, and roof lightbar."""
        root = self.root.attachNewNode(f"Ambulance_{amb.id}")

        # Chassis body
        body_white = Vec4(0.96, 0.97, 0.98, 1.0)
        body = make_box("Body", 2.2, 4.6, 2.0, body_white, center_bottom=True)
        body.setPos(0, 0, 0.3)
        body.reparentTo(root)

        # Class stripe color
        if amb.unit_class == AmbulanceClass.BLS:
            stripe_col = Vec4(0.18, 0.75, 0.90, 1.0) # Cyan
        elif amb.unit_class == AmbulanceClass.ALS:
            stripe_col = Vec4(0.96, 0.50, 0.15, 1.0) # Orange
        else:
            stripe_col = Vec4(0.90, 0.15, 0.20, 1.0) # Red

        stripe = make_box("Stripe", 2.24, 4.62, 0.45, stripe_col, center_bottom=True)
        stripe.setPos(0, 0, 1.0)
        stripe.reparentTo(root)

        # Windshield
        windshield = make_box("Windshield", 2.0, 0.8, 0.7, Vec4(0.2, 0.25, 0.35, 1.0), center_bottom=True)
        windshield.setPos(0, 1.4, 1.4)
        windshield.reparentTo(root)

        # Wheels (4 dark boxes)
        wheel_col = Vec4(0.15, 0.15, 0.15, 1.0)
        for wx in [-1.1, 1.1]:
            for wy in [-1.4, 1.4]:
                wheel = make_box("Wheel", 0.3, 0.8, 0.6, wheel_col, center_bottom=True)
                wheel.setPos(wx, wy, 0.0)
                wheel.reparentTo(root)

        # Lightbar on roof
        lightbar = make_box("Lightbar", 1.4, 0.4, 0.3, Vec4(1.0, 0.1, 0.1, 1.0), center_bottom=True)
        lightbar.setPos(0, 0.5, 2.35)
        lightbar.reparentTo(root)

        # Unit ID label plate
        id_plate = make_box("IDPlate", 1.2, 0.1, 0.4, Vec4(0.2, 0.25, 0.3, 1.0), center_bottom=True)
        id_plate.setPos(0, -2.32, 1.2)
        id_plate.reparentTo(root)

        # Prominent glowing floating diamond indicator above ambulance
        beacon = make_box("UnitBeacon", 1.1, 1.1, 1.1, stripe_col, center_bottom=False)
        beacon.setPos(0, 0, 4.8)
        beacon.setHpr(45, 45, 0)
        beacon.reparentTo(root)

        return root

    def _create_police_model(self, police: PoliceUnit) -> NodePath:
        """Create a procedural police cruiser 3D model."""
        root = self.root.attachNewNode(f"Police_{police.id}")

        # Cruiser body (Black & White)
        body = make_box("PoliceBody", 2.0, 4.2, 1.5, Vec4(0.12, 0.14, 0.16, 1.0), center_bottom=True)
        body.setPos(0, 0, 0.25)
        body.reparentTo(root)

        cabin_white = make_box("PoliceCabin", 1.8, 2.0, 0.9, Vec4(0.95, 0.95, 0.95, 1.0), center_bottom=True)
        cabin_white.setPos(0, -0.2, 1.3)
        cabin_white.reparentTo(root)

        # Blue lightbar
        lightbar = make_box("PoliceLightbar", 1.2, 0.3, 0.25, Vec4(0.15, 0.45, 1.0, 1.0), center_bottom=True)
        lightbar.setPos(0, -0.2, 2.22)
        lightbar.reparentTo(root)

        # Wheels
        for wx in [-1.0, 1.0]:
            for wy in [-1.3, 1.3]:
                wheel = make_box("PWheel", 0.25, 0.7, 0.5, Vec4(0.1, 0.1, 0.1, 1.0), center_bottom=True)
                wheel.setPos(wx, wy, 0.0)
                wheel.reparentTo(root)

        # Prominent glowing floating Police Beacon (Blue Diamond) above cruiser
        p_beacon = make_box("PoliceBeacon", 1.1, 1.1, 1.1, Vec4(0.15, 0.55, 1.0, 1.0), center_bottom=False)
        p_beacon.setPos(0, 0, 4.5)
        p_beacon.setHpr(45, 45, 0)
        p_beacon.reparentTo(root)

        return root

    def _create_emergency_marker(self, em: EmergencyIncident) -> NodePath:
        """Create a glowing 3D emergency medical cross floating in the air."""
        root = self.root.attachNewNode(f"EmergencyMarker_{em.id}")

        # Color based on severity
        if em.severity.value == "LOW":
            m_col = Vec4(0.20, 0.75, 0.95, 1.0)
        elif em.severity.value == "MEDIUM":
            m_col = Vec4(0.95, 0.75, 0.15, 1.0)
        elif em.severity.value == "HIGH":
            m_col = Vec4(0.95, 0.35, 0.15, 1.0)
        else: # CRITICAL
            m_col = Vec4(0.92, 0.15, 0.25, 1.0)

        # 3D Floating Medical Cross (vertical + horizontal bar)
        cross_v = make_box("CrossV", 0.45, 0.45, 1.8, m_col, center_bottom=False)
        cross_v.reparentTo(root)

        cross_h = make_box("CrossH", 1.8, 0.45, 0.45, m_col, center_bottom=False)
        cross_h.reparentTo(root)

        # White core backing
        core = make_box("CrossCore", 0.55, 0.55, 0.55, Vec4(1.0, 1.0, 1.0, 1.0), center_bottom=False)
        core.reparentTo(root)

        # Ground pickup zone ring
        ring = make_box("PickupRing", 2.8, 2.8, 0.05, Vec4(m_col.x, m_col.y, m_col.z, 0.7), center_bottom=True)
        ring.setPos(0, 0, -2.95)
        ring.reparentTo(root)

        return root

    def _create_incident_barricade(self, inc: RoadIncident) -> NodePath:
        """Create road hazard / barricade geometry across the road."""
        root = self.root.attachNewNode(f"Barricade_{inc.id}")
        root.setPos(inc.position[0], inc.position[1], inc.position[2] + 0.05)

        if inc.is_closed:
            # Heavy red/white chevron barricade
            bar1 = make_box("Barricade_Top", 4.4, 0.3, 0.6, Vec4(0.95, 0.2, 0.2, 1.0), center_bottom=True)
            bar1.setPos(0, 0, 0.8)
            bar1.reparentTo(root)

            bar2 = make_box("Barricade_Stripe", 4.45, 0.32, 0.25, Vec4(0.98, 0.98, 0.98, 1.0), center_bottom=True)
            bar2.setPos(0, 0, 0.95)
            bar2.reparentTo(root)

            # Warning light
            flash = make_box("WarnLight", 0.5, 0.5, 0.4, Vec4(1.0, 0.65, 0.0, 1.0), center_bottom=True)
            flash.setPos(0, 0, 1.45)
            flash.reparentTo(root)
        else:
            # Traffic cones / congestion markers
            for cx in [-1.5, 0.0, 1.5]:
                cone = make_box("TrafficCone", 0.5, 0.5, 0.9, Vec4(0.95, 0.55, 0.1, 1.0), center_bottom=True)
                cone.setPos(cx, 0, 0.0)
                cone.reparentTo(root)

        return root

    def _create_route_line(self, route: Route) -> NodePath:
        """Create a glowing route path ribbon on the road surface."""
        root = self.root.attachNewNode(f"RouteRibbon_{route.id}")

        lines = LineSegs("RouteLine")
        lines.setColor(Vec4(0.15, 0.95, 0.85, 0.98)) # Bright neon cyan
        lines.setThickness(7.0)

        # Draw along route waypoints starting from current segment index
        start_idx = max(0, min(route.current_segment_index, len(route.waypoints) - 1))
        pts = route.waypoints[start_idx:]

        if pts:
            lines.moveTo(pts[0][0], pts[0][1], 0.35)
            for p in pts[1:]:
                lines.drawTo(p[0], p[1], 0.35)
            line_np = root.attachNewNode(lines.create())
            line_np.setLightOff()

            # Waypoint guidance dots
            for wp in pts:
                dot = make_box("WpDot", 0.9, 0.9, 0.12, Vec4(0.1, 1.0, 0.7, 0.9), center_bottom=True)
                dot.setPos(wp[0], wp[1], 0.28)
                dot.reparentTo(root)

        return root
