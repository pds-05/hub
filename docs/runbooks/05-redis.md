# Redis 指标异常

## 覆盖告警指标

`redis_connected_clients`、`redis_blocked_clients`、`redis_rejected_connections_total`、`redis_used_memory_bytes`、`redis_commands_processed_total`、`redis_keyspace_hits_total`、`redis_keyspace_misses_total`、`redis_evicted_keys_total`、`redis_expired_keys_total`

## 现象和触发条件

- 客户端连接、阻塞客户端、拒绝连接或内存使用异常增长。
- 驱逐 Key 增多、命中率下降、命令吞吐突变或过期 Key 异常。

## 影响范围

- 缓存击穿会把压力转移到数据库；会话、限流、队列或分布式锁场景可能直接影响业务可用性。

## 所需证据

- `INFO` 输出中的 memory、clients、stats、persistence、replication；慢日志和应用错误日志。
- `maxmemory`、淘汰策略、大 Key、热点 Key、客户端来源和主从状态。

## 排查步骤

1. 使用 `redis-cli INFO`，重点检查 `used_memory`、`connected_clients`、`blocked_clients`、`rejected_connections` 和 `evicted_keys`。
2. 使用 `redis-cli CLIENT LIST` 定位连接暴增来源；使用 `redis-cli SLOWLOG GET 10` 检查慢命令。
3. 检查命中/未命中趋势，结合数据库 QPS 判断是否发生缓存击穿。
4. 检查大 Key、过期策略、持久化耗时、主从复制和网络抖动。

## 建议处置

- 先限制异常客户端、修复连接泄漏、设置合理连接池和命令超时。
- 内存接近上限时评估扩容、拆分热点、设置合理淘汰策略和 TTL。
- 命中率低时修复缓存键设计、预热策略和过期抖动，不要盲目提高缓存容量。

## 风险提示

- 生产 Redis 上禁止随意执行 `FLUSHALL`、批量删除或大范围 `KEYS *`。
- 修改淘汰策略、持久化或主从拓扑前必须评估数据一致性和业务语义。

## 恢复验证

- 内存、连接、阻塞、拒绝连接和驱逐趋势恢复；业务缓存命中和数据库负载正常。

## 升级条件

- 主节点故障、持续拒绝连接、缓存大面积失效或数据丢失风险时，升级处理。
