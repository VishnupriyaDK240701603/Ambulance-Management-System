"""Tests for Explainable AI decision records and audit integrity."""
from src.models.decision_record import (
    CandidateEvaluation,
    DecisionRecord,
    DecisionType,
)


def test_decision_record_structure_and_transparency():
    candidate_1 = CandidateEvaluation(
        candidate_id="AMB-ALS-01",
        name="ALS [AMB-ALS-01]",
        is_eligible=True,
        score=24.5,
        metrics={"eta_seconds": 18.2, "distance_meters": 320.0},
        score_components={"time_cost": 10.01, "dist_cost": 8.0, "workload_penalty": 0.0}
    )
    candidate_2 = CandidateEvaluation(
        candidate_id="AMB-BLS-01",
        name="BLS [AMB-BLS-01]",
        is_eligible=False,
        rejection_reason="Missing required capabilities: defibrillator"
    )

    rec = DecisionRecord(
        id="DEC-TEST-001",
        decision_type=DecisionType.DISPATCH,
        timestamp=12.4,
        target_entity_id="INC-001",
        state_version=5,
        selected_id="AMB-ALS-01",
        selected_name="ALS [AMB-ALS-01]",
        eligible_candidates=[candidate_1],
        rejected_candidates=[candidate_2],
        metrics_used=["eta_sec", "distance_meters", "capabilities"],
        reasoning_summary="Selected ALS unit due to lowest response time and valid medical capability."
    )

    assert rec.decision_type == DecisionType.DISPATCH
    assert len(rec.eligible_candidates) == 1
    assert len(rec.rejected_candidates) == 1
    assert rec.rejected_candidates[0].rejection_reason == "Missing required capabilities: defibrillator"
    assert rec.eligible_candidates[0].score == 24.5
