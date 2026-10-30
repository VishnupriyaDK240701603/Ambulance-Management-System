"""Tests for capability-aware ambulance dispatch and Explainable AI audits."""
import pytest

from src.algorithms.dispatch import DispatchAlgorithm
from src.models.ambulance import Ambulance, AmbulanceClass, AmbulanceStatus
from src.models.emergency import EmergencyIncident, EmergencySeverity, IncidentStatus
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import CityGenerator


@pytest.fixture
def dispatch_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph, deployment_limit=3)
    algo = DispatchAlgorithm()
    return state, algo, graph

def test_dispatch_capability_filtering(dispatch_setup):
    state, algo, graph = dispatch_setup

    # Deploy BLS unit
    amb_bls = Ambulance(
        id="AMB-BLS-01",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_1_1"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid"]
    )
    state.fleet[amb_bls.id] = amb_bls

    # Deploy ALS unit
    amb_als = Ambulance(
        id="AMB-ALS-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_4_4"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "defibrillator", "intubation", "iv_access"]
    )
    state.fleet[amb_als.id] = amb_als

    # Emergency requiring cardiac care (defibrillator)
    incident = EmergencyIncident(
        id="INC-001",
        location=graph.nodes["N_1_2"].world_pos,
        nearest_node_id="N_1_2",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["cpr", "defibrillator"]
    )

    selected_id, route, dec = algo.evaluate_and_dispatch(incident, state)

    # BLS is closer to N_1_2, but MUST be rejected due to missing capability!
    assert selected_id == "AMB-ALS-01"
    assert route is not None
    assert dec.applied is True

    # Audit rejected candidates in decision record
    rejected_bls = [c for c in dec.rejected_candidates if c.candidate_id == "AMB-BLS-01"]
    assert len(rejected_bls) == 1
    assert "Missing" in rejected_bls[0].rejection_reason

def test_dispatch_rejects_unavailable_ambulances(dispatch_setup):
    state, algo, graph = dispatch_setup

    amb = Ambulance(
        id="AMB-ALS-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_1_1"].world_pos,
        status=AmbulanceStatus.UNAVAILABLE,
        capabilities=["cpr", "defibrillator"]
    )
    state.fleet[amb.id] = amb

    incident = EmergencyIncident(
        id="INC-002",
        location=graph.nodes["N_2_2"].world_pos,
        nearest_node_id="N_2_2",
        severity=EmergencySeverity.MEDIUM,
        required_capabilities=["cpr"]
    )

    selected_id, route, dec = algo.evaluate_and_dispatch(incident, state)
    assert selected_id is None
    assert route is None
    assert dec.applied is False
    assert len(dec.rejected_candidates) == 1
    assert "UNAVAILABLE" in dec.rejected_candidates[0].rejection_reason

def test_dispatch_prefers_closer_eligible_unit(dispatch_setup):
    state, algo, graph = dispatch_setup

    # Two eligible ALS units at different distances
    amb_near = Ambulance(
        id="AMB-ALS-NEAR",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_2_1"].world_pos,
        capabilities=["cpr", "oxygen", "iv_access"]
    )
    amb_far = Ambulance(
        id="AMB-ALS-FAR",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_6_6"].world_pos,
        capabilities=["cpr", "oxygen", "iv_access"]
    )
    state.fleet[amb_near.id] = amb_near
    state.fleet[amb_far.id] = amb_far

    incident = EmergencyIncident(
        id="INC-003",
        location=graph.nodes["N_2_2"].world_pos,
        nearest_node_id="N_2_2",
        severity=EmergencySeverity.MEDIUM,
        required_capabilities=["cpr", "iv_access"]
    )

    selected_id, _route, dec = algo.evaluate_and_dispatch(incident, state)
    assert selected_id == "AMB-ALS-NEAR"
    assert len(dec.eligible_candidates) == 2
    # Verify candidate ranking
    assert dec.eligible_candidates[0].candidate_id == "AMB-ALS-NEAR"
    assert dec.eligible_candidates[1].candidate_id == "AMB-ALS-FAR"

def test_batch_dispatch_two_emergencies_two_ambulances(dispatch_setup):
    """Pillars 1 & 2: Joint Hungarian matching dispatches both ambulances simultaneously to matching tiers."""
    state, algo, graph = dispatch_setup

    # Deploy BLS unit
    amb_bls = Ambulance(
        id="AMB-BLS-01",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_1_1"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting"],
        speed_mps=14.0
    )
    state.fleet[amb_bls.id] = amb_bls

    # Deploy ALS unit
    amb_als = Ambulance(
        id="AMB-ALS-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_3_3"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting", "iv_access", "intubation", "cardiac_monitor", "defibrillator"],
        speed_mps=16.0
    )
    state.fleet[amb_als.id] = amb_als

    # Emergency 1: Low severity (sprain/fall)
    inc_low = EmergencyIncident(
        id="INC-LOW-01",
        location=graph.nodes["N_1_2"].world_pos,
        nearest_node_id="N_1_2",
        severity=EmergencySeverity.LOW,
        required_capabilities=["cpr", "basic_first_aid"],
        status=IncidentStatus.WAITING_DISPATCH,
        title="Minor Fall"
    )
    state.emergencies[inc_low.id] = inc_low

    # Emergency 2: High severity (cardiac arrest)
    inc_high = EmergencyIncident(
        id="INC-HIGH-01",
        location=graph.nodes["N_3_4"].world_pos,
        nearest_node_id="N_3_4",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["cpr", "cardiac_monitor", "defibrillator", "iv_access"],
        status=IncidentStatus.WAITING_DISPATCH,
        title="Severe Cardiac Arrest"
    )
    state.emergencies[inc_high.id] = inc_high

    # Perform coordinated joint dispatch
    results = algo.dispatch_waiting_emergencies(state)
    assert len(results) == 2

    res_map = {em_id: amb_id for em_id, amb_id, route, dec in results}

    # Verify both emergencies are assigned
    assert res_map["INC-LOW-01"] == "AMB-BLS-01"
    assert res_map["INC-HIGH-01"] == "AMB-ALS-01"

    # Verify both got routes
    for em_id, amb_id, route, dec in results:
        assert route is not None
        assert dec.applied is True
        assert "Joint Multi-Incident Optimizer" in dec.reasoning_summary

def test_concurrent_dispatch_patient_lifecycle(dispatch_setup):
    """Pillar 2: Verify update_patient_lifecycle activates BOTH ambulances with none left idle."""
    from src.systems.patient_lifecycle import update_patient_lifecycle
    state, _algo, graph = dispatch_setup

    amb1 = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_1_1"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting"]
    )
    amb2 = Ambulance(
        id="AMB-02",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_4_4"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting", "iv_access", "cardiac_monitor", "defibrillator"]
    )
    state.fleet[amb1.id] = amb1
    state.fleet[amb2.id] = amb2

    em1 = EmergencyIncident(
        id="INC-01",
        location=graph.nodes["N_1_3"].world_pos,
        nearest_node_id="N_1_3",
        severity=EmergencySeverity.LOW,
        required_capabilities=["cpr", "basic_first_aid"],
        status=IncidentStatus.WAITING_DISPATCH
    )
    em2 = EmergencyIncident(
        id="INC-02",
        location=graph.nodes["N_4_5"].world_pos,
        nearest_node_id="N_4_5",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["cpr", "cardiac_monitor", "defibrillator"],
        status=IncidentStatus.WAITING_DISPATCH
    )
    state.emergencies[em1.id] = em1
    state.emergencies[em2.id] = em2

    # Step lifecycle once
    update_patient_lifecycle(state, 0.05)

    # BOTH ambulances must be EN_ROUTE! Neither should be waiting!
    assert amb1.status == AmbulanceStatus.EN_ROUTE
    assert amb2.status == AmbulanceStatus.EN_ROUTE
    assert amb1.assigned_emergency_id == "INC-01"
    assert amb2.assigned_emergency_id == "INC-02"
    assert em1.status == IncidentStatus.EN_ROUTE
    assert em2.status == IncidentStatus.EN_ROUTE
    assert amb1.id in state.active_routes
    assert amb2.id in state.active_routes

def test_provisional_first_responder_fallback(dispatch_setup):
    """Pillars 2 & 6: When only lower-tier unit is available, dispatch as Provisional First-Responder."""
    state, algo, graph = dispatch_setup

    # Only 1 BLS ambulance in the fleet
    amb_bls = Ambulance(
        id="AMB-BLS-ONLY",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_1_1"].world_pos,
        capabilities=["cpr", "oxygen", "basic_first_aid", "splinting"]
    )
    state.fleet[amb_bls.id] = amb_bls

    # Severe emergency requiring defibrillator
    incident = EmergencyIncident(
        id="INC-CARDIAC-99",
        location=graph.nodes["N_1_2"].world_pos,
        nearest_node_id="N_1_2",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["cpr", "cardiac_monitor", "defibrillator"]
    )

    # Must NOT leave patient stranded; should dispatch BLS provisionally for CPR/oxygen
    sel_id, route, dec = algo.evaluate_and_dispatch(incident, state)
    assert sel_id == "AMB-BLS-ONLY"
    assert route is not None
    assert dec.applied is True
    assert "Provisional First-Responder" in dec.eligible_candidates[0].metrics["dispatch_role"]

def test_hospital_recommendation_inbound_alert_and_reservation_proof(dispatch_setup):
    """Pillar 4: Hospital recommendation choosing by capacity, distance, and specialization with alert proof."""
    from src.algorithms.hospital_selection import HospitalSelectionAlgorithm
    from src.models.hospital import Hospital
    state, _algo, graph = dispatch_setup

    hosp_trauma = Hospital(
        id="HOSP-TRAUMA",
        name="General Trauma Hospital",
        node_id="N_2_2",
        location=graph.nodes["N_2_2"].world_pos,
        total_beds=10,
        occupied_beds=5,
        vacant_beds=5,
        capabilities=["basic", "trauma", "respiratory"]
    )
    hosp_cardiac = Hospital(
        id="HOSP-CARDIAC",
        name="Metro Heart Institute",
        node_id="N_2_6",
        location=graph.nodes["N_2_6"].world_pos,
        total_beds=8,
        occupied_beds=4,
        vacant_beds=4,
        capabilities=["basic", "cardiac", "icu", "critical"]
    )
    state.hospitals[hosp_trauma.id] = hosp_trauma
    state.hospitals[hosp_cardiac.id] = hosp_cardiac

    amb = Ambulance(
        id="AMB-01",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_2_4"].world_pos,
        capabilities=["cpr", "oxygen", "defibrillator", "cardiac_monitor"]
    )
    state.fleet[amb.id] = amb

    em_cardiac = EmergencyIncident(
        id="INC-CARDIAC-88",
        location=graph.nodes["N_2_4"].world_pos,
        nearest_node_id="N_2_4",
        severity=EmergencySeverity.HIGH,
        required_capabilities=["cpr", "cardiac_monitor", "defibrillator"],
        title="Acute Cardiac Arrest"
    )

    h_algo = HospitalSelectionAlgorithm()
    hosp_id, route, dec = h_algo.select_destination(amb, em_cardiac, state)

    # Cardiac hospital selected due to clinical specialization match
    assert hosp_id == "HOSP-CARDIAC"
    assert route is not None
    assert dec.applied is True

    # Verify reservation is proven and inbound alert recorded
    target_hosp = state.hospitals["HOSP-CARDIAC"]
    assert "INC-CARDIAC-88" in target_hosp.reserved_patient_ids
    assert target_hosp.effectively_available_beds == 3
    assert dec.eligible_candidates[0].metrics["bed_reserved_proven"] is True
    assert dec.eligible_candidates[0].metrics["inbound_alert_sent"] is True
    assert "Dispatched inbound alert" in dec.reasoning_summary

def test_dynamic_reallocation_coverage_rebalancing(dispatch_setup):
    """Pillars 5 & 6: Reposition idle clustered ambulance to strategic post to maximize coverage."""
    from src.algorithms.dynamic_reallocation import (
        DynamicReallocationAlgorithm,
        StandbyStation,
    )
    from src.models.decision_record import DecisionType
    state, _algo, graph = dispatch_setup

    # Station 2 ambulances right next to each other at N_1_1
    amb1 = Ambulance(
        id="AMB-IDLE-01",
        unit_class=AmbulanceClass.BLS,
        position=graph.nodes["N_1_1"].world_pos,
        status=AmbulanceStatus.AVAILABLE
    )
    amb2 = Ambulance(
        id="AMB-IDLE-02",
        unit_class=AmbulanceClass.ALS,
        position=graph.nodes["N_1_1"].world_pos,
        status=AmbulanceStatus.AVAILABLE
    )
    state.fleet[amb1.id] = amb1
    state.fleet[amb2.id] = amb2

    stations = [
        StandbyStation("ST-WEST", "West Post", "N_1_1", "West"),
        StandbyStation("ST-SOUTH", "South Post", "N_6_2", "South", weight=1.5),
    ]
    realloc_algo = DynamicReallocationAlgorithm(stations)

    plan = realloc_algo.evaluate_reallocation(state)
    assert plan is not None
    assert plan.station_id == "ST-SOUTH"
    assert plan.decision_record.decision_type == DecisionType.REALLOCATION

    # Apply reallocation plan
    ok = realloc_algo.apply_reallocation(plan, state)
    assert ok is True
    reallocated_amb = state.fleet[plan.ambulance_id]
    assert reallocated_amb.status == AmbulanceStatus.EN_ROUTE
    assert reallocated_amb.assigned_emergency_id is None
    assert reallocated_amb.id in state.active_routes

