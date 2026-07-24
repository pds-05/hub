from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ManagedCluster(Base):
    __tablename__ = "managed_clusters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="kubernetes")
    api_server: Mapped[str] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    agent_token: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="pending")
    agent_version: Mapped[str] = mapped_column(String(50), nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pod_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    logs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
