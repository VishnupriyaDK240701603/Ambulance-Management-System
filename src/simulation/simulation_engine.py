"""Simulation Engine managing deterministic updates, subsystems, and authoritative state."""
from __future__ import annotations

from collections.abc import Callable

from src.simulation.commands import Command
from src.simulation.event_log import EventLog
from src.simulation.simulation_state import SimulationState


class SimulationEngine:
    """Authoritative coordinator of the simulation lifecycle and systems."""

    def __init__(self, state: SimulationState, fixed_dt: float = 0.05):
        self.state = state
        self.fixed_dt = fixed_dt
        self.accumulator: float = 0.0
        self.event_log = EventLog()
        self.subsystems: list[Callable[[SimulationState, float], None]] = []

    def register_subsystem(self, system_fn: Callable[[SimulationState, float], None]) -> None:
        if system_fn not in self.subsystems:
            self.subsystems.append(system_fn)

    def execute_command(self, cmd: Command) -> tuple[bool, str]:
        """Execute command atomically and dispatch resulting events."""
        success, message, events = cmd.execute(self.state)
        for ev in events:
            self.event_log.record(ev)
        return success, message

    def update(self, delta_time: float) -> None:
        """Advance simulation using a fixed timestep accumulator."""
        if not self.state.is_started or self.state.is_paused:
            return

        # Cap max frame delta to prevent spiral of death
        clamped_dt = min(delta_time, 0.2)
        self.accumulator += clamped_dt

        while self.accumulator >= self.fixed_dt:
            self._step(self.fixed_dt)
            self.accumulator -= self.fixed_dt

    def _step(self, dt: float) -> None:
        """Execute one deterministic simulation step."""
        self.state.simulation_time += dt

        # Run registered simulation subsystems
        for sys_fn in self.subsystems:
            try:
                sys_fn(self.state, dt)
            except Exception as e:  # noqa: BLE001
                err_key = (getattr(sys_fn, "__name__", str(sys_fn)), str(e))
                if not hasattr(self, "_last_errors"):
                    self._last_errors = set()
                if err_key not in self._last_errors:
                    self._last_errors.add(err_key)
                    import traceback
                    print(f"[SimulationEngine] Subsystem [{err_key[0]}] error: {e}")
                    traceback.print_exc()
