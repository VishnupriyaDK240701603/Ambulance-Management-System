"""External real-time feed adapters and local simulated data provider."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.models.emergency import EmergencySeverity
from src.models.road_incident import IncidentType
from src.simulation.commands import (
    CreateEmergencyCommand,
    PlaceRoadIncidentCommand,
    UpdateHospitalBedsCommand,
)
from src.simulation.simulation_engine import SimulationEngine


class DataSourceMode(str, Enum):
    LOCAL_SIMULATION = "LOCAL_SIMULATION"
    LOCAL_FEED_ACTIVE = "LOCAL_FEED_ACTIVE"
    EXTERNAL_DISCONNECTED = "EXTERNAL_DISCONNECTED"

@dataclass
class ExternalFeedStatus:
    mode: DataSourceMode = DataSourceMode.LOCAL_SIMULATION
    last_event_timestamp: float = 0.0
    events_received_count: int = 0
    is_connected: bool = True

class ExternalDataProvider:
    """Manages ingestion of external or simulated backend feeds into authoritative state."""

    def __init__(self, engine: SimulationEngine):
        self.engine = engine
        self.status = ExternalFeedStatus()

    def ingest_emergency_report(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """Validate and ingest an emergency report from external feed."""
        required_fields = ["incident_id", "severity", "location", "capabilities"]
        for f in required_fields:
            if f not in payload:
                return False, f"Missing required feed field: {f}"

        raw_sev = payload["severity"]
        try:
            sev = EmergencySeverity(raw_sev.upper() if isinstance(raw_sev, str) else raw_sev)
        except (ValueError, KeyError, AttributeError):
            return False, f"Invalid emergency severity: {raw_sev}"

        cmd = CreateEmergencyCommand(
            emergency_id=str(payload["incident_id"]),
            location=tuple(payload["location"]),
            severity=sev,
            required_capabilities=list(payload["capabilities"]),
            title=payload.get("title", "External Emergency Report"),
            description=payload.get("description", "Ingested from telemetry feed")
        )
        ok, msg = self.engine.execute_command(cmd)
        if ok:
            self.status.events_received_count += 1
            self.status.last_event_timestamp = self.engine.state.simulation_time
        return ok, msg

    def ingest_traffic_hazard(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """Validate and ingest a road hazard / closure from external traffic telemetry."""
        required_fields = ["incident_id", "incident_type", "edge_id", "position"]
        for f in required_fields:
            if f not in payload:
                return False, f"Missing required feed field: {f}"

        raw_type = payload["incident_type"]
        try:
            inc_type = IncidentType(raw_type.upper() if isinstance(raw_type, str) else raw_type)
        except (ValueError, KeyError, AttributeError):
            return False, f"Invalid incident type: {raw_type}"

        cmd = PlaceRoadIncidentCommand(
            incident_id=str(payload["incident_id"]),
            incident_type=inc_type,
            edge_id=str(payload["edge_id"]),
            position=tuple(payload["position"]),
            speed_factor=payload.get("speed_factor", 0.25),
            delay_penalty_sec=payload.get("delay_penalty_sec", 60.0),
            description=payload.get("description", "External traffic alert")
        )
        ok, msg = self.engine.execute_command(cmd)
        if ok:
            self.status.events_received_count += 1
            self.status.last_event_timestamp = self.engine.state.simulation_time
        return ok, msg

    def ingest_hospital_capacity(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """Validate and ingest hospital capacity adjustments from regional health service."""
        required_fields = ["hospital_id", "occupied_beds", "vacant_beds"]
        for f in required_fields:
            if f not in payload:
                return False, f"Missing required feed field: {f}"

        try:
            new_occ = int(payload["occupied_beds"])
            new_vac = int(payload["vacant_beds"])
        except (ValueError, TypeError):
            return False, "occupied_beds and vacant_beds must be valid integers"

        cmd = UpdateHospitalBedsCommand(
            hospital_id=str(payload["hospital_id"]),
            new_occupied=new_occ,
            new_vacant=new_vac
        )
        ok, msg = self.engine.execute_command(cmd)
        if ok:
            self.status.events_received_count += 1
            self.status.last_event_timestamp = self.engine.state.simulation_time
        return ok, msg
