from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ManagedClusterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="kubernetes", max_length=50)
    api_server: str | None = Field(default=None, max_length=300)
    description: str | None = None


class ManagedClusterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=50)
    api_server: str | None = Field(default=None, max_length=300)
    description: str | None = None


class ManagedClusterRead(BaseModel):
    id: int
    user_id: int
    name: str
    provider: str
    api_server: str | None
    description: str | None
    agent_token: str
    status: str
    agent_version: str | None
    node_count: int
    pod_count: int
    metrics_count: int
    logs_count: int
    alerts_count: int
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManagedClusterInstallRead(BaseModel):
    cluster_id: int
    agent_token: str
    platform_api_url: str
    install_command: str
    manifest: str


class ClusterHeartbeatIn(BaseModel):
    status: str = "online"
    agent_version: str | None = None
    node_count: int = 0
    pod_count: int = 0
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClusterReportIn(BaseModel):
    report_type: str = Field(pattern="^(metric|log|alert)$")
    source: str | None = None
    level: str | None = None
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClusterAgentReportRead(BaseModel):
    id: int
    cluster_id: int
    report_type: str
    source: str | None
    level: str | None
    message: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ClusterAgentHeartbeatRead(BaseModel):
    id: int
    cluster_id: int
    status: str
    agent_version: str | None
    node_count: int
    pod_count: int
    message: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ClusterAgentAck(BaseModel):
    ok: bool
    message: str
