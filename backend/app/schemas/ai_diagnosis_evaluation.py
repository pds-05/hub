from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ToolName = Literal[
    "get_alert_context",
    "get_target_status",
    "get_target_metrics",
    "search_target_logs",
    "get_related_alerts",
    "get_kubernetes_events",
    "get_service_dependencies",
    "get_incident_timeline",
]
FeedbackVerdict = Literal["accepted", "partially_accepted", "rejected", "insufficient_evidence"]


class AIDiagnosisEvaluationCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    target_id: int = Field(gt=0)
    event_id: int | None = Field(default=None, gt=0)
    question: str = Field(min_length=1, max_length=2000)
    expected_tool_names: list[ToolName] = Field(default_factory=list, max_length=8)
    expected_evidence_terms: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = True


class AIDiagnosisEvaluationCaseRead(AIDiagnosisEvaluationCaseCreate):
    id: int
    user_id: int
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class AIDiagnosisEvaluationRunRequest(BaseModel):
    diagnosis_id: int = Field(gt=0)


class AIDiagnosisEvaluationResultRead(BaseModel):
    id: int
    case_id: int
    diagnosis_id: int
    expected_tool_names: list[str]
    expected_evidence_terms: list[str]
    successful_tool_names: list[str]
    cited_tool_names: list[str]
    unsupported_cited_tool_names: list[str]
    matched_evidence_terms: list[str]
    unsupported_evidence_terms: list[str]
    tool_call_score: float
    evidence_citation_score: float
    evidence_term_score: float
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class AIDiagnosisFeedbackUpsert(BaseModel):
    verdict: FeedbackVerdict
    note: str | None = Field(default=None, max_length=2000)


class AIDiagnosisFeedbackRead(BaseModel):
    id: int
    diagnosis_id: int
    verdict: FeedbackVerdict
    note: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}