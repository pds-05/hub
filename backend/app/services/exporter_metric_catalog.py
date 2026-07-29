from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExporterMetricDefinition:
    key: str
    label: str
    unit: str
    expressions: tuple[str, ...]


def metric(key: str, label: str, unit: str, *expressions: str) -> ExporterMetricDefinition:
    return ExporterMetricDefinition(key=key, label=label, unit=unit, expressions=expressions)


def total(name: str) -> str:
    return f"sum({name}{{$selector}})"


def maximum(name: str) -> str:
    return f"max({name}{{$selector}})"


EXPORTER_METRICS: dict[str, tuple[ExporterMetricDefinition, ...]] = {
    "node": (
        metric("cpu_usage_percent", "CPU 使用率", "%", '100 - avg(rate(node_cpu_seconds_total{$selector,mode="idle"}[5m])) * 100'),
        metric("memory_usage_percent", "内存使用率", "%", '(1 - sum(node_memory_MemAvailable_bytes{$selector}) / sum(node_memory_MemTotal_bytes{$selector})) * 100'),
        metric("disk_usage_percent", "根磁盘使用率", "%", '(1 - sum(node_filesystem_avail_bytes{$selector,mountpoint="/",fstype!~"tmpfs|overlay"}) / sum(node_filesystem_size_bytes{$selector,mountpoint="/",fstype!~"tmpfs|overlay"})) * 100'),
        metric("load1", "1 分钟负载", "", maximum("node_load1")),
    ),
    "mysql": (
        metric("threads_connected", "当前连接数", "", maximum("mysql_global_status_threads_connected")),
        metric("threads_running", "运行线程数", "", maximum("mysql_global_status_threads_running")),
        metric("questions_total", "查询总数", "", total("mysql_global_status_questions")),
        metric("connections_total", "连接总数", "", total("mysql_global_status_connections")),
        metric("slow_queries_total", "慢查询总数", "", total("mysql_global_status_slow_queries")),
        metric("aborted_connects_total", "失败连接总数", "", total("mysql_global_status_aborted_connects")),
        metric("innodb_buffer_pool_pages_dirty", "InnoDB 脏页", "", total("mysql_global_status_innodb_buffer_pool_pages_dirty")),
        metric("slave_lag_seconds", "复制延迟", "s", maximum("mysql_slave_status_seconds_behind_master"), maximum("mysql_slave_lag_seconds")),
    ),
    "nginx": (
        metric("active_connections", "活跃连接", "", total("nginx_connections_active")),
        metric("requests_total", "请求总数", "", total("nginx_http_requests_total"), total("nginx_requests_total")),
        metric("reading", "读取连接", "", total("nginx_connections_reading")),
        metric("writing", "写入连接", "", total("nginx_connections_writing")),
        metric("waiting", "等待连接", "", total("nginx_connections_waiting")),
    ),
    "redis": (
        metric("connected_clients", "客户端连接", "", total("redis_connected_clients")),
        metric("blocked_clients", "阻塞客户端", "", total("redis_blocked_clients")),
        metric("used_memory_bytes", "内存使用", "bytes", total("redis_memory_used_bytes")),
        metric("commands_processed_total", "命令处理总数", "", total("redis_commands_processed_total")),
        metric("keyspace_hits_total", "Key 命中总数", "", total("redis_keyspace_hits_total")),
        metric("keyspace_misses_total", "Key 未命中总数", "", total("redis_keyspace_misses_total")),
        metric("rejected_connections_total", "拒绝连接总数", "", total("redis_rejected_connections_total")),
        metric("evicted_keys_total", "淘汰 Key 总数", "", total("redis_evicted_keys_total")),
        metric("expired_keys_total", "过期 Key 总数", "", total("redis_expired_keys_total")),
    ),
    "postgresql": (
        metric("active_backends", "数据库连接", "", total("pg_stat_database_numbackends")),
        metric("locks", "锁数量", "", total("pg_locks_count"), total("pg_stat_activity_count")),
        metric("deadlocks_total", "死锁总数", "", total("pg_stat_database_deadlocks")),
        metric("transactions_commit_total", "提交事务总数", "", total("pg_stat_database_xact_commit")),
        metric("transactions_rollback_total", "回滚事务总数", "", total("pg_stat_database_xact_rollback")),
        metric("blocks_hit_total", "缓存命中块", "", total("pg_stat_database_blks_hit")),
        metric("blocks_read_total", "磁盘读取块", "", total("pg_stat_database_blks_read")),
        metric("conflicts_total", "冲突总数", "", total("pg_stat_database_conflicts")),
        metric("temp_bytes_total", "临时文件字节", "bytes", total("pg_stat_database_temp_bytes")),
    ),
    "mongodb": (
        metric("connections_current", "当前连接", "", total("mongodb_connections_current")),
        metric("connections_available", "可用连接", "", total("mongodb_connections_available")),
        metric("op_counters_query_total", "查询操作总数", "", total("mongodb_ss_opcounters_query"), total("mongodb_op_counters_total")),
        metric("op_counters_insert_total", "插入操作总数", "", total("mongodb_ss_opcounters_insert")),
        metric("op_counters_update_total", "更新操作总数", "", total("mongodb_ss_opcounters_update")),
        metric("op_counters_delete_total", "删除操作总数", "", total("mongodb_ss_opcounters_delete")),
        metric("memory_resident_bytes", "常驻内存", "bytes", total("mongodb_memory_resident_bytes"), total("mongodb_ss_mem_resident")),
        metric("asserts_total", "断言总数", "", total("mongodb_asserts_total"), total("mongodb_ss_asserts_total")),
    ),
    "kafka": (
        metric("brokers", "Broker 数量", "", maximum("kafka_brokers"), maximum("kafka_cluster_brokers")),
        metric("under_replicated_partitions", "副本不足分区", "", total("kafka_topic_partition_under_replicated_partition"), total("kafka_server_replicamanager_underreplicatedpartitions")),
        metric("offline_partitions_count", "离线分区", "", total("kafka_controller_kafkacontroller_offlinepartitionscount")),
        metric("active_controller_count", "活跃 Controller", "", total("kafka_controller_kafkacontroller_activecontrollercount")),
        metric("topic_partition_current_offset", "分区当前 Offset", "", total("kafka_topic_partition_current_offset")),
        metric("consumergroup_lag", "消费组积压", "", total("kafka_consumergroup_lag"), total("kafka_consumergroup_current_offset_sum")),
    ),
    "rabbitmq": (
        metric("queue_messages", "队列消息总数", "", total("rabbitmq_queue_messages")),
        metric("queue_messages_ready", "待消费消息", "", total("rabbitmq_queue_messages_ready")),
        metric("queue_messages_unacked", "未确认消息", "", total("rabbitmq_queue_messages_unacked")),
        metric("connections", "连接数", "", total("rabbitmq_connections")),
        metric("channels", "Channel 数", "", total("rabbitmq_channels")),
        metric("consumers", "消费者数", "", total("rabbitmq_queue_consumers"), total("rabbitmq_consumers")),
    ),
    "elasticsearch": (
        metric("cluster_health_status", "集群健康状态", "", maximum("elasticsearch_cluster_health_status")),
        metric("active_shards", "活跃分片", "", total("elasticsearch_cluster_health_active_shards")),
        metric("relocating_shards", "迁移中分片", "", total("elasticsearch_cluster_health_relocating_shards")),
        metric("initializing_shards", "初始化分片", "", total("elasticsearch_cluster_health_initializing_shards")),
        metric("unassigned_shards", "未分配分片", "", total("elasticsearch_cluster_health_unassigned_shards")),
        metric("jvm_memory_used_bytes", "JVM 内存", "bytes", total("elasticsearch_jvm_memory_used_bytes")),
        metric("filesystem_data_available_bytes", "可用磁盘", "bytes", total("elasticsearch_filesystem_data_available_bytes")),
    ),
    "clickhouse": (
        metric("query_total", "查询总数", "", total("ClickHouseProfileEvents_Query"), total("clickhouse_query_total")),
        metric("tcp_connections", "TCP 连接", "", total("ClickHouseMetrics_TCPConnection"), total("clickhouse_tcp_connections")),
        metric("http_connections", "HTTP 连接", "", total("ClickHouseMetrics_HTTPConnection"), total("clickhouse_http_connections")),
        metric("memory_tracking", "内存使用", "bytes", total("ClickHouseMetrics_MemoryTracking"), total("clickhouse_memory_tracking")),
        metric("delayed_inserts", "延迟写入", "", total("ClickHouseMetrics_DelayedInserts"), total("clickhouse_delayed_inserts")),
    ),
    "zookeeper": (
        metric("approximate_data_size", "数据大小", "bytes", total("zookeeper_approximate_data_size")),
        metric("num_alive_connections", "存活连接", "", total("zookeeper_num_alive_connections")),
        metric("outstanding_requests", "待处理请求", "", total("zookeeper_outstanding_requests")),
        metric("znode_count", "ZNode 数量", "", total("zookeeper_znode_count")),
        metric("watch_count", "Watch 数量", "", total("zookeeper_watch_count")),
    ),
    "etcd": (
        metric("server_has_leader", "Leader 状态", "", maximum("etcd_server_has_leader")),
        metric("server_leader_changes_seen_total", "Leader 变更总数", "", total("etcd_server_leader_changes_seen_total")),
        metric("mvcc_db_total_size_in_bytes", "数据库大小", "bytes", total("etcd_mvcc_db_total_size_in_bytes")),
        metric("network_peer_round_trip_time_seconds", "节点通信延迟", "s", maximum("etcd_network_peer_round_trip_time_seconds")),
        metric("disk_backend_commit_duration_seconds", "磁盘提交耗时", "s", maximum("etcd_disk_backend_commit_duration_seconds")),
    ),
    "blackbox": (
        metric("probe_success", "探测状态", "", maximum("probe_success")),
        metric("probe_duration_seconds", "探测耗时", "s", maximum("probe_duration_seconds")),
        metric("probe_http_status_code", "HTTP 状态码", "", maximum("probe_http_status_code")),
        metric("probe_ssl_days_remaining", "证书剩余天数", "days", '(max(probe_ssl_earliest_cert_expiry{$selector}) - time()) / 86400'),
    ),
    "cadvisor": (
        metric("container_cpu_usage", "容器 CPU 使用", "cores", 'sum(rate(container_cpu_usage_seconds_total{$selector}[5m]))'),
        metric("container_memory_usage_bytes", "容器内存", "bytes", total("container_memory_working_set_bytes")),
        metric("container_network_receive_bytes_total", "网络接收总量", "bytes", total("container_network_receive_bytes_total")),
        metric("container_network_transmit_bytes_total", "网络发送总量", "bytes", total("container_network_transmit_bytes_total")),
    ),
    "windows": (
        metric("cpu_usage_percent", "CPU 使用率", "%", '100 - avg(rate(windows_cpu_time_total{$selector,mode="idle"}[5m])) * 100'),
        metric("memory_usage_percent", "内存使用率", "%", '(1 - sum(windows_os_physical_memory_free_bytes{$selector}) / sum(windows_cs_physical_memory_bytes{$selector})) * 100'),
        metric("logical_disk_free_bytes", "磁盘可用空间", "bytes", total("windows_logical_disk_free_bytes")),
        metric("service_state", "运行服务数", "", 'sum(windows_service_state{$selector,state="running"})'),
    ),
    "process": (
        metric("process_cpu_seconds_total", "进程 CPU 时间", "s", total("namedprocess_namegroup_cpu_seconds_total"), total("process_cpu_seconds_total")),
        metric("process_resident_memory_bytes", "进程常驻内存", "bytes", total("namedprocess_namegroup_memory_bytes"), total("process_resident_memory_bytes")),
        metric("process_open_fds", "打开文件数", "", total("process_open_fds")),
        metric("process_num_threads", "线程数", "", total("namedprocess_namegroup_num_threads"), total("process_num_threads")),
    ),
    "jmx": (
        metric("jvm_memory_used_bytes", "JVM 已用内存", "bytes", total("jvm_memory_used_bytes")),
        metric("jvm_memory_committed_bytes", "JVM 已提交内存", "bytes", total("jvm_memory_committed_bytes")),
        metric("jvm_threads_current", "JVM 线程", "", total("jvm_threads_current")),
        metric("jvm_gc_collection_seconds_count", "GC 次数", "", total("jvm_gc_collection_seconds_count")),
        metric("jvm_gc_collection_seconds_sum", "GC 总耗时", "s", total("jvm_gc_collection_seconds_sum")),
    ),
    "custom": (),
}


def target_selector(user_id: int, target_id: int) -> str:
    return f'platform_user_id="{user_id}",platform_target_id="{target_id}"'


def render_expression(expression: str, selector: str) -> str:
    return expression.replace("$selector", selector)


def definitions_for(exporter_kind: str | None) -> tuple[ExporterMetricDefinition, ...]:
    return EXPORTER_METRICS.get(exporter_kind or "custom", ())