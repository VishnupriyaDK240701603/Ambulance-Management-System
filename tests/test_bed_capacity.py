"""Tests for hospital bed capacity invariants, updates, and reservations."""
import pytest

from src.models.hospital import Hospital, HospitalStatus
from src.simulation.commands import UpdateHospitalBedsCommand
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState


def test_hospital_invariant_enforcement():
    # Valid hospital
    hosp = Hospital(
        id="H1",
        name="Test Hospital",
        node_id="N_1_1",
        location=(0, 0, 0),
        total_beds=10,
        occupied_beds=6,
        vacant_beds=4,
        capabilities=["trauma"]
    )
    assert hosp.total_beds == hosp.occupied_beds + hosp.vacant_beds

    # Violating invariant throws ValueError
    with pytest.raises(ValueError):
        Hospital(
            id="H2",
            name="Broken Hospital",
            node_id="N_1_1",
            location=(0, 0, 0),
            total_beds=10,
            occupied_beds=7,
            vacant_beds=5, # 7+5 != 10
            capabilities=["trauma"]
        )

def test_bed_reservation_and_admission():
    hosp = Hospital(
        id="H1",
        name="General Care",
        node_id="N_1_1",
        location=(0, 0, 0),
        total_beds=5,
        occupied_beds=3,
        vacant_beds=2,
        capabilities=["trauma"]
    )
    assert hosp.effectively_available_beds == 2

    # Reserve bed for patient 1
    ok1, _ = hosp.reserve_bed("INC-01")
    assert ok1 is True
    assert hosp.effectively_available_beds == 1

    # Reserve bed for patient 2
    ok2, _ = hosp.reserve_bed("INC-02")
    assert ok2 is True
    assert hosp.effectively_available_beds == 0
    assert hosp.operational_status == HospitalStatus.FULL

    # Patient 3 tries to reserve: rejected (no beds available)
    ok3, reason = hosp.reserve_bed("INC-03")
    assert ok3 is False
    assert "no available vacant beds" in reason

    # Admit patient 1: converts reservation into occupied bed
    ok_admit, _ = hosp.admit_patient("INC-01")
    assert ok_admit is True
    assert hosp.occupied_beds == 4
    assert hosp.vacant_beds == 1
    assert hosp.total_beds == 5

def test_update_hospital_beds_command():
    state = SimulationState()
    hosp = Hospital(
        id="HOSP-01",
        name="Trauma Center",
        node_id="N_1_1",
        location=(0, 0, 0),
        total_beds=10,
        occupied_beds=5,
        vacant_beds=5,
        capabilities=["trauma"]
    )
    state.hospitals["HOSP-01"] = hosp
    engine = SimulationEngine(state)

    # Valid bed update
    ok, _ = engine.execute_command(UpdateHospitalBedsCommand("HOSP-01", new_occupied=7, new_vacant=3))
    assert ok is True
    assert hosp.occupied_beds == 7
    assert hosp.vacant_beds == 3

    # Invalid total mismatch rejected
    ok_bad, msg = engine.execute_command(UpdateHospitalBedsCommand("HOSP-01", new_occupied=8, new_vacant=4))
    assert ok_bad is False
    assert "mismatch" in msg.lower()
    assert hosp.occupied_beds == 7  # Unchanged

def test_all_hospitals_vacancy_adjustments_running_and_paused():
    """Verify that any hospital vacancy can be adjusted anytime whether running or paused."""
    from src.app.application import LifeLineDispatchApp
    app = LifeLineDispatchApp(headless=True)

    # 3 default hospitals present
    assert len(app.state.hospitals) == 3
    assert "HOSP-01" in app.state.hospitals
    assert "HOSP-02" in app.state.hospitals
    assert "HOSP-03" in app.state.hospitals

    h1 = app.state.hospitals["HOSP-01"]
    h2 = app.state.hospitals["HOSP-02"]
    h3 = app.state.hospitals["HOSP-03"]

    # When paused (or not yet started), change vacancy of HOSP-01
    app.handle_set_hospital_vacant("HOSP-01", 1)
    assert h1.vacant_beds == 1
    assert h1.occupied_beds == h1.total_beds - 1

    # Nudge HOSP-02 by +2 vacant beds
    initial_vac2 = h2.vacant_beds
    app.handle_edit_hospital_beds("HOSP-02", -2, 2)
    assert h2.vacant_beds == initial_vac2 + 2

    # Toggle HOSP-03 to DIVERT
    assert h3.operational_status == HospitalStatus.NORMAL
    app.handle_toggle_hospital_divert("HOSP-03")
    assert h3.operational_status == HospitalStatus.DIVERT

    # Start simulation
    app.handle_start()
    assert app.state.is_started is True
    assert app.state.is_paused is False

    # While running, change vacancy of HOSP-02 to 0 (FULL)
    app.handle_set_hospital_vacant("HOSP-02", 0)
    assert h2.vacant_beds == 0
    assert h2.occupied_beds == h2.total_beds
    assert h2.operational_status == HospitalStatus.FULL

    # While running, set HOSP-01 to max vacant
    app.handle_set_hospital_vacant("HOSP-01", h1.total_beds)
    assert h1.vacant_beds == h1.total_beds
    assert h1.occupied_beds == 0

    # Pause simulation
    app.handle_pause_resume()
    assert app.state.is_paused is True

    # While paused, toggle HOSP-03 back to NORMAL and restore vacancy
    app.handle_toggle_hospital_divert("HOSP-03")
    assert h3.operational_status == HospitalStatus.NORMAL
    app.handle_set_hospital_vacant("HOSP-03", 5)
    assert h3.vacant_beds == 5

    app.destroy()
    import builtins
    if hasattr(builtins, "base"):
        delattr(builtins, "base")
