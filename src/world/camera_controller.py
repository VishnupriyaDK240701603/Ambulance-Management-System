"""Smooth RTS/Simulation Isometric Camera Controller for Panda3D."""
from __future__ import annotations

import math

from direct.showbase.DirectObject import DirectObject
from panda3d.core import Point3


class CameraController(DirectObject):
    """Controls the isometric orbital/panning camera."""

    def __init__(self, base, target: Point3 | None = None):
        super().__init__()
        self.base = base
        self.target = Point3(target) if target is not None else Point3(0, 0, 0)

        # Spherical coords: distance, yaw (heading), pitch (elevation)
        self.distance = 150.0
        self.min_distance = 30.0
        self.max_distance = 320.0
        self.yaw = 45.0          # 45 deg isometric angle
        self.pitch = 38.0        # ~38 deg downward tilt
        self.min_pitch = 15.0
        self.max_pitch = 75.0

        self.pan_speed = 70.0
        self.zoom_speed = 15.0
        self.rot_speed = 60.0

        # Input state tracking
        self.keys = {
            "pan_left": False,
            "pan_right": False,
            "pan_up": False,
            "pan_down": False,
            "rot_left": False,
            "rot_right": False,
        }

        self.is_dragging_mouse = False
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0

        # Create camera pivot node
        self.pivot = self.base.render.attachNewNode("CameraPivot")
        self.pivot.setPos(self.target)

        self._setup_keybindings()
        self._update_camera()

        # Add per-frame task
        self.base.taskMgr.add(self._update_task, "CameraControllerUpdate")

    def _setup_keybindings(self):
        # Keyboard pan bindings
        self.accept("arrow_left", self._set_key, ["pan_left", True])
        self.accept("arrow_left-up", self._set_key, ["pan_left", False])
        self.accept("arrow_right", self._set_key, ["pan_right", True])
        self.accept("arrow_right-up", self._set_key, ["pan_right", False])
        self.accept("arrow_up", self._set_key, ["pan_up", True])
        self.accept("arrow_up-up", self._set_key, ["pan_up", False])
        self.accept("arrow_down", self._set_key, ["pan_down", True])
        self.accept("arrow_down-up", self._set_key, ["pan_down", False])

        # Rotation keys
        self.accept("q", self._set_key, ["rot_left", True])
        self.accept("q-up", self._set_key, ["rot_left", False])
        self.accept("e", self._set_key, ["rot_right", True])
        self.accept("e-up", self._set_key, ["rot_right", False])

        # Zoom keys
        self.accept("wheel_up", self._on_zoom, [-1.0])
        self.accept("wheel_down", self._on_zoom, [1.0])
        self.accept("page_up", self._on_zoom, [-1.0])
        self.accept("page_down", self._on_zoom, [1.0])
        self.accept("+", self._on_zoom, [-1.0])
        self.accept("=", self._on_zoom, [-1.0])
        self.accept("-", self._on_zoom, [1.0])

        # Reset camera
        self.accept("home", self.reset_view)

        # Mouse drag for orbit/pan
        self.accept("mouse3", self._on_mouse_down)
        self.accept("mouse3-up", self._on_mouse_up)
        self.accept("mouse2", self._on_mouse_down)
        self.accept("mouse2-up", self._on_mouse_up)

    def _set_key(self, key_name: str, value: bool):
        self.keys[key_name] = value

    def _on_zoom(self, direction: float):
        self.distance = max(self.min_distance, min(self.max_distance, self.distance + direction * self.zoom_speed))
        self._update_camera()

    def _on_mouse_down(self):
        if hasattr(self.base, "mouseWatcherNode") and self.base.mouseWatcherNode and self.base.mouseWatcherNode.hasMouse():
            self.is_dragging_mouse = True
            self.last_mouse_x = self.base.mouseWatcherNode.getMouseX()
            self.last_mouse_y = self.base.mouseWatcherNode.getMouseY()

    def _on_mouse_up(self):
        self.is_dragging_mouse = False

    def reset_view(self):
        self.target = Point3(0, 0, 0)
        self.distance = 150.0
        self.yaw = 45.0
        self.pitch = 38.0
        self.pivot.setPos(self.target)
        self._update_camera()

    def focus_on(self, x: float, y: float, z: float = 0.0):
        self.target = Point3(x, y, z)
        self.pivot.setPos(self.target)
        self._update_camera()

    def adjust_target(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0):
        """Nudge camera focal target along world X, Y, Z."""
        self.target.x = max(-220.0, min(220.0, self.target.x + dx))
        self.target.y = max(-220.0, min(220.0, self.target.y + dy))
        self.target.z = max(-50.0, min(100.0, self.target.z + dz))
        self.pivot.setPos(self.target)
        self._update_camera()

    def set_target_xyz(self, x: float, y: float, z: float):
        """Set exact camera target focal coordinates."""
        self.target = Point3(x, y, z)
        self.pivot.setPos(self.target)
        self._update_camera()

    def adjust_distance(self, delta: float):
        """Nudge camera zoom distance."""
        self.distance = max(self.min_distance, min(self.max_distance, self.distance + delta))
        self._update_camera()

    def adjust_pitch(self, delta: float):
        """Nudge elevation pitch angle."""
        self.pitch = max(self.min_pitch, min(self.max_pitch, self.pitch + delta))
        self._update_camera()

    def adjust_yaw(self, delta: float):
        """Nudge horizontal rotation angle."""
        self.yaw = (self.yaw + delta) % 360.0
        self._update_camera()

    def set_preset(self, preset_name: str):
        """Apply a predefined camera vantage angle."""
        if preset_name == "ISOMETRIC":
            self.distance = 150.0
            self.yaw = 45.0
            self.pitch = 38.0
            self.target = Point3(0, 0, 0)
        elif preset_name == "TOP_DOWN":
            self.distance = 160.0
            self.yaw = 0.0
            self.pitch = 75.0
            self.target = Point3(0, 0, 0)
        elif preset_name == "STREET":
            self.distance = 55.0
            self.yaw = 45.0
            self.pitch = 20.0
        elif preset_name == "NORTH":
            self.yaw = 0.0
        elif preset_name == "EAST":
            self.yaw = 90.0
        elif preset_name == "CENTER":
            self.target = Point3(0, 0, 0)

        self.pivot.setPos(self.target)
        self._update_camera()

    def toggle_overhead_view(self):
        """Toggle between isometric 3D view and overhead tactical map camera."""
        if self.pitch >= 70.0:
            self.set_preset("ISOMETRIC")
        else:
            self.set_preset("TOP_DOWN")

    def follow_target(self, x: float, y: float, z: float = 0.0, smoothing: float = 0.20):
        """Smoothly glide camera pivot to follow a moving vehicle."""
        self.target.x += (x - self.target.x) * smoothing
        self.target.y += (y - self.target.y) * smoothing
        self.target.z += (z - self.target.z) * smoothing
        self.pivot.setPos(self.target)
        self._update_camera()

    def _update_task(self, task):
        dt = self.base.clock.getDt()
        dt = min(dt, 0.1)

        # Handle keyboard rotation
        if self.keys["rot_left"]:
            self.yaw = (self.yaw - self.rot_speed * dt) % 360.0
        if self.keys["rot_right"]:
            self.yaw = (self.yaw + self.rot_speed * dt) % 360.0

        # Handle mouse drag
        if self.is_dragging_mouse and hasattr(self.base, "mouseWatcherNode") and self.base.mouseWatcherNode and self.base.mouseWatcherNode.hasMouse():
            mx = self.base.mouseWatcherNode.getMouseX()
            my = self.base.mouseWatcherNode.getMouseY()
            dx = mx - self.last_mouse_x
            dy = my - self.last_mouse_y
            self.last_mouse_x = mx
            self.last_mouse_y = my

            self.yaw = (self.yaw - dx * 140.0) % 360.0
            self.pitch = max(self.min_pitch, min(self.max_pitch, self.pitch + dy * 70.0))

        # Handle panning along camera horizontal plane
        pan_dx = 0.0
        pan_dy = 0.0
        if self.keys["pan_left"]:
            pan_dx -= 1.0
        if self.keys["pan_right"]:
            pan_dx += 1.0
        if self.keys["pan_up"]:
            pan_dy += 1.0
        if self.keys["pan_down"]:
            pan_dy -= 1.0

        if pan_dx != 0.0 or pan_dy != 0.0:
            rad = math.radians(self.yaw)
            sin_a = math.sin(rad)
            cos_a = math.cos(rad)
            # Forward vector in world XY
            forward_x = sin_a
            forward_y = cos_a
            # Right vector
            right_x = cos_a
            right_y = -sin_a

            move_x = (right_x * pan_dx + forward_x * pan_dy) * self.pan_speed * dt
            move_y = (right_y * pan_dx + forward_y * pan_dy) * self.pan_speed * dt

            self.target.x = max(-180.0, min(180.0, self.target.x + move_x))
            self.target.y = max(-180.0, min(180.0, self.target.y + move_y))
            self.pivot.setPos(self.target)

        self._update_camera()
        return task.cont

    def _update_camera(self):
        """Position camera in spherical coords relative to pivot."""
        if self.base.camera is None:
            return

        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)

        cam_x = self.target.x - self.distance * math.cos(rad_pitch) * math.sin(rad_yaw)
        cam_y = self.target.y - self.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
        cam_z = self.target.z + self.distance * math.sin(rad_pitch)

        self.base.camera.setPos(cam_x, cam_y, cam_z)
        self.base.camera.lookAt(self.target)
