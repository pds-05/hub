from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.ai_diagnosis import AIDiagnosis
from app.models.ai_diagnosis_evaluation import AIDiagnosisEvaluationCase, AIDiagnosisEvaluationResult, AIDiagnosisFeedback
from app.models.ai_tool_call_audit import AIToolCallAudit
from app.models.alert_event import AlertEvent
from app.models.monitor_target import MonitorTarget
from app.models.user import User
from app.schemas.ai_diagnosis import AIDiagnosisCreate, AIDiagnosisRead, AIToolCallAuditRead
from app.schemas.ai_diagnosis_evaluation import (
    AIDiagnosisEvaluationCaseCreate,
    AIDiagnosisEvaluationCaseRead,
    AIDiagnosisEvaluationResultRead,
    AIDiagnosisEvaluationRunRequest,
    AIDiagnosisFeedbackRead,
    AIDiagnosisFeedbackUpsert,
)
from app.services.ai_assistant import AIAssistantService, get_ai_assistant_service
from app.services.diagnosis_tool_service import DiagnosisToolService, _event_belongs_to_target
from app.services.diagnosis_evaluation import score_diagnosis_evaluation
from app.services.dify_diagnosis_client import (
    DifyDiagnosisClient,
    DifyDiagnosisError,
    DifyDiagnosisNotConfiguredError,
    get_dify_diagnosis_client,
)

router = APIRouter(prefix="/assistant", tags=["ai assistant"])


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: dict = Field(default_factory=dict)


@router.post("/analyze")
async def analyze_incident(
    payload: AnalyzeRequest,
    service: AIAssistantService = Depends(get_ai_assistant_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = current_user
    return await service.analyze_incident(payload.question, payload.context)


def diagnosis_service(db: Session = Depends(get_db)) -> DiagnosisToolService:
    settings = get_settings()
    return DiagnosisToolService(
        db,
        token_ttl_minutes=settings.ai_diagnosis_token_ttl_minutes,
        max_tool_calls=settings.ai_diagnosis_max_tool_calls,
        tool_timeout_seconds=settings.ai_diagnosis_tool_timeout_seconds,
    )


def diagnosis_read(db: Session, diagnosis: AIDiagnosis) -> AIDiagnosisRead:
    audits = (
        db.query(AIToolCallAudit)
        .filter(AIToolCallAudit.diagnosis_id == diagnosis.id)
        .order_by(AIToolCallAudit.created_at.asc(), AIToolCallAudit.id.asc())
        .all()
    )
    return AIDiagnosisRead(
        id=diagnosis.id,
        target_id=diagnosis.target_id,
        event_id=diagnosis.event_id,
        status=diagnosis.status,
        question=diagnosis.question,
        provider=diagnosis.provider,
        dify_conversation_id=diagnosis.dify_conversation_id,
        report_summary=diagnosis.report_summary,
        report_json=diagnosis.report_json,
        error_message=diagnosis.error_message,
        tool_calls_used=diagnosis.tool_calls_used,
        expires_at=diagnosis.expires_at,
        created_at=diagnosis.created_at,
        updated_at=diagnosis.updated_at,
        tool_calls=[
            AIToolCallAuditRead(
                tool_name=audit.tool_name,
                parameter_summary=audit.parameter_summary,
                status=audit.status,
                duration_ms=audit.duration_ms,
                result_summary=audit.result_summary,
                created_at=audit.created_at,
            )
            for audit in audits
        ],
    )


@router.post("/diagnoses", response_model=AIDiagnosisRead, status_code=status.HTTP_201_CREATED)
async def create_diagnosis(
    payload: AIDiagnosisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: DiagnosisToolService = Depends(diagnosis_service),
    dify: DifyDiagnosisClient = Depends(get_dify_diagnosis_client),
) -> AIDiagnosisRead:
    diagnosis, diagnosis_token = service.create_diagnosis(
        current_user,
        target_id=payload.target_id,
        question=payload.question,
        event_id=payload.event_id,
    )
    diagnosis.status = "running"
    diagnosis.provider = "dify-agent"
    db.commit()

    try:
        result = await dify.diagnose(
            question=payload.question,
            diagnosis_token=diagnosis_token,
            diagnosis_id=diagnosis.id,
        )
    except DifyDiagnosisNotConfiguredError as exc:
        diagnosis.status = "failed"
        diagnosis.error_message = "Dify diagnosis integration is not configured"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=diagnosis.error_message) from exc
    except DifyDiagnosisError as exc:
        diagnosis.status = "failed"
        diagnosis.error_message = "Dify diagnosis request failed"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=diagnosis.error_message) from exc

    diagnosis.status = "completed"
    diagnosis.dify_conversation_id = result.conversation_id
    diagnosis.report_summary = result.answer
    diagnosis.report_json = {"message_id": result.message_id, "metadata": result.metadata}
    diagnosis.error_message = None
    db.commit()
    db.refresh(diagnosis)
    return diagnosis_read(db, diagnosis)


@router.get("/diagnoses/{diagnosis_id}", response_model=AIDiagnosisRead)
def get_diagnosis(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIDiagnosisRead:
    diagnosis = (
        db.query(AIDiagnosis)
        .filter(AIDiagnosis.id == diagnosis_id, AIDiagnosis.user_id == current_user.id)
        .first()
    )
    if diagnosis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
    return diagnosis_read(db, diagnosis)

def _owned_diagnosis(db: Session, user_id: int, diagnosis_id: int) -> AIDiagnosis:
    diagnosis = db.query(AIDiagnosis).filter(AIDiagnosis.id == diagnosis_id, AIDiagnosis.user_id == user_id).first()
    if diagnosis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
    return diagnosis


def _owned_target(db: Session, user_id: int, target_id: int) -> MonitorTarget:
    target = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.id == target_id, MonitorTarget.user_id == user_id, MonitorTarget.deleted_at.is_(None))
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target


@router.post("/evaluation-cases", response_model=AIDiagnosisEvaluationCaseRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_case(
    payload: AIDiagnosisEvaluationCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIDiagnosisEvaluationCase:
    target = _owned_target(db, current_user.id, payload.target_id)
    if payload.event_id is not None:
        event = (
            db.query(AlertEvent)
            .filter(AlertEvent.id == payload.event_id, AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None))
            .first()
        )
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert event not found")
        if not _event_belongs_to_target(event, target):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The alert event is not associated with this target")
    case = AIDiagnosisEvaluationCase(user_id=current_user.id, **payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("/evaluation-cases", response_model=list[AIDiagnosisEvaluationCaseRead])
def list_evaluation_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AIDiagnosisEvaluationCase]:
    return list(
        db.query(AIDiagnosisEvaluationCase)
        .filter(AIDiagnosisEvaluationCase.user_id == current_user.id)
        .order_by(AIDiagnosisEvaluationCase.updated_at.desc(), AIDiagnosisEvaluationCase.id.desc())
        .all()
    )


@router.post("/evaluation-cases/{case_id}/evaluate", response_model=AIDiagnosisEvaluationResultRead)
def evaluate_diagnosis_case(
    case_id: int,
    payload: AIDiagnosisEvaluationRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIDiagnosisEvaluationResult:
    case = (
        db.query(AIDiagnosisEvaluationCase)
        .filter(AIDiagnosisEvaluationCase.id == case_id, AIDiagnosisEvaluationCase.user_id == current_user.id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation case not found")
    diagnosis = _owned_diagnosis(db, current_user.id, payload.diagnosis_id)
    if diagnosis.target_id != case.target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diagnosis target does not match the evaluation case")
    audits = db.query(AIToolCallAudit).filter(AIToolCallAudit.diagnosis_id == diagnosis.id).all()
    score = score_diagnosis_evaluation(
        expected_tool_names=case.expected_tool_names or [],
        expected_evidence_terms=case.expected_evidence_terms or [],
        audit_rows=audits,
        report=diagnosis.report_summary,
    )
    result = (
        db.query(AIDiagnosisEvaluationResult)
        .filter(AIDiagnosisEvaluationResult.case_id == case.id, AIDiagnosisEvaluationResult.diagnosis_id == diagnosis.id)
        .first()
    )
    if result is None:
        result = AIDiagnosisEvaluationResult(case_id=case.id, diagnosis_id=diagnosis.id, user_id=current_user.id)
        db.add(result)
    for field, value in score.items():
        setattr(result, field, value)
    db.commit()
    db.refresh(result)
    return result


@router.get("/diagnoses/{diagnosis_id}/evaluations", response_model=list[AIDiagnosisEvaluationResultRead])
def list_diagnosis_evaluations(
    diagnosis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AIDiagnosisEvaluationResult]:
    _owned_diagnosis(db, current_user.id, diagnosis_id)
    return list(
        db.query(AIDiagnosisEvaluationResult)
        .filter(AIDiagnosisEvaluationResult.diagnosis_id == diagnosis_id, AIDiagnosisEvaluationResult.user_id == current_user.id)
        .order_by(AIDiagnosisEvaluationResult.created_at.desc(), AIDiagnosisEvaluationResult.id.desc())
        .all()
    )


@router.put("/diagnoses/{diagnosis_id}/feedback", response_model=AIDiagnosisFeedbackRead)
def upsert_diagnosis_feedback(
    diagnosis_id: int,
    payload: AIDiagnosisFeedbackUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIDiagnosisFeedback:
    _owned_diagnosis(db, current_user.id, diagnosis_id)
    feedback = (
        db.query(AIDiagnosisFeedback)
        .filter(AIDiagnosisFeedback.diagnosis_id == diagnosis_id, AIDiagnosisFeedback.user_id == current_user.id)
        .first()
    )
    if feedback is None:
        feedback = AIDiagnosisFeedback(diagnosis_id=diagnosis_id, user_id=current_user.id, **payload.model_dump())
        db.add(feedback)
    else:
        feedback.verdict = payload.verdict
        feedback.note = payload.note
    db.commit()
    db.refresh(feedback)
    return feedback
