"""Top Status Bar for LifeLine Dispatch."""
from __future__ import annotations

from collections.abc import Callable

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import TextNode

from src.simulation.simulation_state import SimulationState


class TopStatusBar:
    """Fixed top status bar displaying operational telemetry and global lifecycle controls."""

    def __init__(
        self,
        parent,
        on_start: Callable[[], None],
        on_pause_resume: Callable[[], None],
        on_reset: Callable[[], None]
    ):
        self.parent = parent
        self.on_start = on_start
        self.on_pause_resume = on_pause_resume
        self.on_reset = on_reset

        # Full width top bar (-1.78 to 1.78 horizontally for 16:9, Z: 0.91 to 1.0)
        self.frame = DirectFrame(
            parent=self.parent,
            frameColor=(0.09, 0.12, 0.16, 0.96),
            frameSize=(-1.80, 1.80, -0.05, 0.05),
            pos=(0, 0, 0.95),
            relief=1
        )

        # Title badge
        self.title_label = DirectLabel(
            parent=self.frame,
            text="LIFELINE DISPATCH",
            text_scale=0.042,
            text_fg=(0.20, 0.82, 0.95, 1.0),
            text_align=TextNode.ALeft,
            pos=(-1.35, 0, -0.012),
            frameColor=(0, 0, 0, 0)
        )

        # Status & Time telemetry
        self.telemetry_label = DirectLabel(
            parent=self.frame,
            text="STATUS: READY | TIME: 00:00.0 | FLEET: 0/2 | EMERGENCIES: 0 | BEDS: 12/30 VACANT | TRAFFIC: 0",
            text_scale=0.032,
            text_fg=(0.92, 0.94, 0.96, 1.0),
            text_align=TextNode.ALeft,
            pos=(-0.85, 0, -0.010),
            frameColor=(0, 0, 0, 0)
        )

        # Buttons on right: START, PAUSE/RESUME, RESET
        btn_style = {
            "text_scale": 0.032,
            "text_fg": (1.0, 1.0, 1.0, 1.0),
            "frameSize": (-0.11, 0.11, -0.03, 0.03),
            "relief": 1
        }

        self.btn_start = DirectButton(
            parent=self.frame,
            text="START",
            command=self.on_start,
            frameColor=(0.18, 0.65, 0.35, 1.0),
            pos=(0.88, 0, -0.005),
            **btn_style
        )

        self.btn_pause = DirectButton(
            parent=self.frame,
            text="PAUSE",
            command=self.on_pause_resume,
            frameColor=(0.85, 0.55, 0.15, 1.0),
            pos=(1.12, 0, -0.005),
            **btn_style
        )

        self.btn_reset = DirectButton(
            parent=self.frame,
            text="RESET",
            command=self.on_reset,
            frameColor=(0.75, 0.20, 0.20, 1.0),
            pos=(1.36, 0, -0.005),
            **btn_style
        )

    def update_telemetry(self, state: SimulationState):
        """Update top bar text based on current authoritative simulation state."""
        # Simulation state tag
        if not state.is_started:
            sim_status = "SETUP / READY"
        elif state.is_paused:
            sim_status = "PAUSED"
        else:
            sim_status = "LIVE"

        # Formatted time
        total_sec = state.simulation_time
        mins = int(total_sec // 60)
        secs = total_sec % 60
        time_str = f"{mins:02d}:{secs:04.1f}"

        # Fleet breakdown
        deployed_count = len(state.fleet)
        available_count = state.available_ambulances_count

        # Emergencies count
        active_emergencies = state.active_emergencies_count

        # Hospital beds
        vacant_beds = state.total_vacant_beds
        total_beds = state.total_hospital_beds

        # Road incidents
        traffic_count = state.active_road_incidents_count

        text = (
            f"SIM: {sim_status} | "
            f"TIME: {time_str} | "
            f"FLEET: {deployed_count}/{state.deployment_limit} ({available_count} Avail) | "
            f"EMERGENCIES: {active_emergencies} | "
            f"BEDS: {vacant_beds}/{total_beds} VACANT | "
            f"TRAFFIC: {traffic_count} INCIDENTS"
        )
        self.telemetry_label["text"] = text

        # Update button labels
        if state.is_paused:
            self.btn_pause["text"] = "RESUME"
            self.btn_pause["frameColor"] = (0.22, 0.65, 0.85, 1.0)
        else:
            self.btn_pause["text"] = "PAUSE"
            self.btn_pause["frameColor"] = (0.85, 0.55, 0.15, 1.0)
