import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.assistant_tools import (
    MetricsToolRequest,
    TokenToolRequest,
    translate_tool_error,
    verify_dify_tool_secret,
)
from app.services.diagnosis_tool_service import (
    DiagnosisTokenError,
    DiagnosisToolLimitError,
    DiagnosisToolService,
    METRIC_TYPES,
)
from app.services.dify_tool_openapi import dify_tool_openapi


class DiagnosisToolSecurityTest(unittest.TestCase):
    def test_metric_type_whitelist_is_fixed(self) -> None:
        self.assertEqual(
            METRIC_TYPES,
            {
                "availability",
                "response_time",
                "cpu",
                "memory",
                "disk",
                "connections",
                "queue_messages",
                "consumers",
                "error_rate",
            },
        )

    def test_metric_request_rejects_unknown_type_and_long_ranges(self) -> None:
        with self.assertRaises(ValidationError):
            MetricsToolRequest(diagnosis_token="a" * 32, metric_type="promql")
        with self.assertRaises(ValidationError):
            MetricsToolRequest(diagnosis_token="a" * 32, metric_type="cpu", minutes=61)

    def test_token_request_has_no_user_target_or_event_scope_fields(self) -> None:
        fields = set(TokenToolRequest.model_fields)
        self.assertEqual(fields, {"diagnosis_token"})

    def test_logql_is_scoped_to_the_exact_target_and_escapes_input(self) -> None:
        target = type(
            "Target",
            (),
            {
                "name": "rabbitmq",
                "endpoint": "https://mq.example.com:15692/metrics",
                "exporter_kind": "rabbitmq",
                "id": 20,
            },
        )()

        expression = DiagnosisToolService._target_logql(9, target, "error.*")

        self.assertIn('platform_user_id="9"', expression)
        self.assertIn('platform_target_id="20"', expression)
        self.assertIn("error\\.\\*", expression)
        self.assertNotIn("rabbitmq", expression)
        self.assertNotIn("mq.example.com", expression)

    def test_sensitive_values_are_redacted_before_returning_to_dify(self) -> None:
        self.assertEqual(DiagnosisToolService._redact_text("password=abc token: xyz"), "password=*** token=***")
        self.assertEqual(
            DiagnosisToolService._redact_endpoint("https://alice:secret@example.com/metrics"),
            "https://***@example.com/metrics",
        )
        self.assertEqual(
            DiagnosisToolService._redact_value({"password": "abc", "nested": {"token": "xyz"}}),
            {"password": "***", "nested": {"token": "***"}},
        )

    def test_tool_secret_is_required_and_constant_time_compared(self) -> None:
        with patch.dict(os.environ, {"DIFY_TOOL_SECRET": "expected"}, clear=False):
            verify_dify_tool_secret("expected")
            with self.assertRaises(HTTPException) as context:
                verify_dify_tool_secret("wrong")
            self.assertEqual(context.exception.status_code, 401)

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as context:
                verify_dify_tool_secret("anything")
            self.assertEqual(context.exception.status_code, 503)

    def test_token_and_quota_errors_have_distinct_http_statuses(self) -> None:
        self.assertEqual(translate_tool_error(DiagnosisTokenError("expired")).status_code, 401)
        self.assertEqual(translate_tool_error(DiagnosisToolLimitError("limit")).status_code, 429)

    def test_openapi_exports_only_the_four_read_only_tools(self) -> None:
        spec = dify_tool_openapi("https://pdsaiops.com/api/v1/assistant/tools")

        self.assertEqual(
            set(spec["paths"]),
            {"/alert-context", "/target-status", "/target-metrics", "/target-logs"},
        )
        self.assertEqual(spec["servers"][0]["url"], "https://pdsaiops.com/api/v1/assistant/tools")
        self.assertIn("X-Dify-Tool-Secret", str(spec))
        self.assertNotIn("kubectl", str(spec).lower())
        metrics_schema = spec["components"]["schemas"]["MetricsToolRequest"]
        self.assertEqual(metrics_schema["required"], ["diagnosis_token", "metric_type"])
        self.assertEqual(set(metrics_schema["properties"]), {"diagnosis_token", "metric_type", "minutes"})
        self.assertNotIn("allOf", metrics_schema)

        logs_schema = spec["components"]["schemas"]["LogsToolRequest"]
        self.assertEqual(logs_schema["required"], ["diagnosis_token"])
        self.assertEqual(set(logs_schema["properties"]), {"diagnosis_token", "keyword", "minutes", "limit"})
        self.assertNotIn("allOf", logs_schema)


if __name__ == "__main__":
    unittest.main()
