import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.monitor_target import MonitorTarget
from app.models.user import User

TARGET_ALERTS = [
    ("AI测试-官网HTTP500", "AI测试-官网HTTP500-目标告警", "response_time_ms", 1840, 1000, "severe", "目标网站 HTTP 500 且响应时间过高。"),
    ("AI测试-node_exporter异常", "AI测试-node_exporter异常-目标告警", "response_time_ms", 230, 100, "severe", "Exporter 返回内容不是 Prometheus metrics 格式。"),
    ("AI测试-PostgreSQL端口不可达", "AI测试-PostgreSQL端口不可达-目标告警", "response_time_ms", 5000, 1000, "urgent", "PostgreSQL TCP 端口连接超时。"),
    ("AI测试-证书即将过期", "AI测试-证书即将过期-目标告警", "tls_days_remaining", 5, 7, "general", "HTTPS 证书剩余时间低于阈值。"),
]


def main(username: str = "admin"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise RuntimeError(f"User not found: {username}")
        created_rules = 0
        created_events = 0
        for target_name, rule_name, metric, value, threshold, level, message in TARGET_ALERTS:
            target = db.query(MonitorTarget).filter(MonitorTarget.user_id == user.id, MonitorTarget.name == target_name).first()
            if not target:
                continue
            rule = db.query(AlertRule).filter(AlertRule.user_id == user.id, AlertRule.name == rule_name).first()
            if not rule:
                rule = AlertRule(
                    user_id=user.id,
                    name=rule_name,
                    scope="target",
                    metric=metric,
                    operator=">=",
                    threshold=float(threshold),
                    level=level,
                    enabled=True,
                    description="AI Assistant target scoped test alert.",
                )
                db.add(rule)
                db.flush()
                created_rules += 1
            event = db.query(AlertEvent).filter(AlertEvent.user_id == user.id, AlertEvent.rule_name == rule_name, AlertEvent.status == "active").first()
            if not event:
                db.add(AlertEvent(
                    user_id=user.id,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    scope="target",
                    instance=target.endpoint,
                    level=level,
                    metric=metric,
                    operator=">=",
                    value=float(value),
                    threshold=float(threshold),
                    status="active",
                    message=message,
                    trigger_count=2,
                    acknowledged=False,
                ))
                created_events += 1
        db.commit()
        print(f"user={user.username} created_rules={created_rules} created_events={created_events}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "admin")
