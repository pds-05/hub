from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AIDiagnosisEvaluationCase(Base):
    __tablename__ = "ai_diagnosis_evaluation_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    target_id: Mapped[int] = mapped_column(ForeignKey("monitor_targets.id"), index=True, nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_evidence_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIDiagnosisEvaluationResult(Base):
    __tablename__ = "ai_diagnosis_evaluation_results"
    __table_args__ = (UniqueConstraint("case_id", "diagnosis_id", name="uq_ai_diagnosis_evaluation_result"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("ai_diagnosis_evaluation_cases.id"), index=True, nullable=False)
    diagnosis_id: Mapped[int] = mapped_column(ForeignKey("ai_diagnoses.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    expected_tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_evidence_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    successful_tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cited_tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unsupported_cited_tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matched_evidence_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unsupported_evidence_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tool_call_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    evidence_citation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    evidence_term_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIDiagnosisFeedback(Base):
    __tablename__ = "ai_diagnosis_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    diagnosis_id: Mapped[int] = mapped_column(ForeignKey("ai_diagnoses.id"), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())