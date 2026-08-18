# Elasticsearch 集群、分片与存储异常

## 覆盖告警指标

`elasticsearch_cluster_health_status`、`elasticsearch_active_shards`、`elasticsearch_relocating_shards`、`elasticsearch_initializing_shards`、`elasticsearch_unassigned_shards`、`elasticsearch_jvm_memory_used_bytes`、`elasticsearch_filesystem_data_available_bytes`

## 现象和触发条件

- 集群健康变黄/红、未分配分片增加、迁移/初始化持续不结束。
- JVM 内存高、数据盘可用空间低，或活跃分片数量异常。

## 影响范围

- 搜索、写入、日志检索可能延迟或不可用；红色状态通常表示部分主分片不可用。

## 所需证据

- Cluster health、cat shards/allocation、节点状态、磁盘水位、JVM/GC、索引写入量与集群日志。

## 排查步骤

1. 查询 `_cluster/health` 和 `_cat/shards?v`，确认未分配分片原因。
2. 检查 `_cluster/allocation/explain`、节点是否离线、磁盘水位、分片过滤和副本配置。
3. JVM 高时检查 heap、GC、查询聚合、fielddata、慢查询和索引压力。
4. 磁盘低时检查索引保留、快照、分片均衡和高水位限制。

## 建议处置

- 先恢复离线节点或可用容量，再处理分片分配；必要时扩容数据节点/磁盘。
- 对高内存查询限制聚合、优化 mapping 与查询；对日志索引执行生命周期管理。
- 任何关闭分配、删除索引或强制分片操作均应由负责人审批。

## 风险提示

- 不要为消除告警直接删除未知索引或强制分配过期主分片。
- 红色集群和低磁盘水位可能有数据不可恢复风险。

## 恢复验证

- 集群健康恢复预期状态，未分配/迁移分片归零或回到可解释范围，JVM 和磁盘水位稳定。

## 升级条件

- 红色集群、主分片丢失、写入不可用或磁盘水位触发只读保护时，立即升级。
