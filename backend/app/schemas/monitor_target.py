from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

EXPORTER_KIND_PATTERN = "^(node|mysql|nginx|redis|postgresql|mongodb|kafka|rabbitmq|elasticsearch|clickhouse|zookeeper|etcd|blackbox|cadvisor|windows|process|jmx|custom)$"


class MonitorTargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_type: str = Field(pattern="^(website|port|exporter)$")
    endpoint: str = Field(min_length=1, max_length=500)
    expected_keyword: str | None = Field(default=None, max_length=200)
    exporter_kind: str | None = Field(default=None, pattern=EXPORTER_KIND_PATTERN)
    description: str | None = None


class MonitorTargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_type: str | None = Field(default=None, pattern="^(website|port|exporter)$")
    endpoint: str | None = Field(default=None, min_length=1, max_length=500)
    expected_keyword: str | None = Field(default=None, max_length=200)
    exporter_kind: str | None = Field(default=None, pattern=EXPORTER_KIND_PATTERN)
    description: str | None = None


class MonitorTargetCheckRead(BaseModel):
    check_id: int
    target_id: int
    status: str
    response_time_ms: int
    message: str
    status_code: int | None = None
    details: dict[str, Any] | None = None
    checked_at: datetime

    model_config = {"from_attributes": True}


class MonitorTargetSummaryRead(BaseModel):
    total: int
    up: int
    down: int
    unknown: int
    avg_response_time_ms: int | None = None


class MonitorTargetRead(BaseModel):
    id: int
    user_id: int
    name: str
    target_type: str
    endpoint: str
    expected_keyword: str | None
    exporter_kind: str | None
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
