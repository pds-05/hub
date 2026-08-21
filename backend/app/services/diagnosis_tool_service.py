from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_diagnosis import AIDiagnosis
from app.models.ai_tool_call_audit import AIToolCallAudit
from app.models.alert_event import AlertEvent
from app.models.alert_event_activity import AlertEventActivity
from app.models.cluster_agent import ClusterAgentReport
from app.models.managed_cluster import ManagedCluster
from app.models.monitor_target import MonitorTarget
from app.models.service_dependency import ServiceDependency
from app.models.target_check_result import TargetCheckResult
from app.models.user import User
from app.services.logql_scope import scope_logql
from app.services.loki_client import LokiClient
from app.services.prometheus_client import PrometheusClient, PrometheusError


METRIC_TYPES = {
    "availability",
    "response_time",
    "cpu",
    "memory",
    "disk",
    "connections",
    "queue_messages",
    "consumers",
    "error_rate",
}

METRIC_TYPE_KEYS: dict[str, set[str]] = {
    "availability": {"probe_success", "up"},
    "response_time": {"probe_duration_seconds", "response_time_ms"},
    "cpu": {"cpu_usage_percent", "process_cpu_seconds_total"},
    "memory": {"memory_usage_percent", "used_memory_bytes", "process_resident_memory_bytes", "jvm_memory_used_bytes"},
    "disk": {"disk_usage_percent", "logical_disk_free_bytes", "filesystem_data_available_bytes"},
    "connections": {
        "connections", "active_connections", "threads_connected", "active_backends", "connected_clients",
        "connections_current", "tcp_connections", "http_connections",
    },
    "queue_messages": {"queue_messages", "queue_messages_ready", "queue_messages_unacked", "consumergroup_lag"},
    "consumers": {"consumers", "blocked_clients"},
    "error_rate": {"aborted_connects_total", "rejected_connections_total", "deadlocks_total", "asserts_total"},
}


class DiagnosisToolError(Exception):
    pass


class DiagnosisTokenError(DiagnosisToolError):
    pass


class DiagnosisToolLimitError(DiagnosisToolError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _endpoint_variants(endpoint: str) -> set[str]:
    normalized = endpoint.lower().strip().rstrip("/")
    without_scheme = normalized.removeprefix("https://").removeprefix("http://")
    host = without_scheme.split("/", 1)[0]
    return {value for value in {normalized, without_scheme, host} if value}


def _event_belongs_to_target(event: AlertEvent, target: MonitorTarget) -> bool:
    event_instance = event.instance.lower().strip().rstrip("/")
    variants = _endpoint_variants(target.endpoint)
    return any(event_instance == value or event_instance in value or value in event_instance for value in variants)


class DiagnosisToolService:
    def __init__(
        self,
        db: Session,
        *,
        token_ttl_minutes: int = 10,
        max_tool_calls: int = 8,
        prometheus: PrometheusClient | None = None,
        loki: LokiClient | None = None,
        tool_timeout_seconds: int = 10,
    ) -> None:
        self.db = db
        self.token_ttl_minutes = max(1, min(token_ttl_minutes, 10))
        self.max_tool_calls = max(1, min(max_tool_calls, 8))
        self.prometheus = prometheus or PrometheusClient()
        self.loki = loki or LokiClient()
        self.tool_timeout_seconds = max(1, min(tool_timeout_seconds, 10))

    def create_diagnosis(self, current_user: User, target_id: int, question: str, event_id: int | None = None) -> tuple[AIDiagnosis, str]:
        target = self._owned_target(current_user.id, target_id)
        event = self._owned_event(current_user.id, event_id) if event_id is not None else None
        if event is not None and not _event_belongs_to_target(event, target):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The alert event is not associated with this target")

        raw_token = secrets.token_urlsafe(32)
        diagnosis = AIDiagnosis(
            user_id=current_user.id,
            target_id=target.id,
            event_id=event.id if event else None,
            token_hash=_token_hash(raw_token),
            expires_at=_utcnow() + timedelta(minutes=self.token_ttl_minutes),
            question=question,
            status="created",
        )
        self.db.add(diagnosis)
        self.db.commit()
        self.db.refresh(diagnosis)
        return diagnosis, raw_token

    def resolve_token(self, diagnosis_token: str, tool_name: str, parameter_summary: dict[str, Any] | None = None) -> tuple[AIDiagnosis, MonitorTarget]:
        # Lock this diagnosis row until the reservation is committed. Concurrent
        # Dify retries must observe the incremented quota before they can proceed.
        diagnosis = (
            self.db.query(AIDiagnosis)
            .filter(AIDiagnosis.token_hash == _token_hash(diagnosis_token))
            .with_for_update()
            .first()
        )
        if diagnosis is None:
            raise DiagnosisTokenError("Invalid diagnosis token")
        expires_at = diagnosis.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _utcnow():
            raise DiagnosisTokenError("Diagnosis token has expired")
        if diagnosis.tool_calls_used >= self.max_tool_calls:
            raise DiagnosisToolLimitError("Diagnosis tool-call limit reached")

        target = self._owned_target(diagnosis.user_id, diagnosis.target_id)
        diagnosis.tool_calls_used += 1
        self.db.add(
            AIToolCallAudit(
                diagnosis_id=diagnosis.id,
                tool_name=tool_name,
                parameter_summary=parameter_summary or {},
                status="running",
            )
        )
        self.db.commit()
        return diagnosis, target

    def complete_audit(self, diagnosis_id: int, tool_name: str, started_at: float, result: Any = None, error: Exception | None = None) -> None:
        audit = (
            self.db.query(AIToolCallAudit)
            .filter(AIToolCallAudit.diagnosis_id == diagnosis_id, AIToolCallAudit.tool_name == tool_name, AIToolCallAudit.status == "running")
            .order_by(AIToolCallAudit.id.desc())
            .first()
        )
        if audit is None:
            return
        audit.duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        audit.status = "failed" if error else "success"
        audit.result_summary = self._summary(result if error is None else str(error))
        self.db.commit()

    def alert_context(self, diagnosis_token: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        diagnosis, _ = self.resolve_token(diagnosis_token, "get_alert_context")
        try:
            if diagnosis.event_id is None:
                payload = {"event": None, "activities": [], "note": "No alert event is attached to this diagnosis."}
            else:
                event = self._owned_event(diagnosis.user_id, diagnosis.event_id)
                activities = (
                    self.db.query(AlertEventActivity)
                    .filter(AlertEventActivity.event_id == event.id, AlertEventActivity.user_id == diagnosis.user_id)
                    .order_by(AlertEventActivity.created_at.desc(), AlertEventActivity.id.desc())
                    .limit(20)
                    .all()
                )
                payload = {
                    "event": self._event_payload(event),
                    "activities": [
                        {"action": item.action, "note": self._redact_text(item.note), "actor": item.actor, "created_at": item.created_at.isoformat() if item.created_at else None}
                        for item in activities
                    ],
                }
            self.complete_audit(diagnosis.id, "get_alert_context", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_alert_context", started_at, error=exc)
            raise

    def target_status(self, diagnosis_token: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(diagnosis_token, "get_target_status")
        try:
            check = (
                self.db.query(TargetCheckResult)
                .filter(TargetCheckResult.target_id == target.id, TargetCheckResult.user_id == diagnosis.user_id)
                .order_by(TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
                .first()
            )
            payload = {
                "target": {
                    "name": target.name,
                    "target_type": target.target_type,
                    "exporter_kind": target.exporter_kind,
                    "endpoint": self._redact_endpoint(target.endpoint),
                },
                "latest_check": self._check_payload(check),
                "note": "No target check is available yet." if check is None else None,
            }
            self.complete_audit(diagnosis.id, "get_target_status", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_target_status", started_at, error=exc)
            raise

    async def target_metrics(self, diagnosis_token: str, metric_type: str, minutes: int) -> dict[str, Any]:
        if metric_type not in METRIC_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported metric_type")
        safe_minutes = max(5, min(minutes, 60))
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(
            diagnosis_token,
            "get_target_metrics",
            {"metric_type": metric_type, "minutes": safe_minutes},
        )
        try:
            if target.target_type not in {"website", "port", "exporter"}:
                raise DiagnosisToolError("This target type does not provide Prometheus metrics")
            raw = await asyncio.wait_for(self.prometheus.target_metrics(target, minutes=safe_minutes), timeout=self.tool_timeout_seconds)
            allowed = METRIC_TYPE_KEYS[metric_type]
            metrics = [
                {key: metric.get(key) for key in ("key", "label", "unit", "value", "series")}
                for metric in raw.get("metrics", [])
                if metric.get("key") in allowed
            ]
            if metric_type == "availability":
                metrics.insert(0, {"key": "up", "label": "Target availability", "unit": "", "value": raw.get("up"), "series": []})
            payload = {
                "target_id": target.id,
                "target_name": target.name,
                "metric_type": metric_type,
                "minutes": safe_minutes,
                "scrape_status": raw.get("scrape_status"),
                "last_scrape_at": raw.get("last_scrape_at"),
                "scrape_duration_seconds": raw.get("scrape_duration_seconds"),
                "last_error": raw.get("last_error"),
                "metrics": metrics,
                "note": "No matching configured metric was returned for this target." if not metrics else None,
            }
            self.complete_audit(diagnosis.id, "get_target_metrics", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_target_metrics", started_at, error=exc)
            if isinstance(exc, PrometheusError):
                raise DiagnosisToolError(str(exc)) from exc
            raise

    async def target_logs(self, diagnosis_token: str, keyword: str, minutes: int, limit: int) -> dict[str, Any]:
        safe_minutes = max(1, min(minutes, 60))
        safe_limit = max(1, min(limit, 100))
        safe_keyword = keyword.strip()[:200]
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(
            diagnosis_token,
            "search_target_logs",
            {"keyword": safe_keyword, "minutes": safe_minutes, "limit": safe_limit},
        )
        try:
            expression = self._target_logql(diagnosis.user_id, target, safe_keyword)
            try:
                raw = await asyncio.wait_for(self.loki.query_range(expression, limit=safe_limit, minutes=safe_minutes), timeout=self.tool_timeout_seconds)
            except Exception as exc:
                payload = {
                    "entries": [],
                    "note": "Loki is unavailable or no target logs are connected. Do not infer log evidence from this result.",
                    "error": self._redact_text(str(exc)),
                }
                self.complete_audit(diagnosis.id, "search_target_logs", started_at, payload)
                return payload
            entries = self._loki_entries(raw, safe_limit)
            payload = {
                "entries": entries,
                "note": "No Loki logs tagged for this target were found in the selected time range. Do not infer log evidence from this result." if not entries else None,
            }
            self.complete_audit(diagnosis.id, "search_target_logs", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "search_target_logs", started_at, error=exc)
            raise

    def related_alerts(self, diagnosis_token: str, minutes: int, limit: int) -> dict[str, Any]:
        safe_minutes = max(5, min(minutes, 240))
        safe_limit = max(1, min(limit, 100))
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(
            diagnosis_token,
            "get_related_alerts",
            {"minutes": safe_minutes, "limit": safe_limit},
        )
        try:
            payload = {
                "target": self._target_reference(target),
                "minutes": safe_minutes,
                "alerts": self._related_alert_payloads(diagnosis.user_id, target, safe_minutes, safe_limit, exclude_event_id=diagnosis.event_id),
                "note": "Results are deduplicated platform alerts related by the selected target endpoint or a user-configured service dependency.",
            }
            self.complete_audit(diagnosis.id, "get_related_alerts", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_related_alerts", started_at, error=exc)
            raise

    def kubernetes_events(self, diagnosis_token: str, minutes: int, limit: int) -> dict[str, Any]:
        safe_minutes = max(5, min(minutes, 240))
        safe_limit = max(1, min(limit, 100))
        started_at = time.perf_counter()
        diagnosis, _ = self.resolve_token(
            diagnosis_token,
            "get_kubernetes_events",
            {"minutes": safe_minutes, "limit": safe_limit},
        )
        try:
            events = self._kubernetes_warning_payloads(diagnosis.user_id, safe_minutes, safe_limit)
            payload = {
                "minutes": safe_minutes,
                "events": events,
                "note": (
                    "Kubernetes warning events are read-only cluster context from clusters owned by this user. "
                    "There is no target-to-cluster binding yet, so they are not proof that a warning belongs to the diagnosis target."
                ),
            }
            self.complete_audit(diagnosis.id, "get_kubernetes_events", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_kubernetes_events", started_at, error=exc)
            raise

    def service_dependencies(self, diagnosis_token: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(diagnosis_token, "get_service_dependencies")
        try:
            dependencies, targets = self._dependency_context(diagnosis.user_id, target.id)
            payload = {
                "target": self._target_reference(target),
                "dependencies": [self._dependency_payload(item, targets, target.id) for item in dependencies],
                "note": "Dependencies are user-maintained topology metadata. They guide correlation but do not prove causality.",
            }
            self.complete_audit(diagnosis.id, "get_service_dependencies", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_service_dependencies", started_at, error=exc)
            raise

    def incident_timeline(self, diagnosis_token: str, minutes: int, limit: int) -> dict[str, Any]:
        safe_minutes = max(5, min(minutes, 240))
        safe_limit = max(5, min(limit, 100))
        started_at = time.perf_counter()
        diagnosis, target = self.resolve_token(
            diagnosis_token,
            "get_incident_timeline",
            {"minutes": safe_minutes, "limit": safe_limit},
        )
        try:
            timeline: list[dict[str, Any]] = []
            if diagnosis.event_id is not None:
                event = self._owned_event(diagnosis.user_id, diagnosis.event_id)
                timeline.append({
                    "time": self._iso(event.last_triggered_at or event.created_at),
                    "kind": "selected_alert",
                    "summary": event.rule_name,
                    "details": self._event_payload(event),
                })
                activities = (
                    self.db.query(AlertEventActivity)
                    .filter(AlertEventActivity.event_id == event.id, AlertEventActivity.user_id == diagnosis.user_id)
                    .order_by(AlertEventActivity.created_at.asc(), AlertEventActivity.id.asc())
                    .limit(20)
                    .all()
                )
                timeline.extend({
                    "time": self._iso(activity.created_at),
                    "kind": "alert_activity",
                    "summary": activity.action,
                    "details": {"actor": activity.actor, "note": self._redact_text(activity.note)},
                } for activity in activities)

            check = (
                self.db.query(TargetCheckResult)
                .filter(TargetCheckResult.target_id == target.id, TargetCheckResult.user_id == diagnosis.user_id)
                .order_by(TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
                .first()
            )
            if check is not None:
                timeline.append({
                    "time": self._iso(check.checked_at),
                    "kind": "target_check",
                    "summary": f"Target check: {check.status}",
                    "details": self._check_payload(check),
                })

            for event in self._related_alert_payloads(diagnosis.user_id, target, safe_minutes, safe_limit, exclude_event_id=diagnosis.event_id):
                timeline.append({
                    "time": event.get("last_triggered_at"),
                    "kind": "related_alert",
                    "summary": event.get("rule_name"),
                    "details": event,
                })
            for event in self._kubernetes_warning_payloads(diagnosis.user_id, safe_minutes, safe_limit):
                timeline.append({
                    "time": event.get("created_at"),
                    "kind": "kubernetes_warning_context",
                    "summary": event.get("reason") or event.get("message") or "Kubernetes warning",
                    "details": event,
                })

            timeline.sort(key=lambda item: item.get("time") or "")
            payload = {
                "target": self._target_reference(target),
                "minutes": safe_minutes,
                "timeline": timeline[-safe_limit:],
                "note": (
                    "This is an ordered evidence timeline. Kubernetes entries are cluster context only until a target-to-cluster binding is configured. "
                    "A time relationship is not proof of root cause."
                ),
            }
            self.complete_audit(diagnosis.id, "get_incident_timeline", started_at, payload)
            return payload
        except Exception as exc:
            self.complete_audit(diagnosis.id, "get_incident_timeline", started_at, error=exc)
            raise

    def _dependency_context(self, user_id: int, target_id: int) -> tuple[list[ServiceDependency], dict[int, MonitorTarget]]:
        dependencies = (
            self.db.query(ServiceDependency)
            .filter(
                ServiceDependency.user_id == user_id,
                or_(ServiceDependency.source_target_id == target_id, ServiceDependency.destination_target_id == target_id),
            )
            .order_by(ServiceDependency.created_at.desc(), ServiceDependency.id.desc())
            .all()
        )
        target_ids = {target_id}
        for dependency in dependencies:
            target_ids.add(dependency.source_target_id)
            target_ids.add(dependency.destination_target_id)
        targets = (
            self.db.query(MonitorTarget)
            .filter(MonitorTarget.user_id == user_id, MonitorTarget.deleted_at.is_(None), MonitorTarget.id.in_(target_ids))
            .all()
        )
        return dependencies, {item.id: item for item in targets}

    def _related_alert_payloads(self, user_id: int, target: MonitorTarget, minutes: int, limit: int, *, exclude_event_id: int | None = None) -> list[dict[str, Any]]:
        dependencies, targets = self._dependency_context(user_id, target.id)
        related_targets = {target.id: target}
        for dependency in dependencies:
            related_id = dependency.destination_target_id if dependency.source_target_id == target.id else dependency.source_target_id
            if related_id in targets:
                related_targets[related_id] = targets[related_id]
        since = _utcnow() - timedelta(minutes=minutes)
        events = (
            self.db.query(AlertEvent)
            .filter(AlertEvent.user_id == user_id, AlertEvent.deleted_at.is_(None), AlertEvent.last_triggered_at >= since)
            .order_by(AlertEvent.last_triggered_at.desc(), AlertEvent.id.desc())
            .limit(500)
            .all()
        )
        related: list[dict[str, Any]] = []
        seen: set[int] = set()
        for event in events:
            if event.id == exclude_event_id:
                continue
            matching_target_ids = [target_id for target_id, candidate in related_targets.items() if _event_belongs_to_target(event, candidate)]
            if not matching_target_ids or event.id in seen:
                continue
            seen.add(event.id)
            payload = self._event_payload(event)
            payload["relation"] = "same_target" if target.id in matching_target_ids else "dependency"
            payload["related_target"] = self._target_reference(related_targets[matching_target_ids[0]])
            related.append(payload)
            if len(related) >= limit:
                break
        return related

    def _kubernetes_warning_payloads(self, user_id: int, minutes: int, limit: int) -> list[dict[str, Any]]:
        clusters = (
            self.db.query(ManagedCluster)
            .filter(ManagedCluster.user_id == user_id, ManagedCluster.deleted_at.is_(None))
            .all()
        )
        cluster_names = {cluster.id: cluster.name for cluster in clusters}
        if not cluster_names:
            return []
        since = _utcnow() - timedelta(minutes=minutes)
        reports = (
            self.db.query(ClusterAgentReport)
            .filter(
                ClusterAgentReport.cluster_id.in_(set(cluster_names)),
                ClusterAgentReport.report_type == "alert",
                ClusterAgentReport.created_at >= since,
            )
            .order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc())
            .limit(500)
            .all()
        )
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for report in reports:
            raw_payload = report.payload or {}
            if raw_payload.get("alert_type") != "kubernetes_warning":
                continue
            fingerprint = str(raw_payload.get("fingerprint") or report.id)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            details = raw_payload.get("details") if isinstance(raw_payload.get("details"), dict) else raw_payload
            events.append({
                "cluster": {"id": report.cluster_id, "name": cluster_names.get(report.cluster_id, "unknown")},
                "namespace": self._redact_text(str(details.get("namespace") or "")) or None,
                "reason": self._redact_text(str(details.get("reason") or report.source or "")) or None,
                "message": self._redact_text(str(details.get("message") or report.message or "")) or None,
                "resource_kind": self._redact_text(str(details.get("resource_kind") or "")) or None,
                "resource_name": self._redact_text(str(details.get("resource_name") or "")) or None,
                "level": report.level,
                "created_at": self._iso(report.created_at),
            })
            if len(events) >= limit:
                break
        return events

    @staticmethod
    def _target_reference(target: MonitorTarget) -> dict[str, Any]:
        return {"id": target.id, "name": target.name, "target_type": target.target_type, "exporter_kind": target.exporter_kind}

    def _dependency_payload(self, dependency: ServiceDependency, targets: dict[int, MonitorTarget], selected_target_id: int) -> dict[str, Any]:
        direction = "outbound" if dependency.source_target_id == selected_target_id else "inbound"
        return {
            "id": dependency.id,
            "direction": direction,
            "dependency_type": dependency.dependency_type,
            "description": self._redact_text(dependency.description),
            "source": self._target_reference(targets[dependency.source_target_id]) if dependency.source_target_id in targets else {"id": dependency.source_target_id, "name": "unavailable"},
            "destination": self._target_reference(targets[dependency.destination_target_id]) if dependency.destination_target_id in targets else {"id": dependency.destination_target_id, "name": "unavailable"},
            "created_at": self._iso(dependency.created_at),
        }

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
    def _owned_target(self, user_id: int, target_id: int) -> MonitorTarget:
        target = (
            self.db.query(MonitorTarget)
            .filter(MonitorTarget.id == target_id, MonitorTarget.user_id == user_id, MonitorTarget.deleted_at.is_(None))
            .first()
        )
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
        return target

    def _owned_event(self, user_id: int, event_id: int) -> AlertEvent:
        event = (
            self.db.query(AlertEvent)
            .filter(AlertEvent.id == event_id, AlertEvent.user_id == user_id, AlertEvent.deleted_at.is_(None))
            .first()
        )
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert event not found")
        return event

    @staticmethod
    def _event_payload(event: AlertEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "rule_name": event.rule_name,
            "scope": event.scope,
            "instance": event.instance,
            "level": event.level,
            "metric": event.metric,
            "operator": event.operator,
            "value": event.value,
            "threshold": event.threshold,
            "status": event.status,
            "handling_status": event.handling_status,
            "message": DiagnosisToolService._redact_text(event.message),
            "last_triggered_at": event.last_triggered_at.isoformat() if event.last_triggered_at else None,
        }

    @staticmethod
    def _check_payload(check: TargetCheckResult | None) -> dict[str, Any] | None:
        if check is None:
            return None
        return {
            "status": check.status,
            "response_time_ms": check.response_time_ms,
            "status_code": check.status_code,
            "message": DiagnosisToolService._redact_text(check.message),
            "details": DiagnosisToolService._redact_value(check.details or {}),
            "checked_at": check.checked_at.isoformat() if check.checked_at else None,
        }

    @staticmethod
    def _target_logql(user_id: int, target: MonitorTarget, keyword: str) -> str:
        # Logs are evidence only when the collector stamped the exact target ID.
        # Do not fall back to matching target names or endpoints: such matches can
        # mix multiple Targets owned by the same platform user.
        expression = f'{{platform_target_id="{target.id}"}}'
        if keyword:
            expression += f' |~ "{re.escape(keyword)}"'
        return scope_logql(expression, user_id)

    @staticmethod
    def _loki_entries(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        streams = payload.get("data", {}).get("result", [])
        for stream in streams:
            labels = stream.get("stream") or {}
            for timestamp, line in stream.get("values") or []:
                entries.append({"time_ns": timestamp, "labels": labels, "line": DiagnosisToolService._redact_text(str(line))[:2000]})
                if len(entries) >= limit:
                    return entries
        return entries

    @staticmethod
    def _redact_endpoint(endpoint: str) -> str:
        return re.sub(r'(https?://)[^/@\s]+@', r'\1***@', endpoint)

    @staticmethod
    def _redact_text(value: str | None) -> str | None:
        if value is None:
            return None
        return re.sub(r'(?i)\b(password|passwd|token|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;]+', r'\1=***', value)

    @staticmethod
    def _redact_value(value: Any) -> Any:
        if isinstance(value, dict):
            sensitive_keys = {"password", "passwd", "token", "secret", "api_key", "apikey", "authorization"}
            return {
                str(key): "***" if str(key).lower().replace("-", "_") in sensitive_keys else DiagnosisToolService._redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [DiagnosisToolService._redact_value(item) for item in value]
        if isinstance(value, str):
            return DiagnosisToolService._redact_text(value)
        return value

    @staticmethod
    def _summary(value: Any) -> str:
        text = str(DiagnosisToolService._redact_value(value)).replace("\n", " ").strip()
        return text[:1000]
