from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AIToolCallAudit(Base):
    __tablename__ = "ai_tool_call_audits"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    diagnosis_id: Mapped[int] = mapped_column(ForeignKey("ai_diagnoses.id"), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    parameter_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
