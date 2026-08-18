# etcd Leader、容量和延迟异常

## 覆盖告警指标

`etcd_server_has_leader`、`etcd_server_leader_changes_seen_total`、`etcd_mvcc_db_total_size_in_bytes`、`etcd_network_peer_round_trip_time_seconds`、`etcd_disk_backend_commit_duration_seconds`

## 现象和触发条件

- 节点无 Leader、Leader 频繁变化、MVCC 数据库持续增长、Peer RTT 高或后端提交延迟高。

## 影响范围

- Kubernetes API、控制器、调度、服务发现和集群状态写入可能延迟或不可用。

## 所需证据

- etcd 成员健康、Leader、日志、磁盘 fsync 延迟、网络 RTT、数据库大小、告警和 API Server 延迟。

## 排查步骤

1. 确认成员数量、quorum 与 Leader 状态，检查是否有节点宕机、证书/时间或网络问题。
2. Peer RTT 或 Leader 频繁切换时检查节点网络丢包、延迟、CPU 和磁盘 IO。
3. backend commit 高时检查磁盘 IOPS、fsync 延迟、存储设备和后台快照/压缩。
4. 数据库持续增长时检查对象写入风暴、事件保留、历史版本和维护计划。

## 建议处置

- 优先恢复 quorum、稳定网络和低延迟磁盘；控制面组件应避免与高 IO 业务混部。
- 在明确备份和维护窗口内，由集群负责人执行 compaction/defrag 等维护。

## 风险提示

- 不能在没有一致备份和正确 endpoint 的情况下操作 etcd 数据或执行 defrag。
- 不要同时重启多数 etcd 成员，否则会失去 quorum。

## 恢复验证

- 所有成员健康、有稳定 Leader，RTT/提交延迟下降，Kubernetes API 操作与调度恢复。

## 升级条件

- etcd 失去 quorum、API Server 不可用、数据损坏或控制面大范围异常时，立即升级为最高优先级。
