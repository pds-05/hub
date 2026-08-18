import hashlib
import unittest
from datetime import timedelta
from types import SimpleNamespace

from fastapi import HTTPException

from app.models.ai_diagnosis import AIDiagnosis
from app.models.alert_event import AlertEvent
from app.models.monitor_target import MonitorTarget
from app.services.diagnosis_tool_service import (
    DiagnosisTokenError,
    DiagnosisToolLimitError,
    DiagnosisToolService,
    _utcnow,
)


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self, diagnosis=None, target=None, event=None):
        self.diagnosis = diagnosis
        self.target = target
        self.event = event
        self.added = []

    def query(self, model):
        if model is AIDiagnosis:
            return FakeQuery(self.diagnosis)
        if model is MonitorTarget:
            return FakeQuery(self.target)
        if model is AlertEvent:
            return FakeQuery(self.event)
        return FakeQuery(None)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass

    def refresh(self, value):
        if getattr(value, "id", None) is None:
            value.id = 100


class DiagnosisTokenLifecycleTest(unittest.TestCase):
    def make_target(self):
        return SimpleNamespace(id=20, user_id=7, deleted_at=None, endpoint="https://mq.example.com:15692/metrics")

    def make_diagnosis(self, raw_token: str, **overrides):
        values = {
            "id": 10,
            "user_id": 7,
            "target_id": 20,
            "expires_at": _utcnow() + timedelta(minutes=5),
            "tool_calls_used": 0,
            "token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_raw_token_is_never_stored_and_event_must_match_target(self):
        target = self.make_target()
        event = SimpleNamespace(id=30, user_id=7, deleted_at=None, instance="other.example.com:15692")
        session = FakeSession(target=target, event=event)
        service = DiagnosisToolService(session)
        user = SimpleNamespace(id=7)

        with self.assertRaises(HTTPException) as context:
            service.create_diagnosis(user, target.id, "diagnose RabbitMQ", event.id)
        self.assertEqual(context.exception.status_code, 400)

        session.event = SimpleNamespace(id=30, user_id=7, deleted_at=None, instance="mq.example.com:15692")
        diagnosis, raw_token = service.create_diagnosis(user, target.id, "diagnose RabbitMQ", session.event.id)

        self.assertNotEqual(diagnosis.token_hash, raw_token)
        self.assertEqual(diagnosis.token_hash, hashlib.sha256(raw_token.encode("utf-8")).hexdigest())
        self.assertLessEqual(diagnosis.expires_at, _utcnow() + timedelta(minutes=10, seconds=1))

    def test_expired_token_is_rejected_before_target_lookup(self):
        raw_token = "x" * 32
        diagnosis = self.make_diagnosis(raw_token, expires_at=_utcnow() - timedelta(seconds=1))
        service = DiagnosisToolService(FakeSession(diagnosis=diagnosis))

        with self.assertRaises(DiagnosisTokenError):
            service.resolve_token(raw_token, "get_target_status")

    def test_tool_call_quota_is_enforced(self):
        raw_token = "y" * 32
        diagnosis = self.make_diagnosis(raw_token, tool_calls_used=5)
        service = DiagnosisToolService(FakeSession(diagnosis=diagnosis), max_tool_calls=5)

        with self.assertRaises(DiagnosisToolLimitError):
            service.resolve_token(raw_token, "get_target_status")

    def test_successful_call_uses_token_scope_and_audits_safe_parameters(self):
        raw_token = "z" * 32
        diagnosis = self.make_diagnosis(raw_token)
        session = FakeSession(diagnosis=diagnosis, target=self.make_target())
        service = DiagnosisToolService(session)

        resolved, target = service.resolve_token(raw_token, "get_target_metrics", {"metric_type": "queue_messages", "minutes": 30})

        self.assertIs(resolved, diagnosis)
        self.assertEqual(target.id, 20)
        self.assertEqual(diagnosis.tool_calls_used, 1)
        audit = session.added[-1]
        self.assertEqual(audit.tool_name, "get_target_metrics")
        self.assertNotIn("diagnosis_token", audit.parameter_summary)
        self.assertEqual(audit.parameter_summary, {"metric_type": "queue_messages", "minutes": 30})


if __name__ == "__main__":
    unittest.main()
