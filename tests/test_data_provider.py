"""Tests for ExternalDataProvider feed ingestion and validation."""
import pytest

from src.integrations.data_provider import ExternalDataProvider
from src.models.emergency import EmergencySeverity
from src.models.hospital import Hospital
from src.simulation.simulation_engine import SimulationEngine
from src.simulation.simulation_state import SimulationState
from src.world.city_generator import CityGenerator


@pytest.fixture
def provider_setup():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()
    state = SimulationState(road_graph=graph, is_started=True)
    engine = SimulationEngine(state)

    hosp = Hospital(
        id="HOSP-FEED-01",
        name="Telemetry Regional Hospital",
        node_id="N_2_2",
        location=graph.nodes["N_2_2"].world_pos,
        total_beds=10,
        occupied_beds=5,
        vacant_beds=5,
        capabilities=["trauma", "icu"]
    )
    state.hospitals[hosp.id] = hosp

    provider = ExternalDataProvider(engine)
    return state, engine, graph, provider

def test_ingest_emergency_report_success(provider_setup):
    state, _engine, graph, provider = provider_setup
    payload = {
        "incident_id": "FEED-EM-001",
        "severity": "high",  # Tests lowercase tolerance
        "location": graph.nodes["N_1_1"].world_pos,
        "capabilities": ["cpr", "defibrillator"],
        "title": "Severe Trauma Ingested",
        "description": "Feed telematics incident"
    }
    ok, _msg = provider.ingest_emergency_report(payload)
    assert ok is True
    assert "FEED-EM-001" in state.emergencies
    em = state.emergencies["FEED-EM-001"]
    assert em.severity == EmergencySeverity.HIGH
    assert provider.status.events_received_count == 1

def test_ingest_emergency_report_missing_field(provider_setup):
    state, _engine, _graph, provider = provider_setup
    payload = {
        "incident_id": "FEED-EM-BAD",
        # missing severity
        "location": (0.0, 0.0, 0.0),
        "capabilities": ["cpr"]
    }
    ok, msg = provider.ingest_emergency_report(payload)
    assert ok is False
    assert "Missing required feed field: severity" in msg
    assert "FEED-EM-BAD" not in state.emergencies

def test_ingest_emergency_report_invalid_severity(provider_setup):
    _state, _engine, _graph, provider = provider_setup
    payload = {
        "incident_id": "FEED-EM-INVALID",
        "severity": "SUPER_EXTREME",
        "location": (0.0, 0.0, 0.0),
        "capabilities": ["cpr"]
    }
    ok, msg = provider.ingest_emergency_report(payload)
    assert ok is False
    assert "Invalid emergency severity" in msg

def test_ingest_traffic_hazard_success_and_invalid(provider_setup):
    state, _engine, graph, provider = provider_setup
    # Valid roadblock
    payload = {
        "incident_id": "FEED-HAZ-001",
        "incident_type": "roadblock",
        "edge_id": "E_N_2_2_N_3_2",
        "position": graph.nodes["N_2_2"].world_pos,
        "description": "Bridge maintenance closure"
    }
    ok, _msg = provider.ingest_traffic_hazard(payload)
    assert ok is True
    assert "FEED-HAZ-001" in state.road_incidents
    assert graph.edges["E_N_2_2_N_3_2"].is_closed is True

    # Invalid incident type
    bad_payload = {
        "incident_id": "FEED-HAZ-BAD",
        "incident_type": "METEOR_STRIKE",
        "edge_id": "E_N_2_2_N_3_2",
        "position": (0, 0, 0)
    }
    ok_bad, msg_bad = provider.ingest_traffic_hazard(bad_payload)
    assert ok_bad is False
    assert "Invalid incident type" in msg_bad

def test_ingest_hospital_capacity(provider_setup):
    state, _engine, _graph, provider = provider_setup
    payload = {
        "hospital_id": "HOSP-FEED-01",
        "occupied_beds": "7",  # Tests string integer tolerance
        "vacant_beds": "3"
    }
    ok, _msg = provider.ingest_hospital_capacity(payload)
    assert ok is True
    hosp = state.hospitals["HOSP-FEED-01"]
    assert hosp.occupied_beds == 7
    assert hosp.vacant_beds == 3

    # Invalid bed count string
    bad_payload = {
        "hospital_id": "HOSP-FEED-01",
        "occupied_beds": "not_a_number",
        "vacant_beds": 3
    }
    ok_bad, msg_bad = provider.ingest_hospital_capacity(bad_payload)
    assert ok_bad is False
    assert "must be valid integers" in msg_bad
