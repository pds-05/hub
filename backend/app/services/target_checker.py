from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models.monitor_target import MonitorTarget

MetricSamples = dict[str, list[tuple[dict[str, str], float]]]


def parse_metric_labels(label_text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in label_text.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        labels[key.strip()] = value.strip().strip('"')
    return labels


def parse_prometheus_samples(text: str) -> MetricSamples:
    samples: MetricSamples = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name_and_labels, _, raw_value = line.rpartition(" ")
        if not name_and_labels or not raw_value:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if "{" in name_and_labels and name_and_labels.endswith("}"):
            name, label_text = name_and_labels.split("{", 1)
            labels = parse_metric_labels(label_text[:-1])
        else:
            name = name_and_labels
            labels = {}
        samples.setdefault(name, []).append((labels, value))
    return samples


def first_metric_value(samples: MetricSamples, name: str) -> float | None:
    values = samples.get(name) or []
    return values[0][1] if values else None


def first_existing_metric(samples: MetricSamples, names: list[str]) -> float | None:
    for name in names:
        value = first_metric_value(samples, name)
        if value is not None:
            return value
    return None


def sum_metric(samples: MetricSamples, name: str) -> float | None:
    values = samples.get(name) or []
    if not values:
        return None
    return round(sum(value for _, value in values), 2)



def max_metric(samples: MetricSamples, name: str) -> float | None:
    values = samples.get(name) or []
    if not values:
        return None
    return round(max(value for _, value in values), 2)


def first_existing_metric_by_names(samples: MetricSamples, names: list[str]) -> float | None:
    for name in names:
        value = first_metric_value(samples, name)
        if value is not None:
            return value
    return None


def sum_existing_metric(samples: MetricSamples, names: list[str]) -> float | None:
    for name in names:
        value = sum_metric(samples, name)
        if value is not None:
            return value
    return None


def max_existing_metric(samples: MetricSamples, names: list[str]) -> float | None:
    for name in names:
        value = max_metric(samples, name)
        if value is not None:
            return value
    return None
def parse_node_exporter_metrics(samples: MetricSamples) -> dict[str, float | None]:
    cpu_total = 0.0
    cpu_idle = 0.0
    for labels, value in samples.get("node_cpu_seconds_total", []):
        cpu_total += value
        if labels.get("mode") == "idle":
            cpu_idle += value
    cpu_usage = round((1 - cpu_idle / cpu_total) * 100, 2) if cpu_total > 0 else None

    memory_total = first_metric_value(samples, "node_memory_MemTotal_bytes")
    memory_available = first_metric_value(samples, "node_memory_MemAvailable_bytes")
    memory_usage = None
    if memory_total and memory_available is not None:
        memory_usage = round((1 - memory_available / memory_total) * 100, 2)

    disk_size = None
    disk_available = None
    for labels, value in samples.get("node_filesystem_size_bytes", []):
        if labels.get("mountpoint") == "/" and labels.get("fstype") not in {"tmpfs", "overlay"}:
            disk_size = value
            break
    for labels, value in samples.get("node_filesystem_avail_bytes", []):
        if labels.get("mountpoint") == "/" and labels.get("fstype") not in {"tmpfs", "overlay"}:
            disk_available = value
            break
    disk_usage = None
    if disk_size and disk_available is not None:
        disk_usage = round((1 - disk_available / disk_size) * 100, 2)

    return {
        "cpu_usage_percent": cpu_usage,
        "memory_usage_percent": memory_usage,
        "disk_usage_percent": disk_usage,
        "load1": first_metric_value(samples, "node_load1"),
    }


def parse_exporter_metrics(text: str, exporter_kind: str | None) -> dict[str, Any]:
    samples = parse_prometheus_samples(text)
    kind = exporter_kind or "custom"
    common = {
        "kind": kind,
        "series_count": sum(len(values) for values in samples.values()),
        "metric_count": len(samples),
        "sample_metric_names": sorted(samples.keys())[:12],
    }

    if kind == "node":
        return {**common, **parse_node_exporter_metrics(samples)}
    if kind == "mysql":
        return {
            **common,
            "up": first_existing_metric(samples, ["mysql_up", "up"]),
            "threads_connected": first_metric_value(samples, "mysql_global_status_threads_connected"),
            "questions_total": first_metric_value(samples, "mysql_global_status_questions"),
            "connections_total": first_metric_value(samples, "mysql_global_status_connections"),
            "slow_queries_total": first_metric_value(samples, "mysql_global_status_slow_queries"),
            "uptime_seconds": first_metric_value(samples, "mysql_global_status_uptime"),
        }
    if kind == "nginx":
        return {
            **common,
            "up": first_existing_metric(samples, ["nginx_up", "up"]),
            "active_connections": first_metric_value(samples, "nginx_connections_active"),
            "requests_total": first_existing_metric(samples, ["nginx_http_requests_total", "nginx_requests_total"]),
            "reading": first_metric_value(samples, "nginx_connections_reading"),
            "writing": first_metric_value(samples, "nginx_connections_writing"),
            "waiting": first_metric_value(samples, "nginx_connections_waiting"),
        }
    if kind == "redis":
        return {
            **common,
            "up": first_existing_metric(samples, ["redis_up", "up"]),
            "connected_clients": first_metric_value(samples, "redis_connected_clients"),
            "used_memory_bytes": first_metric_value(samples, "redis_memory_used_bytes"),
            "commands_processed_total": first_metric_value(samples, "redis_commands_processed_total"),
            "keyspace_hits_total": first_metric_value(samples, "redis_keyspace_hits_total"),
            "keyspace_misses_total": first_metric_value(samples, "redis_keyspace_misses_total"),
        }
    if kind == "postgresql":
        return {
            **common,
            "up": first_existing_metric(samples, ["pg_up", "up"]),
            "active_backends": sum_metric(samples, "pg_stat_database_numbackends"),
            "locks": sum_existing_metric(samples, ["pg_locks_count", "pg_stat_activity_count"]),
            "deadlocks_total": sum_metric(samples, "pg_stat_database_deadlocks"),
            "transactions_commit_total": sum_metric(samples, "pg_stat_database_xact_commit"),
            "transactions_rollback_total": sum_metric(samples, "pg_stat_database_xact_rollback"),
            "blocks_hit_total": sum_metric(samples, "pg_stat_database_blks_hit"),
            "blocks_read_total": sum_metric(samples, "pg_stat_database_blks_read"),
            "conflicts_total": sum_metric(samples, "pg_stat_database_conflicts"),
            "temp_bytes_total": sum_metric(samples, "pg_stat_database_temp_bytes"),
        }

    generic_metric_map = {
        "mongodb": {
            "up": ["mongodb_up", "up"],
            "connections_current": ["mongodb_connections_current"],
            "connections_available": ["mongodb_connections_available"],
            "op_counters_query_total": ["mongodb_op_counters_total", "mongodb_ss_opcounters_query"],
            "op_counters_insert_total": ["mongodb_ss_opcounters_insert"],
            "op_counters_update_total": ["mongodb_ss_opcounters_update"],
            "op_counters_delete_total": ["mongodb_ss_opcounters_delete"],
            "memory_resident_bytes": ["mongodb_memory_resident_bytes", "mongodb_ss_mem_resident"],
            "asserts_total": ["mongodb_asserts_total", "mongodb_ss_asserts_total"],
        },
        "kafka": {
            "up": ["kafka_up", "up"],
            "brokers": ["kafka_brokers", "kafka_cluster_brokers"],
            "under_replicated_partitions": ["kafka_topic_partition_under_replicated_partition", "kafka_server_replicamanager_underreplicatedpartitions"],
            "offline_partitions_count": ["kafka_controller_kafkacontroller_offlinepartitionscount"],
            "active_controller_count": ["kafka_controller_kafkacontroller_activecontrollercount"],
            "topic_partition_current_offset": ["kafka_topic_partition_current_offset"],
            "consumergroup_lag": ["kafka_consumergroup_lag", "kafka_consumergroup_current_offset_sum"],
        },
        "rabbitmq": {
            "up": ["rabbitmq_up", "up"],
            "queue_messages": ["rabbitmq_queue_messages"],
            "queue_messages_ready": ["rabbitmq_queue_messages_ready"],
            "queue_messages_unacked": ["rabbitmq_queue_messages_unacked"],
            "connections": ["rabbitmq_connections"],
            "channels": ["rabbitmq_channels"],
            "consumers": ["rabbitmq_queue_consumers", "rabbitmq_consumers"],
        },
        "elasticsearch": {
            "up": ["elasticsearch_up", "up"],
            "cluster_health_status": ["elasticsearch_cluster_health_status"],
            "active_shards": ["elasticsearch_cluster_health_active_shards"],
            "relocating_shards": ["elasticsearch_cluster_health_relocating_shards"],
            "initializing_shards": ["elasticsearch_cluster_health_initializing_shards"],
            "unassigned_shards": ["elasticsearch_cluster_health_unassigned_shards"],
            "jvm_memory_used_bytes": ["elasticsearch_jvm_memory_used_bytes"],
            "filesystem_data_available_bytes": ["elasticsearch_filesystem_data_available_bytes"],
        },
        "clickhouse": {
            "up": ["clickhouse_up", "up"],
            "query_total": ["ClickHouseProfileEvents_Query", "clickhouse_query_total"],
            "tcp_connections": ["ClickHouseMetrics_TCPConnection", "clickhouse_tcp_connections"],
            "http_connections": ["ClickHouseMetrics_HTTPConnection", "clickhouse_http_connections"],
            "memory_tracking": ["ClickHouseMetrics_MemoryTracking", "clickhouse_memory_tracking"],
            "delayed_inserts": ["ClickHouseMetrics_DelayedInserts", "clickhouse_delayed_inserts"],
        },
        "zookeeper": {
            "up": ["zookeeper_up", "up"],
            "approximate_data_size": ["zookeeper_approximate_data_size"],
            "num_alive_connections": ["zookeeper_num_alive_connections"],
            "outstanding_requests": ["zookeeper_outstanding_requests"],
            "znode_count": ["zookeeper_znode_count"],
            "watch_count": ["zookeeper_watch_count"],
        },
        "etcd": {
            "up": ["etcd_up", "up"],
            "server_has_leader": ["etcd_server_has_leader"],
            "server_leader_changes_seen_total": ["etcd_server_leader_changes_seen_total"],
            "mvcc_db_total_size_in_bytes": ["etcd_mvcc_db_total_size_in_bytes"],
            "network_peer_round_trip_time_seconds": ["etcd_network_peer_round_trip_time_seconds"],
            "disk_backend_commit_duration_seconds": ["etcd_disk_backend_commit_duration_seconds"],
        },
        "jmx": {
            "up": ["jmx_scrape_error"],
            "jvm_memory_used_bytes": ["jvm_memory_used_bytes"],
            "jvm_memory_committed_bytes": ["jvm_memory_committed_bytes"],
            "jvm_threads_current": ["jvm_threads_current"],
            "jvm_gc_collection_seconds_count": ["jvm_gc_collection_seconds_count"],
            "jvm_gc_collection_seconds_sum": ["jvm_gc_collection_seconds_sum"],
        },
        "windows": {
            "up": ["windows_exporter_build_info", "up"],
            "cpu_usage_percent": ["windows_cpu_time_total"],
            "memory_usage_percent": ["windows_cs_physical_memory_bytes"],
            "logical_disk_free_bytes": ["windows_logical_disk_free_bytes"],
            "service_state": ["windows_service_state"],
        },
        "process": {
            "up": ["namedprocess_namegroup_num_procs", "up"],
            "process_cpu_seconds_total": ["namedprocess_namegroup_cpu_seconds_total", "process_cpu_seconds_total"],
            "process_resident_memory_bytes": ["namedprocess_namegroup_memory_bytes", "process_resident_memory_bytes"],
            "process_open_fds": ["process_open_fds"],
            "process_num_threads": ["namedprocess_namegroup_num_threads", "process_num_threads"],
        },
    }
    metric_names = generic_metric_map.get(kind)
    if metric_names:
        parsed = {**common}
        for output_name, names in metric_names.items():
            parsed[output_name] = sum_existing_metric(samples, names)
        return parsed
    return common


# Kept for existing callers/tests that expect node metrics directly.
def parse_prometheus_text_metrics(text: str) -> dict[str, float | None]:
    return parse_node_exporter_metrics(parse_prometheus_samples(text))


@dataclass
class TargetCheckResult:
    status: str
    response_time_ms: int
    message: str
    status_code: int | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "response_time_ms": self.response_time_ms,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details,
        }


async def check_monitor_target(target: MonitorTarget) -> TargetCheckResult:
    if target.target_type == "website":
        return await check_http_target(target.endpoint, expected_keyword=target.expected_keyword)
    if target.target_type == "exporter":
        return await check_http_target(target.endpoint, expect_metrics=True, exporter_kind=target.exporter_kind)
    if target.target_type == "port":
        return check_tcp_target(target.endpoint)
    return TargetCheckResult(status="down", response_time_ms=0, message="Unsupported target type")


async def check_http_target(
    endpoint: str,
    expect_metrics: bool = False,
    expected_keyword: str | None = None,
    exporter_kind: str | None = None,
) -> TargetCheckResult:
    start = time.perf_counter()
    details: dict[str, Any] = {
        "dns_ok": False,
        "resolved_ips": [],
        "tls_ok": None,
        "tls_days_remaining": None,
        "keyword_ok": None,
        "metrics_format_ok": None,
    }
    if expect_metrics:
        details["exporter_kind"] = exporter_kind or "custom"
    try:
        parsed = urlparse(endpoint)
        if not parsed.scheme or not parsed.hostname:
            return TargetCheckResult(status="down", response_time_ms=0, message="Endpoint must be a valid URL", details=details)

        details.update(resolve_dns(parsed.hostname))
        if parsed.scheme == "https":
            details.update(check_tls_certificate(parsed.hostname, parsed.port or 443))

        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(endpoint)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if expected_keyword:
            details["keyword_ok"] = expected_keyword in response.text
            details["expected_keyword"] = expected_keyword
        if expect_metrics:
            details["metrics_format_ok"] = "# HELP" in response.text or "# TYPE" in response.text
            if details["metrics_format_ok"]:
                exporter_metrics = parse_exporter_metrics(response.text, exporter_kind)
                details["exporter_metrics"] = exporter_metrics
                if (exporter_kind or "node") == "node":
                    details["node_metrics"] = {
                        key: exporter_metrics.get(key)
                        for key in ["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent", "load1"]
                    }

        failed_reasons: list[str] = []
        if not details["dns_ok"]:
            failed_reasons.append("DNS resolution failed")
        if response.status_code >= 500:
            failed_reasons.append(f"HTTP status is {response.status_code}")
        if expected_keyword and not details["keyword_ok"]:
            failed_reasons.append("Expected keyword not found")
        if expect_metrics and not details["metrics_format_ok"]:
            failed_reasons.append("Endpoint does not look like Prometheus metrics")
        if details["tls_ok"] is False:
            failed_reasons.append("TLS certificate check failed")

        if failed_reasons:
            return TargetCheckResult(
                status="down",
                response_time_ms=elapsed_ms,
                status_code=response.status_code,
                message="; ".join(failed_reasons),
                details=details,
            )
        return TargetCheckResult(
            status="up",
            response_time_ms=elapsed_ms,
            status_code=response.status_code,
            message="HTTP target is reachable",
            details=details,
        )
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return TargetCheckResult(status="down", response_time_ms=elapsed_ms, message=str(exc), details=details)


def check_tcp_target(endpoint: str) -> TargetCheckResult:
    start = time.perf_counter()
    try:
        host, port = parse_host_port(endpoint)
        dns_details = resolve_dns(host)
        with socket.create_connection((host, port), timeout=5):
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return TargetCheckResult(
                status="up",
                response_time_ms=elapsed_ms,
                message="TCP port is reachable",
                details={"host": host, "port": port, **dns_details},
            )
    except OSError as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return TargetCheckResult(status="down", response_time_ms=elapsed_ms, message=str(exc))
    except ValueError as exc:
        return TargetCheckResult(status="down", response_time_ms=0, message=str(exc))


def resolve_dns(hostname: str) -> dict[str, Any]:
    try:
        addresses = sorted({info[4][0] for info in socket.getaddrinfo(hostname, None)})
        return {"dns_ok": True, "resolved_ips": addresses}
    except socket.gaierror as exc:
        return {"dns_ok": False, "resolved_ips": [], "dns_error": str(exc)}


def check_tls_certificate(hostname: str, port: int) -> dict[str, Any]:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return {"tls_ok": False, "tls_error": "Certificate has no notAfter field"}
        expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds() // 86400)
        return {"tls_ok": days_remaining >= 0, "tls_days_remaining": days_remaining, "tls_expires_at": expires_at.isoformat()}
    except (OSError, ssl.SSLError, ValueError) as exc:
        return {"tls_ok": False, "tls_error": str(exc)}


def parse_host_port(endpoint: str) -> tuple[str, int]:
    parsed = urlparse(endpoint if "://" in endpoint else f"tcp://{endpoint}")
    if not parsed.hostname or not parsed.port:
        raise ValueError("Endpoint must include host and port, for example 1.2.3.4:9100")
    return parsed.hostname, parsed.port
