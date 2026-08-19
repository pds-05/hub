from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AIDiagnosisCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    target_id: int = Field(gt=0)
    event_id: int | None = Field(default=None, gt=0)


class AIToolCallAuditRead(BaseModel):
    tool_name: str
    parameter_summary: dict[str, Any]
    status: str
    duration_ms: int
    result_summary: str | None
    created_at: datetime | None


class AIDiagnosisRead(BaseModel):
    id: int
    target_id: int
    event_id: int | None
    status: str
    question: str
    provider: str | None
    dify_conversation_id: str | None
    report_summary: str | None
    report_json: dict[str, Any] | None
    error_message: str | None
    tool_calls_used: int
    expires_at: datetime
    created_at: datetime | None
    updated_at: datetime | None
    tool_calls: list[AIToolCallAuditRead] = Field(default_factory=list)