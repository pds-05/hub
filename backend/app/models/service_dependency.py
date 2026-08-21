from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"
    __table_args__ = (UniqueConstraint("user_id", "source_target_id", "destination_target_id", name="uq_service_dependency"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    source_target_id: Mapped[int] = mapped_column(ForeignKey("monitor_targets.id"), index=True, nullable=False)
    destination_target_id: Mapped[int] = mapped_column(ForeignKey("monitor_targets.id"), index=True, nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False, default="runtime")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())