from datetime import datetime

from pydantic import BaseModel, Field


ALERT_RULE_METRIC_PATTERN = "^(" + "|".join(["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent", "load1", "response_time_ms", "tls_days_remaining", "status_down", "http_status_code", "dns_failed", "tls_failed", "keyword_mismatch", "metrics_format_invalid", "exporter_up", "exporter_metric_count", "exporter_series_count", "mysql_threads_connected", "mysql_threads_running", "mysql_questions_total", "mysql_connections_total", "mysql_slow_queries_total", "mysql_aborted_connects_total", "mysql_innodb_buffer_pool_pages_dirty", "mysql_slave_lag_seconds", "redis_connected_clients", "redis_blocked_clients", "redis_rejected_connections_total", "redis_used_memory_bytes", "redis_commands_processed_total", "redis_keyspace_hits_total", "redis_keyspace_misses_total", "redis_evicted_keys_total", "redis_expired_keys_total", "postgresql_active_backends", "postgresql_locks", "postgresql_deadlocks_total", "postgresql_transactions_commit_total", "postgresql_transactions_rollback_total", "postgresql_blocks_hit_total", "postgresql_blocks_read_total", "postgresql_conflicts_total", "postgresql_temp_bytes_total", "nginx_active_connections", "nginx_requests_total", "nginx_reading", "nginx_writing", "nginx_waiting", "mongodb_connections_current", "mongodb_connections_available", "mongodb_op_counters_query_total", "mongodb_op_counters_insert_total", "mongodb_op_counters_update_total", "mongodb_op_counters_delete_total", "mongodb_memory_resident_bytes", "mongodb_asserts_total", "kafka_brokers", "kafka_under_replicated_partitions", "kafka_offline_partitions_count", "kafka_active_controller_count", "kafka_topic_partition_current_offset", "kafka_consumergroup_lag", "rabbitmq_queue_messages", "rabbitmq_queue_messages_ready", "rabbitmq_queue_messages_unacked", "rabbitmq_connections", "rabbitmq_channels", "rabbitmq_consumers", "elasticsearch_cluster_health_status", "elasticsearch_active_shards", "elasticsearch_relocating_shards", "elasticsearch_initializing_shards", "elasticsearch_unassigned_shards", "elasticsearch_jvm_memory_used_bytes", "elasticsearch_filesystem_data_available_bytes", "clickhouse_up", "clickhouse_query_total", "clickhouse_tcp_connections", "clickhouse_http_connections", "clickhouse_memory_tracking", "clickhouse_delayed_inserts", "zookeeper_up", "zookeeper_approximate_data_size", "zookeeper_num_alive_connections", "zookeeper_outstanding_requests", "zookeeper_znode_count", "zookeeper_watch_count", "etcd_server_has_leader", "etcd_server_leader_changes_seen_total", "etcd_mvcc_db_total_size_in_bytes", "etcd_network_peer_round_trip_time_seconds", "etcd_disk_backend_commit_duration_seconds", "jvm_memory_used_bytes", "jvm_memory_committed_bytes", "jvm_threads_current", "jvm_gc_collection_seconds_count", "jvm_gc_collection_seconds_sum", "windows_cpu_usage_percent", "windows_memory_usage_percent", "windows_logical_disk_free_bytes", "windows_service_state", "process_cpu_seconds_total", "process_resident_memory_bytes", "process_open_fds", "process_num_threads"]) + ")$"


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: str = Field(default="node", pattern="^(node|target)$")
    metric: str = Field(pattern=ALERT_RULE_METRIC_PATTERN)
    operator: str = Field(default=">=", pattern="^(>=|>|<=|<|==)$")
    threshold: float
    level: str = Field(pattern="^(general|severe|urgent)$")
    enabled: bool = True
    description: str | None = None


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    scope: str | None = Field(default=None, pattern="^(node|target)$")
    metric: str | None = Field(default=None, pattern=ALERT_RULE_METRIC_PATTERN)
    operator: str | None = Field(default=None, pattern="^(>=|>|<=|<|==)$")
    threshold: float | None = None
    level: str | None = Field(default=None, pattern="^(general|severe|urgent)$")
    enabled: bool | None = None
    description: str | None = None


class AlertRuleRead(BaseModel):
    id: int
    user_id: int
    name: str
    scope: str
    metric: str
    operator: str
    threshold: float
    level: str
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertEvaluationRead(BaseModel):
    rule_id: int
    rule_name: str
    instance: str
    level: str
    metric: str
    operator: str
    value: float
    threshold: float
    message: str
