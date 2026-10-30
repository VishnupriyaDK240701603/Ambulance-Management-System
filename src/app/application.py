"""Main Panda3D ShowBase Application for LifeLine Dispatch."""
from __future__ import annotations

import json
import os

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Point3,
    Vec4,
    loadPrcFileData,
)

from src.models.ambulance import AmbulanceClass, ControlMode
from src.models.emergency import EmergencySeverity
from src.models.hospital import Hospital, HospitalStatus
from src.models.police_unit import PoliceStatus, PoliceUnit
from src.models.road_incident import IncidentType
from src.models.route import Route
from src.simulation.commands import (
    AcceptPoliceDispatchCommand,
    ClearRoadIncidentCommand,
    CreateEmergencyCommand,
    DeployAmbulanceCommand,
    PauseSimulationCommand,
    PlaceRoadIncidentCommand,
    ReAlertPoliceDispatchCommand,
    RejectPoliceDispatchCommand,
    ResetSimulationCommand,
    ResumeSimulationCommand,
    SetControlModeCommand,
    SetPoliceControlModeCommand,
    StartSimulationCommand,
    UpdateHospitalBedsCommand,
)
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState
from src.ui.bottom_dashboard import BottomDashboard
from src.ui.notifications import NotificationManager
from src.ui.top_status_bar import TopStatusBar
from src.world.camera_controller import CameraController
from src.world.city_generator import CityGenerator
from src.world.visual_entity_manager import VisualEntityManager
from src.world.world_coordinates import CoordinateConverter


class LifeLineDispatchApp(ShowBase):
    """The central Panda3D application wiring the engine, world, renderer, and user interface."""

    def __init__(self, headless: bool = False):
        if headless:
            loadPrcFileData("", "window-type none")
        else:
            loadPrcFileData("", "window-title LifeLine Dispatch — 3D Emergency Response Simulator")
            loadPrcFileData("", "win-size 1280 720")
            loadPrcFileData("", "show-frame-rate-meter #t")
            loadPrcFileData("", "sync-video #t")

        super().__init__()

        # Disable default mouse drive to let CameraController take control
        self.disableMouse()

        # Load configurations
        self.sim_config = self._load_json_config("config/simulation.json")
        self.city_config = self._load_json_config("config/city.json")

        # 1. World & Road Graph Generation
        grid_w = self.city_config.get("grid_width", 8)
        grid_h = self.city_config.get("grid_height", 8)
        block_sz = self.city_config.get("block_size", 28.0)
        self.converter = CoordinateConverter(grid_w, grid_h, block_sz)

        self.city_gen = CityGenerator(grid_w, grid_h, block_sz)
        self.road_graph = self.city_gen.build_road_graph()
        self.city_root = self.city_gen.generate_city_scene(self.render)

        # 2. State & Engine Initialization
        self.state = SimulationState(
            road_graph=self.road_graph,
            deployment_limit=self.sim_config.get("simulation", {}).get("initial_deployment_limit", 8)
        )
        self._initialize_hospitals()
        self._initialize_police()
        self.engine = SimulationEngine(self.state, fixed_dt=0.05)

        # Register authoritative simulation subsystems
        from src.algorithms.dynamic_reallocation import DynamicReallocationAlgorithm
        from src.algorithms.traffic_recovery import TrafficRecoveryAlgorithm
        from src.integrations.data_provider import ExternalDataProvider
        from src.systems.ambulance_movement import update_ambulance_movement
        from src.systems.manual_driving import ManualDrivingController
        from src.systems.patient_lifecycle import update_patient_lifecycle
        from src.systems.police_system import update_police_system
        from src.ui.decision_modal import DecisionInspectorModal

        self.engine.register_subsystem(update_ambulance_movement)
        self.engine.register_subsystem(update_patient_lifecycle)
        self.engine.register_subsystem(update_police_system)

        self.manual_driver = ManualDrivingController(
            on_reroute=self.handle_manual_reroute,
            on_destination_reached=self.handle_manual_destination_reached
        )
        self.data_provider = ExternalDataProvider(self.engine)
        self.recovery_algo = TrafficRecoveryAlgorithm()
        self.reallocation_algo = DynamicReallocationAlgorithm()

        # 3. Lighting (Warm Isometric Emergency Command Center)
        self._setup_lighting()

        # 4. Camera Controller
        self.camera_ctrl = CameraController(self, target=Point3(0, 0, 0))

        # 5. Visual Entity Manager (3D ambulances, emergencies, roadblocks, route lines)
        self.visual_mgr = VisualEntityManager(self.render)

        # 6. UI: Notifications, Top Bar, Bottom Operations Dashboard, Decision Modal, Route Map, Placement Controller
        self.notifications = NotificationManager(self.aspect2d)
        self.decision_modal = DecisionInspectorModal(self.aspect2d)

        from src.ui.route_map_modal import RouteMapModal
        self.route_map = RouteMapModal(
            parent=self.aspect2d,
            road_graph=self.road_graph,
            on_toggle_camera_overhead=self.camera_ctrl.toggle_overhead_view
        )

        from src.ui.placement_controller import PlacementController
        self.placement_ctrl = PlacementController(
            base=self,
            road_graph=self.road_graph,
            on_confirm_placement=self.handle_confirm_placement,
            on_cancel_placement=lambda: self.notifications.show("Placement cancelled.")
        )

        self.top_bar = TopStatusBar(
            parent=self.aspect2d,
            on_start=self.handle_start,
            on_pause_resume=self.handle_pause_resume,
            on_reset=self.handle_reset
        )
        self.dashboard = BottomDashboard(
            parent=self.aspect2d,
            on_deploy_ambulance=self.handle_deploy_ambulance,
            on_create_emergency=self.handle_create_emergency,
            on_place_traffic_incident=self.handle_place_traffic_incident,
            on_deploy_police=self.handle_deploy_police,
            on_accept_police_dispatch=self.handle_accept_police_dispatch,
            on_reject_police_dispatch=self.handle_reject_police_dispatch,
            on_re_alert_police=self.handle_re_alert_police,
            on_toggle_police_manual=self.handle_toggle_police_manual,
            on_cant_proceed=self.handle_cant_proceed,
            on_toggle_manual_control=self.handle_toggle_manual_control,
            on_see_reason=self.handle_see_reason,
            on_edit_hospital_beds=self.handle_edit_hospital_beds,
            on_set_hospital_vacant=self.handle_set_hospital_vacant,
            on_toggle_hospital_divert=self.handle_toggle_hospital_divert,
            on_open_route_map=self.handle_toggle_route_map,
            on_reallocate_fleet=self.handle_dynamic_reallocation
        )

        # On-screen adjustable View & Camera (XYZ) Panel
        from src.ui.view_adjuster import ViewAdjusterWidget
        self.view_adjuster = ViewAdjusterWidget(self.aspect2d, self.camera_ctrl)

        # Keyboard shortcuts for quick actions
        self.accept("space", self.handle_pause_resume)
        self.accept("1", lambda: self.handle_deploy_ambulance(AmbulanceClass.BLS))
        self.accept("2", lambda: self.handle_deploy_ambulance(AmbulanceClass.ALS))
        self.accept("3", lambda: self.handle_deploy_ambulance(AmbulanceClass.CCT))
        self.accept("r", self.handle_dynamic_reallocation)
        self.accept("R", self.handle_dynamic_reallocation)

        # Camera XYZ & Angle Direct Adjustment shortcuts
        self.accept("j", lambda: self.camera_ctrl.adjust_target(-10, 0, 0)) # Target X left
        self.accept("l", lambda: self.camera_ctrl.adjust_target(10, 0, 0))  # Target X right
        self.accept("i", lambda: self.camera_ctrl.adjust_target(0, 10, 0))  # Target Y forward
        self.accept("k", lambda: self.camera_ctrl.adjust_target(0, -10, 0)) # Target Y back
        self.accept("u", lambda: self.camera_ctrl.adjust_target(0, 0, 5))   # Target Z up
        self.accept("o", lambda: self.camera_ctrl.adjust_target(0, 0, -5))  # Target Z down
        self.accept("[", lambda: self.camera_ctrl.adjust_pitch(-5.0))       # Tilt down
        self.accept("]", lambda: self.camera_ctrl.adjust_pitch(5.0))        # Tilt up

        # Manual driving WASD & Arrow Key bindings (case-insensitive & Shift tolerant)
        for key in ["w", "W", "shift-w"]:
            self.accept(key, lambda: self.manual_driver.set_input("forward", True))
            self.accept(f"{key}-up", lambda: self.manual_driver.set_input("forward", False))
        for key in ["s", "S", "shift-s"]:
            self.accept(key, lambda: self.manual_driver.set_input("backward", True))
            self.accept(f"{key}-up", lambda: self.manual_driver.set_input("backward", False))
        for key in ["a", "A", "shift-a"]:
            self.accept(key, lambda: self.manual_driver.set_input("left", True))
            self.accept(f"{key}-up", lambda: self.manual_driver.set_input("left", False))
        for key in ["d", "D", "shift-d"]:
            self.accept(key, lambda: self.manual_driver.set_input("right", True))
            self.accept(f"{key}-up", lambda: self.manual_driver.set_input("right", False))

        # Route Map & Overhead Camera shortcuts
        self.accept("m", self.handle_toggle_route_map)
        self.accept("M", self.handle_toggle_route_map)
        self.accept("v", self.camera_ctrl.toggle_overhead_view)
        self.accept("V", self.camera_ctrl.toggle_overhead_view)

        # Simulation and UI update task
        self.taskMgr.add(self.update_simulation, "LifeLineDispatchMainUpdate")

        # Ready notification
        self.notifications.show(f"LifeLine Dispatch online. Deploy up to {self.state.deployment_limit} ambulances to begin.")

    def _load_json_config(self, filepath: str) -> dict:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _initialize_hospitals(self):
        """Populate initial hospitals from configuration."""
        raw_hospitals = self.sim_config.get("hospitals", [])
        for h_data in raw_hospitals:
            h_id = h_data["id"]
            node_id = h_data["node_id"]
            node = self.road_graph.nodes.get(node_id)
            pos = node.world_pos if node else (0.0, 0.0, 0.0)

            hospital = Hospital(
                id=h_id,
                name=h_data["name"],
                node_id=node_id,
                location=pos,
                total_beds=h_data["total_beds"],
                occupied_beds=h_data["occupied_beds"],
                vacant_beds=h_data["vacant_beds"],
                capabilities=h_data.get("capabilities", ["basic", "trauma"]),
                operational_status=HospitalStatus(h_data.get("operational_status", "NORMAL"))
            )
            self.state.hospitals[h_id] = hospital

    def _initialize_police(self):
        """Station initial police cruiser at precinct depot ready for auto-dispatch."""
        depot_pos = (120.0, 40.0, 0.0)
        if "N_6_2" in self.road_graph.nodes:
            depot_pos = self.road_graph.nodes["N_6_2"].world_pos
        elif self.road_graph.nodes:
            first_node = next(iter(self.road_graph.nodes.values()))
            depot_pos = first_node.world_pos

        police_01 = PoliceUnit(
            id="POLICE-01",
            position=depot_pos,
            heading=0.0,
            status=PoliceStatus.IDLE,
            speed_mps=18.0,
            response_deadline_sec=20.0
        )
        self.state.police_units[police_01.id] = police_01

    def _setup_lighting(self):
        """Configure warm isometric sunlight, soft ambient illumination, and directional rim light."""
        # Ambient light
        ambient = AmbientLight("AmbientLight")
        ambient.setColor(Vec4(0.42, 0.45, 0.52, 1.0))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        # Primary warm directional sun
        sun = DirectionalLight("SunLight")
        sun.setColor(Vec4(0.85, 0.82, 0.75, 1.0))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(45, -45, 0)
        self.render.setLight(sun_np)

        # Secondary cool rim fill light
        rim = DirectionalLight("RimLight")
        rim.setColor(Vec4(0.25, 0.35, 0.45, 1.0))
        rim_np = self.render.attachNewNode(rim)
        rim_np.setHpr(-135, -30, 0)
        self.render.setLight(rim_np)

    # ---------------- USER COMMAND HANDLERS ----------------

    def handle_start(self):
        cmd = StartSimulationCommand()
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_pause_resume(self):
        if not self.state.is_started:
            self.notifications.show("Press START to launch simulation before pausing.", is_error=True)
            return
        if self.state.is_paused:
            cmd = ResumeSimulationCommand()
        else:
            cmd = PauseSimulationCommand()
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_reset(self):
        cmd = ResetSimulationCommand()
        ok, msg = self.engine.execute_command(cmd)
        self._initialize_police()
        self.notifications.show(msg, is_error=not ok)

    def handle_deploy_ambulance(self, u_class: AmbulanceClass):
        """Deploy an ambulance of the specified class to a designated parking bay."""
        # Check current count against deployment limit
        if len(self.state.fleet) >= self.state.deployment_limit:
            self.notifications.show(
                f"Deployment limit reached ({len(self.state.fleet)}/{self.state.deployment_limit}). Fleet limit is {self.state.deployment_limit} units.",
                is_error=True
            )
            return

        # Start interactive 3D placement mode
        self.placement_ctrl.start_placement(f"DEPLOY_{u_class.value}", {"unit_class": u_class})
        self.notifications.show(f"Click anywhere on a road to place {u_class.value} ambulance (ESC to cancel).")

    def handle_create_emergency(self, severity: EmergencySeverity):
        """Report a new medical emergency incident at a user-clicked road location."""
        self.placement_ctrl.start_placement(f"EMERGENCY_{severity.value}", {"severity": severity})
        self.notifications.show(f"Click anywhere on a road to report {severity.value} Emergency (ESC to cancel).")

    def handle_place_traffic_incident(self, inc_type: IncidentType):
        """Place a road hazard / roadblock at a user-clicked road segment."""
        self.placement_ctrl.start_placement(f"HAZARD_{inc_type.value}", {"incident_type": inc_type})
        self.notifications.show(f"Click anywhere on a road segment to place {inc_type.value} (ESC to cancel).")

    def handle_confirm_placement(self, tool_type: str, payload: dict, pos: tuple[float, float, float]):
        """Confirm placement at the exact 3D coordinates chosen by user click."""
        if tool_type.startswith("DEPLOY_"):
            u_class = payload["unit_class"]
            unit_idx = len(self.state.fleet) + 1
            unit_id = f"AMB-{u_class.value}-{unit_idx:02d}"

            cls_info = self.sim_config.get("ambulance_classes", {}).get(u_class.value, {})
            capabilities = cls_info.get("capabilities", ["cpr", "oxygen"])
            speed = cls_info.get("speed_mps", 15.0)

            cmd = DeployAmbulanceCommand(
                unit_id=unit_id,
                unit_class=u_class,
                position=pos,
                heading=0.0,
                capabilities=capabilities,
                speed_mps=speed
            )
            ok, msg = self.engine.execute_command(cmd)
            if ok:
                self.state.selected_ambulance_id = unit_id
                self.camera_ctrl.focus_on(pos[0], pos[1], pos[2])
            self.notifications.show(msg, is_error=not ok)

        elif tool_type.startswith("EMERGENCY_"):
            severity = payload["severity"]
            em_idx = len(self.state.emergencies) + 1
            em_id = f"INC-{em_idx:03d}"

            if severity == EmergencySeverity.LOW:
                req_caps = ["cpr", "basic_first_aid"]
                title = "Minor Sprain / Fall Incident"
            elif severity == EmergencySeverity.MEDIUM:
                req_caps = ["cpr", "oxygen", "iv_access"]
                title = "Acute Respiratory Distress"
            elif severity == EmergencySeverity.HIGH:
                req_caps = ["cpr", "cardiac_monitor", "defibrillator", "iv_access"]
                title = "Severe Cardiac Emergency"
            else: # CRITICAL
                req_caps = ["ventilator", "critical_meds", "ecmo", "intubation"]
                title = "Critical ICU Transfer / Multi-Trauma"

            cmd = CreateEmergencyCommand(
                emergency_id=em_id,
                location=pos,
                severity=severity,
                required_capabilities=req_caps,
                title=title
            )
            ok, msg = self.engine.execute_command(cmd)
            if ok:
                self.state.selected_emergency_id = em_id
                self.camera_ctrl.focus_on(pos[0], pos[1], pos[2])
            self.notifications.show(msg, is_error=not ok)

        elif tool_type.startswith("HAZARD_"):
            inc_type = payload["incident_type"]
            inc_idx = len(self.state.road_incidents) + 1
            inc_id = f"HAZ-{inc_idx:02d}"

            edge_id = payload.get("edge_id")
            if not edge_id or edge_id not in self.road_graph.edges:
                edge, _, _ = self.road_graph.find_nearest_edge(pos[0], pos[1])
                edge_id = edge.id if edge else "E_N_2_2_N_3_2"

            cmd = PlaceRoadIncidentCommand(
                incident_id=inc_id,
                incident_type=inc_type,
                edge_id=edge_id,
                position=pos,
                speed_factor=0.25 if inc_type != IncidentType.ROADBLOCK else 0.0,
                delay_penalty_sec=60.0
            )
            ok, msg = self.engine.execute_command(cmd)
            if ok:
                self.camera_ctrl.focus_on(pos[0], pos[1], pos[2])
            self.notifications.show(msg, is_error=not ok)

    def handle_deploy_police(self):
        """Dispatch traffic police unit to clear the oldest active roadblock."""
        active_hazards = [h for h in self.state.road_incidents.values() if h.cleared_at is None]
        if not active_hazards:
            self.notifications.show("No active traffic hazards to clear.", is_error=True)
            return

        target = active_hazards[0]
        cmd = ClearRoadIncidentCommand(incident_id=target.id)
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(f"Traffic Police deployed: {msg}", is_error=not ok)

    def handle_accept_police_dispatch(self, unit_id: str = "POLICE-01"):
        """Officer accepts emergency traffic dispatch - dispatches cruiser to scene."""
        cmd = AcceptPoliceDispatchCommand(police_id=unit_id)
        ok, msg = self.engine.execute_command(cmd)
        if ok:
            p_unit = self.state.police_units.get(unit_id)
            if p_unit:
                self.camera_ctrl.focus_on(p_unit.position[0], p_unit.position[1], p_unit.position[2])
        self.notifications.show(msg, is_error=not ok)

    def handle_reject_police_dispatch(self, unit_id: str = "POLICE-01", reason: str = "Officer on high priority patrol / declined"):
        """Officer rejects dispatch - road remains obstructed, ambulances must detour."""
        cmd = RejectPoliceDispatchCommand(police_id=unit_id, reason=reason)
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_re_alert_police(self, unit_id: str = "POLICE-01"):
        """Re-alert police unit after rejection or timeout."""
        cmd = ReAlertPoliceDispatchCommand(police_id=unit_id)
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_toggle_police_manual(self, unit_id: str = "POLICE-01"):
        """Toggle player WASD manual driving control for police cruiser."""
        p_unit = self.state.police_units.get(unit_id)
        if not p_unit:
            self.notifications.show(f"Police unit [{unit_id}] not found.", is_error=True)
            return

        new_mode = not p_unit.is_player_controlled
        cmd = SetPoliceControlModeCommand(police_id=unit_id, is_player_controlled=new_mode)
        ok, msg = self.engine.execute_command(cmd)
        if ok and new_mode:
            # If ambulance was in manual mode, turn it off so WASD controls police
            if self.state.selected_ambulance_id and self.state.selected_ambulance_id in self.state.fleet:
                self.state.fleet[self.state.selected_ambulance_id].control_mode = ControlMode.AUTONOMOUS
            # Ensure simulation is running
            if not self.state.is_started:
                self.engine.execute_command(StartSimulationCommand())
            elif self.state.is_paused:
                self.engine.execute_command(ResumeSimulationCommand())
            self.camera_ctrl.focus_on(p_unit.position[0], p_unit.position[1], p_unit.position[2])
            self.notifications.show(
                f"PLAYER MANUAL CONTROL: Driving Police Cruiser [{unit_id}]! Use W (forward), A (left), S (reverse), D (right) to drive to the scene."
            )
        else:
            self.notifications.show(msg, is_error=not ok)

    def handle_cant_proceed(self):
        """Handle Can't Proceed action for the selected ambulance using TrafficRecoveryAlgorithm."""
        if not self.state.selected_ambulance_id:
            self.notifications.show("No ambulance selected. Select a unit first.", is_error=True)
            return
        amb = self.state.fleet[self.state.selected_ambulance_id]
        active_route = self.state.active_routes.get(amb.id)
        if not active_route:
            self.notifications.show(f"Ambulance [{amb.id}] has no active route to recover.", is_error=True)
            return

        action, new_route, dec_record = self.recovery_algo.evaluate_recovery(amb, active_route, self.state)
        self.state.decision_records.append(dec_record)

        if action == "REROUTE" and new_route:
            self.state.active_routes[amb.id] = new_route
            amb.active_route_id = new_route.id
            self.state.increment_version()
            self.notifications.show(f"Recovery Reroute applied for [{amb.id}]: ETA {new_route.time_remaining_sec:.1f}s.")
        else:
            self.notifications.show(f"Recovery: {dec_record.reasoning_summary}")

    def handle_toggle_manual_control(self):
        """Toggle manual vs autonomous driving for selected unit with auto-activation."""
        if not self.state.selected_ambulance_id:
            if self.state.fleet:
                self.state.selected_ambulance_id = next(iter(self.state.fleet.keys()))
            else:
                self.notifications.show("No ambulances deployed. Deploy an ambulance in Tab 1 first.", is_error=True)
                return

        amb = self.state.fleet[self.state.selected_ambulance_id]
        new_mode = ControlMode.MANUAL if amb.control_mode == ControlMode.AUTONOMOUS else ControlMode.AUTONOMOUS
        cmd = SetControlModeCommand(unit_id=amb.id, control_mode=new_mode)
        ok, msg = self.engine.execute_command(cmd)

        if ok and new_mode == ControlMode.MANUAL:
            # Ensure simulation is running
            if not self.state.is_started:
                self.engine.execute_command(StartSimulationCommand())
            elif self.state.is_paused:
                self.engine.execute_command(ResumeSimulationCommand())

            # Focus camera on vehicle
            self.camera_ctrl.focus_on(amb.position[0], amb.position[1], amb.position[2])
            self.notifications.show(
                f"MANUAL DRIVING ENABLED for [{amb.id}]: Use W (forward), A (left), S (reverse), D (right). Auto-reroute active on deviation! Press M to view Route Map."
            )
        else:
            self.notifications.show(msg, is_error=not ok)

    def handle_manual_reroute(self, amb_id: str, new_route: Route):
        """Handle dynamic auto-reroute when manual driver deviates or misses planned path."""
        self.notifications.show(
            f"Off-route deviation detected for [{amb_id}]! Dynamically recalculated new path to {new_route.destination_title} (ETA: {new_route.time_remaining_sec:.1f}s)."
        )

    def handle_manual_destination_reached(self, amb_id: str):
        """Handle destination arrival when manual driver reaches emergency scene or hospital."""
        self.notifications.show(f"Mission target reached by manual unit [{amb_id}]!")

    def handle_toggle_route_map(self):
        """Toggle the Tactical Route Map overlay on/off."""
        if hasattr(self, "route_map"):
            self.route_map.toggle()

    def handle_see_reason(self):
        """Show full structured Explainable AI decision audit modal."""
        if not self.state.decision_records:
            self.notifications.show("No algorithmic decision records captured yet.")
            return

        latest = self.state.decision_records[-1]
        self.decision_modal.show_decision(latest)

    def handle_dynamic_reallocation(self):
        """Evaluate and reposition idle ambulances to under-covered strategic stations."""
        plan = self.reallocation_algo.evaluate_reallocation(self.state)
        if plan:
            self.reallocation_algo.apply_reallocation(plan, self.state)
            self.notifications.show(
                f"Dynamic Reallocation: {plan.ambulance_id} dispatched to {plan.station_name} "
                f"(+{plan.coverage_improvement_sec:.1f}s coverage gain)!"
            )
        else:
            self.notifications.show("Fleet coverage is currently balanced across all districts.")

    def handle_edit_hospital_beds(self, hospital_id: str, delta_occ: int, delta_vac: int):
        """Adjust hospital vacant/occupied beds while maintaining invariant."""
        if hospital_id not in self.state.hospitals:
            self.notifications.show(f"Hospital {hospital_id} not found.", is_error=True)
            return
        hosp = self.state.hospitals[hospital_id]
        new_occ = hosp.occupied_beds + delta_occ
        new_vac = hosp.vacant_beds + delta_vac
        cmd = UpdateHospitalBedsCommand(hospital_id, new_occ, new_vac)
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_set_hospital_vacant(self, hospital_id: str, target_vacant: int):
        """Set exact vacant beds for hospital, adjusting occupied beds to maintain total capacity invariant."""
        if hospital_id not in self.state.hospitals:
            self.notifications.show(f"Hospital {hospital_id} not found.", is_error=True)
            return
        hosp = self.state.hospitals[hospital_id]
        min_vacant = len(hosp.reserved_patient_ids)
        target_vacant = max(min_vacant, min(hosp.total_beds, target_vacant))
        new_occ = hosp.total_beds - target_vacant
        cmd = UpdateHospitalBedsCommand(hospital_id, new_occ, target_vacant)
        ok, msg = self.engine.execute_command(cmd)
        self.notifications.show(msg, is_error=not ok)

    def handle_toggle_hospital_divert(self, hospital_id: str):
        """Toggle DIVERT vs NORMAL operational status for hospital."""
        if hospital_id not in self.state.hospitals:
            self.notifications.show(f"Hospital {hospital_id} not found.", is_error=True)
            return
        hosp = self.state.hospitals[hospital_id]
        new_status = HospitalStatus.DIVERT if hosp.operational_status == HospitalStatus.NORMAL else HospitalStatus.NORMAL
        hosp.operational_status = new_status
        self.state.increment_version()
        self.notifications.show(f"Hospital [{hospital_id}] status set to {new_status.value}.")

    # ---------------- MAIN UPDATE LOOP ----------------

    def update_simulation(self, task):
        dt = self.clock.getDt()
        dt = min(dt, 0.1)

        # Manual driving update for player-controlled units
        if hasattr(self, "manual_driver"):
            self.manual_driver.update(self.state, dt)

        # Smooth camera tracking when in manual mode
        if self.state.selected_ambulance_id and self.state.selected_ambulance_id in self.state.fleet:
            sel_amb = self.state.fleet[self.state.selected_ambulance_id]
            if sel_amb.control_mode == ControlMode.MANUAL and hasattr(self, "camera_ctrl"):
                self.camera_ctrl.follow_target(sel_amb.position[0], sel_amb.position[1], sel_amb.position[2])

        # Smooth camera tracking if police cruiser is player-controlled
        p_cruiser = self.state.police_units.get("POLICE-01")
        if p_cruiser and p_cruiser.is_player_controlled and hasattr(self, "camera_ctrl"):
            self.camera_ctrl.follow_target(p_cruiser.position[0], p_cruiser.position[1], p_cruiser.position[2])

        # Advance authoritative simulation engine
        self.engine.update(dt)

        # Sync 3D representations
        self.visual_mgr.sync_with_state(self.state, dt)

        # Update HUD telemetry, dashboard panels, route map, and camera view adjuster
        self.top_bar.update_telemetry(self.state)
        self.dashboard.update_from_state(self.state)
        self.notifications.update(dt)
        if hasattr(self, "route_map"):
            self.route_map.update_from_state(self.state)
        if hasattr(self, "view_adjuster"):
            self.view_adjuster.update()

        return task.cont

    def destroy(self):
        """Clean up application tasks and subsystems."""
        if hasattr(self, "placement_ctrl"):
            self.placement_ctrl.destroy()
        self.ignoreAll()
        super().destroy()
