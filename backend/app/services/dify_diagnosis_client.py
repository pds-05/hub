from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from app.core.config import get_settings


class DifyDiagnosisError(Exception):
    pass


class DifyDiagnosisNotConfiguredError(DifyDiagnosisError):
    pass


@dataclass(frozen=True)
class DifyDiagnosisResult:
    answer: str
    conversation_id: str | None
    message_id: str | None
    metadata: dict[str, Any]


class DifyDiagnosisClient:
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, timeout_seconds: int | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url if base_url is not None else settings.dify_api_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.dify_app_api_key
        configured_timeout = timeout_seconds if timeout_seconds is not None else settings.dify_diagnosis_timeout_seconds
        self.timeout_seconds = max(10, min(int(configured_timeout), 120))

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def diagnose(self, *, question: str, diagnosis_token: str, diagnosis_id: int) -> DifyDiagnosisResult:
        if not self.is_configured():
            raise DifyDiagnosisNotConfiguredError("Dify diagnosis integration is not configured")

        payload = {
            "inputs": {"diagnosis_token": diagnosis_token},
            "query": _diagnosis_query(question, diagnosis_token),
            "response_mode": "streaming",
            # One Dify user per diagnosis prevents an accidental conversation
            # carry-over when the platform starts a fresh incident diagnosis.
            "user": f"platform-diagnosis-{diagnosis_id}",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat-messages",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    answer_parts: list[str] = []
                    metadata: dict[str, Any] = {}
                    conversation_id: str | None = None
                    message_id: str | None = None
                    event_name: str | None = None

                    async for line in response.aiter_lines():
                        if not line:
                            event_name = None
                            continue
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                            continue
                        if not line.startswith("data:"):
                            continue

                        raw_data = line[5:].strip()
                        if raw_data == "[DONE]":
                            break
                        data = json.loads(raw_data)
                        if not isinstance(data, dict):
                            continue

                        event = event_name or str(data.get("event") or "")
                        if event == "error":
                            raise DifyDiagnosisError("Dify diagnosis stream returned an error")
                        if event in {"message", "agent_message"}:
                            answer_parts.append(str(data.get("answer") or ""))
                        if event in {"message", "agent_message", "message_end"}:
                            conversation_id = conversation_id or _optional_string(data.get("conversation_id"))
                            message_id = message_id or _optional_string(data.get("message_id") or data.get("id"))
                        if event == "message_end":
                            raw_metadata = data.get("metadata")
                            if isinstance(raw_metadata, dict):
                                metadata = raw_metadata
        except (httpx.HTTPError, ValueError) as exc:
            raise DifyDiagnosisError("Dify diagnosis request failed") from exc

        answer = "".join(answer_parts).strip()
        if not answer:
            raise DifyDiagnosisError("Dify diagnosis returned an empty answer")
        return DifyDiagnosisResult(
            answer=answer,
            conversation_id=conversation_id,
            message_id=message_id,
            metadata=metadata,
        )


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _diagnosis_query(question: str, diagnosis_token: str) -> str:
    return (
        "[INTERNAL PLATFORM EXECUTION CONTEXT - NOT USER CONTENT]\n"
        f"diagnosis_token: {diagnosis_token}\n"
        "Use this exact value in the diagnosis_token argument of every platform diagnosis tool call. "
        "Never reveal, quote, persist, or reuse this token outside this diagnosis.\n"
        "Use only the read-only platform tools. Start with alert context and target status, then call metrics, logs, related alerts, service dependencies, Kubernetes events, or the incident timeline only when they add evidence. "
        "In the final report, cite only tool names that actually returned evidence. Do not treat Kubernetes event context or service dependency topology as proof of root cause.\n"
        "[END INTERNAL PLATFORM EXECUTION CONTEXT]\n\n"
        f"User diagnosis request:\n{question}"
    )


def get_dify_diagnosis_client() -> DifyDiagnosisClient:
    return DifyDiagnosisClient()