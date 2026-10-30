"""Authoritative validation rules for LifeLine Dispatch."""
from __future__ import annotations

import math

from src.models.ambulance import Ambulance, AmbulanceClass
from src.models.hospital import Hospital
from src.world.road_graph import RoadGraph


class ValidationResult:
    def __init__(self, is_valid: bool, reason: str = ""):
        self.is_valid = is_valid
        self.reason = reason

    def __bool__(self):
        return self.is_valid

class ScenarioValidator:
    """Validates simulation state and command preconditions."""

    @staticmethod
    def validate_ambulance_deployment(
        unit_id: str,
        unit_class: AmbulanceClass,
        position: tuple[float, float, float],
        current_fleet: dict[str, Ambulance],
        deployment_limit: int,
        road_graph: RoadGraph,
        min_vehicle_spacing: float = 4.0
    ) -> ValidationResult:
        """Validate deployment constraints: limit, legality of location, no overlapping."""
        # 1. Deployment limit check
        if len(current_fleet) >= deployment_limit:
            return ValidationResult(
                False,
                f"Fleet deployment limit reached ({len(current_fleet)}/{deployment_limit}). Increase limit or recall a unit."
            )

        # 2. Duplicate ID check
        if unit_id in current_fleet:
            return ValidationResult(False, f"Ambulance with ID '{unit_id}' already exists.")

        # 3. Valid drivable road check
        is_drivable, road_info = road_graph.is_on_drivable_road(position[0], position[1], tolerance=4.0)
        if not is_drivable:
            return ValidationResult(False, f"Invalid deployment location: {road_info}")

        # 4. Overlap check with other deployed ambulances
        for other in current_fleet.values():
            dist = math.hypot(position[0] - other.position[0], position[1] - other.position[1])
            if dist < min_vehicle_spacing:
                return ValidationResult(
                    False,
                    f"Deployment position overlaps with existing unit {other.id} ({dist:.1f}m < {min_vehicle_spacing}m)."
                )

        return ValidationResult(True, "Deployment position valid.")

    @staticmethod
    def validate_hospital_capacity(hospital: Hospital, new_occupied: int, new_vacant: int) -> ValidationResult:
        """Validate proposed bed updates against hospital invariants and reservations."""
        if new_occupied < 0 or new_vacant < 0:
            return ValidationResult(False, "Bed counts cannot be negative.")
        if new_occupied + new_vacant != hospital.total_beds:
            return ValidationResult(
                False,
                f"Total beds mismatch: Occupied ({new_occupied}) + Vacant ({new_vacant}) != Capacity ({hospital.total_beds})"
            )
        active_reservations = len(hospital.reserved_patient_ids)
        if new_vacant < active_reservations:
            return ValidationResult(
                False,
                f"Cannot reduce vacant beds to {new_vacant}: {active_reservations} incoming patients currently hold reservations."
            )
        return ValidationResult(True, "Hospital capacity valid.")
