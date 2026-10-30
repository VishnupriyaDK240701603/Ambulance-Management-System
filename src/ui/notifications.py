"""Toast and alert banner notifications for LifeLine Dispatch."""
from __future__ import annotations

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import TextNode


class NotificationManager:
    """Manages on-screen status notifications and alerts."""

    def __init__(self, parent):
        self.parent = parent
        self.frame = DirectFrame(
            parent=self.parent,
            frameColor=(0.12, 0.15, 0.20, 0.92),
            frameSize=(-0.75, 0.75, -0.045, 0.045),
            pos=(0, 0, 0.86),
            relief=1
        )
        self.label = DirectLabel(
            parent=self.frame,
            text="LifeLine Dispatch initialized. Ready to deploy fleet.",
            text_scale=0.038,
            text_fg=(0.95, 0.96, 0.98, 1.0),
            text_align=TextNode.ACenter,
            pos=(0, 0, -0.012),
            frameColor=(0, 0, 0, 0)
        )
        self.timer: float = 5.0
        self.default_message = "Ready. Configure fleet deployment and scenario."

    def show(self, message: str, is_error: bool = False, duration: float = 4.5):
        self.label["text"] = message
        if is_error:
            self.label["text_fg"] = (1.0, 0.35, 0.35, 1.0)
            self.frame["frameColor"] = (0.28, 0.10, 0.12, 0.94)
        else:
            self.label["text_fg"] = (0.35, 0.95, 0.65, 1.0)
            self.frame["frameColor"] = (0.10, 0.22, 0.16, 0.94)
        self.timer = duration
        self.frame.show()

    def update(self, dt: float):
        if self.timer > 0:
            self.timer -= dt
            if self.timer <= 0:
                self.label["text"] = self.default_message
                self.label["text_fg"] = (0.85, 0.88, 0.92, 1.0)
                self.frame["frameColor"] = (0.12, 0.15, 0.20, 0.92)
