from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.dify_tool_openapi import dify_tool_openapi
from app.services.diagnosis_tool_service import (
    DiagnosisTokenError,
    DiagnosisToolLimitError,
    DiagnosisToolError,
    DiagnosisToolService,
)

router = APIRouter(prefix="/assistant/tools", tags=["ai diagnosis tools"])


class TokenToolRequest(BaseModel):
    diagnosis_token: str = Field(min_length=20, max_length=500)


class MetricsToolRequest(TokenToolRequest):
    metric_type: Literal[
        "availability",
        "response_time",
        "cpu",
        "memory",
        "disk",
        "connections",
        "queue_messages",
        "consumers",
        "error_rate",
    ]
    minutes: int = Field(default=30, ge=1, le=60)


class LogsToolRequest(TokenToolRequest):
    keyword: str = Field(default="", max_length=200)
    minutes: int = Field(default=30, ge=1, le=60)
    limit: int = Field(default=50, ge=1, le=100)


class ContextToolRequest(TokenToolRequest):
    minutes: int = Field(default=60, ge=5, le=240)
    limit: int = Field(default=50, ge=1, le=100)

def verify_dify_tool_secret(x_dify_tool_secret: str | None = Header(default=None)) -> None:
    expected = os.getenv("DIFY_TOOL_SECRET", "") or get_settings().dify_tool_secret
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dify tool integration is not configured")
    if not x_dify_tool_secret or not secrets_compare(x_dify_tool_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Dify tool secret")


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def tool_service(db: Session = Depends(get_db)) -> DiagnosisToolService:
    settings = get_settings()
    max_calls = _safe_int(str(settings.ai_diagnosis_max_tool_calls), default=8, lower=1, upper=8)
    ttl_minutes = _safe_int(str(settings.ai_diagnosis_token_ttl_minutes), default=10, lower=1, upper=10)
    timeout_seconds = _safe_int(str(settings.ai_diagnosis_tool_timeout_seconds), default=10, lower=1, upper=10)
    return DiagnosisToolService(db, token_ttl_minutes=ttl_minutes, max_tool_calls=max_calls, tool_timeout_seconds=timeout_seconds)


def _safe_int(value: str | None, *, default: int, lower: int, upper: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return max(lower, min(parsed, upper))


@router.get("/openapi.json", include_in_schema=False)
def get_tool_openapi(request: Request) -> dict:
    public_base_url = get_settings().dify_tool_public_base_url.rstrip("/")
    if not public_base_url:
        public_base_url = f"{str(request.base_url).rstrip('/')}/api/v1/assistant/tools"
    return dify_tool_openapi(public_base_url)

def translate_tool_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DiagnosisTokenError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, DiagnosisToolLimitError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if isinstance(exc, DiagnosisToolError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Diagnosis tool request failed")


@router.post("/alert-context", dependencies=[Depends(verify_dify_tool_secret)])
def get_alert_context(payload: TokenToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.alert_context(payload.diagnosis_token)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/target-status", dependencies=[Depends(verify_dify_tool_secret)])
def get_target_status(payload: TokenToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.target_status(payload.diagnosis_token)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/target-metrics", dependencies=[Depends(verify_dify_tool_secret)])
async def get_target_metrics(payload: MetricsToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return await service.target_metrics(payload.diagnosis_token, payload.metric_type, payload.minutes)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/target-logs", dependencies=[Depends(verify_dify_tool_secret)])
async def search_target_logs(payload: LogsToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return await service.target_logs(payload.diagnosis_token, payload.keyword, payload.minutes, payload.limit)
    except Exception as exc:
        raise translate_tool_error(exc) from exc

@router.post("/related-alerts", dependencies=[Depends(verify_dify_tool_secret)])
def get_related_alerts(payload: ContextToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.related_alerts(payload.diagnosis_token, payload.minutes, payload.limit)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/kubernetes-events", dependencies=[Depends(verify_dify_tool_secret)])
def get_kubernetes_events(payload: ContextToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.kubernetes_events(payload.diagnosis_token, payload.minutes, payload.limit)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/service-dependencies", dependencies=[Depends(verify_dify_tool_secret)])
def get_service_dependencies(payload: TokenToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.service_dependencies(payload.diagnosis_token)
    except Exception as exc:
        raise translate_tool_error(exc) from exc


@router.post("/incident-timeline", dependencies=[Depends(verify_dify_tool_secret)])
def get_incident_timeline(payload: ContextToolRequest, service: DiagnosisToolService = Depends(tool_service)) -> dict:
    try:
        return service.incident_timeline(payload.diagnosis_token, payload.minutes, payload.limit)
    except Exception as exc:
        raise translate_tool_error(exc) from exc
