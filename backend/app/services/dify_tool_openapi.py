from __future__ import annotations


_TOKEN_DESCRIPTION = "Short-lived token supplied by the platform for this diagnosis only."


def _request_schema(*, fields: dict, required: list[str]) -> dict:
    return {"type": "object", "required": required, "properties": fields}


def _post_operation(operation_id: str, summary: str, schema_name: str, response: str) -> dict:
    return {
        "operationId": operation_id,
        "summary": summary,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
        },
        "responses": {"200": {"description": response}},
    }


def dify_tool_openapi(public_base_url: str) -> dict:
    base_url = public_base_url.rstrip("/")
    token_fields = {"diagnosis_token": {"type": "string", "description": _TOKEN_DESCRIPTION}}
    context_fields = {
        **token_fields,
        "minutes": {"type": "integer", "default": 60, "minimum": 5, "maximum": 240},
        "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
    }
    metrics_fields = {
        **token_fields,
        "metric_type": {
            "type": "string",
            "enum": ["availability", "response_time", "cpu", "memory", "disk", "connections", "queue_messages", "consumers", "error_rate"],
        },
        "minutes": {"type": "integer", "default": 30, "minimum": 1, "maximum": 60},
    }
    logs_fields = {
        **token_fields,
        "keyword": {"type": "string", "maxLength": 200},
        "minutes": {"type": "integer", "default": 30, "minimum": 1, "maximum": 60},
        "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "AIOps Diagnosis Read-only Tools",
            "version": "2.0.0",
            "description": (
                "Read-only tools scoped by a short-lived diagnosis_token. Never send user_id, target_id, event_id, PromQL, "
                "LogQL, SQL, shell commands, or Kubernetes commands. Kubernetes events are cluster context, not target proof."
            ),
        },
        "servers": [{"url": base_url}],
        "components": {
            "securitySchemes": {"DifyToolSecret": {"type": "apiKey", "in": "header", "name": "X-Dify-Tool-Secret"}},
            "schemas": {
                "TokenToolRequest": _request_schema(fields=token_fields, required=["diagnosis_token"]),
                "MetricsToolRequest": _request_schema(fields=metrics_fields, required=["diagnosis_token", "metric_type"]),
                "LogsToolRequest": _request_schema(fields=logs_fields, required=["diagnosis_token"]),
                "ContextToolRequest": _request_schema(fields=context_fields, required=["diagnosis_token"]),
            },
        },
        "security": [{"DifyToolSecret": []}],
        "paths": {
            "/alert-context": {"post": _post_operation("get_alert_context", "Read the alert context and handling activities attached to the diagnosis", "TokenToolRequest", "Alert context")},
            "/target-status": {"post": _post_operation("get_target_status", "Read the current platform target metadata and most recent check", "TokenToolRequest", "Target status")},
            "/target-metrics": {"post": _post_operation("get_target_metrics", "Read a whitelisted category of Prometheus metrics for the diagnosis target", "MetricsToolRequest", "Metrics")},
            "/target-logs": {"post": _post_operation("search_target_logs", "Search recent Loki logs scoped to the diagnosis target", "LogsToolRequest", "Log entries")},
            "/related-alerts": {"post": _post_operation("get_related_alerts", "Read deduplicated recent alerts for the target and its configured dependencies", "ContextToolRequest", "Related alerts")},
            "/kubernetes-events": {"post": _post_operation("get_kubernetes_events", "Read recent Kubernetes Warning events as user-owned cluster context", "ContextToolRequest", "Kubernetes event context")},
            "/service-dependencies": {"post": _post_operation("get_service_dependencies", "Read user-configured service dependency topology for the diagnosis target", "TokenToolRequest", "Service dependencies")},
            "/incident-timeline": {"post": _post_operation("get_incident_timeline", "Read an ordered timeline of alert, target check, related-alert and Kubernetes context", "ContextToolRequest", "Incident timeline")},
        },
    }