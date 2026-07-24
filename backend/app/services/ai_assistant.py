from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.knowledge.ops_runbooks import select_runbooks


class AIAssistantService:
    async def analyze_incident(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        runbooks = select_runbooks(context)
        local = self._local_analysis(question, context, runbooks)
        if not settings.ai_api_key:
            return {
                **local,
                "enabled": False,
                "provider": "local-rules",
                "model": None,
                "note": "AI_API_KEY is not configured. Returned local rule-based analysis.",
            }

        base_url = settings.ai_api_base_url.rstrip("/") or "https://api.deepseek.com"
        endpoint = f"{base_url}/chat/completions"
        payload = {
            "model": settings.ai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior Kubernetes, Linux, database, middleware, and web SRE. "
                        "You work inside an intelligent monitoring platform. "
                        "Use the monitoring context and matched runbooks to produce concrete incident actions. "
                        "Answer in Chinese. Do not invent data. If evidence is insufficient, say what data is missing."
                    ),
                },
                {"role": "user", "content": self._build_prompt(question, context, runbooks)},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("AI provider returned an empty response.")
            return {
                "enabled": True,
                "provider": base_url,
                "model": settings.ai_model,
                "summary": content,
                "runbooks": runbooks,
                "local_fallback": local,
            }
        except Exception as exc:
            return {
                **local,
                "enabled": False,
                "provider": base_url,
                "model": settings.ai_model,
                "note": f"AI provider request failed. Returned local rule-based analysis. Error: {exc}",
            }

    def _build_prompt(self, question: str, context: dict[str, Any], runbooks: list[dict[str, Any]]) -> str:
        return (
            f"User question:\n{question}\n\n"
            "Monitoring context JSON:\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Matched operations runbooks JSON:\n"
            f"{json.dumps(runbooks, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Please answer in Chinese with this structure:\n"
            "1. Fault conclusion: the most likely issue in 1-3 sentences.\n"
            "2. Evidence: cite status, metrics, status code, DNS/TLS/metrics results from context.\n"
            "3. Impact scope: affected target and possible user impact.\n"
            "4. Troubleshooting steps: ordered commands or checks.\n"
            "5. Handling history: summarize selected_alert_activities, including notes, ack, resolve, actor and time; say what has already been tried.\n"
            "6. Fix plan: immediate mitigation and long-term prevention. Avoid repeating actions that handling history says were already completed unless verification is needed.\n"
            "7. Alert escalation: general, severe, or urgent, with reasons.\n"
            "If context_type is analysis_session, analyze the selected target and selected_alert only, then continue from the conversation history and selected_alert_activities.\n"
            "Do not summarize unrelated platform alerts unless the user explicitly asks.\n"
        )

    def _local_analysis(
        self,
        question: str,
        context: dict[str, Any],
        runbooks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        suggestions: list[str] = []
        risks: list[str] = []
        target = context.get("target") or {}
        latest_check = context.get("latest_check") or {}
        selected_alert = context.get("selected_alert") or {}
        target_alerts = context.get("target_alerts") or []
        alert_activities = context.get("selected_alert_activities") or []
        activity_summary = context.get("selected_alert_activity_summary") or {}
        recent_alerts = [selected_alert] if selected_alert else (target_alerts or context.get("recent_alerts") or [])

        status = str(latest_check.get("status") or selected_alert.get("status") or "unknown")
        details = latest_check.get("details") or {}
        metrics = {str(event.get("metric")) for event in recent_alerts if event.get("metric")}

        if status == "down":
            risks.append("The selected target is currently down or failed its latest check.")
            suggestions.extend([
                "Verify the endpoint from the backend server with curl, nc, or Test-NetConnection.",
                "Check network path, firewall/security group, target process, and Kubernetes Service/Ingress routing.",
            ])
        if latest_check.get("status_code") and int(latest_check["status_code"]) >= 500:
            risks.append("The HTTP target returned a 5xx status code, which usually means a server-side failure.")
            suggestions.append("Check application logs, ingress/proxy logs, dependency health, and recent deployments.")
        if details.get("dns_ok") is False:
            risks.append("DNS resolution failed.")
            suggestions.append("Check DNS records, resolver configuration, and whether the domain exists from the backend network.")
        if details.get("tls_ok") is False:
            risks.append("TLS certificate validation failed.")
            suggestions.append("Check certificate chain, expiration time, SNI, and domain matching.")
        if details.get("metrics_format_ok") is False:
            risks.append("The exporter endpoint is reachable but does not look like Prometheus metrics format.")
            suggestions.append("Confirm the endpoint is /metrics and returns Prometheus text with # HELP or # TYPE lines.")
        if selected_alert:
            risks.append(f"Selected alert: {selected_alert.get('rule_name')} on {selected_alert.get('instance')} is {selected_alert.get('status')}.")
            suggestions.append("Analyze this selected alert first; do not mix it with unrelated alert events.")
        if alert_activities:
            last_action = activity_summary.get("last_action") or alert_activities[0].get("action")
            last_actor = activity_summary.get("last_actor") or alert_activities[0].get("actor")
            last_note = activity_summary.get("last_note") or alert_activities[0].get("note")
            risks.append(f"Handling history exists: {len(alert_activities)} activity records. Latest action is {last_action} by {last_actor}.")
            if last_note:
                suggestions.append(f"Continue from the latest handling note instead of restarting: {last_note}")
            if any(item.get("action") == "ack" for item in alert_activities):
                suggestions.append("This alert has already been acknowledged; focus on verification, mitigation, and final recovery criteria.")
            if any(item.get("action") == "resolve" for item in alert_activities):
                suggestions.append("This alert has a resolve record; verify metrics and target checks before recommending more recovery actions.")
        if metrics.intersection({"cpu_usage_percent", "memory_usage_percent", "disk_usage_percent", "load1"}):
            risks.append("The selected node resource alert needs Prometheus plus node-level investigation.")
            suggestions.append("Check top nodes/pods, node process usage, disk IO, and recent workload changes for the selected instance.")
        for runbook in runbooks:
            title = runbook.get("title")
            actions = runbook.get("actions") or []
            if title:
                suggestions.append(f"Use runbook: {title}.")
            suggestions.extend(str(action) for action in actions[:2])
        if not suggestions:
            suggestions.extend([
                "No obvious fault signal was found in the current context. Continue watching target history and alert trends.",
                "For production targets, add alert rules, notification channels, and periodic checks.",
            ])

        return {
            "summary": "Local rule-based analysis completed." if risks else "No clear abnormal signal found yet.",
            "question": question,
            "target_name": target.get("name"),
            "risks": risks,
            "suggestions": suggestions,
            "runbooks": runbooks,
        }


def get_ai_assistant_service() -> AIAssistantService:
    return AIAssistantService()



