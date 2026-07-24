import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from kubernetes import client, config

PLATFORM_API_URL = os.getenv("PLATFORM_API_URL", "").rstrip("/")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "unknown")
INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "30"))
AGENT_VERSION = os.getenv("AGENT_VERSION", "v1")
LOG_NAMESPACE = os.getenv("LOG_NAMESPACE", "")
LOG_TAIL_LINES = int(os.getenv("LOG_TAIL_LINES", "30"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_kubernetes_client() -> tuple[client.CoreV1Api | None, str | None]:
    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception as exc:
            return None, f"无法加载 Kubernetes 配置：{exc}"
    return client.CoreV1Api(), None


def post(path: str, payload: dict[str, Any]) -> None:
    if not PLATFORM_API_URL or not AGENT_TOKEN:
        print("PLATFORM_API_URL 或 AGENT_TOKEN 未配置", flush=True)
        return
    url = f"{PLATFORM_API_URL}{path}"
    headers = {"X-Agent-Token": AGENT_TOKEN}
    with httpx.Client(timeout=15) as http:
        response = http.post(url, headers=headers, json=payload)
        response.raise_for_status()


def safe_count(items: Any) -> int:
    return len(getattr(items, "items", []) or [])


def collect_snapshot(api: client.CoreV1Api | None) -> dict[str, Any]:
    if api is None:
        return {"node_count": 0, "pod_count": 0, "namespaces": []}
    nodes = api.list_node(_request_timeout=10)
    pods = api.list_pod_for_all_namespaces(_request_timeout=10)
    namespaces = sorted({pod.metadata.namespace for pod in pods.items if pod.metadata and pod.metadata.namespace})
    return {
        "node_count": safe_count(nodes),
        "pod_count": safe_count(pods),
        "namespaces": namespaces[:50],
    }


def report_logs(api: client.CoreV1Api | None) -> None:
    if api is None or not LOG_NAMESPACE:
        return
    pods = api.list_namespaced_pod(LOG_NAMESPACE, _request_timeout=10).items[:5]
    for pod in pods:
        name = pod.metadata.name if pod.metadata else "unknown"
        try:
            log_text = api.read_namespaced_pod_log(name=name, namespace=LOG_NAMESPACE, tail_lines=LOG_TAIL_LINES, _request_timeout=10)
        except Exception as exc:
            post("/agent/reports", {
                "report_type": "log",
                "source": f"{LOG_NAMESPACE}/{name}",
                "level": "warning",
                "message": f"读取日志失败：{exc}",
                "payload": {"cluster": CLUSTER_NAME, "time": now_iso()},
            })
            continue
        if log_text.strip():
            post("/agent/reports", {
                "report_type": "log",
                "source": f"{LOG_NAMESPACE}/{name}",
                "level": "info",
                "message": log_text[-2000:],
                "payload": {"cluster": CLUSTER_NAME, "pod": name, "namespace": LOG_NAMESPACE, "time": now_iso()},
            })


def main() -> None:
    api, error = load_kubernetes_client()
    print(f"monitor-agent started cluster={CLUSTER_NAME} platform={PLATFORM_API_URL}", flush=True)
    while True:
        try:
            snapshot = collect_snapshot(api)
            message = error or "Agent 正常运行"
            post("/agent/heartbeat", {
                "status": "online" if not error else "degraded",
                "agent_version": AGENT_VERSION,
                "node_count": snapshot["node_count"],
                "pod_count": snapshot["pod_count"],
                "message": message,
                "payload": {"cluster": CLUSTER_NAME, "time": now_iso(), "namespaces": snapshot.get("namespaces", [])},
            })
            post("/agent/reports", {
                "report_type": "metric",
                "source": CLUSTER_NAME,
                "level": "info",
                "message": f"节点 {snapshot['node_count']} 个，Pod {snapshot['pod_count']} 个",
                "payload": snapshot,
            })
            report_logs(api)
        except Exception as exc:
            print(f"agent loop error: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
