from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.monitor_target import MonitorTarget
from app.models.target_check_result import TargetCheckResult
from app.models.user import User

TEST_TARGETS = [
    {
        "name": "测试-Port-SSH连通",
        "target_type": "port",
        "endpoint": "114.55.117.211:22",
        "description": "Port 类型只检测 host:port 是否可连通，不产生 CPU/内存/磁盘图表。",
        "check": {
            "status": "up",
            "response_time_ms": 42,
            "message": "TCP port is reachable",
            "details": {"host": "114.55.117.211", "port": 22, "dns_ok": True, "resolved_ips": ["114.55.117.211"]},
        },
    },
    {
        "name": "测试-Port-SSH不通",
        "target_type": "port",
        "endpoint": "203.0.113.60:22",
        "description": "Port 类型不可达示例。",
        "check": {
            "status": "down",
            "response_time_ms": 5000,
            "message": "timed out",
            "details": {"host": "203.0.113.60", "port": 22, "dns_ok": True, "resolved_ips": ["203.0.113.60"]},
        },
    },
    {
        "name": "测试-Exporter-外部服务器A",
        "target_type": "exporter",
        "exporter_kind": "node",
        "endpoint": "http://198.51.100.10:9100/metrics",
        "description": "Exporter 类型会进入 Monitored Servers 资源图表。",
        "check": {
            "status": "up",
            "response_time_ms": 88,
            "status_code": 200,
            "message": "HTTP target is reachable",
            "details": {
                "dns_ok": True,
                "resolved_ips": ["198.51.100.10"],
                "metrics_format_ok": True,
                "node_metrics": {
                    "cpu_usage_percent": 37.5,
                    "memory_usage_percent": 62.2,
                    "disk_usage_percent": 48.7,
                    "load1": 1.36,
                },
            },
        },
    },
    {
        "name": "测试-Exporter-外部服务器B",
        "target_type": "exporter",
        "exporter_kind": "node",
        "endpoint": "http://198.51.100.11:9100/metrics",
        "description": "Exporter 资源偏高示例。",
        "check": {
            "status": "up",
            "response_time_ms": 104,
            "status_code": 200,
            "message": "HTTP target is reachable",
            "details": {
                "dns_ok": True,
                "resolved_ips": ["198.51.100.11"],
                "metrics_format_ok": True,
                "node_metrics": {
                    "cpu_usage_percent": 81.4,
                    "memory_usage_percent": 74.8,
                    "disk_usage_percent": 91.2,
                    "load1": 5.74,
                },
            },
        },
    },
    {
        "name": "测试-Exporter-格式错误",
        "target_type": "exporter",
        "exporter_kind": "custom",
        "endpoint": "http://203.0.113.20:9100/metrics",
        "description": "Exporter 可访问但不是 Prometheus metrics 格式。",
        "check": {
            "status": "down",
            "response_time_ms": 230,
            "status_code": 200,
            "message": "Endpoint does not look like Prometheus metrics",
            "details": {"dns_ok": True, "resolved_ips": ["203.0.113.20"], "metrics_format_ok": False},
        },
    },
]


def main(username: str = "admin") -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise RuntimeError(f"User not found: {username}")
        created_targets = 0
        created_checks = 0
        for item in TEST_TARGETS:
            target = db.query(MonitorTarget).filter(MonitorTarget.user_id == user.id, MonitorTarget.name == item["name"]).first()
            if not target:
                target = MonitorTarget(
                    user_id=user.id,
                    name=item["name"],
                    target_type=item["target_type"],
                    endpoint=item["endpoint"],
                    exporter_kind=item.get("exporter_kind"),
                    expected_keyword=None,
                    description=item["description"],
                )
                db.add(target)
                db.flush()
                created_targets += 1
            check = item["check"]
            exists = db.query(TargetCheckResult).filter(
                TargetCheckResult.user_id == user.id,
                TargetCheckResult.target_id == target.id,
                TargetCheckResult.message == check["message"],
            ).first()
            if not exists:
                db.add(TargetCheckResult(
                    user_id=user.id,
                    target_id=target.id,
                    status=check["status"],
                    response_time_ms=check["response_time_ms"],
                    status_code=check.get("status_code"),
                    message=check["message"],
                    details=check["details"],
                ))
                created_checks += 1
        db.commit()
        print(f"user={user.username} created_targets={created_targets} created_checks={created_checks}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "admin")



