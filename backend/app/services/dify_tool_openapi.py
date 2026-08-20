from __future__ import annotations


def dify_tool_openapi(public_base_url: str) -> dict:
    base_url = public_base_url.rstrip("/")
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "AIOps Diagnosis Read-only Tools",
            "version": "1.0.0",
            "description": "Read-only tools scoped by a short-lived diagnosis_token. Never send user_id, target_id, event_id, PromQL, LogQL, SQL, shell commands, or Kubernetes commands.",
        },
        "servers": [{"url": base_url}],
        "components": {
            "securitySchemes": {"DifyToolSecret": {"type": "apiKey", "in": "header", "name": "X-Dify-Tool-Secret"}},
            "schemas": {
                "TokenToolRequest": {
                    "type": "object",
                    "required": ["diagnosis_token"],
                    "properties": {"diagnosis_token": {"type": "string", "description": "Short-lived token supplied by the platform for this diagnosis only."}},
                },
                "MetricsToolRequest": {
                    "type": "object",
                    "required": ["diagnosis_token", "metric_type"],
                    "properties": {
                        "diagnosis_token": {"type": "string", "description": "Short-lived token supplied by the platform for this diagnosis only."},
                        "metric_type": {"type": "string", "enum": ["availability", "response_time", "cpu", "memory", "disk", "connections", "queue_messages", "consumers", "error_rate"]},
                        "minutes": {"type": "integer", "default": 30, "minimum": 1, "maximum": 60},
                    },
                },
                "LogsToolRequest": {
                    "type": "object",
                    "required": ["diagnosis_token"],
                    "properties": {
                        "diagnosis_token": {"type": "string", "description": "Short-lived token supplied by the platform for this diagnosis only."},
                        "keyword": {"type": "string", "maxLength": 200},
                        "minutes": {"type": "integer", "default": 30, "minimum": 1, "maximum": 60},
                        "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
                    },
                },
            },
        },
        "security": [{"DifyToolSecret": []}],
        "paths": {
            "/alert-context": {"post": {"operationId": "get_alert_context", "summary": "Read the alert context and handling activities attached to the diagnosis", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/TokenToolRequest"}}}}, "responses": {"200": {"description": "Alert context"}}}},
            "/target-status": {"post": {"operationId": "get_target_status", "summary": "Read the current platform target metadata and most recent check", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/TokenToolRequest"}}}}, "responses": {"200": {"description": "Target status"}}}},
            "/target-metrics": {"post": {"operationId": "get_target_metrics", "summary": "Read a whitelisted category of Prometheus metrics for the diagnosis target", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MetricsToolRequest"}}}}, "responses": {"200": {"description": "Metrics"}}}},
            "/target-logs": {"post": {"operationId": "search_target_logs", "summary": "Search recent Loki logs scoped to the diagnosis target", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LogsToolRequest"}}}}, "responses": {"200": {"description": "Log entries"}}}},
        },
    }
