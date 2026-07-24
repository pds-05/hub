from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.alert_rules import compare_value
from app.db.session import get_db
from app.models.alert_event import AlertEvent
from app.models.alert_event_activity import AlertEventActivity
from app.models.alert_rule import AlertRule
from app.models.monitor_target import MonitorTarget
from app.models.target_check_result import TargetCheckResult
from app.models.user import User
from app.schemas.alert_event import AlertEventAnalysis, AlertEventEvaluateResponse, AlertEventHandlingStatusRequest, AlertEventRead, AlertEventSummary
from app.schemas.alert_event_activity import AlertEventActionRequest, AlertEventActivityCreate, AlertEventActivityRead
from app.schemas.common import MessageResponse
from app.services.notification_records import create_notification_records_for_event
from app.services.notification_sender import send_notification_record
from app.services.prometheus_client import PrometheusClient, PrometheusUnavailableError, get_prometheus_client

router = APIRouter(prefix="/alert-events", tags=["alert events"])

def build_event_analysis(event: AlertEvent) -> AlertEventAnalysis:
    metric_guides = {
        "cpu_usage_percent": {
            "name": "CPU usage",
            "causes": [
                "Application traffic or background tasks are consuming CPU.",
                "A process may be stuck in a busy loop.",
                "The node has too many workloads scheduled for its CPU capacity.",
            ],
            "impact": [
                "Requests may become slower.",
                "Pods on this node may have delayed scheduling or throttling.",
            ],
            "actions": [
                "Check the top CPU-consuming pods and processes on the node.",
                "Compare current CPU usage with recent traffic changes.",
                "Consider scaling workloads or moving pods away from this node.",
            ],
            "promql": [
                "100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
                "topk(5, rate(container_cpu_usage_seconds_total[5m]))",
            ],
        },
        "memory_usage_percent": {
            "name": "Memory usage",
            "causes": [
                "Applications may be holding too much memory.",
                "Cache or buffers may have grown quickly.",
                "A workload may have a memory leak.",
            ],
            "impact": [
                "Pods may be OOMKilled if memory pressure continues.",
                "Node stability may degrade under high memory pressure.",
            ],
            "actions": [
                "Check memory usage by pod and container.",
                "Review recent deployments for memory behavior changes.",
                "Increase memory limits or scale out affected workloads if needed.",
            ],
            "promql": [
                "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
                "topk(5, container_memory_working_set_bytes)",
            ],
        },
        "disk_usage_percent": {
            "name": "Disk usage",
            "causes": [
                "Logs, images, or application data may be consuming disk space.",
                "Old container images may not have been cleaned up.",
                "A persistent volume may be growing faster than expected.",
            ],
            "impact": [
                "Pods may fail to write data or restart unexpectedly.",
                "Kubernetes may evict pods when disk pressure is high.",
            ],
            "actions": [
                "Check large directories and container logs on the node.",
                "Clean unused images and rotated logs carefully.",
                "Expand storage if the growth is expected.",
            ],
            "promql": [
                "(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100",
                "node_filesystem_avail_bytes",
            ],
        },
        "load1": {
            "name": "System load",
            "causes": [
                "CPU saturation or many runnable processes may increase load.",
                "Disk IO wait can also raise system load.",
            ],
            "impact": [
                "The node may respond slowly under sustained high load.",
                "Workloads may experience latency spikes.",
            ],
            "actions": [
                "Check CPU, IO, and process count on the node.",
                "Correlate load with application traffic and scheduled jobs.",
            ],
            "promql": [
                "node_load1",
                "rate(node_cpu_seconds_total{mode=\"iowait\"}[5m])",
            ],
        },
    }
    guide = metric_guides.get(
        event.metric,
        {
            "name": event.metric,
            "causes": ["The metric crossed the configured alert threshold."],
            "impact": ["The affected target may be unhealthy or degraded."],
            "actions": ["Review the metric trend and related logs before taking action."],
            "promql": [],
        },
    )
    summary = (
        f"{event.instance} triggered {event.level} alert for {guide['name']}: "
        f"current value {event.value} {event.operator} threshold {event.threshold}."
    )
    return AlertEventAnalysis(
        event=event,
        summary=summary,
        severity=event.level,
        possible_causes=guide["causes"],
        impact=guide["impact"],
        recommended_actions=guide["actions"],
        promql_hints=guide["promql"],
    )


def latest_target_check(db: Session, user_id: int, target_id: int) -> TargetCheckResult | None:
    return (
        db.query(TargetCheckResult)
        .filter(TargetCheckResult.user_id == user_id, TargetCheckResult.target_id == target_id)
        .order_by(TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
        .first()
    )


def target_metric_value(rule: AlertRule, check: TargetCheckResult) -> float | None:
    details = check.details or {}
    metric = rule.metric
    if metric == "response_time_ms":
        return float(check.response_time_ms)
    if metric == "status_down":
        return 1.0 if check.status == "down" else 0.0
    if metric == "http_status_code":
        return float(check.status_code) if check.status_code is not None else None
    if metric == "tls_days_remaining":
        value = details.get("tls_days_remaining")
        return float(value) if isinstance(value, (int, float)) else None
    if metric == "dns_failed":
        return 1.0 if details.get("dns_ok") is False else 0.0
    if metric == "tls_failed":
        return 1.0 if details.get("tls_ok") is False else 0.0
    if metric == "keyword_mismatch":
        return 1.0 if details.get("keyword_ok") is False else 0.0
    if metric == "metrics_format_invalid":
        return 1.0 if details.get("metrics_format_ok") is False else 0.0

    exporter_metrics = details.get("exporter_metrics") or {}
    exporter_metric_map = {
        "exporter_up": "up",
        "exporter_metric_count": "metric_count",
        "exporter_series_count": "series_count",
        "mysql_threads_connected": "threads_connected",
        "mysql_questions_total": "questions_total",
        "mysql_connections_total": "connections_total",
        "mysql_slow_queries_total": "slow_queries_total",
        "redis_connected_clients": "connected_clients",
        "redis_used_memory_bytes": "used_memory_bytes",
        "redis_commands_processed_total": "commands_processed_total",
        "redis_keyspace_hits_total": "keyspace_hits_total",
        "redis_keyspace_misses_total": "keyspace_misses_total",
        "postgresql_active_backends": "active_backends",
        "postgresql_transactions_commit_total": "transactions_commit_total",
        "postgresql_transactions_rollback_total": "transactions_rollback_total",
        "postgresql_blocks_hit_total": "blocks_hit_total",
        "postgresql_blocks_read_total": "blocks_read_total",
        "nginx_active_connections": "active_connections",
        "nginx_requests_total": "requests_total",
        "nginx_reading": "reading",
        "nginx_writing": "writing",
        "nginx_waiting": "waiting",
        "mysql_threads_running": "threads_running",
        "mysql_aborted_connects_total": "aborted_connects_total",
        "mysql_innodb_buffer_pool_pages_dirty": "innodb_buffer_pool_pages_dirty",
        "mysql_slave_lag_seconds": "slave_lag_seconds",
        "redis_blocked_clients": "blocked_clients",
        "redis_rejected_connections_total": "rejected_connections_total",
        "redis_evicted_keys_total": "evicted_keys_total",
        "redis_expired_keys_total": "expired_keys_total",
        "postgresql_locks": "locks",
        "postgresql_deadlocks_total": "deadlocks_total",
        "postgresql_conflicts_total": "conflicts_total",
        "postgresql_temp_bytes_total": "temp_bytes_total",
        "mongodb_connections_current": "connections_current",
        "mongodb_connections_available": "connections_available",
        "mongodb_op_counters_query_total": "op_counters_query_total",
        "mongodb_op_counters_insert_total": "op_counters_insert_total",
        "mongodb_op_counters_update_total": "op_counters_update_total",
        "mongodb_op_counters_delete_total": "op_counters_delete_total",
        "mongodb_memory_resident_bytes": "memory_resident_bytes",
        "mongodb_asserts_total": "asserts_total",
        "kafka_brokers": "brokers",
        "kafka_under_replicated_partitions": "under_replicated_partitions",
        "kafka_offline_partitions_count": "offline_partitions_count",
        "kafka_active_controller_count": "active_controller_count",
        "kafka_topic_partition_current_offset": "topic_partition_current_offset",
        "kafka_consumergroup_lag": "consumergroup_lag",
        "rabbitmq_queue_messages": "queue_messages",
        "rabbitmq_queue_messages_ready": "queue_messages_ready",
        "rabbitmq_queue_messages_unacked": "queue_messages_unacked",
        "rabbitmq_connections": "connections",
        "rabbitmq_channels": "channels",
        "rabbitmq_consumers": "consumers",
        "elasticsearch_cluster_health_status": "cluster_health_status",
        "elasticsearch_active_shards": "active_shards",
        "elasticsearch_relocating_shards": "relocating_shards",
        "elasticsearch_initializing_shards": "initializing_shards",
        "elasticsearch_unassigned_shards": "unassigned_shards",
        "elasticsearch_jvm_memory_used_bytes": "jvm_memory_used_bytes",
        "elasticsearch_filesystem_data_available_bytes": "filesystem_data_available_bytes",
        "clickhouse_up": "up",
        "clickhouse_query_total": "query_total",
        "clickhouse_tcp_connections": "tcp_connections",
        "clickhouse_http_connections": "http_connections",
        "clickhouse_memory_tracking": "memory_tracking",
        "clickhouse_delayed_inserts": "delayed_inserts",
        "zookeeper_up": "up",
        "zookeeper_approximate_data_size": "approximate_data_size",
        "zookeeper_num_alive_connections": "num_alive_connections",
        "zookeeper_outstanding_requests": "outstanding_requests",
        "zookeeper_znode_count": "znode_count",
        "zookeeper_watch_count": "watch_count",
        "etcd_server_has_leader": "server_has_leader",
        "etcd_server_leader_changes_seen_total": "server_leader_changes_seen_total",
        "etcd_mvcc_db_total_size_in_bytes": "mvcc_db_total_size_in_bytes",
        "etcd_network_peer_round_trip_time_seconds": "network_peer_round_trip_time_seconds",
        "etcd_disk_backend_commit_duration_seconds": "disk_backend_commit_duration_seconds",
        "jvm_memory_used_bytes": "jvm_memory_used_bytes",
        "jvm_memory_committed_bytes": "jvm_memory_committed_bytes",
        "jvm_threads_current": "jvm_threads_current",
        "jvm_gc_collection_seconds_count": "jvm_gc_collection_seconds_count",
        "jvm_gc_collection_seconds_sum": "jvm_gc_collection_seconds_sum",
        "windows_cpu_usage_percent": "cpu_usage_percent",
        "windows_memory_usage_percent": "memory_usage_percent",
        "windows_logical_disk_free_bytes": "logical_disk_free_bytes",
        "windows_service_state": "service_state",
        "process_cpu_seconds_total": "process_cpu_seconds_total",
        "process_resident_memory_bytes": "process_resident_memory_bytes",
        "process_open_fds": "process_open_fds",
        "process_num_threads": "process_num_threads",
    }
    mapped_metric = exporter_metric_map.get(metric)
    if mapped_metric:
        value = exporter_metrics.get(mapped_metric)
        return float(value) if isinstance(value, (int, float)) else None
    return None

def get_owned_event(event_id: int, db: Session, current_user: User) -> AlertEvent:
    event = db.query(AlertEvent).filter(AlertEvent.id == event_id, AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None)).first()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert event not found")
    return event


def create_event_activity(db: Session, event: AlertEvent, current_user: User, action: str, note: str | None = None) -> AlertEventActivity:
    activity = AlertEventActivity(
        user_id=current_user.id,
        event_id=event.id,
        action=action,
        note=note,
        actor=current_user.username,
    )
    db.add(activity)
    return activity


@router.get("", response_model=list[AlertEventRead])
def list_alert_events(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|resolved)$"),
    level: str | None = Query(default=None, pattern="^(general|severe|urgent)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertEvent]:
    query = db.query(AlertEvent).filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None))
    if status_filter:
        query = query.filter(AlertEvent.status == status_filter)
    if level:
        query = query.filter(AlertEvent.level == level)
    return list(query.order_by(AlertEvent.last_triggered_at.desc()).limit(limit).all())


@router.get("/active", response_model=list[AlertEventRead])
def list_active_alert_events(
    level: str | None = Query(default=None, pattern="^(general|severe|urgent)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertEvent]:
    query = db.query(AlertEvent).filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None), AlertEvent.status == "active")
    if level:
        query = query.filter(AlertEvent.level == level)
    return list(query.order_by(AlertEvent.last_triggered_at.desc()).limit(limit).all())

@router.get("/summary", response_model=AlertEventSummary)
def get_alert_events_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEventSummary:
    events = list(db.query(AlertEvent).filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None)).all())
    levels = ("general", "severe", "urgent")
    handling_statuses = ("new", "acknowledged", "investigating", "mitigating", "watching", "resolved", "closed")
    active_events = [event for event in events if event.status == "active"]
    resolved_events = [event for event in events if event.status == "resolved"]
    recent_events = list(
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None))
        .order_by(AlertEvent.last_triggered_at.desc())
        .limit(10)
        .all()
    )

    return AlertEventSummary(
        total_count=len(events),
        active_count=len(active_events),
        resolved_count=len(resolved_events),
        unacknowledged_active_count=len([event for event in active_events if not event.acknowledged]),
        handling_by_status={item: len([event for event in events if event.handling_status == item]) for item in handling_statuses},
        active_by_level={level: len([event for event in active_events if event.level == level]) for level in levels},
        total_by_level={level: len([event for event in events if event.level == level]) for level in levels},
        recent_events=recent_events,
    )

@router.post("/evaluate/nodes", response_model=AlertEventEvaluateResponse)
async def evaluate_node_alert_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    prometheus: PrometheusClient = Depends(get_prometheus_client),
) -> AlertEventEvaluateResponse:
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.user_id == current_user.id, AlertRule.deleted_at.is_(None), AlertRule.enabled.is_(True), AlertRule.scope == "node")
        .all()
    )
    try:
        nodes = await prometheus.all_node_metrics()
    except PrometheusUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    triggered_keys: set[tuple[int, str, str]] = set()
    changed_events: list[AlertEvent] = []
    newly_triggered_events: list[AlertEvent] = []
    resolved_events_for_notification: list[AlertEvent] = []
    triggered_count = 0

    for node in nodes:
        instance = node["instance"]
        metrics = node.get("metrics", {})
        for rule in rules:
            value = metrics.get(rule.metric)
            if not isinstance(value, (int, float)):
                continue
            if not compare_value(float(value), rule.operator, rule.threshold):
                continue

            triggered_count += 1
            key = (rule.id, instance, rule.metric)
            triggered_keys.add(key)
            message = f"{instance} {rule.metric} {value} {rule.operator} {rule.threshold}"
            event = (
                db.query(AlertEvent)
                .filter(
                    AlertEvent.user_id == current_user.id,
                    AlertEvent.deleted_at.is_(None),
                    AlertEvent.rule_id == rule.id,
                    AlertEvent.instance == instance,
                    AlertEvent.metric == rule.metric,
                    AlertEvent.status == "active",
                )
                .first()
            )
            if event is None:
                event = AlertEvent(
                    user_id=current_user.id,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    scope=rule.scope,
                    instance=instance,
                    level=rule.level,
                    metric=rule.metric,
                    operator=rule.operator,
                    value=float(value),
                    threshold=rule.threshold,
                    status="active",
                    handling_status="new",
                    message=message,
                    trigger_count=1,
                    first_triggered_at=now,
                    last_triggered_at=now,
                )
                db.add(event)
                newly_triggered_events.append(event)
            else:
                event.rule_name = rule.name
                event.level = rule.level
                event.operator = rule.operator
                event.value = float(value)
                event.threshold = rule.threshold
                event.message = message
                event.trigger_count += 1
                event.last_triggered_at = now
            changed_events.append(event)

    active_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None), AlertEvent.status == "active", AlertEvent.scope == "node")
        .all()
    )
    resolved_count = 0
    enabled_rule_ids = {rule.id for rule in rules}
    for event in active_events:
        key = (event.rule_id, event.instance, event.metric)
        if event.rule_id in enabled_rule_ids and key in triggered_keys:
            continue
        event.status = "resolved"
        event.handling_status = "resolved"
        event.resolved_at = now
        event.updated_at = now
        resolved_count += 1
        resolved_events_for_notification.append(event)
        changed_events.append(event)

    db.commit()
    for event in changed_events:
        db.refresh(event)

    notification_events = []
    for event in newly_triggered_events:
        notification_events.extend(create_notification_records_for_event(db, event, "triggered"))
    for event in resolved_events_for_notification:
        notification_events.extend(create_notification_records_for_event(db, event, "resolved"))
    if notification_events:
        db.commit()
        for record in notification_events:
            await send_notification_record(db, record)

    current_active_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None), AlertEvent.status == "active", AlertEvent.scope == "node")
        .order_by(AlertEvent.last_triggered_at.desc())
        .all()
    )
    return AlertEventEvaluateResponse(
        active_count=len(current_active_events),
        triggered_count=triggered_count,
        resolved_count=resolved_count,
        events=current_active_events,
    )


@router.post("/evaluate/targets", response_model=AlertEventEvaluateResponse)
async def evaluate_target_alert_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEventEvaluateResponse:
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.user_id == current_user.id, AlertRule.deleted_at.is_(None), AlertRule.enabled.is_(True), AlertRule.scope == "target")
        .all()
    )
    targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None)).all()
    now = datetime.now(timezone.utc)
    triggered_keys: set[tuple[int, str, str]] = set()
    changed_events: list[AlertEvent] = []
    newly_triggered_events: list[AlertEvent] = []
    resolved_events_for_notification: list[AlertEvent] = []
    triggered_count = 0

    for target in targets:
        check = latest_target_check(db, current_user.id, target.id)
        if check is None:
            continue
        instance = target.endpoint
        for rule in rules:
            value = target_metric_value(rule, check)
            if value is None or not compare_value(value, rule.operator, rule.threshold):
                continue
            triggered_count += 1
            key = (rule.id, instance, rule.metric)
            triggered_keys.add(key)
            message = f"{target.name} {rule.metric} {value} {rule.operator} {rule.threshold}: {check.message}"
            event = (
                db.query(AlertEvent)
                .filter(
                    AlertEvent.user_id == current_user.id,
                    AlertEvent.deleted_at.is_(None),
                    AlertEvent.rule_id == rule.id,
                    AlertEvent.instance == instance,
                    AlertEvent.metric == rule.metric,
                    AlertEvent.status == "active",
                )
                .first()
            )
            if event is None:
                event = AlertEvent(
                    user_id=current_user.id,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    scope=rule.scope,
                    instance=instance,
                    level=rule.level,
                    metric=rule.metric,
                    operator=rule.operator,
                    value=float(value),
                    threshold=rule.threshold,
                    status="active",
                    handling_status="new",
                    message=message,
                    trigger_count=1,
                    first_triggered_at=now,
                    last_triggered_at=now,
                )
                db.add(event)
                newly_triggered_events.append(event)
            else:
                event.rule_name = rule.name
                event.level = rule.level
                event.operator = rule.operator
                event.value = float(value)
                event.threshold = rule.threshold
                event.message = message
                event.trigger_count += 1
                event.last_triggered_at = now
            changed_events.append(event)

    active_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None), AlertEvent.status == "active", AlertEvent.scope == "target")
        .all()
    )
    resolved_count = 0
    enabled_rule_ids = {rule.id for rule in rules}
    for event in active_events:
        key = (event.rule_id, event.instance, event.metric)
        if event.rule_id in enabled_rule_ids and key in triggered_keys:
            continue
        event.status = "resolved"
        event.handling_status = "resolved"
        event.resolved_at = now
        event.updated_at = now
        resolved_count += 1
        resolved_events_for_notification.append(event)
        changed_events.append(event)

    db.commit()
    for event in changed_events:
        db.refresh(event)

    notification_events = []
    for event in newly_triggered_events:
        notification_events.extend(create_notification_records_for_event(db, event, "triggered"))
    for event in resolved_events_for_notification:
        notification_events.extend(create_notification_records_for_event(db, event, "resolved"))
    if notification_events:
        db.commit()
        for record in notification_events:
            await send_notification_record(db, record)

    current_active_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.user_id == current_user.id, AlertEvent.deleted_at.is_(None), AlertEvent.status == "active", AlertEvent.scope == "target")
        .order_by(AlertEvent.last_triggered_at.desc())
        .all()
    )
    return AlertEventEvaluateResponse(
        active_count=len(current_active_events),
        triggered_count=triggered_count,
        resolved_count=resolved_count,
        events=current_active_events,
    )

@router.get("/{event_id}/analysis", response_model=AlertEventAnalysis)
def analyze_alert_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEventAnalysis:
    event = get_owned_event(event_id, db, current_user)
    return build_event_analysis(event)

@router.get("/{event_id}/activities", response_model=list[AlertEventActivityRead])
def list_alert_event_activities(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertEventActivity]:
    event = get_owned_event(event_id, db, current_user)
    return list(
        db.query(AlertEventActivity)
        .filter(AlertEventActivity.user_id == current_user.id, AlertEventActivity.event_id == event.id)
        .order_by(AlertEventActivity.created_at.desc(), AlertEventActivity.id.desc())
        .all()
    )


@router.post("/{event_id}/activities", response_model=AlertEventActivityRead)
def create_alert_event_activity(
    event_id: int,
    payload: AlertEventActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEventActivity:
    event = get_owned_event(event_id, db, current_user)
    activity = create_event_activity(db, event, current_user, payload.action, payload.note)
    db.commit()
    db.refresh(activity)
    return activity


@router.post("/{event_id}/ack", response_model=AlertEventRead)
def acknowledge_alert_event(
    event_id: int,
    payload: AlertEventActionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEvent:
    event = get_owned_event(event_id, db, current_user)
    event.acknowledged = True
    event.handling_status = "acknowledged"
    event.acknowledged_at = datetime.now(timezone.utc)
    create_event_activity(db, event, current_user, "ack", payload.note if payload else None)
    db.commit()
    db.refresh(event)
    return event


@router.post("/{event_id}/resolve", response_model=AlertEventRead)
def resolve_alert_event(
    event_id: int,
    payload: AlertEventActionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEvent:
    event = get_owned_event(event_id, db, current_user)
    event.status = "resolved"
    event.handling_status = "resolved"
    event.resolved_at = datetime.now(timezone.utc)
    create_event_activity(db, event, current_user, "resolve", payload.note if payload else None)
    db.commit()
    db.refresh(event)
    return event



@router.post("/{event_id}/handling-status", response_model=AlertEventRead)
def update_alert_event_handling_status(
    event_id: int,
    payload: AlertEventHandlingStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertEvent:
    event = get_owned_event(event_id, db, current_user)
    previous_status = event.handling_status
    event.handling_status = payload.handling_status
    if payload.handling_status == "acknowledged":
        event.acknowledged = True
        event.acknowledged_at = event.acknowledged_at or datetime.now(timezone.utc)
    if payload.handling_status in {"resolved", "closed"}:
        event.status = "resolved"
        event.handling_status = "resolved"
        event.resolved_at = event.resolved_at or datetime.now(timezone.utc)
    note = payload.note or f"Handling status changed from {previous_status} to {payload.handling_status}."
    create_event_activity(db, event, current_user, "status", note)
    db.commit()
    db.refresh(event)
    return event

@router.delete("/{event_id}", response_model=MessageResponse)
def delete_alert_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    event = get_owned_event(event_id, db, current_user)
    db.delete(event)
    db.commit()
    return MessageResponse(message="Alert event deleted")
















