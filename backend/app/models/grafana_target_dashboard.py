from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GrafanaTargetDashboard(Base):
    __tablename__ = "grafana_target_dashboards"
    __table_args__ = (UniqueConstraint("target_id", name="uq_grafana_target_dashboard_target"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    target_id: Mapped[int] = mapped_column(ForeignKey("monitor_targets.id"), index=True, nullable=False)
    dashboard_uid: Mapped[str] = mapped_column(String(120), nullable=False)
    public_url: Mapped[str] = mapped_column(String(500), nullable=False)
    access_token: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
