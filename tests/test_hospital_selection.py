"""Tests for dynamic hospital selection, capacity filtering, and bed reservations."""
import pytest

from src.algorithms.hospital_selection import HospitalSelectionAlgorithm
from src.models.ambulance import Ambulance, AmbulanceClass
from src.models.emergency import EmergencyIncident, EmergencySeverity
from src.models.hospital import Hospital, HospitalStatus
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import CityGenerator


@pytest.fixture
def hospital_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph)
    algo = HospitalSelectionAlgorithm()

    # Hospital 1: Closer, but full (0 vacant beds)
    hosp1 = Hospital(
        id="HOSP-FULL",
        name="Full Trauma Center",
        node_id="N_2_2",
        location=graph.nodes["N_2_2"].world_pos,
        total_beds=10,
        occupied_beds=10,
        vacant_beds=0,
        capabilities=["trauma", "icu"],
        operational_status=HospitalStatus.FULL
    )
    # Hospital 2: Further, but has available beds
    hosp2 = Hospital(
        id="HOSP-AVAIL",
        name="Suburban Hospital",
        node_id="N_5_5",
        location=graph.nodes["N_5_5"].world_pos,
        total_beds=12,
        occupied_beds=6,
        vacant_beds=6,
        capabilities=["trauma", "icu"],
        operational_status=HospitalStatus.NORMAL
    )
    # Hospital 3: On DIVERT status
    hosp3 = Hospital(
        id="HOSP-DIVERT",
        name="Diverting Medical Center",
        node_id="N_2_4",
        location=graph.nodes["N_2_4"].world_pos,
        total_beds=8,
        occupied_beds=4,
        vacant_beds=4,
        capabilities=["trauma", "icu"],
        operational_status=HospitalStatus.DIVERT
    )

    state.hospitals["HOSP-FULL"] = hosp1
    state.hospitals["HOSP-AVAIL"] = hosp2
    state.hospitals["HOSP-DIVERT"] = hosp3

    return state, algo, graph

def test_hospital_selection_rejects_full_and_divert(hospital_setup):
    state, algo, graph = hospital_setup

    amb = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_2_1"].world_pos,
        capabilities=["cpr", "trauma"]
    )
    incident = EmergencyIncident(
        id="INC-101",
        location=graph.nodes["N_2_1"].world_pos,
        nearest_node_id="N_2_1",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["trauma"]
    )

    selected_id, route, dec = algo.select_destination(amb, incident, state)

    # Must pick HOSP-AVAIL, rejecting HOSP-FULL (0 beds) and HOSP-DIVERT (status)
    assert selected_id == "HOSP-AVAIL"
    assert route is not None
    assert dec.applied is True

    # Verify atomic bed reservation
    hosp_avail = state.hospitals["HOSP-AVAIL"]
    assert "INC-101" in hosp_avail.reserved_patient_ids
    assert hosp_avail.effectively_available_beds == 5

    # Check rejected audits
    rejections = {c.candidate_id: c.rejection_reason for c in dec.rejected_candidates}
    assert "HOSP-FULL" in rejections
    assert "Zero vacant beds" in rejections["HOSP-FULL"]
    assert "HOSP-DIVERT" in rejections
    assert "diverting" in rejections["HOSP-DIVERT"]
