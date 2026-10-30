"""Event logging and history storage."""
from __future__ import annotations

from collections.abc import Callable

from src.simulation.events import EventType, SimulationEvent


class EventLog:
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.history: list[SimulationEvent] = []
        self.listeners: list[Callable[[SimulationEvent], None]] = []

    def subscribe(self, callback: Callable[[SimulationEvent], None]) -> None:
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unsubscribe(self, callback: Callable[[SimulationEvent], None]) -> None:
        if callback in self.listeners:
            self.listeners.remove(callback)

    def record(self, event: SimulationEvent) -> None:
        self.history.append(event)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception as e:  # noqa: BLE001
                print(f"[EventLog] Error notifying listener: {e}")

    def get_recent(self, count: int = 20, event_type: EventType | None = None) -> list[SimulationEvent]:
        if event_type:
            filtered = [e for e in self.history if e.event_type == event_type]
            return filtered[-count:]
        return self.history[-count:]
