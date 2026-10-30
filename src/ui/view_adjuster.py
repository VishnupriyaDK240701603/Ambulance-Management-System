"""Interactive on-screen Environment & Camera (XYZ) View Adjustment Widget."""
from __future__ import annotations

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import TextNode

from src.world.camera_controller import CameraController


class ViewAdjusterWidget:
    """Collapsible floating HUD panel allowing direct adjustment of camera target XYZ, zoom, pitch, and angle."""

    def __init__(self, parent, camera_ctrl: CameraController):
        self.parent = parent
        self.camera_ctrl = camera_ctrl
        self.is_collapsed = False

        # Toggle button in top right (visible at all times)
        self.btn_toggle = DirectButton(
            parent=self.parent,
            text="Camera Controls (XYZ)",
            text_scale=0.030,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.18, 0.45, 0.70, 0.95),
            frameSize=(-0.25, 0.25, -0.032, 0.032),
            pos=(1.42, 0, 0.88),
            command=self.toggle_collapse,
            relief=1
        )

        # Main floating panel (X: 1.15 to 1.70, Z: 0.15 to 0.84)
        self.panel = DirectFrame(
            parent=self.parent,
            frameColor=(0.08, 0.11, 0.16, 0.94),
            frameSize=(-0.28, 0.28, -0.70, 0.0),
            pos=(1.42, 0, 0.84),
            relief=1
        )

        # Header Title
        DirectLabel(
            parent=self.panel,
            text="VIEWPORT ADJUSTER",
            text_scale=0.032,
            text_fg=(0.20, 0.85, 0.95, 1.0),
            pos=(0, 0, -0.04),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0)
        )

        # Readout label
        self.readout_label = DirectLabel(
            parent=self.panel,
            text="Target: (0.0, 0.0, 0.0)\nDist: 150m | Pitch: 38° | Yaw: 45°",
            text_scale=0.024,
            text_fg=(0.92, 0.95, 0.98, 1.0),
            pos=(0, 0, -0.10),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0)
        )

        btn_style = {
            "text_scale": 0.024,
            "text_fg": (1.0, 1.0, 1.0, 1.0),
            "frameSize": (-0.11, 0.11, -0.025, 0.025),
            "relief": 1
        }

        # 1. Target X Row
        DirectLabel(parent=self.panel, text="Target X:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.17), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="X - 10m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(-0.05, 0, -0.165), command=lambda: self._nudge_target(-10, 0, 0), **btn_style)
        DirectButton(parent=self.panel, text="X + 10m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(0.17, 0, -0.165), command=lambda: self._nudge_target(10, 0, 0), **btn_style)

        # 2. Target Y Row
        DirectLabel(parent=self.panel, text="Target Y:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.23), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="Y - 10m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(-0.05, 0, -0.225), command=lambda: self._nudge_target(0, -10, 0), **btn_style)
        DirectButton(parent=self.panel, text="Y + 10m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(0.17, 0, -0.225), command=lambda: self._nudge_target(0, 10, 0), **btn_style)

        # 3. Target Z Row (Height)
        DirectLabel(parent=self.panel, text="Target Z:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.29), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="Z - 5m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(-0.05, 0, -0.285), command=lambda: self._nudge_target(0, 0, -5), **btn_style)
        DirectButton(parent=self.panel, text="Z + 5m", frameColor=(0.2, 0.35, 0.45, 1.0), pos=(0.17, 0, -0.285), command=lambda: self._nudge_target(0, 0, 5), **btn_style)

        # 4. Zoom Distance Row
        DirectLabel(parent=self.panel, text="Distance:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.35), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="Zoom In", frameColor=(0.25, 0.5, 0.35, 1.0), pos=(-0.05, 0, -0.345), command=lambda: self.camera_ctrl.adjust_distance(-15.0), **btn_style)
        DirectButton(parent=self.panel, text="Zoom Out", frameColor=(0.25, 0.5, 0.35, 1.0), pos=(0.17, 0, -0.345), command=lambda: self.camera_ctrl.adjust_distance(15.0), **btn_style)

        # 5. Tilt Pitch Angle Row
        DirectLabel(parent=self.panel, text="Tilt Pitch:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.41), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="Pitch Down", frameColor=(0.5, 0.35, 0.2, 1.0), pos=(-0.05, 0, -0.405), command=lambda: self.camera_ctrl.adjust_pitch(-7.0), **btn_style)
        DirectButton(parent=self.panel, text="Pitch Up", frameColor=(0.5, 0.35, 0.2, 1.0), pos=(0.17, 0, -0.405), command=lambda: self.camera_ctrl.adjust_pitch(7.0), **btn_style)

        # 6. Yaw Rotation Row
        DirectLabel(parent=self.panel, text="Rotate Yaw:", text_scale=0.023, text_fg=(0.8, 0.85, 0.9, 1.0), pos=(-0.24, 0, -0.47), text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        DirectButton(parent=self.panel, text="Turn Left", frameColor=(0.35, 0.35, 0.55, 1.0), pos=(-0.05, 0, -0.465), command=lambda: self.camera_ctrl.adjust_yaw(-45.0), **btn_style)
        DirectButton(parent=self.panel, text="Turn Right", frameColor=(0.35, 0.35, 0.55, 1.0), pos=(0.17, 0, -0.465), command=lambda: self.camera_ctrl.adjust_yaw(45.0), **btn_style)

        # 7. Quick Presets Header
        DirectLabel(
            parent=self.panel,
            text="VIEW PRESETS:",
            text_scale=0.023,
            text_fg=(0.7, 0.8, 0.9, 1.0),
            pos=(0, 0, -0.525),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0)
        )

        preset_style = {
            "text_scale": 0.023,
            "text_fg": (1.0, 1.0, 1.0, 1.0),
            "frameSize": (-0.11, 0.11, -0.025, 0.025),
            "relief": 1
        }
        DirectButton(parent=self.panel, text="Isometric", frameColor=(0.2, 0.55, 0.65, 1.0), pos=(-0.13, 0, -0.575), command=lambda: self.camera_ctrl.set_preset("ISOMETRIC"), **preset_style)
        DirectButton(parent=self.panel, text="Top-Down", frameColor=(0.2, 0.55, 0.65, 1.0), pos=(0.13, 0, -0.575), command=lambda: self.camera_ctrl.set_preset("TOP_DOWN"), **preset_style)

        DirectButton(parent=self.panel, text="Street Level", frameColor=(0.65, 0.4, 0.15, 1.0), pos=(-0.13, 0, -0.635), command=lambda: self.camera_ctrl.set_preset("STREET"), **preset_style)
        DirectButton(parent=self.panel, text="Center (0,0)", frameColor=(0.7, 0.2, 0.25, 1.0), pos=(0.13, 0, -0.635), command=lambda: self.camera_ctrl.set_preset("CENTER"), **preset_style)

    def _nudge_target(self, dx: float, dy: float, dz: float):
        self.camera_ctrl.adjust_target(dx, dy, dz)

    def toggle_collapse(self):
        """Toggle view adjuster panel visibility."""
        if self.is_collapsed:
            self.panel.show()
            self.btn_toggle["text"] = "Hide Controls"
            self.btn_toggle["frameColor"] = (0.6, 0.25, 0.25, 0.95)
            self.is_collapsed = False
        else:
            self.panel.hide()
            self.btn_toggle["text"] = "Camera Controls (XYZ)"
            self.btn_toggle["frameColor"] = (0.18, 0.45, 0.70, 0.95)
            self.is_collapsed = True

    def update(self):
        """Update live telemetry readout."""
        if self.is_collapsed:
            return
        t = self.camera_ctrl.target
        d = self.camera_ctrl.distance
        p = self.camera_ctrl.pitch
        y = self.camera_ctrl.yaw
        self.readout_label["text"] = (
            f"Target: ({t.getX():+.1f}, {t.getY():+.1f}, {t.getZ():+.1f})\n"
            f"Dist: {d:.0f}m | Pitch: {p:.0f}° | Yaw: {y:.0f}°"
        )
