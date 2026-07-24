from datetime import datetime

from pydantic import BaseModel, Field


class AlertEventRead(BaseModel):
    id: int
    user_id: int
    rule_id: int
    rule_name: str
    scope: str
    instance: str
    level: str
    metric: str
    operator: str
    value: float
    threshold: float
    status: str
    handling_status: str
    message: str
    trigger_count: int
    acknowledged: bool
    acknowledged_at: datetime | None
    first_triggered_at: datetime
    last_triggered_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertEventEvaluateResponse(BaseModel):
    active_count: int
    triggered_count: int
    resolved_count: int
    events: list[AlertEventRead]

class AlertEventSummary(BaseModel):
    total_count: int
    active_count: int
    resolved_count: int
    unacknowledged_active_count: int
    handling_by_status: dict[str, int]
    active_by_level: dict[str, int]
    total_by_level: dict[str, int]
    recent_events: list[AlertEventRead]
class AlertEventAnalysis(BaseModel):
    event: AlertEventRead
    summary: str
    severity: str
    possible_causes: list[str]
    impact: list[str]
    recommended_actions: list[str]
    promql_hints: list[str]

class AlertEventListQuery(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|resolved)$")
    level: str | None = Field(default=None, pattern="^(general|severe|urgent)$")
class AlertEventHandlingStatusRequest(BaseModel):
    handling_status: str = Field(pattern="^(new|acknowledged|investigating|mitigating|watching|resolved|closed)$")
    note: str | None = Field(default=None, max_length=1000)



