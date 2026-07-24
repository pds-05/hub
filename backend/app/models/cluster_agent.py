from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ClusterAgentHeartbeat(Base):
    __tablename__ = "cluster_agent_heartbeats"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("managed_clusters.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="online")
    agent_version: Mapped[str] = mapped_column(String(50), nullable=True)
    node_count: Mapped[int] = mapped_column(nullable=False, default=0)
    pod_count: Mapped[int] = mapped_column(nullable=False, default=0)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ClusterAgentReport(Base):
    __tablename__ = "cluster_agent_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("managed_clusters.id"), index=True, nullable=False)
    report_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=True)
    level: Mapped[str] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
