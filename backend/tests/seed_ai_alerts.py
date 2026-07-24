from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.monitor_target import MonitorTarget
from app.models.target_check_result import TargetCheckResult
from app.models.user import User

PREFIX = "AI测试-"

RULES = [
    {"name": "AI测试-CPU使用率过高", "scope": "node", "metric": "cpu_usage_percent", "operator": ">=", "threshold": 80, "level": "severe", "instance": "k8s-worker-01:9100", "value": 93.4, "message": "k8s-worker-01 CPU 使用率持续高于 90%，可能存在异常进程或流量突增。"},
    {"name": "AI测试-内存使用率过高", "scope": "node", "metric": "memory_usage_percent", "operator": ">=", "threshold": 85, "level": "urgent", "instance": "k8s-worker-02:9100", "value": 96.2, "message": "k8s-worker-02 内存使用率接近耗尽，存在 OOM 和 Pod 驱逐风险。"},
    {"name": "AI测试-磁盘空间不足", "scope": "node", "metric": "disk_usage_percent", "operator": ">=", "threshold": 85, "level": "severe", "instance": "k8s-control-01:9100", "value": 91.7, "message": "k8s-control-01 根分区磁盘使用率过高，可能由容器日志或镜像缓存导致。"},
    {"name": "AI测试-系统负载过高", "scope": "node", "metric": "load1", "operator": ">=", "threshold": 4, "level": "general", "instance": "k8s-worker-01:9100", "value": 7.8, "message": "k8s-worker-01 1分钟负载过高，需要区分 CPU、IO wait 或进程阻塞。"},
]

TARGETS = [
    {
        "name": "AI测试-官网HTTP500",
        "target_type": "website",
        "endpoint": "https://www.example-prod.com",
        "expected_keyword": "Welcome",
        "description": "用于测试 AI 对 HTTP 5xx 的分析能力。",
        "check": {"status": "down", "response_time_ms": 1840, "status_code": 500, "message": "HTTP status is 500; Expected keyword not found", "details": {"dns_ok": True, "resolved_ips": ["203.0.113.10"], "tls_ok": True, "tls_days_remaining": 43, "keyword_ok": False, "expected_keyword": "Welcome", "metrics_format_ok": None}},
    },
    {
        "name": "AI测试-node_exporter异常",
        "target_type": "exporter",
        "endpoint": "http://203.0.113.20:9100/metrics",
        "expected_keyword": None,
        "description": "用于测试 AI 对 exporter /metrics 异常的分析能力。",
        "check": {"status": "down", "response_time_ms": 230, "status_code": 200, "message": "Endpoint does not look like Prometheus metrics", "details": {"dns_ok": True, "resolved_ips": ["203.0.113.20"], "tls_ok": None, "tls_days_remaining": None, "keyword_ok": None, "metrics_format_ok": False}},
    },
    {
        "name": "AI测试-PostgreSQL端口不可达",
        "target_type": "port",
        "endpoint": "203.0.113.30:5432",
        "expected_keyword": None,
        "description": "用于测试 AI 对 TCP 端口不可达的分析能力。",
        "check": {"status": "down", "response_time_ms": 5000, "status_code": None, "message": "timed out", "details": {"host": "203.0.113.30", "port": 5432, "dns_ok": True, "resolved_ips": ["203.0.113.30"]}},
    },
    {
        "name": "AI测试-证书即将过期",
        "target_type": "website",
        "endpoint": "https://soon-expire.example.com",
        "expected_keyword": None,
        "description": "用于测试 AI 对 TLS 证书问题的分析能力。",
        "check": {"status": "up", "response_time_ms": 420, "status_code": 200, "message": "HTTP target is reachable", "details": {"dns_ok": True, "resolved_ips": ["203.0.113.40"], "tls_ok": True, "tls_days_remaining": 5, "tls_expires_at": "2026-07-10T00:00:00+00:00", "keyword_ok": None, "metrics_format_ok": None}},
    },
]


def get_or_create_rule(db, user_id: int, item: dict) -> AlertRule:
    rule = db.query(AlertRule).filter(AlertRule.user_id == user_id, AlertRule.name == item["name"]).first()
    if rule:
        return rule
    rule = AlertRule(
        user_id=user_id,
        name=item["name"],
        scope=item["scope"],
        metric=item["metric"],
        operator=item["operator"],
        threshold=item["threshold"],
        level=item["level"],
        enabled=True,
        description="AI Assistant 测试告警规则，可用于验证运维知识库和大模型分析。",
    )
    db.add(rule)
    db.flush()
    return rule


def seed():
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id.asc()).first()
        if not user:
            raise RuntimeError("No user found. Please register or create an admin user first.")

        created_rules = 0
        created_events = 0
        created_targets = 0
        created_checks = 0

        for item in RULES:
            existed_rule = db.query(AlertRule).filter(AlertRule.user_id == user.id, AlertRule.name == item["name"]).first()
            rule = get_or_create_rule(db, user.id, item)
            if not existed_rule:
                created_rules += 1
            existed_event = db.query(AlertEvent).filter(AlertEvent.user_id == user.id, AlertEvent.rule_name == item["name"], AlertEvent.status == "active").first()
            if not existed_event:
                db.add(AlertEvent(
                    user_id=user.id,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    scope=rule.scope,
                    instance=item["instance"],
                    level=item["level"],
                    metric=item["metric"],
                    operator=item["operator"],
                    value=float(item["value"]),
                    threshold=float(item["threshold"]),
                    status="active",
                    message=item["message"],
                    trigger_count=3,
                    acknowledged=False,
                ))
                created_events += 1

        for item in TARGETS:
            target = db.query(MonitorTarget).filter(MonitorTarget.user_id == user.id, MonitorTarget.name == item["name"]).first()
            if not target:
                target = MonitorTarget(
                    user_id=user.id,
                    name=item["name"],
                    target_type=item["target_type"],
                    endpoint=item["endpoint"],
                    expected_keyword=item["expected_keyword"],
                    description=item["description"],
                )
                db.add(target)
                db.flush()
                created_targets += 1
            check = item["check"]
            existed_check = db.query(TargetCheckResult).filter(TargetCheckResult.user_id == user.id, TargetCheckResult.target_id == target.id, TargetCheckResult.message == check["message"]).first()
            if not existed_check:
                db.add(TargetCheckResult(
                    user_id=user.id,
                    target_id=target.id,
                    status=check["status"],
                    response_time_ms=check["response_time_ms"],
                    status_code=check["status_code"],
                    message=check["message"],
                    details=check["details"],
                ))
                created_checks += 1

        db.commit()
        print(f"user={user.username} id={user.id}")
        print(f"created_rules={created_rules}")
        print(f"created_events={created_events}")
        print(f"created_targets={created_targets}")
        print(f"created_checks={created_checks}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
