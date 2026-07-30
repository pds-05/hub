import hashlib
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
AGENT_VERSION = os.getenv("AGENT_VERSION", "v2")
LOG_NAMESPACES = {item.strip() for item in os.getenv("LOG_NAMESPACES", "").split(",") if item.strip()}
LOG_TAIL_LINES = int(os.getenv("LOG_TAIL_LINES", "80"))
LOG_MAX_PODS = int(os.getenv("LOG_MAX_PODS", "10"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_clients() -> tuple[dict[str, Any] | None, str | None]:
    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception as exc:
            return None, f"无法加载 Kubernetes 配置：{exc}"
    return {
        "core": client.CoreV1Api(),
        "apps": client.AppsV1Api(),
        "network": client.NetworkingV1Api(),
        "custom": client.CustomObjectsApi(),
        "version": client.VersionApi(),
    }, None


def post(path: str, payload: dict[str, Any]) -> None:
    if not PLATFORM_API_URL or not AGENT_TOKEN:
        raise RuntimeError("PLATFORM_API_URL 或 AGENT_TOKEN 未配置")
    with httpx.Client(timeout=20) as http:
        response = http.post(
            f"{PLATFORM_API_URL}{path}",
            headers={"X-Agent-Token": AGENT_TOKEN},
            json=payload,
        )
        response.raise_for_status()


def fetch(errors: list[str], label: str, call: Any, **kwargs: Any) -> list[Any]:
    try:
        result = call(_request_timeout=15, **kwargs)
        return list(getattr(result, "items", []) or [])
    except Exception as exc:
        errors.append(f"{label}：{exc}")
        return []


def parse_cpu(value: Any) -> float:
    text = str(value or "0")
    for suffix, factor in (("n", 1e-9), ("u", 1e-6), ("m", 1e-3)):
        if text.endswith(suffix):
            return float(text[:-1] or 0) * factor
    return float(text or 0)


def parse_memory(value: Any) -> float:
    text = str(value or "0")
    factors = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4, "K": 1000, "M": 1000**2, "G": 1000**3}
    for suffix, factor in factors.items():
        if text.endswith(suffix):
            return float(text[:-len(suffix)] or 0) * factor
    return float(text or 0)


def percent(used: float, total: float) -> float | None:
    return round(used / total * 100, 2) if total > 0 else None


def resources(containers: list[Any]) -> dict[str, float]:
    result = {"cpu_request_cores": 0.0, "cpu_limit_cores": 0.0, "memory_request_bytes": 0.0, "memory_limit_bytes": 0.0}
    for container in containers or []:
        resource = getattr(container, "resources", None)
        requests = getattr(resource, "requests", None) or {}
        limits = getattr(resource, "limits", None) or {}
        result["cpu_request_cores"] += parse_cpu(requests.get("cpu"))
        result["cpu_limit_cores"] += parse_cpu(limits.get("cpu"))
        result["memory_request_bytes"] += parse_memory(requests.get("memory"))
        result["memory_limit_bytes"] += parse_memory(limits.get("memory"))
    return {key: round(value, 3) for key, value in result.items()}


def is_ready(conditions: list[Any] | None) -> bool:
    return any(item.type == "Ready" and item.status == "True" for item in conditions or [])


def waiting_reasons(pod: Any) -> list[str]:
    result = []
    statuses = (pod.status.init_container_statuses or []) + (pod.status.container_statuses or [])
    for status in statuses:
        waiting = getattr(getattr(status, "state", None), "waiting", None)
        if waiting and waiting.reason:
            result.append(waiting.reason)
    return sorted(set(result))


def collect_metrics(custom: Any) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    try:
        node_result = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes", _request_timeout=15)
        pod_result = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods", _request_timeout=15)
        nodes = {
            item["metadata"]["name"]: {
                "cpu_usage_cores": round(parse_cpu(item.get("usage", {}).get("cpu")), 4),
                "memory_usage_bytes": round(parse_memory(item.get("usage", {}).get("memory"))),
            }
            for item in node_result.get("items", [])
        }
        pods = {}
        for item in pod_result.get("items", []):
            key = f"{item['metadata'].get('namespace', 'default')}/{item['metadata']['name']}"
            pods[key] = {
                "cpu_usage_cores": round(sum(parse_cpu(c.get("usage", {}).get("cpu")) for c in item.get("containers", [])), 4),
                "memory_usage_bytes": round(sum(parse_memory(c.get("usage", {}).get("memory")) for c in item.get("containers", []))),
            }
        return nodes, pods, None
    except Exception as exc:
        return {}, {}, str(exc)


def workload_row(kind: str, item: Any) -> dict[str, Any]:
    if kind == "DaemonSet":
        desired, available = item.status.desired_number_scheduled or 0, item.status.number_available or 0
    elif kind == "StatefulSet":
        desired, available = item.spec.replicas or 0, item.status.ready_replicas or 0
    else:
        desired, available = item.spec.replicas or 0, item.status.available_replicas or 0
    return {
        "kind": kind,
        "namespace": item.metadata.namespace,
        "name": item.metadata.name,
        "desired_replicas": desired,
        "available_replicas": available,
        "unavailable_replicas": max(desired - available, 0),
    }


def collect_snapshot(clients: dict[str, Any] | None) -> dict[str, Any]:
    if clients is None:
        return {"collected_at": now_iso(), "cluster": {"node_count": 0}, "errors": ["Kubernetes 客户端不可用"]}
    errors: list[str] = []
    core, apps, network = clients["core"], clients["apps"], clients["network"]
    nodes = fetch(errors, "节点", core.list_node)
    pods = fetch(errors, "Pod", core.list_pod_for_all_namespaces)
    namespaces = fetch(errors, "命名空间", core.list_namespace)
    services = fetch(errors, "Service", core.list_service_for_all_namespaces)
    endpoints = fetch(errors, "Endpoint", core.list_endpoints_for_all_namespaces)
    pvs = fetch(errors, "PV", core.list_persistent_volume)
    pvcs = fetch(errors, "PVC", core.list_persistent_volume_claim_for_all_namespaces)
    events = fetch(errors, "事件", core.list_event_for_all_namespaces, field_selector="type=Warning")
    deployments = fetch(errors, "Deployment", apps.list_deployment_for_all_namespaces)
    statefulsets = fetch(errors, "StatefulSet", apps.list_stateful_set_for_all_namespaces)
    daemonsets = fetch(errors, "DaemonSet", apps.list_daemon_set_for_all_namespaces)
    ingresses = fetch(errors, "Ingress", network.list_ingress_for_all_namespaces)
    node_metrics, pod_metrics, metrics_error = collect_metrics(clients["custom"])
    if metrics_error:
        errors.append(f"资源指标：{metrics_error}")
    try:
        kubernetes_version = clients["version"].get_code(_request_timeout=10).git_version
    except Exception as exc:
        kubernetes_version = None
        errors.append(f"Kubernetes 版本：{exc}")

    pods_by_node: dict[str, list[Any]] = {}
    pod_rows, problem_pods = [], []
    phases = {"running": 0, "pending": 0, "failed": 0, "succeeded": 0, "unknown": 0}
    crash_loop = image_pull = 0
    for pod in pods:
        namespace, name = pod.metadata.namespace or "default", pod.metadata.name
        phase = (pod.status.phase or "Unknown").lower()
        phases[phase if phase in phases else "unknown"] += 1
        reasons = waiting_reasons(pod)
        crash_loop += int("CrashLoopBackOff" in reasons)
        image_pull += int(any(reason in {"ImagePullBackOff", "ErrImagePull"} for reason in reasons))
        row = {
            "namespace": namespace,
            "name": name,
            "node": pod.spec.node_name,
            "phase": pod.status.phase or "Unknown",
            "ready": is_ready(pod.status.conditions),
            "restarts": sum(status.restart_count or 0 for status in pod.status.container_statuses or []),
            "waiting_reasons": reasons,
            "containers": [container.name for container in pod.spec.containers or []],
            **resources(pod.spec.containers or []),
            **pod_metrics.get(f"{namespace}/{name}", {}),
        }
        pod_rows.append(row)
        if pod.spec.node_name:
            pods_by_node.setdefault(pod.spec.node_name, []).append(pod)
        if phase in {"pending", "failed", "unknown"} or reasons:
            problem_pods.append(row)

    node_rows, runtimes, os_images = [], set(), set()
    for node in nodes:
        name = node.metadata.name
        labels = node.metadata.labels or {}
        allocatable, capacity = node.status.allocatable or {}, node.status.capacity or {}
        node_pods = pods_by_node.get(name, [])
        requested = resources([container for pod in node_pods for container in (pod.spec.containers or [])])
        usage = node_metrics.get(name, {})
        cpu_total, memory_total = parse_cpu(allocatable.get("cpu")), parse_memory(allocatable.get("memory"))
        runtimes.add(node.status.node_info.container_runtime_version)
        os_images.add(node.status.node_info.os_image)
        node_rows.append({
            "name": name,
            "roles": sorted(k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/") and k.split("/", 1)[1]) or ["worker"],
            "ready": is_ready(node.status.conditions),
            "internal_ip": next((a.address for a in node.status.addresses or [] if a.type == "InternalIP"), None),
            "kubelet_version": node.status.node_info.kubelet_version,
            "container_runtime": node.status.node_info.container_runtime_version,
            "os_image": node.status.node_info.os_image,
            "kernel_version": node.status.node_info.kernel_version,
            "pod_count": len(node_pods),
            "taints": [f"{t.key}{'=' + t.value if t.value else ''}:{t.effect}" for t in node.spec.taints or []],
            "cpu_capacity_cores": round(parse_cpu(capacity.get("cpu")), 3),
            "memory_capacity_bytes": round(parse_memory(capacity.get("memory"))),
            **requested,
            **usage,
            "cpu_usage_percent": percent(usage.get("cpu_usage_cores", 0), cpu_total),
            "memory_usage_percent": percent(usage.get("memory_usage_bytes", 0), memory_total),
            "cpu_request_percent": percent(requested["cpu_request_cores"], cpu_total),
            "memory_request_percent": percent(requested["memory_request_bytes"], memory_total),
        })

    workload_groups = {
        "deployments": [workload_row("Deployment", item) for item in deployments],
        "statefulsets": [workload_row("StatefulSet", item) for item in statefulsets],
        "daemonsets": [workload_row("DaemonSet", item) for item in daemonsets],
    }
    workloads = sum(workload_groups.values(), [])
    ready_endpoints = {
        (item.metadata.namespace, item.metadata.name): bool(any(subset.addresses or [] for subset in item.subsets or []))
        for item in endpoints
    }
    no_endpoint = [
        {"namespace": item.metadata.namespace, "name": item.metadata.name, "type": item.spec.type}
        for item in services
        if item.spec.type != "ExternalName" and not ready_endpoints.get((item.metadata.namespace, item.metadata.name), False)
    ]
    warning_events = []
    for event in events:
        obj = event.involved_object
        event_time = event.event_time or event.last_timestamp or event.first_timestamp or event.metadata.creation_timestamp
        warning_events.append({
            "namespace": event.metadata.namespace or obj.namespace or "-",
            "reason": event.reason or "Warning",
            "message": event.message or "",
            "resource_kind": obj.kind,
            "resource_name": obj.name,
            "count": event.count or 1,
            "time": event_time.isoformat() if hasattr(event_time, "isoformat") else str(event_time or ""),
        })
    warning_events.sort(key=lambda item: item["time"], reverse=True)

    def status_counts(items: list[Any]) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in items:
            value = item.status.phase or "Unknown"
            result[value] = result.get(value, 0) + 1
        return result

    return {
        "collected_at": now_iso(),
        "cluster": {
            "name": CLUSTER_NAME,
            "kubernetes_version": kubernetes_version,
            "node_count": len(nodes),
            "ready_node_count": sum(1 for node in node_rows if node["ready"]),
            "node_online_rate": round(sum(1 for node in node_rows if node["ready"]) / len(nodes) * 100, 2) if nodes else 0,
            "namespace_count": len(namespaces),
            "runtime_summary": sorted(runtimes),
            "os_summary": sorted(os_images),
        },
        "pod_summary": {"total": len(pods), **phases, "crash_loop_backoff": crash_loop, "image_pull_backoff": image_pull},
        "workload_summary": {
            "deployment_count": len(deployments),
            "statefulset_count": len(statefulsets),
            "daemonset_count": len(daemonsets),
            "abnormal_count": sum(1 for item in workloads if item["unavailable_replicas"] > 0),
        },
        "nodes": node_rows,
        "workloads": workload_groups,
        "problem_pods": problem_pods[:100],
        "top_restarts": sorted(pod_rows, key=lambda item: item["restarts"], reverse=True)[:10],
        "resource_summary": {
            "metrics_available": not bool(metrics_error),
            "metrics_error": metrics_error,
            "top_cpu_nodes": sorted([n for n in node_rows if n.get("cpu_usage_percent") is not None], key=lambda n: n["cpu_usage_percent"], reverse=True)[:10],
            "top_memory_nodes": sorted([n for n in node_rows if n.get("memory_usage_percent") is not None], key=lambda n: n["memory_usage_percent"], reverse=True)[:10],
            "top_cpu_request_nodes": sorted(node_rows, key=lambda n: n.get("cpu_request_percent") or 0, reverse=True)[:10],
            "top_memory_request_nodes": sorted(node_rows, key=lambda n: n.get("memory_request_percent") or 0, reverse=True)[:10],
            "top_cpu_pods": sorted([p for p in pod_rows if "cpu_usage_cores" in p], key=lambda p: p["cpu_usage_cores"], reverse=True)[:10],
            "top_memory_pods": sorted([p for p in pod_rows if "memory_usage_bytes" in p], key=lambda p: p["memory_usage_bytes"], reverse=True)[:10],
            "top_cpu_request_pods": sorted(pod_rows, key=lambda p: p.get("cpu_request_cores") or 0, reverse=True)[:10],
            "top_memory_request_pods": sorted(pod_rows, key=lambda p: p.get("memory_request_bytes") or 0, reverse=True)[:10],
        },
        "storage": {
            "pv_count": len(pvs), "pvc_count": len(pvcs), "pv_status": status_counts(pvs), "pvc_status": status_counts(pvcs),
            "persistent_volumes": [{"name": p.metadata.name, "phase": p.status.phase, "capacity": (p.spec.capacity or {}).get("storage"), "storage_class": p.spec.storage_class_name} for p in pvs],
            "persistent_volume_claims": [{"namespace": p.metadata.namespace, "name": p.metadata.name, "phase": p.status.phase, "storage_class": p.spec.storage_class_name, "volume": p.spec.volume_name} for p in pvcs],
        },
        "network": {
            "service_count": len(services),
            "ingress_count": len(ingresses),
            "services": [{
                "namespace": item.metadata.namespace,
                "name": item.metadata.name,
                "type": item.spec.type,
                "cluster_ip": item.spec.cluster_ip,
                "external_ips": item.spec.external_i_ps or [],
                "has_endpoints": ready_endpoints.get((item.metadata.namespace, item.metadata.name), False),
            } for item in services],
            "services_without_endpoints": no_endpoint[:100],
            "ingresses": [{"namespace": i.metadata.namespace, "name": i.metadata.name, "class": i.spec.ingress_class_name, "hosts": sorted({r.host for r in i.spec.rules or [] if r.host})} for i in ingresses],
        },
        "warning_events": warning_events[:100],
        "errors": errors,
    }


def fingerprint(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part or "") for part in parts).encode()).hexdigest()[:32]


def build_alerts(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}

    def add(level: str, kind: str, source: str, message: str, details: dict[str, Any]) -> None:
        key = fingerprint(kind, source, details.get("reason"), message)
        result[key] = {"fingerprint": key, "level": level, "alert_type": kind, "source": source, "message": message, "details": details}

    for node in snapshot.get("nodes", []):
        if not node.get("ready"):
            add("urgent", "node_not_ready", node["name"], f"节点 {node['name']} 未就绪", node)
    for pod in snapshot.get("problem_pods", []):
        reason = ", ".join(pod.get("waiting_reasons", [])) or pod.get("phase", "Unknown")
        source = f"{pod['namespace']}/{pod['name']}"
        add("urgent" if reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"} else "severe", "pod_unhealthy", source, f"Pod {source} 异常：{reason}", {**pod, "reason": reason})
    for rows in snapshot.get("workloads", {}).values():
        for item in rows:
            if item.get("unavailable_replicas", 0):
                source = f"{item['namespace']}/{item['name']}"
                add("severe", "workload_unavailable", source, f"{item['kind']} {source} 有 {item['unavailable_replicas']} 个异常副本", item)
    for item in snapshot.get("storage", {}).get("persistent_volume_claims", []):
        if item.get("phase") != "Bound":
            source = f"{item['namespace']}/{item['name']}"
            add("severe", "pvc_unbound", source, f"PVC {source} 状态为 {item.get('phase')}", item)
    for item in snapshot.get("network", {}).get("services_without_endpoints", []):
        source = f"{item['namespace']}/{item['name']}"
        add("general", "service_without_endpoint", source, f"Service {source} 没有可用 Endpoint", item)
    for item in snapshot.get("warning_events", [])[:50]:
        source = f"{item['namespace']}/{item.get('resource_kind')}/{item.get('resource_name')}"
        add("severe", "kubernetes_warning", source, f"{item.get('reason')}: {item.get('message')}", item)
    return result


def report_alert_changes(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    for key in current.keys() - previous.keys():
        alert = current[key]
        post("/agent/reports", {"report_type": "alert", "source": alert["source"], "level": alert["level"], "message": alert["message"], "payload": {**alert, "status": "active", "time": now_iso()}})
    for key in previous.keys() - current.keys():
        alert = previous[key]
        post("/agent/reports", {"report_type": "alert", "source": alert["source"], "level": "info", "message": f"已恢复：{alert['message']}", "payload": {**alert, "status": "resolved", "time": now_iso()}})
    return current


def report_logs(clients: dict[str, Any] | None, snapshot: dict[str, Any], previous: set[str]) -> set[str]:
    if clients is None:
        return previous
    core, candidates = clients["core"], {}
    for pod in snapshot.get("problem_pods", []):
        candidates[(pod["namespace"], pod["name"])] = pod.get("containers", [])
    errors: list[str] = []
    for namespace in LOG_NAMESPACES:
        for pod in fetch(errors, f"{namespace} 日志 Pod", core.list_namespaced_pod, namespace=namespace)[:LOG_MAX_PODS]:
            candidates[(namespace, pod.metadata.name)] = [c.name for c in pod.spec.containers or []]
    current = set()
    for (namespace, pod_name), containers in list(candidates.items())[:LOG_MAX_PODS]:
        for container_name in (containers or [None])[:3]:
            try:
                text = core.read_namespaced_pod_log(name=pod_name, namespace=namespace, container=container_name, tail_lines=LOG_TAIL_LINES, since_seconds=max(INTERVAL * 2, 60), timestamps=True, _request_timeout=15)
            except Exception:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                key = fingerprint(namespace, pod_name, container_name, line)
                current.add(key)
                if key in previous:
                    continue
                lower = line.lower()
                level = "error" if any(word in lower for word in ("error", "fatal", "panic", "exception", "failed")) else "warning" if "warn" in lower else "info"
                post("/agent/reports", {"report_type": "log", "source": f"{namespace}/{pod_name}/{container_name or '-'}", "level": level, "message": line[-6000:], "payload": {"fingerprint": key, "cluster": CLUSTER_NAME, "namespace": namespace, "pod": pod_name, "container": container_name, "level": level, "time": now_iso()}})
    seen = previous | current
    return current if len(seen) > 10000 else seen


def main() -> None:
    clients, load_error = load_clients()
    active_alerts, sent_logs = {}, set()
    print(f"monitor-agent started cluster={CLUSTER_NAME} version={AGENT_VERSION}", flush=True)
    while True:
        try:
            snapshot = collect_snapshot(clients)
            cluster = snapshot.get("cluster", {})
            current_alerts = build_alerts(snapshot)
            snapshot["active_alert_fingerprints"] = sorted(current_alerts)
            degraded = bool(load_error) or any(error.startswith(("节点：", "Pod：")) for error in snapshot.get("errors", []))
            post("/agent/heartbeat", {"status": "degraded" if degraded else "online", "agent_version": AGENT_VERSION, "node_count": cluster.get("node_count", 0), "pod_count": snapshot.get("pod_summary", {}).get("total", 0), "message": load_error or ("部分数据采集失败" if degraded else "Agent 正常运行"), "payload": {"cluster": CLUSTER_NAME, "time": now_iso(), "errors": snapshot.get("errors", [])}})
            post("/agent/reports", {"report_type": "metric", "source": CLUSTER_NAME, "level": "warning" if degraded else "info", "message": "集群当前状态已更新", "payload": snapshot})
            active_alerts = report_alert_changes(current_alerts, active_alerts)
            sent_logs = report_logs(clients, snapshot, sent_logs)
        except Exception as exc:
            print(f"agent loop error: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()