"""Structured explainable AI decision record for algorithmic transparency."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionType(str, Enum):
    DISPATCH = "DISPATCH"
    HOSPITAL_SELECTION = "HOSPITAL_SELECTION"
    ROUTE_SELECTION = "ROUTE_SELECTION"
    TRAFFIC_RECOVERY = "TRAFFIC_RECOVERY"
    REALLOCATION = "REALLOCATION"

@dataclass
class CandidateEvaluation:
    candidate_id: str
    name: str
    is_eligible: bool
    rejection_reason: str | None = None
    score: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    score_components: dict[str, float] = field(default_factory=dict)

@dataclass
class DecisionRecord:
    id: str
    decision_type: DecisionType
    timestamp: float
    target_entity_id: str
    state_version: int
    selected_id: str | None
    selected_name: str
    eligible_candidates: list[CandidateEvaluation] = field(default_factory=list)
    rejected_candidates: list[CandidateEvaluation] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    metrics_used: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    applied: bool = True
