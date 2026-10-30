"""Fixed Bottom Operations Dashboard for LifeLine Dispatch."""
from __future__ import annotations

from collections.abc import Callable

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import TextNode

from src.models.ambulance import AmbulanceClass, ControlMode
from src.models.emergency import EmergencySeverity
from src.models.police_unit import PoliceStatus
from src.models.road_incident import IncidentType
from src.simulation.simulation_state import SimulationState


class BottomDashboard:
    """Fixed bottom operations dashboard with tabbed management consoles."""

    def __init__(
        self,
        parent,
        on_deploy_ambulance: Callable[[AmbulanceClass], None],
        on_create_emergency: Callable[[EmergencySeverity], None],
        on_place_traffic_incident: Callable[[IncidentType], None],
        on_deploy_police: Callable[[], None],
        on_cant_proceed: Callable[[], None],
        on_toggle_manual_control: Callable[[], None],
        on_see_reason: Callable[[], None],
        on_edit_hospital_beds: Callable[[str, int, int], None],
        on_set_hospital_vacant: Callable[[str, int], None] | None = None,
        on_toggle_hospital_divert: Callable[[str], None] | None = None,
        on_open_route_map: Callable[[], None] | None = None,
        on_accept_police_dispatch: Callable[[str], None] | None = None,
        on_reject_police_dispatch: Callable[[str], None] | None = None,
        on_re_alert_police: Callable[[str], None] | None = None,
        on_toggle_police_manual: Callable[[str], None] | None = None,
        on_reallocate_fleet: Callable[[], None] | None = None,
    ):
        self.parent = parent
        self.on_deploy_ambulance = on_deploy_ambulance
        self.on_create_emergency = on_create_emergency
        self.on_place_traffic_incident = on_place_traffic_incident
        self.on_deploy_police = on_deploy_police
        self.on_cant_proceed = on_cant_proceed
        self.on_toggle_manual_control = on_toggle_manual_control
        self.on_see_reason = on_see_reason
        self.on_edit_hospital_beds = on_edit_hospital_beds
        self.on_set_hospital_vacant = on_set_hospital_vacant
        self.on_toggle_hospital_divert = on_toggle_hospital_divert
        self.on_open_route_map = on_open_route_map
        self.on_accept_police_dispatch = on_accept_police_dispatch
        self.on_reject_police_dispatch = on_reject_police_dispatch
        self.on_re_alert_police = on_re_alert_police
        self.on_toggle_police_manual = on_toggle_police_manual
        self.on_reallocate_fleet = on_reallocate_fleet

        self.current_tab = "FLEET"

        # Main background container frame (Z: -1.0 to -0.52)
        self.main_frame = DirectFrame(
            parent=self.parent,
            frameColor=(0.08, 0.10, 0.14, 0.96),
            frameSize=(-1.80, 1.80, -0.48, 0.0),
            pos=(0, 0, -0.52),
            relief=1
        )

        # Tab navigation bar
        self.tab_bar = DirectFrame(
            parent=self.main_frame,
            frameColor=(0.12, 0.15, 0.20, 1.0),
            frameSize=(-1.80, 1.80, -0.045, 0.045),
            pos=(0, 0, -0.045),
            relief=1
        )

        self.tabs = [
            ("FLEET", "1. Fleet Deployment"),
            ("EMERGENCIES", "2. Emergencies"),
            ("TRAFFIC", "3. Traffic & Roads"),
            ("POLICE", "4. Traffic Police"),
            ("HOSPITALS", "5. Hospitals"),
            ("NAV", "6. Navigation & Alerts"),
            ("AI_REASON", "7. Explainable AI"),
        ]

        self.tab_buttons: dict[str, DirectButton] = {}
        tab_start_x = -1.30
        tab_spacing = 0.43
        for idx, (tab_key, tab_label) in enumerate(self.tabs):
            x_pos = tab_start_x + idx * tab_spacing
            btn = DirectButton(
                parent=self.tab_bar,
                text=tab_label,
                text_scale=0.030,
                text_fg=(0.85, 0.90, 0.95, 1.0),
                frameColor=(0.16, 0.20, 0.26, 1.0),
                frameSize=(-0.20, 0.20, -0.030, 0.030),
                pos=(x_pos, 0, 0),
                command=self.switch_tab,
                extraArgs=[tab_key],
                relief=1
            )
            self.tab_buttons[tab_key] = btn

        # Content area frame
        self.content_frame = DirectFrame(
            parent=self.main_frame,
            frameColor=(0, 0, 0, 0),
            frameSize=(-1.70, 1.70, -0.38, 0.0),
            pos=(0, 0, -0.09)
        )

        # Build sub-panels
        self._build_fleet_panel()
        self._build_emergencies_panel()
        self._build_traffic_panel()
        self._build_police_panel()
        self._build_hospitals_panel()
        self._build_nav_panel()
        self._build_ai_reason_panel()

        self.switch_tab("FLEET")

    def switch_tab(self, tab_key: str):
        """Switch visible tab panel."""
        self.current_tab = tab_key
        for key, btn in self.tab_buttons.items():
            if key == tab_key:
                btn["frameColor"] = (0.20, 0.60, 0.85, 1.0)
                btn["text_fg"] = (1.0, 1.0, 1.0, 1.0)
            else:
                btn["frameColor"] = (0.16, 0.20, 0.26, 1.0)
                btn["text_fg"] = (0.75, 0.80, 0.85, 1.0)

        # Show/hide panels
        self.panel_fleet.hide()
        self.panel_emergencies.hide()
        self.panel_traffic.hide()
        self.panel_police.hide()
        self.panel_hospitals.hide()
        self.panel_nav.hide()
        self.panel_ai_reason.hide()

        if tab_key == "FLEET":
            self.panel_fleet.show()
        elif tab_key == "EMERGENCIES":
            self.panel_emergencies.show()
        elif tab_key == "TRAFFIC":
            self.panel_traffic.show()
        elif tab_key == "POLICE":
            self.panel_police.show()
        elif tab_key == "HOSPITALS":
            self.panel_hospitals.show()
        elif tab_key == "NAV":
            self.panel_nav.show()
        elif tab_key == "AI_REASON":
            self.panel_ai_reason.show()

    def _handle_accept_police(self):
        if self.on_accept_police_dispatch:
            self.on_accept_police_dispatch("POLICE-01")

    def _handle_reject_police(self):
        if self.on_reject_police_dispatch:
            self.on_reject_police_dispatch("POLICE-01")

    def _handle_re_alert_police(self):
        if self.on_re_alert_police:
            self.on_re_alert_police("POLICE-01")

    def _handle_toggle_police_manual(self):
        if self.on_toggle_police_manual:
            self.on_toggle_police_manual("POLICE-01")

    def _handle_reallocate_fleet(self):
        if self.on_reallocate_fleet:
            self.on_reallocate_fleet()

    # ---------------- 1. FLEET PANEL ----------------
    def _build_fleet_panel(self):
        self.panel_fleet = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        # Cards for the 3 ambulance classes
        classes_info = [
            (
                AmbulanceClass.BLS,
                "BLS — Basic Life Support",
                "Speed: 14 m/s | Cost: 1.5x\nCPR, Oxygen, First Aid, Splinting\nFor minor to moderate trauma.",
                (0.18, 0.45, 0.65, 0.95),
                -0.95
            ),
            (
                AmbulanceClass.ALS,
                "ALS — Advanced Life Support",
                "Speed: 16 m/s | Cost: 2.2x\nIV, Intubation, Defibrillator, ECG\nFor acute & severe trauma.",
                (0.70, 0.35, 0.12, 0.95),
                0.0
            ),
            (
                AmbulanceClass.CCT,
                "CCT — Critical Care Transport",
                "Speed: 15 m/s | Cost: 3.0x\nVentilator, ECMO, Critical Meds, ICU\nFor critical life support & ICU transfer.",
                (0.65, 0.15, 0.20, 0.95),
                0.95
            ),
        ]

        for u_class, title, desc, col, x_pos in classes_info:
            card = DirectFrame(
                parent=self.panel_fleet,
                frameColor=col,
                frameSize=(-0.44, 0.44, -0.32, 0.0),
                pos=(x_pos, 0, -0.03),
                relief=1
            )
            DirectLabel(
                parent=card,
                text=title,
                text_scale=0.032,
                text_fg=(1.0, 1.0, 1.0, 1.0),
                pos=(-0.41, 0, -0.045),
                text_align=TextNode.ALeft,
                frameColor=(0, 0, 0, 0)
            )
            DirectLabel(
                parent=card,
                text=desc,
                text_scale=0.026,
                text_fg=(0.90, 0.92, 0.95, 1.0),
                pos=(-0.41, 0, -0.10),
                text_align=TextNode.ALeft,
                frameColor=(0, 0, 0, 0)
            )
            DirectButton(
                parent=card,
                text=f"Deploy {u_class.value}",
                text_scale=0.030,
                text_fg=(1.0, 1.0, 1.0, 1.0),
                frameColor=(0.15, 0.65, 0.35, 1.0),
                frameSize=(-0.20, 0.20, -0.03, 0.03),
                pos=(0.0, 0, -0.26),
                command=self.on_deploy_ambulance,
                extraArgs=[u_class],
                relief=1
            )

        # Fleet Dynamic Reallocation Action Button
        DirectButton(
            parent=self.panel_fleet,
            text="DYNAMIC REALLOCATION (Reposition Idle Fleet for Max Coverage) [R]",
            text_scale=0.023,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.18, 0.52, 0.45, 1.0),
            frameSize=(-0.56, 0.56, -0.026, 0.026),
            pos=(0.0, 0, -0.345),
            command=self._handle_reallocate_fleet,
            relief=1
        )

    # ---------------- 2. EMERGENCIES PANEL ----------------
    def _build_emergencies_panel(self):
        self.panel_emergencies = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        # Severity buttons
        DirectLabel(
            parent=self.panel_emergencies,
            text="DISPATCH INCIDENT CREATOR (Click to report new incident at active district):",
            text_scale=0.032,
            text_fg=(0.95, 0.95, 0.95, 1.0),
            pos=(-1.35, 0, -0.05),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        severities = [
            (EmergencySeverity.LOW, "Report LOW Severity (BLS)", (0.2, 0.5, 0.7, 1.0), -1.0),
            (EmergencySeverity.MEDIUM, "Report MEDIUM Severity (ALS)", (0.8, 0.5, 0.1, 1.0), -0.35),
            (EmergencySeverity.HIGH, "Report HIGH Trauma (ALS)", (0.85, 0.25, 0.15, 1.0), 0.30),
            (EmergencySeverity.CRITICAL, "Report CRITICAL ICU (CCT)", (0.75, 0.1, 0.35, 1.0), 0.95),
        ]

        for sev, label, col, x_pos in severities:
            DirectButton(
                parent=self.panel_emergencies,
                text=label,
                text_scale=0.027,
                text_fg=(1.0, 1.0, 1.0, 1.0),
                frameColor=col,
                frameSize=(-0.28, 0.28, -0.04, 0.04),
                pos=(x_pos, 0, -0.14),
                command=self.on_create_emergency,
                extraArgs=[sev],
                relief=1
            )

        self.emergencies_list_label = DirectLabel(
            parent=self.panel_emergencies,
            text="Active Incidents: None reported yet.",
            text_scale=0.028,
            text_fg=(0.85, 0.90, 0.95, 1.0),
            pos=(-1.35, 0, -0.23),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

    # ---------------- 3. TRAFFIC PANEL ----------------
    def _build_traffic_panel(self):
        self.panel_traffic = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        DirectLabel(
            parent=self.panel_traffic,
            text="ROAD NETWORK HAZARDS & TRAFFIC POLICE AUTO-DISPATCH CONSOLE:",
            text_scale=0.030,
            text_fg=(0.95, 0.95, 0.95, 1.0),
            pos=(-1.35, 0, -0.035),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        hazards = [
            (IncidentType.ROADBLOCK, "Place ROADBLOCK (Edge Closed)", (0.8, 0.15, 0.15, 1.0), -0.85),
            (IncidentType.CONGESTION, "Inject CONGESTION (25% Speed)", (0.85, 0.55, 0.15, 1.0), 0.0),
            (IncidentType.ACCIDENT, "Place VEHICLE ACCIDENT (+60s)", (0.75, 0.35, 0.20, 1.0), 0.85),
        ]

        for inc_type, label, col, x_pos in hazards:
            DirectButton(
                parent=self.panel_traffic,
                text=label,
                text_scale=0.026,
                text_fg=(1.0, 1.0, 1.0, 1.0),
                frameColor=col,
                frameSize=(-0.38, 0.38, -0.032, 0.032),
                pos=(x_pos, 0, -0.085),
                command=self.on_place_traffic_incident,
                extraArgs=[inc_type],
                relief=1
            )

        # Left Column: Active Obstructions List
        DirectLabel(
            parent=self.panel_traffic,
            text="Active Road Obstructions & Closures:",
            text_scale=0.025,
            text_fg=(0.85, 0.90, 0.95, 1.0),
            pos=(-1.35, 0, -0.145),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.traffic_list_label = DirectLabel(
            parent=self.panel_traffic,
            text="All roads open and passable.",
            text_scale=0.023,
            text_fg=(0.80, 0.85, 0.90, 1.0),
            pos=(-1.35, 0, -0.185),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Right Column: Dedicated Traffic Police Dispatch Notification & Control Card
        self.traffic_police_card = DirectFrame(
            parent=self.panel_traffic,
            frameColor=(0.10, 0.14, 0.20, 0.95),
            frameSize=(-0.05, 1.55, -0.22, 0.0),
            pos=(-0.20, 0, -0.14),
            relief=1
        )

        DirectLabel(
            parent=self.traffic_police_card,
            text="TRAFFIC POLICE DISPATCH NOTIFICATION (Auto-Sent on Incident)",
            text_scale=0.026,
            text_fg=(1.0, 0.85, 0.2, 1.0),
            pos=(0.02, 0, -0.032),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.traffic_police_notif_status_label = DirectLabel(
            parent=self.traffic_police_card,
            text="DISPATCH NOTIFICATION: NO (STANDING BY)  |  STATUS: IDLE",
            text_scale=0.025,
            text_fg=(0.75, 0.80, 0.85, 1.0),
            pos=(0.02, 0, -0.070),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.traffic_police_timer_label = DirectLabel(
            parent=self.traffic_police_card,
            text="Response Countdown: Awaiting road hazard to auto-dispatch...",
            text_scale=0.024,
            text_fg=(0.70, 0.75, 0.80, 1.0),
            pos=(0.02, 0, -0.105),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.traffic_police_detail_label = DirectLabel(
            parent=self.traffic_police_card,
            text="Outcome: Accepted = road clears & detours revert. Rejected/Timeout = road stays closed.",
            text_scale=0.022,
            text_fg=(0.65, 0.70, 0.75, 1.0),
            pos=(0.02, 0, -0.140),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Action Buttons in Notification Card
        self.btn_traffic_accept = DirectButton(
            parent=self.traffic_police_card,
            text="[POLICE: CONFIRM CLEARED]",
            text_scale=0.021,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.15, 0.65, 0.35, 1.0),
            frameSize=(-0.22, 0.22, -0.024, 0.024),
            pos=(0.26, 0, -0.185),
            command=self._handle_accept_police,
            relief=1
        )

        self.btn_traffic_reject = DirectButton(
            parent=self.traffic_police_card,
            text="[POLICE: CANNOT CLEAR]",
            text_scale=0.021,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.80, 0.25, 0.20, 1.0),
            frameSize=(-0.22, 0.22, -0.024, 0.024),
            pos=(0.75, 0, -0.185),
            command=self._handle_reject_police,
            relief=1
        )

        self.btn_traffic_realert = DirectButton(
            parent=self.traffic_police_card,
            text="[RE-ALERT POLICE]",
            text_scale=0.021,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.85, 0.55, 0.15, 1.0),
            frameSize=(-0.18, 0.18, -0.024, 0.024),
            pos=(1.22, 0, -0.185),
            command=self._handle_re_alert_police,
            relief=1
        )

    # ---------------- 4. POLICE PANEL ----------------
    def _build_police_panel(self):
        self.panel_police = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        DirectLabel(
            parent=self.panel_police,
            text="TRAFFIC POLICE INCIDENT CLEARANCE CONSOLE:",
            text_scale=0.030,
            text_fg=(0.95, 0.95, 0.95, 1.0),
            pos=(-1.35, 0, -0.035),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        DirectButton(
            parent=self.panel_police,
            text="POLICE: CONFIRM CLEARED",
            text_scale=0.025,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.15, 0.65, 0.35, 1.0),
            frameSize=(-0.30, 0.30, -0.032, 0.032),
            pos=(-0.70, 0, -0.095),
            command=self._handle_accept_police,
            relief=1
        )

        DirectButton(
            parent=self.panel_police,
            text="POLICE: CANNOT CLEAR",
            text_scale=0.025,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.80, 0.25, 0.20, 1.0),
            frameSize=(-0.30, 0.30, -0.032, 0.032),
            pos=(0.0, 0, -0.095),
            command=self._handle_reject_police,
            relief=1
        )

        DirectButton(
            parent=self.panel_police,
            text="RE-ALERT POLICE",
            text_scale=0.025,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.85, 0.55, 0.15, 1.0),
            frameSize=(-0.25, 0.25, -0.032, 0.032),
            pos=(0.65, 0, -0.095),
            command=self._handle_re_alert_police,
            relief=1
        )

        self.btn_police_manual = DirectButton(
            parent=self.panel_police,
            text="DRIVE CRUISER (WASD)",
            text_scale=0.024,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.20, 0.50, 0.75, 1.0),
            frameSize=(-0.25, 0.25, -0.032, 0.032),
            pos=(1.25, 0, -0.095),
            command=self._handle_toggle_police_manual,
            relief=1
        )

        self.police_status_label = DirectLabel(
            parent=self.panel_police,
            text="Traffic Police Department: Status: IDLE | All roads clear.",
            text_scale=0.027,
            text_fg=(0.85, 0.90, 0.95, 1.0),
            pos=(-1.35, 0, -0.17),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.police_outcome_label = DirectLabel(
            parent=self.panel_police,
            text=(
                "OPERATIONAL RULES & CLEARANCE TIMEOUT:\n"
                "• AUTO-ALERT: When any traffic hazard occurs, alert is automatically sent to Traffic Police.\n"
                "• CONFIRM CLEARED: Police confirms the obstruction is cleared -> Road reopens -> Ambulances return to direct route.\n"
                "• CANNOT CLEAR / AUTO-REJECT: If not cleared within 20s, the request is REJECTED automatically -> Road stays closed.\n"
                "• RE-ALERT: Send a fresh clearance alert to police with a new 20-second countdown window."
            ),
            text_scale=0.023,
            text_fg=(0.75, 0.80, 0.85, 1.0),
            pos=(-1.35, 0, -0.22),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

    # ---------------- 5. HOSPITALS PANEL ----------------
    def _build_hospitals_panel(self):
        self.panel_hospitals = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        DirectLabel(
            parent=self.panel_hospitals,
            text="HOSPITAL BED CAPACITY & DIVERSION CONSOLE (Adjust Vacancies & Status Anytime):",
            text_scale=0.030,
            text_fg=(0.95, 0.95, 0.95, 1.0),
            pos=(-1.35, 0, -0.04),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        self.hospital_stat_labels: dict[str, DirectLabel] = {}

        hospitals_cfg = [
            ("HOSP-01", "Central Emergency Trauma", -0.96),
            ("HOSP-02", "Mercy General Care", 0.0),
            ("HOSP-03", "Metro Heart & Critical", 0.96),
        ]

        btn_style_small = {
            "text_scale": 0.022,
            "text_fg": (1.0, 1.0, 1.0, 1.0),
            "frameSize": (-0.08, 0.08, -0.024, 0.024),
            "relief": 1
        }
        btn_style_wide = {
            "text_scale": 0.020,
            "text_fg": (1.0, 1.0, 1.0, 1.0),
            "frameSize": (-0.12, 0.12, -0.022, 0.022),
            "relief": 1
        }

        for h_id, h_name, x_pos in hospitals_cfg:
            card = DirectFrame(
                parent=self.panel_hospitals,
                frameColor=(0.11, 0.15, 0.21, 0.96),
                frameSize=(-0.45, 0.45, -0.30, 0.0),
                pos=(x_pos, 0, -0.075),
                relief=1
            )

            # Hospital Name & ID
            DirectLabel(
                parent=card,
                text=f"{h_name}\n[{h_id}]",
                text_scale=0.024,
                text_fg=(0.25, 0.85, 0.95, 1.0),
                pos=(-0.42, 0, -0.035),
                text_align=TextNode.ALeft,
                frameColor=(0, 0, 0, 0)
            )

            # Live Stats Label
            stat_lbl = DirectLabel(
                parent=card,
                text="Total: -- | Occupied: --\nVacant: -- | Reserved: 0\nStatus: NORMAL",
                text_scale=0.022,
                text_fg=(0.92, 0.94, 0.96, 1.0),
                pos=(-0.42, 0, -0.095),
                text_align=TextNode.ALeft,
                frameColor=(0, 0, 0, 0)
            )
            self.hospital_stat_labels[h_id] = stat_lbl

            # Row 1: Direct Vacancy Nudge Buttons (-3, -1, +1, +3)
            DirectButton(parent=card, text="-3 Vac", frameColor=(0.7, 0.25, 0.2, 1.0), pos=(-0.30, 0, -0.19), command=self._nudge_hospital_vacant, extraArgs=[h_id, -3], **btn_style_small)
            DirectButton(parent=card, text="-1 Vac", frameColor=(0.8, 0.35, 0.2, 1.0), pos=(-0.10, 0, -0.19), command=self._nudge_hospital_vacant, extraArgs=[h_id, -1], **btn_style_small)
            DirectButton(parent=card, text="+1 Vac", frameColor=(0.2, 0.65, 0.35, 1.0), pos=(0.10, 0, -0.19), command=self._nudge_hospital_vacant, extraArgs=[h_id, 1], **btn_style_small)
            DirectButton(parent=card, text="+3 Vac", frameColor=(0.15, 0.75, 0.45, 1.0), pos=(0.30, 0, -0.19), command=self._nudge_hospital_vacant, extraArgs=[h_id, 3], **btn_style_small)

            # Row 2: Instant Overrides (Set FULL (0), Set MAX Vac, Toggle DIVERT)
            DirectButton(parent=card, text="Set FULL (0)", frameColor=(0.85, 0.5, 0.15, 1.0), pos=(-0.28, 0, -0.255), command=self._set_hospital_vacant, extraArgs=[h_id, 0], **btn_style_wide)
            DirectButton(parent=card, text="Set MAX Vac", frameColor=(0.2, 0.55, 0.75, 1.0), pos=(0.0, 0, -0.255), command=self._set_hospital_vacant, extraArgs=[h_id, 999], **btn_style_wide)
            DirectButton(parent=card, text="Toggle DIVERT", frameColor=(0.65, 0.2, 0.45, 1.0), pos=(0.28, 0, -0.255), command=self._toggle_hospital_divert, extraArgs=[h_id], **btn_style_wide)

    def _nudge_hospital_vacant(self, hospital_id: str, delta: int):
        self.on_edit_hospital_beds(hospital_id, -delta, delta)

    def _set_hospital_vacant(self, hospital_id: str, target: int):
        if self.on_set_hospital_vacant:
            self.on_set_hospital_vacant(hospital_id, target)
        else:
            # Fallback
            self.on_edit_hospital_beds(hospital_id, 0, target)

    def _toggle_hospital_divert(self, hospital_id: str):
        if self.on_toggle_hospital_divert:
            self.on_toggle_hospital_divert(hospital_id)

    # ---------------- 6. NAVIGATION PANEL ----------------
    def _build_nav_panel(self):
        self.panel_nav = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        self.nav_status_label = DirectLabel(
            parent=self.panel_nav,
            text="SELECTED AMBULANCE NAVIGATION TELEMETRY:\nNo ambulance selected. Click or deploy a unit to view active route guidance.",
            text_scale=0.028,
            text_fg=(0.90, 0.94, 0.98, 1.0),
            pos=(-1.35, 0, -0.06),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Navigation Action Buttons
        DirectButton(
            parent=self.panel_nav,
            text="CAN'T PROCEED (Algorithmic Recovery)",
            text_scale=0.026,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.85, 0.25, 0.15, 1.0),
            frameSize=(-0.38, 0.38, -0.035, 0.035),
            pos=(-0.85, 0, -0.26),
            command=self.on_cant_proceed,
            relief=1
        )

        # Toggle Manual driving
        self.btn_manual_toggle = DirectButton(
            parent=self.panel_nav,
            text="Switch to Manual (WASD)",
            text_scale=0.026,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.20, 0.55, 0.75, 1.0),
            frameSize=(-0.36, 0.36, -0.035, 0.035),
            pos=(-0.05, 0, -0.26),
            command=self.on_toggle_manual_control,
            relief=1
        )

        # View Route Map / GPS Button
        DirectButton(
            parent=self.panel_nav,
            text="VIEW ROUTE MAP / GPS (M)",
            text_scale=0.026,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.12, 0.65, 0.65, 1.0),
            frameSize=(-0.36, 0.36, -0.035, 0.035),
            pos=(0.75, 0, -0.26),
            command=self._handle_open_route_map,
            relief=1
        )

    def _handle_open_route_map(self):
        if self.on_open_route_map:
            self.on_open_route_map()

    # ---------------- 7. EXPLAINABLE AI PANEL ----------------
    def _build_ai_reason_panel(self):
        self.panel_ai_reason = DirectFrame(parent=self.content_frame, frameColor=(0, 0, 0, 0))

        DirectLabel(
            parent=self.panel_ai_reason,
            text="EXPLAINABLE AI ENGINE — TRANSPARENT ALGORITHMIC DECISION AUDIT:",
            text_scale=0.032,
            text_fg=(0.20, 0.85, 0.95, 1.0),
            pos=(-1.35, 0, -0.05),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        DirectButton(
            parent=self.panel_ai_reason,
            text="SEE REASON (Audit Latest Algorithmic Decision)",
            text_scale=0.028,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.20, 0.65, 0.55, 1.0),
            frameSize=(-0.45, 0.45, -0.035, 0.035),
            pos=(-0.70, 0, -0.12),
            command=self.on_see_reason,
            relief=1
        )

        self.ai_reason_text = DirectLabel(
            parent=self.panel_ai_reason,
            text="Awaiting automated decision events (Dispatch, Hospital Selection, Route Reroute, or Traffic Recovery)...",
            text_scale=0.026,
            text_fg=(0.85, 0.90, 0.95, 1.0),
            pos=(-1.35, 0, -0.19),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

    def update_from_state(self, state: SimulationState):
        """Update dashboard panel displays with fresh state."""
        # 1. Update Emergencies text
        if state.emergencies:
            active_list = [f"[{e.id}] {e.severity.value} ({e.status.value})" for e in state.emergencies.values() if e.status.value != "COMPLETED"]
            self.emergencies_list_label["text"] = f"Active Incidents ({len(active_list)}):\n" + ", ".join(active_list[:6])
        else:
            self.emergencies_list_label["text"] = "Active Incidents: None reported yet. Use buttons above to report."

        # 2. Update Traffic text
        active_inc = [inc for inc in state.road_incidents.values() if inc.cleared_at is None]
        if active_inc:
            txt = f"Active Obstructions ({len(active_inc)}):\n"
            for inc in active_inc[:3]:
                txt += f"• {inc.id}: {inc.incident_type.value} on {inc.edge_id} (Closed: {inc.is_closed})\n"
            self.traffic_list_label["text"] = txt.strip()
        else:
            self.traffic_list_label["text"] = "Active Obstructions: None.\nAll roads open and passable."

        # Update Traffic Police Dispatch Notification Card in Traffic Tab
        p_unit = state.police_units.get("POLICE-01")
        if p_unit:
            notif_str = "YES (ALERT RECEIVED)" if p_unit.notification_received else "NO (STANDING BY)"
            notif_col = (0.2, 0.95, 0.4, 1.0) if p_unit.notification_received else (0.7, 0.75, 0.8, 1.0)

            if p_unit.status == PoliceStatus.REQUESTED:
                elapsed = state.simulation_time - p_unit.notification_time
                remaining = max(0.0, p_unit.response_deadline_sec - elapsed)
                timer_str = f"CLEARANCE TIME LIMIT: {remaining:.1f}s REMAINING [Auto-Rejects on Expiry]"
                timer_col = (1.0, 0.85, 0.2, 1.0) if remaining > 5.0 else (1.0, 0.3, 0.3, 1.0)
                detail_str = f"Hazard: [{p_unit.assigned_incident_id or 'ROAD BLOCK'}] | Police must report: CLEARED or CANNOT CLEAR"
            elif p_unit.status == PoliceStatus.REJECTED or p_unit.status == PoliceStatus.TIMEOUT:
                timer_str = "Police NOT CLEARED / REJECTED! Road remains closed (Ambulances detouring)."
                timer_col = (0.95, 0.3, 0.3, 1.0)
                detail_str = f"Reason: {p_unit.rejection_reason or 'Time limit exceeded / Declined'} | Click [RE-ALERT POLICE] to request clearance again"
            elif p_unit.status == PoliceStatus.IDLE:
                timer_str = "All roads clear. Traffic Police standing by."
                timer_col = (0.7, 0.75, 0.8, 1.0)
                detail_str = "Automatic alert will be sent immediately upon placing any road hazard or block."
            else:
                timer_str = f"Status: {p_unit.status.value}"
                timer_col = (0.8, 0.8, 0.8, 1.0)
                detail_str = f"Target Incident: {p_unit.assigned_incident_id or 'None'}"

            if hasattr(self, "traffic_police_notif_status_label"):
                self.traffic_police_notif_status_label["text"] = f"DISPATCH NOTIFICATION: {notif_str}  |  STATUS: {p_unit.status.value}"
                self.traffic_police_notif_status_label["text_fg"] = notif_col
            if hasattr(self, "traffic_police_timer_label"):
                self.traffic_police_timer_label["text"] = timer_str
                self.traffic_police_timer_label["text_fg"] = timer_col
            if hasattr(self, "traffic_police_detail_label"):
                self.traffic_police_detail_label["text"] = detail_str

            # Update Police Tab status
            if hasattr(self, "police_status_label"):
                self.police_status_label["text"] = (
                    f"Traffic Police Dispatch: Status: {p_unit.status.value} | "
                    f"Alert: {'RECEIVED (CONFIRMATION PENDING)' if p_unit.notification_received else 'STANDBY'} | "
                    f"Assigned Hazard: {p_unit.assigned_incident_id or 'None'}"
                )
            if hasattr(self, "btn_police_manual"):
                self.btn_police_manual["text"] = "DISENGAGE MANUAL (AI)" if p_unit.is_player_controlled else "DRIVE CRUISER (WASD)"
                self.btn_police_manual["frameColor"] = (0.75, 0.35, 0.20, 1.0) if p_unit.is_player_controlled else (0.20, 0.50, 0.75, 1.0)
        else:
            if hasattr(self, "police_status_label"):
                self.police_status_label["text"] = "Traffic Police: Standing by at precinct."
            if hasattr(self, "btn_police_manual"):
                self.btn_police_manual["text"] = "DRIVE CRUISER (WASD)"
                self.btn_police_manual["frameColor"] = (0.20, 0.50, 0.75, 1.0)

        # 4. Update Hospitals cards
        for h_id, h in state.hospitals.items():
            if hasattr(self, "hospital_stat_labels") and h_id in self.hospital_stat_labels:
                status_str = h.operational_status.value
                self.hospital_stat_labels[h_id]["text"] = (
                    f"Total: {h.total_beds} Beds | Occupied: {h.occupied_beds}\n"
                    f"Vacant: {h.vacant_beds} (Avail: {h.effectively_available_beds})\n"
                    f"Inbound Reserved: {len(h.reserved_patient_ids)} | Status: {status_str}"
                )

        # 5. Update Nav text
        if state.selected_ambulance_id and state.selected_ambulance_id in state.fleet:
            amb = state.fleet[state.selected_ambulance_id]
            route = state.active_routes.get(amb.id)
            ctrl = amb.control_mode.value
            status_str = f"Ambulance [{amb.id}] ({amb.unit_class.value}) | Status: {amb.status.value} | Control: {ctrl}\n"
            if route:
                status_str += f"Destination: {route.destination_title} | Next Turn: {route.next_turn}\n"
                status_str += f"Distance Remaining: {route.distance_remaining_meters:.1f}m | ETA: {route.time_remaining_sec:.1f}s"
            else:
                status_str += "No active route. Unit is standing by."
            self.nav_status_label["text"] = status_str
            self.btn_manual_toggle["text"] = f"Switch to {'AI' if amb.control_mode == ControlMode.MANUAL else 'Manual (WASD)'}"
        else:
            self.nav_status_label["text"] = "No ambulance selected. Deploy an ambulance or click a unit in the city."

        # 6. Update AI Reason text
        if state.decision_records:
            latest = state.decision_records[-1]
            self.ai_reason_text["text"] = (
                f"Latest Decision [{latest.id}]: {latest.decision_type.value} at T={latest.timestamp:.1f}s\n"
                f"Action: {latest.selected_name}\n"
                f"Reasoning: {latest.reasoning_summary}\n"
                f"Evaluated {len(latest.eligible_candidates)} eligible, {len(latest.rejected_candidates)} rejected candidate(s)."
            )
