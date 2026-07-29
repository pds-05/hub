import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, ConfigProvider, Descriptions, Drawer, Empty, Form, Input, InputNumber, Layout, Menu, Popconfirm, Progress, Row, Select, Space, Statistic, Switch, Table, Tag, message } from 'antd';
import type { SelectProps } from 'antd';
import { AimOutlined, BarChartOutlined, CheckCircleOutlined, DashboardOutlined, LoginOutlined, MailOutlined, ProfileOutlined, ReloadOutlined, RobotOutlined, SendOutlined, SettingOutlined, WarningOutlined, HeartOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import TargetMetricsPanel from './TargetMetricsPanel';
import 'antd/dist/reset.css';
import './styles.css';

const { Header, Content, Sider } = Layout;
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
const GRAFANA_URL = (import.meta.env.VITE_GRAFANA_URL || 'http://114.55.117.211:31000').replace(/\/$/, '');

type PageKey = 'overview' | 'targets' | 'clusters' | 'rules' | 'events' | 'channels' | 'records' | 'logs' | 'assistant' | 'grafana' | 'platformHealth';
type HandlingStatus = 'new' | 'acknowledged' | 'investigating' | 'mitigating' | 'watching' | 'resolved' | 'closed';
type AlertEvent = { id: number; rule_name: string; scope: 'node' | 'target' | string; instance: string; level: 'general' | 'severe' | 'urgent'; metric: string; operator: string; value: number; threshold: number; status: 'active' | 'resolved'; handling_status: HandlingStatus; acknowledged: boolean; trigger_count: number; last_triggered_at: string; };
type AlertSummary = { total_count: number; active_count: number; resolved_count: number; unacknowledged_active_count: number; handling_by_status: Record<string, number>; active_by_level: Record<string, number>; total_by_level: Record<string, number>; recent_events: AlertEvent[]; };
type AlertRule = { id: number; name: string; scope: 'node' | 'target'; metric: string; operator: '>=' | '>' | '<=' | '<' | '=='; threshold: number; level: 'general' | 'severe' | 'urgent'; enabled: boolean; description?: string; };
type TargetType = 'website' | 'port' | 'exporter';
type ExporterKind = 'node' | 'mysql' | 'nginx' | 'redis' | 'postgresql' | 'mongodb' | 'kafka' | 'rabbitmq' | 'elasticsearch' | 'clickhouse' | 'zookeeper' | 'etcd' | 'blackbox' | 'cadvisor' | 'windows' | 'process' | 'jmx' | 'custom';
type MonitorTarget = { id: number; name: string; target_type: TargetType; endpoint: string; expected_keyword?: string | null; exporter_kind?: ExporterKind | null; description?: string | null; created_at: string; };
type TargetCheck = { check_id: number; target_id: number; status: 'up' | 'down'; response_time_ms: number; message: string; status_code?: number | null; checked_at: string; details?: Record<string, unknown> | null; };
type TargetSummary = { total: number; up: number; down: number; unknown: number; avg_response_time_ms?: number | null; };
type NodeMetric = { instance: string; metrics: { cpu_usage_percent?: number | null; memory_usage_percent?: number | null; disk_usage_percent?: number | null; load1?: number | null; }; };
type NodeSummary = { node_count: number; avg_cpu_usage_percent?: number | null; avg_memory_usage_percent?: number | null; avg_disk_usage_percent?: number | null; avg_load1?: number | null; max_cpu_node?: string | null; max_memory_node?: string | null; max_disk_node?: string | null; nodes: NodeMetric[]; };
type ExporterKindSummary = { kind: ExporterKind; total: number; up: number; down: number; unknown: number; targets: { target_id: number; name: string; endpoint: string; status: string; response_time_ms?: number | null; checked_at?: string | null; message?: string | null }[]; };
type ExporterSummary = { total: number; kinds: ExporterKindSummary[]; };
type NotificationChannelType = 'email' | 'webhook' | 'dingtalk' | 'feishu' | 'wecom';
type NotificationChannel = { id: number; name: string; channel_type: NotificationChannelType; config: Record<string, unknown>; enabled: boolean; description?: string | null; };
type NotificationRecord = { id: number; channel_id: number; alert_event_id: number; notification_type: 'triggered' | 'resolved'; status: 'pending' | 'sent' | 'failed' | 'skipped'; title: string; content: string; error_message?: string | null; created_at: string; };
type GrafanaDashboard = { id?: number; uid?: string; title: string; url: string; full_url: string; folder_title: string; tags: string[]; is_starred: boolean; };
type GrafanaTargetView = { target_id: number; target_name: string; target_type: TargetType; exporter_kind?: ExporterKind | null; endpoint: string; match_type: 'dashboard' | 'explore'; url: string; dashboard?: GrafanaDashboard | null; keywords: string[][]; };
type GrafanaPlatformView = { key: string; title: string; match_type: 'dashboard' | 'search'; url: string; dashboard?: GrafanaDashboard | null; keywords: string[][]; };
type GrafanaViews = { grafana_url: string; grafana_public_url?: string; role: string; targets: GrafanaTargetView[]; platform: GrafanaPlatformView[]; dashboard_count: number; };
type AlertEventActivity = { id: number; user_id: number; event_id: number; action: 'note' | 'ack' | 'resolve' | string; note?: string | null; actor: string; created_at: string; };
type LogEntry = { id: string; time: string; labels: Record<string, string>; line: string; };
type LogQueryMode = 'simple' | 'advanced';
type LogLevelFilter = 'all' | 'error' | 'warning' | 'info';
type CurrentUser = { id: number; username: string; email: string; role: 'root' | 'user' | string; is_active: boolean; created_at: string; };
type PlatformHealthService = { name: string; status: 'healthy' | 'degraded' | 'down' | string; message: string; url?: string };
type PlatformHealth = { status: 'healthy' | 'degraded' | string; services: PlatformHealthService[]; };
type ManagedCluster = { id: number; user_id: number; name: string; provider: string; api_server?: string | null; description?: string | null; agent_token: string; status: string; agent_version?: string | null; node_count: number; pod_count: number; metrics_count: number; logs_count: number; alerts_count: number; last_heartbeat_at?: string | null; created_at: string; updated_at: string; };
type ManagedClusterInstall = { cluster_id: number; agent_token: string; install_command: string; manifest: string; };
type ClusterAgentHeartbeat = { id: number; cluster_id: number; status: string; agent_version?: string | null; node_count: number; pod_count: number; message?: string | null; payload: Record<string, unknown>; created_at: string; };
type ClusterAgentReport = { id: number; cluster_id: number; report_type: 'metric' | 'log' | 'alert'; source?: string | null; level?: string | null; message?: string | null; payload: Record<string, unknown>; created_at: string; };

type AIAnalysis = {
  enabled: boolean;
  provider?: string | null;
  model?: string | null;
  summary: string;
  note?: string;
  risks?: string[];
  suggestions?: string[];
  local_fallback?: {
    summary?: string;
    risks?: string[];
    suggestions?: string[];
  };
};

type AIChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
};

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail || `请求失败：${response.status}`, response.status);
  }
  return response.json();
}

function levelColor(level: string) {
  if (level === 'urgent') return 'red';
  if (level === 'severe') return 'orange';
  return 'blue';
}

function displayText(value: string) {
  const map: Record<string, string> = {
    up: '正常',
    down: '异常',
    unknown: '未知',
    active: '活跃',
    resolved: '已恢复',
    pending: '待发送',
    sent: '已发送',
    failed: '失败',
    skipped: '已跳过',
    general: '一般',
    severe: '严重',
    urgent: '紧急',
    website: '网站',
    port: '端口',
    exporter: 'Exporter',
    node: '节点',
    target: '监控对象',
    triggered: '触发',
    email: '邮箱',
    webhook: 'Webhook',
    generic: '通用 JSON',
    dingtalk: '钉钉',
    feishu: '飞书',
    wecom: '企业微信',
  };
  return map[value] || value;
}

function statusColor(status: string) {
  if (status === 'up' || status === 'sent' || status === 'resolved') return 'green';
  if (status === 'down' || status === 'failed' || status === 'active') return 'red';
  if (status === 'skipped') return 'default';
  return 'gold';
}

const handlingStatuses: { label: string; value: HandlingStatus }[] = [
  { label: '新建', value: 'new' },
  { label: '已确认', value: 'acknowledged' },
  { label: '排查中', value: 'investigating' },
  { label: '处置中', value: 'mitigating' },
  { label: '观察中', value: 'watching' },
  { label: '已恢复', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
];

function handlingStatusColor(status: string) {
  if (status === 'new') return 'red';
  if (status === 'acknowledged') return 'orange';
  if (status === 'investigating') return 'blue';
  if (status === 'mitigating') return 'purple';
  if (status === 'watching') return 'gold';
  if (status === 'resolved') return 'green';
  if (status === 'closed') return 'default';
  return 'default';
}

const exporterKindOptions: { label: string; value: ExporterKind }[] = [
  { label: 'Node Exporter - Linux 服务器 CPU / 内存 / 磁盘', value: 'node' },
  { label: 'MySQL / MariaDB Exporter', value: 'mysql' },
  { label: 'Nginx Exporter', value: 'nginx' },
  { label: 'Redis Exporter', value: 'redis' },
  { label: 'PostgreSQL Exporter', value: 'postgresql' },
  { label: 'MongoDB Exporter', value: 'mongodb' },
  { label: 'Kafka Exporter', value: 'kafka' },
  { label: 'RabbitMQ Exporter', value: 'rabbitmq' },
  { label: 'Elasticsearch Exporter', value: 'elasticsearch' },
  { label: 'ClickHouse Exporter', value: 'clickhouse' },
  { label: 'ZooKeeper Exporter', value: 'zookeeper' },
  { label: 'etcd Exporter', value: 'etcd' },
  { label: 'Blackbox Exporter', value: 'blackbox' },
  { label: 'cAdvisor - 容器指标', value: 'cadvisor' },
  { label: 'Windows Exporter', value: 'windows' },
  { label: 'Process Exporter', value: 'process' },
  { label: 'JMX Exporter - Java 中间件', value: 'jmx' },
  { label: '自定义 Prometheus Exporter', value: 'custom' },
];

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((item) => formatDetailValue(item)).join(', ');
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== null && item !== undefined)
      .map(([key, item]) => `${key}: ${formatDetailValue(item)}`)
      .join('\n');
  }
  return String(value);
}

const exporterEndpointPlaceholder: Record<ExporterKind, string> = {
  node: '示例：http://114.55.117.211:9100/metrics',
  mysql: '示例：http://114.55.117.211:9104/metrics',
  nginx: '示例：http://114.55.117.211:9113/metrics',
  redis: '示例：http://114.55.117.211:9121/metrics',
  postgresql: '示例：http://114.55.117.211:9187/metrics',
  mongodb: '示例：http://114.55.117.211:9216/metrics',
  kafka: '示例：http://114.55.117.211:9308/metrics',
  rabbitmq: '示例：http://用户服务器公网IP:15692/metrics',
  elasticsearch: '示例：http://114.55.117.211:9114/metrics',
  clickhouse: '示例：http://114.55.117.211:9363/metrics',
  zookeeper: '示例：http://114.55.117.211:9141/metrics',
  etcd: '示例：http://114.55.117.211:2379/metrics',
  blackbox: '示例：http://114.55.117.211:9115/metrics',
  cadvisor: '示例：http://114.55.117.211:8080/metrics',
  windows: '示例：http://114.55.117.211:9182/metrics',
  process: '示例：http://114.55.117.211:9256/metrics',
  jmx: '示例：http://114.55.117.211:9404/metrics',
  custom: '示例：http://114.55.117.211:9000/metrics',
};

const exporterKindHelp: Record<ExporterKind, string> = {
  node: 'Linux 服务器资源：CPU、内存、磁盘、负载和网络。服务器资源图只展示 Node Exporter。',
  mysql: 'MySQL/MariaDB 指标：可用状态、连接数、查询、慢查询、线程和 InnoDB。',
  nginx: 'Nginx 指标：活跃连接、请求、读取、写入和等待连接。',
  redis: 'Redis 指标：内存、客户端、命令数、Key 命中/未命中和连接状态。',
  postgresql: 'PostgreSQL 指标：连接、事务、锁、缓存命中、死锁和临时文件。',
  mongodb: 'MongoDB 指标：连接、操作计数、内存和断言。',
  kafka: 'Kafka 指标：Broker、分区、副本、Controller 和消费组延迟。',
  rabbitmq: 'RabbitMQ 指标：队列、消息、消费者、连接和 Channel。',
  elasticsearch: 'Elasticsearch 指标：集群健康、JVM、分片和存储。',
  clickhouse: 'ClickHouse 指标：查询、连接、内存和延迟插入。',
  zookeeper: 'ZooKeeper 指标：连接、请求、znode、watch 和存储大小。',
  etcd: 'etcd 指标：Leader、数据库大小、延迟和提交耗时。',
  blackbox: 'Blackbox 指标：HTTP/TCP/ICMP/DNS 探测、TLS 和响应状态。',
  cadvisor: '容器指标：容器 CPU、内存、文件系统和网络使用。',
  windows: 'Windows 服务器指标：CPU、内存、磁盘、服务和进程。',
  process: '进程级指标：进程 CPU、内存、文件描述符和线程数。',
  jmx: 'Java 中间件指标：JVM、GC、线程，以及 Tomcat/Kafka 等 Java 应用。',
  custom: '任意 Prometheus 格式指标地址，平台会校验 /metrics 格式并保存检测元数据。',
};
const nodeRuleMetricOptions: SelectProps['options'] = [
  { label: '节点 CPU 使用率 %', value: 'cpu_usage_percent' },
  { label: '节点内存使用率 %', value: 'memory_usage_percent' },
  { label: '节点磁盘使用率 %', value: 'disk_usage_percent' },
  { label: '节点 1 分钟负载', value: 'load1' },
];

const targetRuleMetricOptions: SelectProps['options'] = [
  { label: '可用性 / 网站 / 端口', options: [
    { label: '监控对象不可用', value: 'status_down' },
    { label: '响应时间 ms', value: 'response_time_ms' },
    { label: 'HTTP 状态码', value: 'http_status_code' },
    { label: 'TLS 证书剩余天数', value: 'tls_days_remaining' },
    { label: 'DNS 解析失败', value: 'dns_failed' },
    { label: 'TLS 检测失败', value: 'tls_failed' },
    { label: '关键字不匹配', value: 'keyword_mismatch' },
    { label: 'Exporter 指标格式无效', value: 'metrics_format_invalid' },
  ] },
  { label: 'Exporter 通用', options: [
    { label: 'Exporter 可用状态', value: 'exporter_up' },
    { label: 'Exporter 指标数量', value: 'exporter_metric_count' },
    { label: 'Exporter 序列数量', value: 'exporter_series_count' },
  ] },
  { label: 'MySQL / MariaDB', options: [
    { label: 'MySQL 当前连接线程数', value: 'mysql_threads_connected' },
    { label: 'MySQL 正在运行线程数', value: 'mysql_threads_running' },
    { label: 'MySQL 查询总数', value: 'mysql_questions_total' },
    { label: 'MySQL 连接总数', value: 'mysql_connections_total' },
    { label: 'MySQL 慢查询总数', value: 'mysql_slow_queries_total' },
    { label: 'MySQL 失败连接总数', value: 'mysql_aborted_connects_total' },
    { label: 'MySQL InnoDB 脏页数', value: 'mysql_innodb_buffer_pool_pages_dirty' },
    { label: 'MySQL 主从延迟秒数', value: 'mysql_slave_lag_seconds' },
  ] },
  { label: 'Redis', options: [
    { label: 'Redis 客户端连接数', value: 'redis_connected_clients' },
    { label: 'Redis 阻塞客户端数', value: 'redis_blocked_clients' },
    { label: 'Redis 拒绝连接总数', value: 'redis_rejected_connections_total' },
    { label: 'Redis 已用内存字节数', value: 'redis_used_memory_bytes' },
    { label: 'Redis 已处理命令总数', value: 'redis_commands_processed_total' },
    { label: 'Redis Key 命中总数', value: 'redis_keyspace_hits_total' },
    { label: 'Redis Key 未命中总数', value: 'redis_keyspace_misses_total' },
    { label: 'Redis 驱逐 Key 总数', value: 'redis_evicted_keys_total' },
    { label: 'Redis 过期 Key 总数', value: 'redis_expired_keys_total' },
  ] },
  { label: 'PostgreSQL', options: [
    { label: 'PostgreSQL 活跃连接数', value: 'postgresql_active_backends' },
    { label: 'PostgreSQL 锁数量', value: 'postgresql_locks' },
    { label: 'PostgreSQL 死锁总数', value: 'postgresql_deadlocks_total' },
    { label: 'PostgreSQL 提交事务总数', value: 'postgresql_transactions_commit_total' },
    { label: 'PostgreSQL 回滚事务总数', value: 'postgresql_transactions_rollback_total' },
    { label: 'PostgreSQL 缓存命中块总数', value: 'postgresql_blocks_hit_total' },
    { label: 'PostgreSQL 磁盘读取块总数', value: 'postgresql_blocks_read_total' },
    { label: 'PostgreSQL 冲突总数', value: 'postgresql_conflicts_total' },
    { label: 'PostgreSQL 临时文件字节数', value: 'postgresql_temp_bytes_total' },
  ] },
  { label: 'Nginx', options: [
    { label: 'Nginx 活跃连接数', value: 'nginx_active_connections' },
    { label: 'Nginx 请求总数', value: 'nginx_requests_total' },
    { label: 'Nginx 读取连接数', value: 'nginx_reading' },
    { label: 'Nginx 写入连接数', value: 'nginx_writing' },
    { label: 'Nginx 等待连接数', value: 'nginx_waiting' },
  ] },
  { label: 'MongoDB', options: [
    { label: 'MongoDB 当前连接数', value: 'mongodb_connections_current' },
    { label: 'MongoDB 可用连接数', value: 'mongodb_connections_available' },
    { label: 'MongoDB 查询总数', value: 'mongodb_op_counters_query_total' },
    { label: 'MongoDB 插入总数', value: 'mongodb_op_counters_insert_total' },
    { label: 'MongoDB 更新总数', value: 'mongodb_op_counters_update_total' },
    { label: 'MongoDB 删除总数', value: 'mongodb_op_counters_delete_total' },
    { label: 'MongoDB 常驻内存字节数', value: 'mongodb_memory_resident_bytes' },
    { label: 'MongoDB 断言总数', value: 'mongodb_asserts_total' },
  ] },
  { label: 'Kafka', options: [
    { label: 'Kafka Broker 数量', value: 'kafka_brokers' },
    { label: 'Kafka 副本不足分区数', value: 'kafka_under_replicated_partitions' },
    { label: 'Kafka 离线分区数', value: 'kafka_offline_partitions_count' },
    { label: 'Kafka 活跃 Controller 数', value: 'kafka_active_controller_count' },
    { label: 'Kafka 分区当前 Offset', value: 'kafka_topic_partition_current_offset' },
    { label: 'Kafka 消费组延迟', value: 'kafka_consumergroup_lag' },
  ] },
  { label: 'RabbitMQ', options: [
    { label: 'RabbitMQ 队列消息数', value: 'rabbitmq_queue_messages' },
    { label: 'RabbitMQ 就绪消息数', value: 'rabbitmq_queue_messages_ready' },
    { label: 'RabbitMQ 未确认消息数', value: 'rabbitmq_queue_messages_unacked' },
    { label: 'RabbitMQ 连接数', value: 'rabbitmq_connections' },
    { label: 'RabbitMQ Channel 数', value: 'rabbitmq_channels' },
    { label: 'RabbitMQ 消费者数', value: 'rabbitmq_consumers' },
  ] },
  { label: 'Elasticsearch', options: [
    { label: 'ES 集群健康状态', value: 'elasticsearch_cluster_health_status' },
    { label: 'ES 活跃分片数', value: 'elasticsearch_active_shards' },
    { label: 'ES 迁移中分片数', value: 'elasticsearch_relocating_shards' },
    { label: 'ES 初始化分片数', value: 'elasticsearch_initializing_shards' },
    { label: 'ES 未分配分片数', value: 'elasticsearch_unassigned_shards' },
    { label: 'ES JVM 已用内存字节数', value: 'elasticsearch_jvm_memory_used_bytes' },
    { label: 'ES 数据盘可用字节数', value: 'elasticsearch_filesystem_data_available_bytes' },
  ] },
  { label: 'ClickHouse', options: [
    { label: 'ClickHouse 可用状态', value: 'clickhouse_up' },
    { label: 'ClickHouse 查询总数', value: 'clickhouse_query_total' },
    { label: 'ClickHouse TCP 连接数', value: 'clickhouse_tcp_connections' },
    { label: 'ClickHouse HTTP 连接数', value: 'clickhouse_http_connections' },
    { label: 'ClickHouse 内存跟踪值', value: 'clickhouse_memory_tracking' },
    { label: 'ClickHouse 延迟插入数', value: 'clickhouse_delayed_inserts' },
  ] },
  { label: 'ZooKeeper / Etcd', options: [
    { label: 'ZooKeeper 可用状态', value: 'zookeeper_up' },
    { label: 'ZooKeeper 存储近似大小', value: 'zookeeper_approximate_data_size' },
    { label: 'ZooKeeper 活跃连接数', value: 'zookeeper_num_alive_connections' },
    { label: 'ZooKeeper 未完成请求数', value: 'zookeeper_outstanding_requests' },
    { label: 'ZooKeeper ZNode 数', value: 'zookeeper_znode_count' },
    { label: 'ZooKeeper Watch 数', value: 'zookeeper_watch_count' },
    { label: 'Etcd 是否有 Leader', value: 'etcd_server_has_leader' },
    { label: 'Etcd Leader 变更总数', value: 'etcd_server_leader_changes_seen_total' },
    { label: 'Etcd DB 大小字节数', value: 'etcd_mvcc_db_total_size_in_bytes' },
    { label: 'Etcd Peer RTT 秒', value: 'etcd_network_peer_round_trip_time_seconds' },
    { label: 'Etcd 后端提交耗时秒', value: 'etcd_disk_backend_commit_duration_seconds' },
  ] },
  { label: 'JVM / Windows / Process', options: [
    { label: 'JVM 已用内存字节数', value: 'jvm_memory_used_bytes' },
    { label: 'JVM 已提交内存字节数', value: 'jvm_memory_committed_bytes' },
    { label: 'JVM 当前线程数', value: 'jvm_threads_current' },
    { label: 'JVM GC 次数', value: 'jvm_gc_collection_seconds_count' },
    { label: 'JVM GC 总耗时秒', value: 'jvm_gc_collection_seconds_sum' },
    { label: 'Windows CPU 使用率', value: 'windows_cpu_usage_percent' },
    { label: 'Windows 内存使用率', value: 'windows_memory_usage_percent' },
    { label: 'Windows 磁盘可用字节数', value: 'windows_logical_disk_free_bytes' },
    { label: 'Windows 服务状态', value: 'windows_service_state' },
    { label: '进程 CPU 秒数', value: 'process_cpu_seconds_total' },
    { label: '进程常驻内存字节数', value: 'process_resident_memory_bytes' },
    { label: '进程打开文件数', value: 'process_open_fds' },
    { label: '进程线程数', value: 'process_num_threads' },
  ] },
];

const targetRuleDefaults: Record<string, { operator: string; threshold: number }> = {
  status_down: { operator: '>=', threshold: 1 },
  response_time_ms: { operator: '>=', threshold: 1000 },
  http_status_code: { operator: '>=', threshold: 500 },
  tls_days_remaining: { operator: '<=', threshold: 14 },
  dns_failed: { operator: '>=', threshold: 1 },
  tls_failed: { operator: '>=', threshold: 1 },
  keyword_mismatch: { operator: '>=', threshold: 1 },
  metrics_format_invalid: { operator: '>=', threshold: 1 },
  exporter_up: { operator: '<', threshold: 1 },
  exporter_metric_count: { operator: '<=', threshold: 0 },
  exporter_series_count: { operator: '<=', threshold: 0 },
  mysql_threads_connected: { operator: '>=', threshold: 100 }, mysql_threads_running: { operator: '>=', threshold: 50 }, mysql_questions_total: { operator: '>=', threshold: 1000000 }, mysql_connections_total: { operator: '>=', threshold: 100000 }, mysql_slow_queries_total: { operator: '>=', threshold: 10 }, mysql_aborted_connects_total: { operator: '>=', threshold: 10 }, mysql_innodb_buffer_pool_pages_dirty: { operator: '>=', threshold: 1000 }, mysql_slave_lag_seconds: { operator: '>=', threshold: 60 },
  redis_connected_clients: { operator: '>=', threshold: 100 }, redis_blocked_clients: { operator: '>=', threshold: 1 }, redis_rejected_connections_total: { operator: '>=', threshold: 1 }, redis_used_memory_bytes: { operator: '>=', threshold: 1073741824 }, redis_commands_processed_total: { operator: '>=', threshold: 1000000 }, redis_keyspace_hits_total: { operator: '>=', threshold: 1000000 }, redis_keyspace_misses_total: { operator: '>=', threshold: 10000 }, redis_evicted_keys_total: { operator: '>=', threshold: 1 }, redis_expired_keys_total: { operator: '>=', threshold: 10000 },
  postgresql_active_backends: { operator: '>=', threshold: 80 }, postgresql_locks: { operator: '>=', threshold: 50 }, postgresql_deadlocks_total: { operator: '>=', threshold: 1 }, postgresql_transactions_commit_total: { operator: '>=', threshold: 1000000 }, postgresql_transactions_rollback_total: { operator: '>=', threshold: 1000 }, postgresql_blocks_hit_total: { operator: '>=', threshold: 1000000 }, postgresql_blocks_read_total: { operator: '>=', threshold: 100000 }, postgresql_conflicts_total: { operator: '>=', threshold: 1 }, postgresql_temp_bytes_total: { operator: '>=', threshold: 1073741824 },
  nginx_active_connections: { operator: '>=', threshold: 1000 }, nginx_requests_total: { operator: '>=', threshold: 1000000 }, nginx_reading: { operator: '>=', threshold: 100 }, nginx_writing: { operator: '>=', threshold: 100 }, nginx_waiting: { operator: '>=', threshold: 1000 },
  mongodb_connections_current: { operator: '>=', threshold: 1000 }, mongodb_connections_available: { operator: '<=', threshold: 100 }, mongodb_op_counters_query_total: { operator: '>=', threshold: 1000000 }, mongodb_op_counters_insert_total: { operator: '>=', threshold: 1000000 }, mongodb_op_counters_update_total: { operator: '>=', threshold: 1000000 }, mongodb_op_counters_delete_total: { operator: '>=', threshold: 1000000 }, mongodb_memory_resident_bytes: { operator: '>=', threshold: 1073741824 }, mongodb_asserts_total: { operator: '>=', threshold: 1 },
  kafka_brokers: { operator: '<=', threshold: 0 }, kafka_under_replicated_partitions: { operator: '>=', threshold: 1 }, kafka_offline_partitions_count: { operator: '>=', threshold: 1 }, kafka_active_controller_count: { operator: '<', threshold: 1 }, kafka_topic_partition_current_offset: { operator: '>=', threshold: 1000000 }, kafka_consumergroup_lag: { operator: '>=', threshold: 10000 },
  rabbitmq_queue_messages: { operator: '>=', threshold: 10000 }, rabbitmq_queue_messages_ready: { operator: '>=', threshold: 10000 }, rabbitmq_queue_messages_unacked: { operator: '>=', threshold: 1000 }, rabbitmq_connections: { operator: '>=', threshold: 1000 }, rabbitmq_channels: { operator: '>=', threshold: 5000 }, rabbitmq_consumers: { operator: '<=', threshold: 0 },
  elasticsearch_cluster_health_status: { operator: '>=', threshold: 1 }, elasticsearch_active_shards: { operator: '<=', threshold: 0 }, elasticsearch_relocating_shards: { operator: '>=', threshold: 1 }, elasticsearch_initializing_shards: { operator: '>=', threshold: 1 }, elasticsearch_unassigned_shards: { operator: '>=', threshold: 1 }, elasticsearch_jvm_memory_used_bytes: { operator: '>=', threshold: 1073741824 }, elasticsearch_filesystem_data_available_bytes: { operator: '<=', threshold: 10737418240 },
  clickhouse_up: { operator: '<', threshold: 1 }, clickhouse_query_total: { operator: '>=', threshold: 1000000 }, clickhouse_tcp_connections: { operator: '>=', threshold: 1000 }, clickhouse_http_connections: { operator: '>=', threshold: 1000 }, clickhouse_memory_tracking: { operator: '>=', threshold: 1073741824 }, clickhouse_delayed_inserts: { operator: '>=', threshold: 1 },
  zookeeper_up: { operator: '<', threshold: 1 }, zookeeper_approximate_data_size: { operator: '>=', threshold: 1073741824 }, zookeeper_num_alive_connections: { operator: '>=', threshold: 1000 }, zookeeper_outstanding_requests: { operator: '>=', threshold: 100 }, zookeeper_znode_count: { operator: '>=', threshold: 100000 }, zookeeper_watch_count: { operator: '>=', threshold: 100000 },
  etcd_server_has_leader: { operator: '<', threshold: 1 }, etcd_server_leader_changes_seen_total: { operator: '>=', threshold: 1 }, etcd_mvcc_db_total_size_in_bytes: { operator: '>=', threshold: 1073741824 }, etcd_network_peer_round_trip_time_seconds: { operator: '>=', threshold: 1 }, etcd_disk_backend_commit_duration_seconds: { operator: '>=', threshold: 1 },
  jvm_memory_used_bytes: { operator: '>=', threshold: 1073741824 }, jvm_memory_committed_bytes: { operator: '>=', threshold: 1073741824 }, jvm_threads_current: { operator: '>=', threshold: 500 }, jvm_gc_collection_seconds_count: { operator: '>=', threshold: 1000 }, jvm_gc_collection_seconds_sum: { operator: '>=', threshold: 60 },
  windows_cpu_usage_percent: { operator: '>=', threshold: 80 }, windows_memory_usage_percent: { operator: '>=', threshold: 85 }, windows_logical_disk_free_bytes: { operator: '<=', threshold: 10737418240 }, windows_service_state: { operator: '>=', threshold: 1 }, process_cpu_seconds_total: { operator: '>=', threshold: 1000 }, process_resident_memory_bytes: { operator: '>=', threshold: 1073741824 }, process_open_fds: { operator: '>=', threshold: 1000 }, process_num_threads: { operator: '>=', threshold: 200 },
};
function parseLokiEntries(data: any): LogEntry[] {
  const results = data?.data?.result || [];
  const rows: LogEntry[] = [];
  for (const stream of results) {
    const labels = stream.stream || {};
    for (const value of stream.values || []) {
      const ns = Number(value[0]);
      rows.push({
        id: `${value[0]}-${rows.length}`,
        time: Number.isFinite(ns) ? new Date(ns / 1000000).toLocaleString() : String(value[0]),
        labels,
        line: value[1],
      });
    }
  }
  return rows;
}
function escapeLogQL(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function normalizeLogRegex(value: string) {
  return value.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function targetLogKeyword(target: MonitorTarget | null) {
  if (!target) return '';
  const endpointHost = target.endpoint.replace(/^https?:\/\//, '').split('/')[0].split(':')[0];
  return [target.name, endpointHost, target.exporter_kind || '', target.target_type]
    .filter(Boolean)
    .join('|');
}

function buildSimpleLogQL(values: {
  namespace: string;
  app: string;
  level: LogLevelFilter;
  keyword: string;
  targetKeyword: string;
}) {
  const selectors: string[] = [];
  if (values.namespace.trim()) selectors.push(`namespace=~"${escapeLogQL(values.namespace.trim())}"`);
  if (values.app.trim()) {
    const app = escapeLogQL(values.app.trim());
    selectors.push(`pod=~".*${app}.*"`);
  }
  let query = `{${selectors.join(',')}}`;
  if (query === '{}') query = '{namespace=~".+"}';

  const filters: string[] = [];
  if (values.level !== 'all') {
    const levelMap: Record<Exclude<LogLevelFilter, 'all'>, string> = {
      error: 'error|ERROR|Error|exception|Exception|failed|Failed|失败|异常|错误',
      warning: 'warn|WARN|Warning|warning|告警|警告',
      info: 'info|INFO|Info',
    };
    filters.push(levelMap[values.level]);
  }
  if (values.keyword.trim()) filters.push(normalizeLogRegex(values.keyword));
  if (values.targetKeyword.trim()) filters.push(values.targetKeyword);
  for (const filter of filters) {
    query += ` |~ "${escapeLogQL(filter)}"`;
  }
  return query;
}

const pageTitles: Record<PageKey, string> = {
  overview: '总览',
  targets: '监控对象',
  clusters: '集群管理',
  rules: '告警规则',
  events: '告警事件',
  channels: '通知渠道',
  records: '通知记录',
  logs: '日志查询',
  assistant: 'AI 助手',
  grafana: 'Grafana 图表',
  platformHealth: '平台健康',};

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('access_token') || '');
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [platformHealth, setPlatformHealth] = useState<PlatformHealth | null>(null);
  const [activePage, setActivePage] = useState<PageKey>('overview');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [targetSummary, setTargetSummary] = useState<TargetSummary | null>(null);
  const [nodeSummary, setNodeSummary] = useState<NodeSummary | null>(null);
  const [monitoredServerSummary, setMonitoredServerSummary] = useState<NodeSummary | null>(null);
  const [exporterSummary, setExporterSummary] = useState<ExporterSummary | null>(null);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [targets, setTargets] = useState<MonitorTarget[]>([]);
  const [clusters, setClusters] = useState<ManagedCluster[]>([]);
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const [clusterInstall, setClusterInstall] = useState<ManagedClusterInstall | null>(null);
  const [clusterHeartbeats, setClusterHeartbeats] = useState<ClusterAgentHeartbeat[]>([]);
  const [clusterReports, setClusterReports] = useState<ClusterAgentReport[]>([]);
  const [targetChecks, setTargetChecks] = useState<Record<number, TargetCheck | undefined>>({});
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);
  const [selectedTargetChecks, setSelectedTargetChecks] = useState<TargetCheck[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [eventActivities, setEventActivities] = useState<AlertEventActivity[]>([]);
  const [selectedAlertActivities, setSelectedAlertActivities] = useState<AlertEventActivity[]>([]);
  const [eventNote, setEventNote] = useState('');
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [records, setRecords] = useState<NotificationRecord[]>([]);
  const [logQueryMode, setLogQueryMode] = useState<LogQueryMode>('simple');
  const [logNamespace, setLogNamespace] = useState('platform');
  const [logApp, setLogApp] = useState('');
  const [logLevel, setLogLevel] = useState<LogLevelFilter>('all');
  const [logKeyword, setLogKeyword] = useState('');
  const [logTargetId, setLogTargetId] = useState<number | null>(null);
  const [logQuery, setLogQuery] = useState('{namespace="platform"}');
  const [logRangeMinutes, setLogRangeMinutes] = useState(30);
  const [logLimit, setLogLimit] = useState(100);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [grafanaDashboards, setGrafanaDashboards] = useState<GrafanaDashboard[]>([]);
  const [grafanaViews, setGrafanaViews] = useState<GrafanaViews | null>(null);
  const [grafanaError, setGrafanaError] = useState('');
  const [aiQuestion, setAiQuestion] = useState('分析当前监控对象和所选告警，给出可能原因、验证命令和恢复步骤');
  const [aiInput, setAiInput] = useState('');
  const [aiResult, setAiResult] = useState<AIAnalysis | null>(null);
  const [aiSessionActive, setAiSessionActive] = useState(false);
  const [aiMessages, setAiMessages] = useState<AIChatMessage[]>([]);
  const [loginForm] = Form.useForm();
  const [targetForm] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [channelForm] = Form.useForm();
  const [clusterForm] = Form.useForm();
  const watchedTargetType = Form.useWatch('target_type', targetForm) as TargetType | undefined;
  const watchedExporterKind = Form.useWatch('exporter_kind', targetForm) as ExporterKind | undefined;
  const watchedRuleScope = Form.useWatch('scope', ruleForm) as 'node' | 'target' | undefined;
  const watchedChannelType = Form.useWatch('channel_type', channelForm) as NotificationChannelType | undefined;
  const endpointPlaceholder: Record<TargetType, string> = {
    website: '示例：https://www.example.com 或 https://api.example.com/health',
    port: '示例：114.55.117.211:6379 或 114.55.117.211:5432',
    exporter: exporterEndpointPlaceholder[watchedExporterKind || 'node'],
  };
  const targetTypeHelp: Record<TargetType, string> = {
    website: '检测 HTTP/HTTPS 可用性、响应时间、状态码、DNS、TLS 证书和可选关键字。',
    port: '检测 TCP 服务端口是否可连接，例如 SSH、Redis、PostgreSQL、MySQL 或 Nginx。',
    exporter: exporterKindHelp[watchedExporterKind || 'node'],
  };

  function openGrafana(path = '/') {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const baseUrl = (grafanaViews?.grafana_public_url || GRAFANA_URL).replace(/\/$/, '');
    window.open(`${baseUrl}${normalizedPath}`, '_blank', 'noopener,noreferrer');
  }

  function grafanaSearchPath(query: string) {
    return `/dashboards?query=${encodeURIComponent(query)}`;
  }

  function findGrafanaDashboard(keywordGroups: string[][]) {
    let best: { dashboard: GrafanaDashboard; score: number } | null = null;
    for (const dashboard of grafanaDashboards) {
      const haystack = `${dashboard.title} ${dashboard.folder_title} ${dashboard.tags.join(' ')}`.toLowerCase();
      const score = keywordGroups.reduce((total, group) => {
        return total + (group.some((keyword) => haystack.includes(keyword.toLowerCase())) ? 1 : 0);
      }, 0);
      if (score > 0 && (!best || score > best.score)) {
        best = { dashboard, score };
      }
    }
    return best?.dashboard;
  }

  function grafanaDashboardPath(keywordGroups: string[][], fallbackPath = '/dashboards') {
    return findGrafanaDashboard(keywordGroups)?.url || fallbackPath;
  }

  function openTargetGrafana(target: MonitorTarget) {
    if (target.target_type === 'exporter') {
      if (target.exporter_kind === 'node') {
        openGrafana(grafanaDashboardPath([['node', '节点'], ['pod']]));
        return;
      }
      openGrafana(grafanaDashboardPath([[target.exporter_kind || 'exporter']]));
      return;
    }
    if (target.target_type === 'website') {
      openGrafana('/explore');
      return;
    }
    openGrafana(grafanaDashboardPath([['cluster', '集群', '多集群'], ['compute', '计算资源']], '/d/efa86fd1d0c121a26444b636a3f509a8/kubernetes-compute-resources-cluster?orgId=1&refresh=10s'));
  }

  function openAlertGrafana(event: AlertEvent) {
    const text = `${event.rule_name} ${event.scope} ${event.instance} ${event.metric}`.toLowerCase();
    if (text.includes('coredns') || text.includes('dns')) {
      openGrafana(grafanaDashboardPath([['coredns', 'dns']]));
      return;
    }
    if (text.includes('pod')) {
      openGrafana(grafanaDashboardPath([['pod'], ['compute', '计算资源']]));
      return;
    }
    if (text.includes('namespace') || text.includes('命名空间')) {
      openGrafana(grafanaDashboardPath([['namespace', '命名空间'], ['pod']]));
      return;
    }
    if (['cpu', 'memory', 'disk', 'load'].some((keyword) => text.includes(keyword))) {
      openGrafana(grafanaDashboardPath([['node', '节点'], ['pod']]));
      return;
    }
    if (text.includes('alertmanager')) {
      openGrafana(grafanaDashboardPath([['alertmanager']]));
      return;
    }
    openGrafana(grafanaDashboardPath([['cluster', '集群', '多集群'], ['compute', '计算资源']], '/d/efa86fd1d0c121a26444b636a3f509a8/kubernetes-compute-resources-cluster?orgId=1&refresh=10s'));
  }

  const chartOption = useMemo(() => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['48%', '72%'],
      data: [
        { name: 'general', value: summary?.active_by_level.general || 0 },
        { name: 'severe', value: summary?.active_by_level.severe || 0 },
        { name: 'urgent', value: summary?.active_by_level.urgent || 0 },
      ],
    }],
  }), [summary]);

  const targetStatusOption = useMemo(() => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['48%', '72%'],
      data: [
        { name: 'up', value: targetSummary?.up || 0 },
        { name: 'down', value: targetSummary?.down || 0 },
        { name: 'unknown', value: targetSummary?.unknown || 0 },
      ],
    }],
  }), [targetSummary]);

  const createNodeResourceOption = (nodes: NodeMetric[]) => ({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { top: 24, right: 16, bottom: 52, left: 44 },
    xAxis: { type: 'category', data: nodes.map((node) => node.instance), axisLabel: { rotate: 20 } },
    yAxis: { type: 'value', max: 100, name: '%' },
    series: [
      { name: 'CPU', type: 'bar', data: nodes.map((node) => node.metrics.cpu_usage_percent ?? 0) },
      { name: 'Memory', type: 'bar', data: nodes.map((node) => node.metrics.memory_usage_percent ?? 0) },
      { name: 'Disk', type: 'bar', data: nodes.map((node) => node.metrics.disk_usage_percent ?? 0) },
    ],
  });

  const nodeResourceOption = useMemo(() => createNodeResourceOption(nodeSummary?.nodes || []), [nodeSummary]);

  const monitoredServerResourceOption = useMemo(
    () => createNodeResourceOption(monitoredServerSummary?.nodes || []),
    [monitoredServerSummary],
  );

  const notificationStatus = useMemo(() => records.reduce((acc, record) => {
    acc[record.status] = (acc[record.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>), [records]);

  const selectedTarget = useMemo(
    () => targets.find((target) => target.id === selectedTargetId) || null,
    [selectedTargetId, targets],
  );

  const selectedLatestCheck = selectedTargetId ? targetChecks[selectedTargetId] : undefined;

  const targetAlerts = useMemo(() => {
    if (!selectedTarget) return [];
    const endpoint = selectedTarget.endpoint.toLowerCase();
    const endpointHost = endpoint.replace(/^https?:\/\//, '').split('/')[0];
    const targetName = selectedTarget.name.toLowerCase();
    return events.filter((event) => {
      const instance = event.instance.toLowerCase();
      const ruleName = event.rule_name.toLowerCase();
      return instance === endpoint
        || instance === endpointHost
        || instance.includes(endpointHost)
        || endpointHost.includes(instance)
        || ruleName.includes(targetName)
        || instance.includes(targetName);
    });
  }, [events, selectedTarget]);

  const selectedAlert = useMemo(
    () => targetAlerts.find((event) => event.id === selectedAlertId) || targetAlerts[0] || null,
    [targetAlerts, selectedAlertId],
  );

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) || null,
    [events, selectedEventId],
  );

  const selectedEventTarget = useMemo(() => {
    if (!selectedEvent) return null;
    const instance = selectedEvent.instance.toLowerCase();
    return targets.find((target) => {
      const endpoint = target.endpoint.toLowerCase();
      const endpointHost = endpoint.replace(/^https?:\/\//, '').split('/')[0];
      return instance === endpoint || instance === endpointHost || instance.includes(endpointHost) || endpointHost.includes(instance);
    }) || null;
  }, [selectedEvent, targets]);

  const selectedEventNotifications = useMemo(
    () => selectedEvent ? records.filter((record) => record.alert_event_id === selectedEvent.id) : [],
    [records, selectedEvent],
  );
  const targetTrendOption = useMemo(() => {
    const ordered = [...selectedTargetChecks].reverse();
    return {
      tooltip: { trigger: 'axis' },
      grid: { top: 24, right: 18, bottom: 36, left: 50 },
      xAxis: {
        type: 'category',
        data: ordered.map((item) => new Date(item.checked_at).toLocaleTimeString()),
        axisLabel: { rotate: 25 },
      },
      yAxis: { type: 'value', name: 'ms' },
      series: [
        {
          name: '响应时间',
          type: 'line',
          smooth: true,
          data: ordered.map((item) => item.response_time_ms),
          markPoint: {
            data: ordered
              .map((item, index) => item.status === 'down' ? { name: 'down', value: item.response_time_ms, xAxis: index, yAxis: item.response_time_ms } : null)
              .filter(Boolean),
          },
        },
      ],
    };
  }, [selectedTargetChecks]);

  function handleRequestError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) {
      localStorage.removeItem('access_token');
      setToken('');
      message.error('登录已过期，请重新登录');
      return;
    }
    message.error(error instanceof Error ? error.message : fallback);
  }

  async function loadLatestTargetChecks(nextTargets: MonitorTarget[]) {
    if (!token || nextTargets.length === 0) {
      setTargetChecks({});
      return;
    }
    const entries = await Promise.all(nextTargets.map(async (target) => {
      const checks = await request<TargetCheck[]>(`/targets/${target.id}/checks?limit=1`, token);
      return [target.id, checks[0]] as const;
    }));
    setTargetChecks(Object.fromEntries(entries));
  }
  async function loadTargetHistory(targetId: number) {
    if (!token) return;
    try {
      const checks = await request<TargetCheck[]>(`/targets/${targetId}/checks?limit=20`, token);
      setSelectedTargetChecks(checks);
    } catch (error) {
      handleRequestError(error, '加载检测历史失败');
    }
  }


  async function loadCurrentUser(nextToken = token) {
    if (!nextToken) {
      setCurrentUser(null);
      return null;
    }
    try {
      const user = await request<CurrentUser>('/auth/me', nextToken);
      setCurrentUser(user);
      return user;
    } catch (error) {
      handleRequestError(error, '获取当前用户失败');
      return null;
    }
  }

  async function register(values: { username: string; email: string; password: string }) {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || '注册失败');
      }
      message.success('注册成功，请登录');
      setAuthMode('login');
      loginForm.setFieldsValue({ username: values.username, password: values.password });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  async function loadPlatformHealth() {
    if (!token || currentUser?.role !== 'root') return;
    try {
      const health = await request<PlatformHealth>('/platform/health', token);
      setPlatformHealth(health);
    } catch (error) {
      handleRequestError(error, '加载平台健康状态失败');
    }
  }
  async function login(values: { username: string; password: string }) {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!response.ok) throw new Error('登录失败');
      const body = await response.json();
      localStorage.setItem('access_token', body.access_token);
      setToken(body.access_token);
      await loadCurrentUser(body.access_token);
      message.success('登录成功');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  async function loadAll() {
    if (!token) return;
    setLoading(true);
    try {
      const [nextSummary, nextTargetSummary, nextEvents, nextRules, nextTargets, nextClusters, nextChannels, nextRecords, nextNodeSummary, nextMonitoredServerSummary, nextExporterSummary, nextGrafanaDashboards, nextGrafanaViews] = await Promise.all([
        request<AlertSummary>('/alert-events/summary', token),
        request<TargetSummary>('/targets/summary', token),
        request<AlertEvent[]>('/alert-events?limit=50', token),
        request<AlertRule[]>('/alert-rules', token),
        request<MonitorTarget[]>('/targets', token),
        request<ManagedCluster[]>('/clusters', token).catch(() => []),
        request<NotificationChannel[]>('/notification-channels', token),
        request<NotificationRecord[]>('/notification-records?limit=50', token),
        request<NodeSummary>('/monitoring/exporter/nodes/summary', token).catch(() => null),
        request<NodeSummary>('/targets/exporters/resources', token).catch(() => null),
        request<ExporterSummary>('/targets/exporters/summary', token).catch(() => null),
        request<{ count: number; dashboards: GrafanaDashboard[] }>('/grafana/dashboards', token).catch((error) => {
          setGrafanaError(error instanceof Error ? error.message : '加载 Grafana 仪表盘失败');
          return null;
        }),
        request<GrafanaViews>('/grafana/target-views', token).catch((error) => {
          setGrafanaError(error instanceof Error ? error.message : '加载 Grafana 可视化视图失败');
          return null;
        }),
      ]);
      setSummary(nextSummary);
      setTargetSummary(nextTargetSummary);
      setEvents(nextEvents);
      setRules(nextRules);
      setTargets(nextTargets);
      setClusters(nextClusters);
      setChannels(nextChannels);
      setRecords(nextRecords);
      setNodeSummary(nextNodeSummary);
      setMonitoredServerSummary(nextMonitoredServerSummary);
      setExporterSummary(nextExporterSummary);
      setGrafanaDashboards(nextGrafanaDashboards?.dashboards || []);
      setGrafanaViews(nextGrafanaViews);
      if (nextGrafanaDashboards || nextGrafanaViews) setGrafanaError('');
      await loadLatestTargetChecks(nextTargets);
      if (selectedTargetId && nextTargets.some((target) => target.id === selectedTargetId)) {
        await loadTargetHistory(selectedTargetId);
      } else if (!selectedTargetId && nextTargets.length > 0) {
        setSelectedTargetId(nextTargets[0].id);
        await loadTargetHistory(nextTargets[0].id);
      } else if (nextTargets.length === 0) {
        setSelectedTargetId(null);
        setSelectedTargetChecks([]);
      }
      if (selectedClusterId && nextClusters.some((cluster) => cluster.id === selectedClusterId)) {
        await loadClusterDetails(selectedClusterId);
      } else if (!selectedClusterId && nextClusters.length > 0) {
        setSelectedClusterId(nextClusters[0].id);
        await loadClusterDetails(nextClusters[0].id);
      } else if (nextClusters.length === 0) {
        setSelectedClusterId(null);
        setClusterInstall(null);
        setClusterHeartbeats([]);
        setClusterReports([]);
      }
    } catch (error) {
      handleRequestError(error, '加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function createTarget(values: Partial<MonitorTarget>) {
    if (!token) return;
    try {
      await request('/targets', token, {
        method: 'POST',
        body: JSON.stringify({
          name: values.name,
          target_type: values.target_type,
          exporter_kind: values.target_type === 'exporter' ? (values.exporter_kind || 'node') : null,
          endpoint: values.endpoint,
          expected_keyword: values.expected_keyword || null,
          description: values.description || '',
        }),
      });
      targetForm.resetFields();
      message.success('监控对象已创建');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '创建规则失败');
    }
  }

  async function checkTarget(target: MonitorTarget) {
    if (!token) return;
    setLoading(true);
    try {
      const check = await request<TargetCheck>(`/targets/${target.id}/check`, token, { method: 'POST', body: '{}' });
      setTargetChecks((current) => ({ ...current, [target.id]: check }));
      message.success(`检测完成：${displayText(check.status)}`);
      await loadAll();
    } catch (error) {
      handleRequestError(error, '检测失败');
    } finally {
      setLoading(false);
    }
  }

  async function deleteTarget(target: MonitorTarget) {
    if (!token) return;
    try {
      await request(`/targets/${target.id}`, token, { method: 'DELETE' });
      message.success('监控对象已删除');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '删除失败');
    }
  }

  async function evaluateAlerts() {
    if (!token) return;
    setLoading(true);
    try {
      const [nodeResult, targetResult] = await Promise.all([
        request<{ triggered_count: number; resolved_count: number }>('/alert-events/evaluate/nodes', token, { method: 'POST', body: '{}' }),
        request<{ triggered_count: number; resolved_count: number }>('/alert-events/evaluate/targets', token, { method: 'POST', body: '{}' }),
      ]);
      message.success(`告警评估完成：节点触发 ${nodeResult.triggered_count} 条，监控对象触发 ${targetResult.triggered_count} 条`);
      await loadAll();
    } catch (error) {
      handleRequestError(error, '告警评估失败');
    } finally {
      setLoading(false);
    }
  }

  async function createRule(values: Partial<AlertRule>) {
    if (!token) return;
    try {
      await request('/alert-rules', token, {
        method: 'POST',
        body: JSON.stringify({ name: values.name, scope: values.scope || 'node', metric: values.metric, operator: values.operator, threshold: values.threshold, level: values.level, enabled: true, description: values.description || '' }),
      });
      ruleForm.resetFields();
      message.success('规则已创建');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '创建规则失败');
    }
  }

  async function toggleRule(rule: AlertRule, enabled: boolean) {
    if (!token) return;
    try {
      await request(`/alert-rules/${rule.id}`, token, { method: 'PUT', body: JSON.stringify({ enabled }) });
      message.success(enabled ? '规则已启用' : '规则已停用');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '更新规则失败');
    }
  }

  async function deleteRule(rule: AlertRule) {
    if (!token) return;
    try {
      await request(`/alert-rules/${rule.id}`, token, { method: 'DELETE' });
      message.success('规则已删除');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '删除失败');
    }
  }


  async function createCluster(values: { name: string; provider?: string; api_server?: string; description?: string }) {
    if (!token) return;
    try {
      const cluster = await request<ManagedCluster>('/clusters', token, {
        method: 'POST',
        body: JSON.stringify({
          name: values.name,
          provider: values.provider || 'kubernetes',
          api_server: values.api_server || null,
          description: values.description || null,
        }),
      });
      clusterForm.resetFields();
      setSelectedClusterId(cluster.id);
      message.success('集群已添加');
      await loadAll();
      await loadClusterDetails(cluster.id);
    } catch (error) {
      handleRequestError(error, '添加集群失败');
    }
  }

  async function loadClusterDetails(clusterId: number) {
    if (!token) return;
    try {
      const [install, heartbeats, reports] = await Promise.all([
        request<ManagedClusterInstall>(`/clusters/${clusterId}/install`, token),
        request<ClusterAgentHeartbeat[]>(`/clusters/${clusterId}/heartbeats?limit=20`, token),
        request<ClusterAgentReport[]>(`/clusters/${clusterId}/reports?limit=50`, token),
      ]);
      setClusterInstall(install);
      setClusterHeartbeats(heartbeats);
      setClusterReports(reports);
    } catch (error) {
      handleRequestError(error, '加载集群详情失败');
    }
  }

  async function deleteCluster(cluster: ManagedCluster) {
    if (!token) return;
    try {
      await request(`/clusters/${cluster.id}`, token, { method: 'DELETE' });
      message.success('集群已删除');
      if (selectedClusterId === cluster.id) {
        setSelectedClusterId(null);
        setClusterInstall(null);
        setClusterHeartbeats([]);
        setClusterReports([]);
      }
      await loadAll();
    } catch (error) {
      handleRequestError(error, '删除集群失败');
    }
  }

  async function rotateClusterToken(cluster: ManagedCluster) {
    if (!token) return;
    try {
      const updated = await request<ManagedCluster>(`/clusters/${cluster.id}/rotate-token`, token, { method: 'POST', body: '{}' });
      message.success('Agent Token 已重新生成，旧 Agent 需要重新安装');
      setSelectedClusterId(updated.id);
      await loadAll();
      await loadClusterDetails(updated.id);
    } catch (error) {
      handleRequestError(error, '重新生成 Token 失败');
    }
  }


  async function queryLogs() {
    if (!token) return;
    const target = targets.find((item) => item.id === logTargetId) || null;
    const query = logQueryMode === 'advanced'
      ? logQuery.trim()
      : buildSimpleLogQL({
        namespace: logNamespace,
        app: logApp,
        level: logLevel,
        keyword: logKeyword,
        targetKeyword: targetLogKeyword(target),
      });
    if (!query) return;
    setLogQuery(query);
    setLoading(true);
    try {
      const data = await request<any>(`/monitoring/loki/query?query=${encodeURIComponent(query)}&limit=${logLimit}&minutes=${logRangeMinutes}`, token);
      const rows = parseLokiEntries(data);
      setLogEntries(rows);
      message.success(`已加载 ${rows.length} 行日志`);
    } catch (error) {
      handleRequestError(error, '查询日志失败');
    } finally {
      setLoading(false);
    }
  }
  async function sendPending() {
    if (!token) return;
    setLoading(true);
    try {
      const result = await request<{ total: number; sent: number; failed: number; skipped: number }>('/notification-records/send-pending', token, { method: 'POST', body: '{}' });
      message.success(`已处理 ${result.total} 条，发送成功 ${result.sent} 条，失败 ${result.failed} 条，跳过 ${result.skipped} 条`);
      await loadAll();
    } catch (error) {
      handleRequestError(error, '发送失败');
    } finally {
      setLoading(false);
    }
  }


  function buildAIContext(conversation: AIChatMessage[], activities: AlertEventActivity[] = selectedAlertActivities) {
    return {
      context_type: 'analysis_session',
      target: selectedTarget,
      latest_check: selectedLatestCheck,
      recent_checks: selectedTargetChecks.slice(0, 10),
      selected_alert: selectedAlert,
      selected_alert_activities: activities.slice(0, 20),
      selected_alert_activity_summary: {
        total: activities.length,
        last_action: activities[0]?.action || null,
        last_note: activities[0]?.note || null,
        last_actor: activities[0]?.actor || null,
        last_created_at: activities[0]?.created_at || null,
      },
      target_alerts: targetAlerts.slice(0, 20),
      conversation: conversation.slice(-10),
    };
  }

  async function sendAIMessage(content: string, baseMessages: AIChatMessage[] = aiMessages, activityOverride?: AlertEventActivity[]) {
    if (!token || !selectedTarget) return;
    const question = content.trim();
    if (!question) return;
    const userMessage: AIChatMessage = { role: 'user', content: question, created_at: new Date().toISOString() };
    const nextMessages = [...baseMessages, userMessage];
    setAiMessages(nextMessages);
    setAiInput('');
    setLoading(true);
    try {
      const result = await request<AIAnalysis>('/assistant/analyze', token, {
        method: 'POST',
        body: JSON.stringify({ question, context: buildAIContext(nextMessages, activityOverride) }),
      });
      const assistantMessage: AIChatMessage = { role: 'assistant', content: result.summary, created_at: new Date().toISOString() };
      setAiResult(result);
      setAiMessages([...nextMessages, assistantMessage]);
      setAiSessionActive(true);
      message.success('AI 分析完成');
    } catch (error) {
      handleRequestError(error, 'AI 分析失败');
      setAiMessages(baseMessages);
    } finally {
      setLoading(false);
    }
  }

  async function startAIAnalysis() {
    if (!selectedTarget) {
      message.warning('请先选择监控对象');
      return;
    }
    if (!selectedAlert) {
      message.warning('请先选择该监控对象下的告警');
      return;
    }
    const firstQuestion = aiQuestion || '分析当前监控对象和所选告警，给出恢复步骤';
    const activities = await loadSelectedAlertActivities(selectedAlert.id);
    setAiSessionActive(true);
    setAiMessages([]);
    setAiResult(null);
    await sendAIMessage(firstQuestion, [], activities);
  }

  async function fetchEventActivities(eventId: number) {
    if (!token) return [];
    return request<AlertEventActivity[]>(`/alert-events/${eventId}/activities`, token);
  }

  async function loadEventActivities(eventId: number) {
    if (!token) return;
    try {
      const rows = await fetchEventActivities(eventId);
      setEventActivities(rows);
    } catch (error) {
      handleRequestError(error, '加载告警时间线失败');
    }
  }

  async function loadSelectedAlertActivities(eventId: number) {
    if (!token) return [];
    try {
      const rows = await fetchEventActivities(eventId);
      setSelectedAlertActivities(rows);
      return rows;
    } catch (error) {
      handleRequestError(error, '加载告警处理历史失败');
      setSelectedAlertActivities([]);
      return [];
    }
  }

  async function createEventNote() {
    if (!token || !selectedEvent || !eventNote.trim()) return;
    setLoading(true);
    try {
      await request<AlertEventActivity>(`/alert-events/${selectedEvent.id}/activities`, token, {
        method: 'POST',
        body: JSON.stringify({ action: 'note', note: eventNote.trim() }),
      });
      setEventNote('');
      await loadEventActivities(selectedEvent.id);
      if (selectedAlertId === selectedEvent.id) {
        await loadSelectedAlertActivities(selectedEvent.id);
      }
      message.success('记录已添加');
    } catch (error) {
      handleRequestError(error, '添加记录失败');
    } finally {
      setLoading(false);
    }
  }

  async function saveAIResultAsAlertNote() {
    if (!token || !selectedAlert || !aiResult?.summary) return;
    const note = `AI 分析摘要：\n${aiResult.summary}`.slice(0, 1000);
    setLoading(true);
    try {
      await request<AlertEventActivity>(`/alert-events/${selectedAlert.id}/activities`, token, {
        method: 'POST',
        body: JSON.stringify({ action: 'note', note }),
      });
      await loadSelectedAlertActivities(selectedAlert.id);
      if (selectedEventId === selectedAlert.id) {
        await loadEventActivities(selectedAlert.id);
      }
      message.success('AI 分析已保存到告警时间线');
    } catch (error) {
      handleRequestError(error, '保存 AI 记录失败');
    } finally {
      setLoading(false);
    }
  }
  function openEventDetail(event: AlertEvent) {
    setSelectedEventId(event.id);
    const instance = event.instance.toLowerCase();
    const matchedTarget = targets.find((target) => {
      const endpoint = target.endpoint.toLowerCase();
      const endpointHost = endpoint.replace(/^https?:\/\//, '').split('/')[0];
      return instance === endpoint || instance === endpointHost || instance.includes(endpointHost) || endpointHost.includes(instance);
    });
    if (matchedTarget) {
      setSelectedTargetId(matchedTarget.id);
      void loadTargetHistory(matchedTarget.id);
    }
    setSelectedAlertId(event.id);
    void loadSelectedAlertActivities(event.id);
  }

  async function updateAlertEventStatus(event: AlertEvent, action: 'ack' | 'resolve') {
    if (!token) return;
    setLoading(true);
    try {
      const note = selectedEventId === event.id && eventNote.trim() ? eventNote.trim() : undefined;
      const updated = await request<AlertEvent>(`/alert-events/${event.id}/${action}`, token, { method: 'POST', body: JSON.stringify({ note }) });
      setEvents((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (selectedEventId === updated.id && action === 'resolve') {
        setSelectedEventId(updated.id);
      }
      message.success(action === 'ack' ? '告警已确认' : '告警已恢复');
      if (selectedEventId === updated.id) {
        setEventNote('');
        await loadEventActivities(updated.id);
      }
      if (selectedAlertId === updated.id) {
        await loadSelectedAlertActivities(updated.id);
      }
      await loadAll();
    } catch (error) {
      handleRequestError(error, action === 'ack' ? '确认告警失败' : '恢复告警失败');
    } finally {
      setLoading(false);
    }
  }

  async function updateHandlingStatus(event: AlertEvent, nextStatus: HandlingStatus, note?: string) {
    if (!token) return;
    setLoading(true);
    try {
      const updated = await request<AlertEvent>(`/alert-events/${event.id}/handling-status`, token, {
        method: 'POST',
        body: JSON.stringify({ handling_status: nextStatus, note: note || (selectedEventId === event.id && eventNote.trim() ? eventNote.trim() : undefined) }),
      });
      setEvents((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (selectedEventId === updated.id) {
        setEventNote('');
        await loadEventActivities(updated.id);
      }
      if (selectedAlertId === updated.id) {
        await loadSelectedAlertActivities(updated.id);
      }
      await loadAll();
      message.success(`处理状态已更新为 ${displayText(nextStatus)}`);
    } catch (error) {
      handleRequestError(error, '更新处理状态失败');
    } finally {
      setLoading(false);
    }
  }
  function analyzeSelectedEvent() {
    if (!selectedEvent) return;
    if (selectedEventTarget) {
      setSelectedTargetId(selectedEventTarget.id);
      void loadTargetHistory(selectedEventTarget.id);
    }
    setSelectedAlertId(selectedEvent.id);
    void loadSelectedAlertActivities(selectedEvent.id);
    setAiQuestion(`分析告警 ${selectedEvent.rule_name}，实例 ${selectedEvent.instance}。请给出可能原因、验证命令、恢复步骤和风险提示。`);
    setActivePage('assistant');
    message.info('已选择告警上下文，可以开始 AI 分析会话。');
  }
  function exitAIAnalysis() {
    setAiSessionActive(false);
    setAiMessages([]);
    setAiInput('');
    setAiResult(null);
  }

  async function createChannel(values: {
    name: string;
    channel_type: NotificationChannelType;
    target: string;
    provider?: string;
    levels?: string[];
    notify_on_triggered?: boolean;
    notify_on_resolved?: boolean;
    title_template?: string;
    content_template?: string;
    resolved_title_template?: string;
    resolved_content_template?: string;
    smtp_host?: string;
    smtp_port?: number;
    smtp_username?: string;
    smtp_password?: string;
    from_email?: string;
    use_tls?: boolean;
    use_ssl?: boolean;
  }) {
    if (!token) return;
    const commonConfig = {
      levels: values.levels?.length ? values.levels : ['general', 'severe', 'urgent'],
      notify_on_triggered: values.notify_on_triggered !== false,
      notify_on_resolved: values.notify_on_resolved !== false,
      title_template: values.title_template,
      content_template: values.content_template,
      resolved_title_template: values.resolved_title_template,
      resolved_content_template: values.resolved_content_template,
    };
    const config = values.channel_type === 'email'
      ? {
        ...commonConfig,
        to: values.target,
        smtp_host: values.smtp_host,
        smtp_port: values.smtp_port,
        smtp_username: values.smtp_username,
        smtp_password: values.smtp_password,
        from_email: values.from_email || values.smtp_username,
        use_tls: values.use_tls !== false,
        use_ssl: values.use_ssl === true,
      }
      : {
        ...commonConfig,
        url: values.target,
        provider: values.channel_type === 'webhook' ? (values.provider || 'generic') : values.channel_type,
      };
    try {
      await request('/notification-channels', token, {
        method: 'POST',
        body: JSON.stringify({ name: values.name, channel_type: values.channel_type, config, enabled: true }),
      });
      channelForm.resetFields();
      message.success('通知渠道已创建');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '创建通知渠道失败');
    }
  }

  async function deleteChannel(channel: NotificationChannel) {
    if (!token) return;
    try {
      await request(`/notification-channels/${channel.id}`, token, { method: 'DELETE' });
      message.success('通知渠道已删除');
      await loadAll();
    } catch (error) {
      handleRequestError(error, '删除失败');
    }
  }

  useEffect(() => {
    if (token) void loadCurrentUser(token);
  }, [token]);

  useEffect(() => { void loadAll(); }, [token]);

  useEffect(() => {
    if (token && currentUser?.role === 'root') void loadPlatformHealth();
    if (currentUser && currentUser.role !== 'root' && activePage === 'platformHealth') setActivePage('overview');
  }, [token, currentUser?.role, activePage]);

  useEffect(() => {
    if (!selectedTarget) {
      setSelectedAlertId(null);
      setSelectedAlertActivities([]);
      return;
    }
    if (targetAlerts.length === 0) {
      setSelectedAlertId(null);
      setSelectedAlertActivities([]);
      return;
    }
    if (!selectedAlertId || !targetAlerts.some((event) => event.id === selectedAlertId)) {
      const nextAlertId = targetAlerts[0].id;
      setSelectedAlertId(nextAlertId);
      void loadSelectedAlertActivities(nextAlertId);
    }
  }, [selectedTarget, selectedAlertId, targetAlerts]);

  if (!token) {
    const isLogin = authMode === 'login';
    return (
      <ConfigProvider theme={{ token: { borderRadius: 6, colorPrimary: '#1677ff' } }}>
        <div className="loginPage">
          <Card className="loginCard" title="智能运维监控平台">
            <Space direction="vertical" size={16} className="fullWidth">
              <Alert type="info" showIcon message={isLogin ? '请使用账号登录，admin 为 root 管理员账号。' : '注册后默认为普通用户，无法查看平台自身健康状态。'} />
              <Form form={loginForm} layout="vertical" onFinish={isLogin ? login : register} initialValues={{ username: 'admin' }}>
                <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}><Input /></Form.Item>
                {!isLogin ? <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}><Input /></Form.Item> : null}
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}><Input.Password /></Form.Item>
                <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={loading} block>{isLogin ? '登录' : '注册账号'}</Button>
              </Form>
              <Button type="link" block onClick={() => setAuthMode(isLogin ? 'register' : 'login')}>
                {isLogin ? '没有账号？注册普通用户' : '已有账号？返回登录'}
              </Button>
            </Space>
          </Card>
        </div>
      </ConfigProvider>
    );
  }

  const eventColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '规则', dataIndex: 'rule_name', ellipsis: true },
    { title: '实例', dataIndex: 'instance', ellipsis: true },
    { title: '等级', dataIndex: 'level', render: (v: string) => <Tag color={levelColor(v)}>{displayText(v)}</Tag> },
    { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={statusColor(v)}>{displayText(v)}</Tag> },
    { title: '处理状态', dataIndex: 'handling_status', render: (v: string, row: AlertEvent) => <Select size="small" value={v as HandlingStatus} style={{ width: 132 }} options={handlingStatuses} onChange={(next) => updateHandlingStatus(row, next)} /> },
    { title: '当前值', dataIndex: 'value' },
    { title: '操作', render: (_: unknown, row: AlertEvent) => <Space><Button size="small" onClick={() => openEventDetail(row)}>详情</Button><Button size="small" disabled={row.acknowledged} onClick={() => updateAlertEventStatus(row, 'ack')}>确认</Button><Button size="small" disabled={row.status === 'resolved'} onClick={() => updateAlertEventStatus(row, 'resolve')}>恢复</Button><Button size="small" icon={<BarChartOutlined />} onClick={() => openAlertGrafana(row)}>Grafana</Button></Space> },
  ];

  const targetColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '类型', dataIndex: 'target_type', render: (v: string) => <Tag>{displayText(v)}</Tag> },
    { title: 'Exporter 类型', render: (_: unknown, row: MonitorTarget) => row.exporter_kind ? <Tag color="blue">{row.exporter_kind}</Tag> : '-' },
    { title: '地址', dataIndex: 'endpoint', ellipsis: true },
    { title: '状态', render: (_: unknown, row: MonitorTarget) => {
      const check = targetChecks[row.id];
      return check ? <Tag color={statusColor(check.status)}>{displayText(check.status)}</Tag> : <Tag>未知</Tag>;
    } },
    { title: '延迟', render: (_: unknown, row: MonitorTarget) => targetChecks[row.id] ? `${targetChecks[row.id]!.response_time_ms} ms` : '-' },
    { title: 'HTTP', render: (_: unknown, row: MonitorTarget) => targetChecks[row.id]?.status_code ?? '-' },
    { title: '消息', render: (_: unknown, row: MonitorTarget) => targetChecks[row.id]?.message || '-', ellipsis: true },
    { title: '检测时间', render: (_: unknown, row: MonitorTarget) => targetChecks[row.id]?.checked_at ? new Date(targetChecks[row.id]!.checked_at).toLocaleString() : '-' },
    { title: '操作', fixed: 'right' as const, render: (_: unknown, row: MonitorTarget) => <Space><Button size="small" onClick={() => { setSelectedTargetId(row.id); void loadTargetHistory(row.id); }}>查看</Button><Button size="small" onClick={() => checkTarget(row)}>检测</Button><Button size="small" icon={<BarChartOutlined />} onClick={() => openTargetGrafana(row)}>Grafana</Button><Popconfirm title="确认删除这个监控对象？" onConfirm={() => deleteTarget(row)}><Button danger size="small">删除</Button></Popconfirm></Space> },
  ];

  const renderOverview = () => (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}><Card><Statistic title="活跃告警" value={summary?.active_count || 0} prefix={<WarningOutlined />} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="监控对象" value={targetSummary?.total || 0} suffix={`正常 ${targetSummary?.up || 0}`} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="节点" value={nodeSummary?.node_count || 0} suffix={nodeSummary?.avg_load1 != null ? `负载 ${nodeSummary.avg_load1}` : ''} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="通知" value={records.length} suffix={`失败 ${notificationStatus.failed || 0}`} prefix={<MailOutlined />} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} md={6}><Card><Statistic title="新建 / 未处理" value={summary?.handling_by_status?.new || 0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="排查中" value={summary?.handling_by_status?.investigating || 0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="处置中" value={summary?.handling_by_status?.mitigating || 0} /></Card></Col>
        <Col xs={24} md={6}><Card><Statistic title="观察中" value={summary?.handling_by_status?.watching || 0} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} lg={8}><Card title="监控对象状态"><ReactECharts option={targetStatusOption} style={{ height: 260 }} /></Card></Col>
        <Col xs={24} lg={8}><Card title="活跃告警等级"><ReactECharts option={chartOption} style={{ height: 260 }} /></Card></Col>
        <Col xs={24} lg={8}><Card title="平台节点"><ReactECharts option={nodeResourceOption} style={{ height: 260 }} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} lg={12}><Card title="被监控服务器 Exporter 资源"><ReactECharts option={monitoredServerResourceOption} style={{ height: 300 }} /></Card></Col>
        <Col xs={24} lg={12}><Card title="最近告警"><Table rowKey="id" dataSource={events.slice(0, 6)} pagination={false} size="small" columns={eventColumns} scroll={{ x: 900 }} /></Card></Col>
      </Row>
    </>
  );

  const renderTargets = () => (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="添加监控对象">
            <Form form={targetForm} layout="vertical" onFinish={createTarget} initialValues={{ target_type: 'website' }}>
              <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="首页" /></Form.Item>
              <Form.Item name="target_type" label="类型" rules={[{ required: true }]}><Select options={[{ label: '网站 - HTTP/HTTPS 页面', value: 'website' }, { label: '端口 - TCP 服务', value: 'port' }, { label: 'Exporter - Prometheus /metrics 指标地址', value: 'exporter' }]} /></Form.Item>
              {watchedTargetType === 'exporter' ? <Form.Item name="exporter_kind" label="Exporter 类型" initialValue="node" rules={[{ required: true }]}><Select options={exporterKindOptions} showSearch optionFilterProp="label" /></Form.Item> : null}
              <Form.Item name="endpoint" label="地址" rules={[{ required: true }]}><Input placeholder={endpointPlaceholder[watchedTargetType || 'website']} /></Form.Item>
              <Form.Item name="expected_keyword" label="期望关键字"><Input placeholder="可选，用于网站内容检测" /></Form.Item>
              <Alert type="info" showIcon message={targetTypeHelp[watchedTargetType || 'website']} />
              <Button type="primary" htmlType="submit">保存监控对象</Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={16}><Card title="监控对象"><Table rowKey="id" dataSource={targets} size="small" columns={targetColumns} pagination={{ pageSize: 8, showSizeChanger: true }} scroll={{ x: 1200 }} rowClassName={(row) => row.id === selectedTargetId ? 'selectedRow' : ''} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} lg={8}><Card title="监控对象数据">{selectedTarget ? <Descriptions column={1} size="small"><Descriptions.Item label="名称">{selectedTarget.name}</Descriptions.Item><Descriptions.Item label="类型"><Tag>{displayText(selectedTarget.target_type)}</Tag></Descriptions.Item><Descriptions.Item label="地址">{selectedTarget.endpoint}</Descriptions.Item><Descriptions.Item label="状态">{selectedLatestCheck ? <Tag color={statusColor(selectedLatestCheck.status)}>{displayText(selectedLatestCheck.status)}</Tag> : <Tag>未知</Tag>}</Descriptions.Item><Descriptions.Item label="响应">{selectedLatestCheck ? `${selectedLatestCheck.response_time_ms} ms` : '-'}</Descriptions.Item><Descriptions.Item label="消息">{selectedLatestCheck?.message || '-'}</Descriptions.Item></Descriptions> : <Empty description="请选择监控对象" />}</Card></Col>
        <Col xs={24} lg={16}><Card title="检测历史">{selectedTargetChecks.length > 0 ? <><ReactECharts option={targetTrendOption} style={{ height: 260 }} /><Table rowKey="check_id" dataSource={selectedTargetChecks} size="small" pagination={{ pageSize: 6 }} columns={[{ title: '时间', dataIndex: 'checked_at', render: (v: string) => new Date(v).toLocaleString() }, { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={statusColor(v)}>{displayText(v)}</Tag> }, { title: '延迟', dataIndex: 'response_time_ms', render: (v: number) => `${v} ms` }, { title: 'HTTP', dataIndex: 'status_code', render: (v: number | null) => v ?? '-' }, { title: '消息', dataIndex: 'message', ellipsis: true }]} /></> : <Empty description="暂无检测数据" />}</Card></Col>
      </Row>
      <TargetMetricsPanel target={selectedTarget} token={token} />
    </>
  );


  const selectedCluster = clusters.find((cluster) => cluster.id === selectedClusterId) || null;

  const renderClusters = () => (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="添加集群">
            <Form form={clusterForm} layout="vertical" onFinish={createCluster} initialValues={{ provider: 'kubernetes' }}>
              <Form.Item name="name" label="集群名称" rules={[{ required: true, message: '请输入集群名称' }]}><Input placeholder="生产集群 / 客户 A 集群" /></Form.Item>
              <Form.Item name="provider" label="类型" rules={[{ required: true }]}><Select options={[{ label: 'Kubernetes', value: 'kubernetes' }, { label: 'ACK / 阿里云 K8s', value: 'ack' }, { label: '自建 K8s', value: 'self-hosted' }]} /></Form.Item>
              <Form.Item name="api_server" label="API Server"><Input placeholder="可选，例如：https://10.0.0.1:6443" /></Form.Item>
              <Form.Item name="description" label="说明"><Input.TextArea rows={3} placeholder="可选，填写集群用途、负责人或网络说明" /></Form.Item>
              <Alert type="info" showIcon message="添加后会生成 Agent 安装命令。把命令复制到被监控集群执行，Agent 会采集节点、Pod、日志摘要并定时上报心跳。" />
              <Button type="primary" htmlType="submit">保存集群</Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="集群列表">
            <Table
              rowKey="id"
              dataSource={clusters}
              size="small"
              pagination={{ pageSize: 8 }}
              scroll={{ x: 1100 }}
              rowClassName={(row) => row.id === selectedClusterId ? 'selectedRow' : ''}
              columns={[
                { title: '名称', dataIndex: 'name', ellipsis: true },
                { title: '类型', dataIndex: 'provider', render: (value: string) => <Tag>{value}</Tag> },
                { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'online' ? 'green' : value === 'deleted' ? 'default' : 'gold'}>{value === 'online' ? '在线' : value === 'pending' ? '待安装' : value}</Tag> },
                { title: '节点 / Pod', render: (_: unknown, row: ManagedCluster) => `${row.node_count} / ${row.pod_count}` },
                { title: '上报', render: (_: unknown, row: ManagedCluster) => `指标 ${row.metrics_count} / 日志 ${row.logs_count} / 告警 ${row.alerts_count}` },
                { title: '最后心跳', render: (_: unknown, row: ManagedCluster) => row.last_heartbeat_at ? new Date(row.last_heartbeat_at).toLocaleString() : '-' },
                { title: '操作', fixed: 'right' as const, render: (_: unknown, row: ManagedCluster) => <Space><Button size="small" onClick={() => { setSelectedClusterId(row.id); void loadClusterDetails(row.id); }}>查看</Button><Button size="small" onClick={() => rotateClusterToken(row)}>重置 Token</Button><Popconfirm title="确认删除这个集群？" onConfirm={() => deleteCluster(row)}><Button danger size="small">删除</Button></Popconfirm></Space> },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} className="section">
        <Col xs={24} lg={10}>
          <Card title="Agent 安装命令" extra={selectedCluster ? <Tag>{selectedCluster.name}</Tag> : null}>
            {selectedCluster && clusterInstall ? (
              <Space direction="vertical" className="fullWidth" size={12}>
                <Alert type="warning" showIcon message="请在被监控的 Kubernetes 集群控制节点执行。执行前确认该集群可以访问本平台 API 地址。" />
                <Input.TextArea value={clusterInstall.install_command} rows={16} readOnly />
                <Space>
                  <Button onClick={() => navigator.clipboard.writeText(clusterInstall.install_command).then(() => message.success('已复制安装命令'))}>复制命令</Button>
                  <Button onClick={() => loadClusterDetails(selectedCluster.id)}>刷新详情</Button>
                </Space>
              </Space>
            ) : <Empty description="请选择集群" />}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Agent 最近心跳">
            <Table rowKey="id" dataSource={clusterHeartbeats} size="small" pagination={{ pageSize: 6 }} columns={[
              { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString() },
              { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'online' ? 'green' : 'gold'}>{value}</Tag> },
              { title: '版本', dataIndex: 'agent_version', render: (value: string | null) => value || '-' },
              { title: '节点', dataIndex: 'node_count' },
              { title: 'Pod', dataIndex: 'pod_count' },
              { title: '消息', dataIndex: 'message', ellipsis: true },
            ]} />
          </Card>
        </Col>
      </Row>
      <Card className="section" title="Agent 上报数据">
        <Table rowKey="id" dataSource={clusterReports} size="small" pagination={{ pageSize: 10 }} scroll={{ x: 1000 }} columns={[
          { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString() },
          { title: '类型', dataIndex: 'report_type', render: (value: string) => <Tag>{value === 'metric' ? '指标' : value === 'log' ? '日志' : '告警'}</Tag> },
          { title: '来源', dataIndex: 'source', ellipsis: true },
          { title: '等级', dataIndex: 'level', render: (value: string | null) => value ? <Tag color={levelColor(value)}>{displayText(value)}</Tag> : '-' },
          { title: '消息', dataIndex: 'message', ellipsis: true },
          { title: '原始内容', dataIndex: 'payload', render: (value: Record<string, unknown>) => JSON.stringify(value), ellipsis: true },
        ]} />
      </Card>
    </>
  );

  const renderRules = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="添加告警规则">
          <Form form={ruleForm} layout="vertical" onFinish={createRule} initialValues={{ scope: 'node', metric: 'cpu_usage_percent', operator: '>=', threshold: 80, level: 'general' }}>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="CPU 告警或网站不可用" /></Form.Item>
            <Form.Item name="scope" label="范围" rules={[{ required: true }]}><Select options={[{ label: '节点资源', value: 'node' }, { label: '监控对象：网站 / 端口 / Exporter', value: 'target' }]} onChange={(scope) => { const metric = scope === 'target' ? 'status_down' : 'cpu_usage_percent'; ruleForm.setFieldsValue({ scope, metric, ...(scope === 'target' ? targetRuleDefaults.status_down : { operator: '>=', threshold: 80 }) }); }} /></Form.Item>
            <Form.Item name="metric" label="指标" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) || String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())} options={(watchedRuleScope || 'node') === 'target' ? targetRuleMetricOptions : nodeRuleMetricOptions} onChange={(metric) => { const defaults = targetRuleDefaults[metric]; if (defaults) ruleForm.setFieldsValue(defaults); }} /></Form.Item>
            <Space.Compact block><Form.Item name="operator" rules={[{ required: true }]} style={{ width: 120 }}><Select options={['>=', '>', '<=', '<', '=='].map((value) => ({ label: value, value }))} /></Form.Item><Form.Item name="threshold" rules={[{ required: true }]} style={{ flex: 1 }}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Space.Compact>
            <Form.Item name="level" label="等级" rules={[{ required: true }]}><Select options={[{ label: '一般', value: 'general' }, { label: '严重', value: 'severe' }, { label: '紧急', value: 'urgent' }]} /></Form.Item>
            <Form.Item name="description" label="说明"><Input.TextArea rows={2} placeholder="可选，填写处理建议或业务影响" /></Form.Item>
            <Button type="primary" htmlType="submit">保存规则</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} lg={16}><Card title="规则列表"><Table rowKey="id" dataSource={rules} size="small" pagination={{ pageSize: 10, showSizeChanger: true }} scroll={{ x: 900 }} columns={[{ title: 'ID', dataIndex: 'id', width: 70 }, { title: '名称', dataIndex: 'name', ellipsis: true }, { title: '范围', dataIndex: 'scope', render: (v: string) => <Tag>{displayText(v)}</Tag> }, { title: '指标', dataIndex: 'metric', ellipsis: true }, { title: '条件', render: (_: unknown, row: AlertRule) => `${row.operator} ${row.threshold}` }, { title: '等级', dataIndex: 'level', render: (v: string) => <Tag color={levelColor(v)}>{displayText(v)}</Tag> }, { title: '启用', dataIndex: 'enabled', render: (_: unknown, row: AlertRule) => <Switch checked={row.enabled} onChange={(checked) => toggleRule(row, checked)} /> }, { title: '操作', fixed: 'right' as const, render: (_: unknown, row: AlertRule) => <Popconfirm title="确认删除这条规则？" onConfirm={() => deleteRule(row)}><Button danger size="small">删除</Button></Popconfirm> }]} /></Card></Col>
    </Row>
  );

  const renderEvents = () => <Card title="告警事件" extra={<Button type="primary" onClick={evaluateAlerts} loading={loading}>执行告警评估</Button>}><Table rowKey="id" dataSource={events} size="small" columns={eventColumns} pagination={{ pageSize: 10 }} scroll={{ x: 1000 }} /></Card>;

  const renderChannels = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="添加通知渠道">
          <Form
            form={channelForm}
            layout="vertical"
            onFinish={createChannel}
            initialValues={{
              channel_type: 'webhook',
              provider: 'generic',
              levels: ['urgent'],
              notify_on_triggered: true,
              notify_on_resolved: true,
              title_template: '告警触发：$rule_name',
              content_template: '实例：$instance\n指标：$metric\n条件：$value $operator $threshold\n等级：$level\n消息：$message',
              resolved_title_template: '告警已恢复：$rule_name',
              resolved_content_template: '实例：$instance\n指标：$metric\n最后值：$value\n等级：$level\n消息：$message',
            }}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="紧急告警邮箱" /></Form.Item>
            <Form.Item name="channel_type" label="类型" rules={[{ required: true }]}>
              <Select options={[{ label: 'Webhook', value: 'webhook' }, { label: '邮箱', value: 'email' }, { label: '钉钉', value: 'dingtalk' }, { label: '飞书', value: 'feishu' }, { label: '企业微信', value: 'wecom' }]} />
            </Form.Item>
            {watchedChannelType === 'webhook' ? (
              <Form.Item name="provider" label="Webhook 提供方" rules={[{ required: true }]}>
                <Select options={[{ label: '通用 JSON', value: 'generic' }, { label: '企业微信', value: 'wecom' }, { label: '钉钉', value: 'dingtalk' }, { label: '飞书', value: 'feishu' }]} />
              </Form.Item>
            ) : null}
            <Form.Item name="target" label={watchedChannelType === 'email' ? '收件邮箱' : 'Webhook 地址'} rules={[{ required: true }]}>
              <Input placeholder={watchedChannelType === 'email' ? 'dd_1698@qq.com' : '机器人 Webhook 地址'} />
            </Form.Item>
            {watchedChannelType === 'email' ? (
              <>
                <Alert type="warning" showIcon message="邮箱通知需要配置发件邮箱 SMTP。QQ 邮箱通常使用 smtp.qq.com、465 SSL 或 587 STARTTLS，密码填写邮箱授权码，不是登录密码。" />
                <Row gutter={12}>
                  <Col xs={24} md={16}><Form.Item name="smtp_host" label="SMTP 服务器" rules={[{ required: true, message: '请输入 SMTP 服务器' }]}><Input placeholder="smtp.qq.com" /></Form.Item></Col>
                  <Col xs={24} md={8}><Form.Item name="smtp_port" label="SMTP 端口" initialValue={465} rules={[{ required: true, message: '请输入端口' }]}><InputNumber min={1} max={65535} className="fullWidth" /></Form.Item></Col>
                </Row>
                <Form.Item name="smtp_username" label="发件账号" rules={[{ required: true, message: '请输入发件邮箱账号' }]}><Input placeholder="your@qq.com" /></Form.Item>
                <Form.Item name="smtp_password" label="SMTP 授权码 / 密码" rules={[{ required: true, message: '请输入 SMTP 授权码' }]}><Input.Password placeholder="邮箱授权码" /></Form.Item>
                <Form.Item name="from_email" label="发件邮箱"><Input placeholder="默认使用发件账号" /></Form.Item>
                <Space size={24}>
                  <Form.Item name="use_ssl" label="SSL 连接" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
                  <Form.Item name="use_tls" label="STARTTLS" valuePropName="checked" initialValue={false}><Switch /></Form.Item>
                </Space>
              </>
            ) : null}            <Form.Item name="levels" label="发送等级" rules={[{ required: true }]}>
              <Select mode="multiple" options={[{ label: '一般', value: 'general' }, { label: '严重', value: 'severe' }, { label: '紧急', value: 'urgent' }]} />
            </Form.Item>
            <Form.Item name="notify_on_triggered" label="告警触发时发送" valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="notify_on_resolved" label="告警恢复时发送" valuePropName="checked"><Switch /></Form.Item>
            <Alert type="info" showIcon message="模板变量：$rule_name、$level、$instance、$metric、$value、$operator、$threshold、$message、$trigger_count" />
            <Form.Item name="title_template" label="触发通知标题"><Input /></Form.Item>
            <Form.Item name="content_template" label="触发通知正文"><Input.TextArea rows={4} /></Form.Item>
            <Form.Item name="resolved_title_template" label="恢复通知标题"><Input /></Form.Item>
            <Form.Item name="resolved_content_template" label="恢复通知正文"><Input.TextArea rows={3} /></Form.Item>
            <Button type="primary" htmlType="submit">保存渠道</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} lg={16}>
        <Card title="通知渠道">
          <Table
            rowKey="id"
            dataSource={channels}
            size="small"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1000 }}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 70 },
              { title: '名称', dataIndex: 'name' },
              { title: '类型', dataIndex: 'channel_type', render: (v: string) => <Tag>{displayText(v)}</Tag> },
              { title: '等级', render: (_: unknown, row: NotificationChannel) => Array.isArray(row.config?.levels) ? (row.config.levels as string[]).map((level) => <Tag key={level} color={levelColor(level)}>{displayText(level)}</Tag>) : '-' },
              { title: '触发', render: (_: unknown, row: NotificationChannel) => row.config?.notify_on_triggered === false ? <Tag>不发送</Tag> : <Tag color="green">发送</Tag> },
              { title: '恢复', render: (_: unknown, row: NotificationChannel) => row.config?.notify_on_resolved === false ? <Tag>不发送</Tag> : <Tag color="green">发送</Tag> },
              { title: '启用', dataIndex: 'enabled', render: (v: boolean) => v ? <Tag color="green">已启用</Tag> : <Tag>已停用</Tag> },
              { title: '操作', fixed: 'right' as const, render: (_: unknown, row: NotificationChannel) => <Space><Button size="small" onClick={() => request(`/notification-channels/${row.id}/test`, token, { method: 'POST', body: '{}' }).then(() => message.success('测试通知已发送')).catch((error) => handleRequestError(error, '测试通知失败'))}>测试发送</Button><Popconfirm title="确认删除这个通知渠道？" onConfirm={() => deleteChannel(row)}><Button danger size="small">删除</Button></Popconfirm></Space> },
            ]}
          />
        </Card>
      </Col>
    </Row>
  );

  const renderAlertDrawer = () => (
    <Drawer
      title="告警详情"
      width={720}
      open={!!selectedEvent}
      onClose={() => {
        setSelectedEventId(null);
        setEventActivities([]);
        setEventNote('');
      }}
    >
      {selectedEvent ? (
        <Space direction="vertical" className="fullWidth" size={16}>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="规则">{selectedEvent.rule_name}</Descriptions.Item>
            <Descriptions.Item label="实例">{selectedEvent.instance}</Descriptions.Item>
            <Descriptions.Item label="等级"><Tag color={levelColor(selectedEvent.level)}>{displayText(selectedEvent.level)}</Tag></Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={statusColor(selectedEvent.status)}>{displayText(selectedEvent.status)}</Tag></Descriptions.Item>
            <Descriptions.Item label="处理状态"><Tag>{displayText(selectedEvent.handling_status)}</Tag></Descriptions.Item>
            <Descriptions.Item label="指标">{selectedEvent.metric}</Descriptions.Item>
            <Descriptions.Item label="当前值">{selectedEvent.value}</Descriptions.Item>
            <Descriptions.Item label="阈值">{selectedEvent.operator} {selectedEvent.threshold}</Descriptions.Item>
            <Descriptions.Item label="触发次数">{selectedEvent.trigger_count}</Descriptions.Item>
            <Descriptions.Item label="最近触发">{new Date(selectedEvent.last_triggered_at).toLocaleString()}</Descriptions.Item>
          </Descriptions>
          <Space wrap>
            <Button disabled={selectedEvent.acknowledged} onClick={() => updateAlertEventStatus(selectedEvent, 'ack')}>确认告警</Button>
            <Button disabled={selectedEvent.status === 'resolved'} onClick={() => updateAlertEventStatus(selectedEvent, 'resolve')}>标记恢复</Button>
            <Select
              value={selectedEvent.handling_status as HandlingStatus}
              style={{ width: 160 }}
              options={handlingStatuses}
              onChange={(next) => updateHandlingStatus(selectedEvent, next)}
            />
            <Button icon={<RobotOutlined />} onClick={analyzeSelectedEvent}>用 AI 分析</Button>
            <Button icon={<BarChartOutlined />} onClick={() => openAlertGrafana(selectedEvent)}>打开 Grafana</Button>
          </Space>
          <Card size="small" title="处理记录">
            <Space direction="vertical" className="fullWidth">
              <Input.TextArea rows={3} value={eventNote} onChange={(event) => setEventNote(event.target.value)} placeholder="记录处理动作、排查结论或恢复说明" />
              <Button type="primary" onClick={createEventNote} loading={loading} disabled={!eventNote.trim()}>添加记录</Button>
              <Table
                rowKey="id"
                dataSource={eventActivities}
                size="small"
                pagination={{ pageSize: 5 }}
                columns={[
                  { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString() },
                  { title: '动作', dataIndex: 'action', render: (value: string) => <Tag>{displayText(value)}</Tag> },
                  { title: '处理人', dataIndex: 'actor' },
                  { title: '备注', dataIndex: 'note', ellipsis: true },
                ]}
              />
            </Space>
          </Card>
          <Card size="small" title="通知记录">
            <Table
              rowKey="id"
              dataSource={selectedEventNotifications}
              size="small"
              pagination={{ pageSize: 5 }}
              columns={[
                { title: '标题', dataIndex: 'title', ellipsis: true },
                { title: '类型', dataIndex: 'notification_type', render: (value: string) => <Tag>{displayText(value)}</Tag> },
                { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{displayText(value)}</Tag> },
                { title: '错误', dataIndex: 'error_message', ellipsis: true },
              ]}
            />
          </Card>
          {aiResult?.summary ? <Button icon={<CheckCircleOutlined />} onClick={saveAIResultAsAlertNote}>保存当前 AI 分析到处理记录</Button> : null}
        </Space>
      ) : <Empty description="请选择告警事件" />}
    </Drawer>
  );
  const renderAssistant = () => (
    <Space direction="vertical" className="fullWidth" size={16}>
      <Card title="AI 告警分析助手">
        <Alert
          type="info"
          showIcon
          message="正常监控不会调用大模型。只有你选择监控对象和告警，并点击开始分析或继续追问时，平台才会把该上下文发送给 AI。"
        />
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="分析上下文">
            <Space direction="vertical" className="fullWidth" size={12}>
              <Select
                placeholder="选择监控对象"
                value={selectedTargetId ?? undefined}
                onChange={(value) => {
                  setSelectedTargetId(value);
                  setSelectedAlertId(null);
                  setAiSessionActive(false);
                  setAiMessages([]);
                  void loadTargetHistory(value);
                }}
                options={targets.map((target) => ({ label: `${target.name} - ${target.endpoint}`, value: target.id }))}
                showSearch
                optionFilterProp="label"
              />
              <Select
                placeholder="选择该对象下的告警"
                value={selectedAlert?.id ?? undefined}
                disabled={!selectedTarget}
                onChange={(value) => {
                  setSelectedAlertId(value);
                  setAiSessionActive(false);
                  setAiMessages([]);
                  void loadSelectedAlertActivities(value);
                }}
                options={targetAlerts.map((event) => ({ label: `${event.rule_name} - ${displayText(event.level)} - ${displayText(event.status)}`, value: event.id }))}
                showSearch
                optionFilterProp="label"
              />
              {selectedTarget ? (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="对象">{selectedTarget.name}</Descriptions.Item>
                  <Descriptions.Item label="类型"><Tag>{displayText(selectedTarget.target_type)}</Tag></Descriptions.Item>
                  <Descriptions.Item label="地址">{selectedTarget.endpoint}</Descriptions.Item>
                  <Descriptions.Item label="最近状态">{selectedLatestCheck ? <Tag color={statusColor(selectedLatestCheck.status)}>{displayText(selectedLatestCheck.status)}</Tag> : <Tag>未知</Tag>}</Descriptions.Item>
                </Descriptions>
              ) : <Empty description="先选择一个监控对象" />}
              {selectedAlert ? (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="告警规则">{selectedAlert.rule_name}</Descriptions.Item>
                  <Descriptions.Item label="等级"><Tag color={levelColor(selectedAlert.level)}>{displayText(selectedAlert.level)}</Tag></Descriptions.Item>
                  <Descriptions.Item label="指标">{selectedAlert.metric}</Descriptions.Item>
                  <Descriptions.Item label="当前值">{selectedAlert.value}</Descriptions.Item>
                  <Descriptions.Item label="状态"><Tag color={statusColor(selectedAlert.status)}>{displayText(selectedAlert.status)}</Tag></Descriptions.Item>
                </Descriptions>
              ) : <Empty description="再选择一个告警" />}
              <Card size="small" title="处理记录">
                {selectedAlertActivities.length ? (
                  <Space direction="vertical" className="fullWidth">
                    {selectedAlertActivities.slice(0, 5).map((activity) => (
                      <div className="timelineItem" key={activity.id}>
                        <div className="timelineHeader"><Tag>{displayText(activity.action)}</Tag><span>{activity.actor}</span><span>{new Date(activity.created_at).toLocaleString()}</span></div>
                        <div className="timelineNote">{activity.note || '-'}</div>
                      </div>
                    ))}
                  </Space>
                ) : <Empty description="暂无处理记录" />}
              </Card>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card
            title="分析会话"
            extra={<Space><Button type="primary" icon={<RobotOutlined />} loading={loading} onClick={startAIAnalysis} disabled={!selectedTarget || !selectedAlert || aiSessionActive}>开始分析</Button><Button danger onClick={exitAIAnalysis} disabled={!aiSessionActive && aiMessages.length === 0}>退出分析</Button></Space>}
          >
            <Space direction="vertical" className="fullWidth" size={12}>
              {!aiSessionActive && aiMessages.length === 0 ? (
                <Input.TextArea rows={3} value={aiQuestion} onChange={(event) => setAiQuestion(event.target.value)} placeholder="输入首次分析要求，例如：给出可能原因、验证命令、恢复步骤和风险提示" />
              ) : null}
              <div className="chatTranscript">
                {aiMessages.length ? aiMessages.map((item, index) => (
                  <div key={`${item.created_at}-${index}`} className={`chatMessage ${item.role}`}>
                    <div className="chatRole">{item.role === 'user' ? '使用人员' : 'AI 助手'} · {new Date(item.created_at).toLocaleTimeString()}</div>
                    <div className="chatContent">{item.content}</div>
                  </div>
                )) : <Empty description="开始分析后，这里会保留本次运维对话上下文" />}
              </div>
              {aiSessionActive ? (
                <Space.Compact className="fullWidth">
                  <Input.TextArea
                    rows={3}
                    value={aiInput}
                    onChange={(event) => setAiInput(event.target.value)}
                    onPressEnter={(event) => {
                      if (!event.shiftKey) {
                        event.preventDefault();
                        void sendAIMessage(aiInput);
                      }
                    }}
                    placeholder="继续追问，例如：这一步怎么验证？如果是 Redis 连接数高应该先查什么？"
                  />
                  <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={() => sendAIMessage(aiInput)}>发送</Button>
                </Space.Compact>
              ) : null}
              {aiResult?.summary ? <Button icon={<CheckCircleOutlined />} onClick={saveAIResultAsAlertNote}>保存当前 AI 分析到处理记录</Button> : null}
            </Space>
          </Card>
        </Col>
      </Row>
    </Space>
  );  const renderLogs = () => {
    const selectedLogTarget = targets.find((target) => target.id === logTargetId) || null;
    const previewLogQL = buildSimpleLogQL({
      namespace: logNamespace,
      app: logApp,
      level: logLevel,
      keyword: logKeyword,
      targetKeyword: targetLogKeyword(selectedLogTarget),
    });

    return (
      <Card title="日志查询">
        <Space direction="vertical" className="fullWidth" size={16}>
          <Alert
            type="info"
            showIcon
            message="日志来自 Loki。只有已经被 promtail、fluent-bit 等采集进 Loki 的服务器、Pod 或中间件日志才能查到。Target 里的 Exporter 地址本身只提供指标，不直接提供日志。"
          />
          <Row gutter={[12, 12]}>
            <Col xs={24} md={6}>
              <Select
                className="fullWidth"
                value={logQueryMode}
                onChange={setLogQueryMode}
                options={[{ label: '普通查询', value: 'simple' }, { label: '高级 LogQL', value: 'advanced' }]}
              />
            </Col>
            <Col xs={24} md={6}>
              <Select
                className="fullWidth"
                value={logRangeMinutes}
                onChange={setLogRangeMinutes}
                options={[{ label: '最近 5 分钟', value: 5 }, { label: '最近 30 分钟', value: 30 }, { label: '最近 1 小时', value: 60 }, { label: '最近 6 小时', value: 360 }]}
              />
            </Col>
            <Col xs={24} md={6}>
              <Select
                className="fullWidth"
                value={logLimit}
                onChange={setLogLimit}
                options={[100, 200, 500].map((value) => ({ label: `${value} 条`, value }))}
              />
            </Col>
          </Row>
          {logQueryMode === 'simple' ? (
            <>
              <Row gutter={[12, 12]}>
                <Col xs={24} md={6}>
                  <Input value={logNamespace} onChange={(event) => setLogNamespace(event.target.value)} placeholder="命名空间，例如 platform、monitoring" />
                </Col>
                <Col xs={24} md={6}>
                  <Input value={logApp} onChange={(event) => setLogApp(event.target.value)} placeholder="应用 / Pod 关键字，例如 backend、redis" />
                </Col>
                <Col xs={24} md={6}>
                  <Select
                    className="fullWidth"
                    value={logLevel}
                    onChange={setLogLevel}
                    options={[{ label: '全部级别', value: 'all' }, { label: '异常 / Error', value: 'error' }, { label: '警告 / Warning', value: 'warning' }, { label: '信息 / Info', value: 'info' }]}
                  />
                </Col>
                <Col xs={24} md={6}>
                  <Input value={logKeyword} onChange={(event) => setLogKeyword(event.target.value)} placeholder="关键词，可选" />
                </Col>
              </Row>
              <Row gutter={[12, 12]}>
                <Col xs={24} md={12}>
                  <Select
                    allowClear
                    showSearch
                    className="fullWidth"
                    placeholder="可选：选择一个监控对象作为日志过滤辅助"
                    value={logTargetId ?? undefined}
                    onChange={(value) => setLogTargetId(value ?? null)}
                    optionFilterProp="label"
                    options={targets.map((target) => ({ label: `${target.name} - ${target.endpoint}`, value: target.id }))}
                  />
                </Col>
                <Col xs={24} md={12}>
                  <Alert
                    type="success"
                    showIcon
                    message={selectedLogTarget ? `会额外按 ${targetLogKeyword(selectedLogTarget)} 过滤日志内容` : '不选择 Target 时，只按命名空间、应用、级别和关键词查询。'}
                  />
                </Col>
              </Row>
              <Input.TextArea rows={2} value={previewLogQL} readOnly />
            </>
          ) : (
            <Input.TextArea rows={4} value={logQuery} onChange={(event) => setLogQuery(event.target.value)} placeholder='{namespace="platform"} |= "error"' />
          )}
          <Space>
            <Button type="primary" onClick={queryLogs} loading={loading}>查询日志</Button>
            <Button onClick={() => setLogEntries([])}>清空结果</Button>
          </Space>
          <Table
            rowKey="id"
            dataSource={logEntries}
            size="small"
            pagination={{ pageSize: 10, showSizeChanger: true }}
            scroll={{ x: 900 }}
            columns={[
              { title: '时间', dataIndex: 'time', width: 180 },
              { title: '命名空间', render: (_: unknown, row: LogEntry) => row.labels.namespace || '-' },
              { title: 'Pod / 应用', render: (_: unknown, row: LogEntry) => row.labels.pod || row.labels.app || row.labels.container || '-' },
              { title: '标签', render: (_: unknown, row: LogEntry) => JSON.stringify(row.labels), ellipsis: true },
              { title: '内容', dataIndex: 'line', ellipsis: true },
            ]}
          />
        </Space>
      </Card>
    );
  };
  const renderRecords = () => <Card title="通知记录" extra={<Button icon={<SendOutlined />} onClick={sendPending} loading={loading}>发送待处理通知</Button>}><Table rowKey="id" dataSource={records} size="small" pagination={{ pageSize: 10 }} columns={[{ title: 'ID', dataIndex: 'id', width: 70 }, { title: '标题', dataIndex: 'title', ellipsis: true }, { title: '类型', dataIndex: 'notification_type', render: (v: string) => <Tag>{displayText(v)}</Tag> }, { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={statusColor(v)}>{displayText(v)}</Tag> }, { title: '错误', dataIndex: 'error_message', ellipsis: true }]} /></Card>;
  const renderGrafana = () => (
    <Space direction="vertical" className="fullWidth" size={16}>
      <Card
        title="Grafana 可视化"
        extra={<Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>重新加载</Button>}
      >
        <Alert
          type={grafanaError ? 'warning' : 'info'}
          showIcon
          message={grafanaError || `已发现 ${grafanaViews?.dashboard_count ?? grafanaDashboards.length} 个 Grafana 仪表盘。普通用户只展示自己监控对象相关入口，root 额外展示平台支撑组件。`}
        />
      </Card>
      <Card title="我的监控对象图表">
        {grafanaViews?.targets?.length ? (
          <Row gutter={[16, 16]}>
            {grafanaViews.targets.map((view) => (
              <Col xs={24} md={12} xl={8} key={view.target_id}>
                <Card size="small" title={view.target_name} extra={<Tag>{displayText(view.target_type)}</Tag>}>
                  <Space direction="vertical" className="fullWidth">
                    <div>{view.endpoint}</div>
                    {view.exporter_kind ? <Tag color="blue">{view.exporter_kind}</Tag> : null}
                    <div>
                      {view.dashboard ? (
                        <Tag color="green">匹配仪表盘：{view.dashboard.title}</Tag>
                      ) : (
                        <Tag color="orange">未匹配仪表盘，打开 Explore</Tag>
                      )}
                    </div>
                    <Button type="primary" icon={<BarChartOutlined />} onClick={() => openGrafana(view.url)}>
                      打开图表
                    </Button>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        ) : <Empty description="当前账号还没有可关联的监控对象" />}
      </Card>
      {currentUser?.role === 'root' ? (
        <Card title="平台支撑组件图表">
          {grafanaViews?.platform?.length ? (
            <Row gutter={[16, 16]}>
              {grafanaViews.platform.map((view) => (
                <Col xs={24} md={12} xl={8} key={view.key}>
                  <Card size="small" title={view.title}>
                    <Space direction="vertical" className="fullWidth">
                      {view.dashboard ? <Tag color="green">匹配仪表盘：{view.dashboard.title}</Tag> : <Tag color="orange">未匹配仪表盘，打开搜索页</Tag>}
                      <Button icon={<BarChartOutlined />} onClick={() => openGrafana(view.url)}>打开图表</Button>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          ) : <Empty description="暂无平台支撑图表" />}
        </Card>
      ) : null}
      <Card title="全部 Grafana 仪表盘">
        <Table
          rowKey={(row) => row.uid || row.url}
          dataSource={grafanaDashboards}
          size="small"
          pagination={{ pageSize: 10 }}
          columns={[
            { title: '标题', dataIndex: 'title' },
            { title: '目录', dataIndex: 'folder_title' },
            { title: '标签', render: (_: unknown, row: GrafanaDashboard) => (row.tags || []).map((tag) => <Tag key={tag}>{tag}</Tag>) },
            { title: '操作', render: (_: unknown, row: GrafanaDashboard) => <Button size="small" onClick={() => openGrafana(row.url)}>打开</Button> },
          ]}
        />
      </Card>
    </Space>
  );
  const renderPlatformHealth = () => <Card title="平台自身健康" extra={<Button icon={<ReloadOutlined />} onClick={loadPlatformHealth} loading={loading}>刷新</Button>}><Alert type={platformHealth?.status === 'healthy' ? 'success' : 'warning'} showIcon message={`整体状态：${platformHealth?.status || 'unknown'}`} /><Table rowKey="name" dataSource={platformHealth?.services || []} size="small" pagination={false} columns={[{ title: '组件', dataIndex: 'name' }, { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'healthy' ? 'green' : value === 'down' ? 'red' : 'orange'}>{value}</Tag> }, { title: '说明', dataIndex: 'message' }, { title: '地址', dataIndex: 'url', ellipsis: true }]} /></Card>;
  function renderPage() {
    if (activePage === 'targets') return renderTargets();
    if (activePage === 'clusters') return renderClusters();
    if (activePage === 'rules') return renderRules();
    if (activePage === 'events') return renderEvents();
    if (activePage === 'channels') return renderChannels();
    if (activePage === 'records') return renderRecords();
    if (activePage === 'logs') return renderLogs();
    if (activePage === 'assistant') return renderAssistant();
    if (activePage === 'grafana') return renderGrafana();
    if (activePage === 'platformHealth' && currentUser?.role === 'root') return renderPlatformHealth();
    return renderOverview();
  }

  const menuItems = [
    { key: 'overview', icon: <DashboardOutlined />, label: '总览' },
    { key: 'targets', icon: <AimOutlined />, label: '监控对象' },
    { key: 'clusters', icon: <ProfileOutlined />, label: '集群管理' },
    { key: 'rules', icon: <SettingOutlined />, label: '告警规则' },
    { key: 'events', icon: <WarningOutlined />, label: '告警事件' },
    { key: 'channels', icon: <MailOutlined />, label: '通知渠道' },
    { key: 'records', icon: <ProfileOutlined />, label: '通知记录' },
    { key: 'logs', icon: <ProfileOutlined />, label: '日志查询' },
    { key: 'assistant', icon: <RobotOutlined />, label: 'AI 助手' },
    { key: 'grafana', icon: <BarChartOutlined />, label: 'Grafana 图表' },
    ...(currentUser?.role === 'root' ? [{ key: 'platformHealth', icon: <HeartOutlined />, label: '平台健康' }] : []),
  ];

  return (
    <ConfigProvider theme={{ token: { borderRadius: 6, colorPrimary: '#1677ff' } }}>
      <Layout className="appShell">
        <Sider width={240} className="sidebar">
          <div className="sidebarBrand">
            <DashboardOutlined /> 智能运维平台
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[activePage]}
            onClick={({ key }) => setActivePage(key as PageKey)}
            items={menuItems}
          />
        </Sider>
        <Layout>
          <Header className="topbar">
            <div className="pageTitle">{pageTitles[activePage]}</div>
            <Space>
              <Tag color={currentUser?.role === 'root' ? 'red' : 'blue'}>
                {currentUser?.role === 'root' ? 'root 管理员' : '普通用户'}
              </Tag>
              <span>{currentUser?.username}</span>
              <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>
                刷新
              </Button>
              <Button
                onClick={() => {
                  localStorage.removeItem('access_token');
                  setToken('');
                  setCurrentUser(null);
                }}
              >
                退出登录
              </Button>
            </Space>
          </Header>
          <Content className="content">
            {renderPage()}
            {renderAlertDrawer()}
            <Alert className="section" type="info" showIcon message={`API: ${API_BASE}`} />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}





































































































