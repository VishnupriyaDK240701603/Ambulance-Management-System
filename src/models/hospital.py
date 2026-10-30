"""Hospital model with bed capacity invariants and reservation mechanics."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HospitalStatus(str, Enum):
    NORMAL = "NORMAL"
    DIVERT = "DIVERT"
    FULL = "FULL"
    CRITICAL = "CRITICAL"

@dataclass
class Hospital:
    id: str
    name: str
    node_id: str
    location: tuple[float, float, float]
    total_beds: int
    occupied_beds: int
    vacant_beds: int
    capabilities: list[str]
    operational_status: HospitalStatus = HospitalStatus.NORMAL
    reserved_patient_ids: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.validate_invariants()

    def validate_invariants(self) -> None:
        """Enforce total_beds = occupied_beds + vacant_beds and non-negative counts."""
        if self.total_beds < 0 or self.occupied_beds < 0 or self.vacant_beds < 0:
            raise ValueError(f"Hospital {self.id}: Bed counts cannot be negative.")
        if self.occupied_beds + self.vacant_beds != self.total_beds:
            raise ValueError(
                f"Hospital {self.id}: Invariant violated! "
                f"Occupied ({self.occupied_beds}) + Vacant ({self.vacant_beds}) != Total ({self.total_beds})"
            )

    @property
    def effectively_available_beds(self) -> int:
        """Vacant beds minus active patient reservations."""
        return max(0, self.vacant_beds - len(self.reserved_patient_ids))

    def reserve_bed(self, emergency_id: str) -> tuple[bool, str]:
        """Reserve a vacant bed for an incoming patient."""
        if self.operational_status == HospitalStatus.DIVERT:
            return False, f"{self.name} is on DIVERT status"
        if self.effectively_available_beds <= 0:
            return False, f"{self.name} has no available vacant beds (Vacant: {self.vacant_beds}, Reserved: {len(self.reserved_patient_ids)})"
        
        self.reserved_patient_ids.add(emergency_id)
        if self.effectively_available_beds == 0:
            self.operational_status = HospitalStatus.FULL
        return True, f"Bed reserved at {self.name} for incident {emergency_id}"

    def release_reservation(self, emergency_id: str) -> None:
        """Release reservation if transport is cancelled or redirected."""
        self.reserved_patient_ids.discard(emergency_id)
        if self.operational_status == HospitalStatus.FULL and self.effectively_available_beds > 0:
            self.operational_status = HospitalStatus.NORMAL

    def admit_patient(self, emergency_id: str) -> tuple[bool, str]:
        """Admit incoming patient, converting reserved/vacant bed into occupied bed."""
        self.reserved_patient_ids.discard(emergency_id)
        if self.vacant_beds <= 0:
            return False, f"Cannot admit patient to {self.name}: no vacant beds"
        self.vacant_beds -= 1
        self.occupied_beds += 1
        self.validate_invariants()
        if self.vacant_beds == 0:
            self.operational_status = HospitalStatus.FULL
        return True, f"Patient from {emergency_id} admitted to {self.name}"

    def update_bed_counts(self, new_occupied: int, new_vacant: int) -> tuple[bool, str]:
        """Update bed counts while respecting invariants and reservations."""
        if new_occupied < 0 or new_vacant < 0:
            return False, "Bed counts cannot be negative"
        if new_occupied + new_vacant != self.total_beds:
            return False, f"Total beds mismatch: sum ({new_occupied + new_vacant}) does not match total capacity ({self.total_beds})"
        if new_vacant < len(self.reserved_patient_ids):
            return False, f"Cannot reduce vacant beds to {new_vacant}; {len(self.reserved_patient_ids)} incoming patients have reservations"
        
        self.occupied_beds = new_occupied
        self.vacant_beds = new_vacant
        self.validate_invariants()
        if self.effectively_available_beds == 0:
            self.operational_status = HospitalStatus.FULL
        elif self.operational_status == HospitalStatus.FULL:
            self.operational_status = HospitalStatus.NORMAL
        return True, "Bed counts updated successfully"
