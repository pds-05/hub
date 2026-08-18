# ClickHouse 可用性、连接与查询异常

## 覆盖告警指标

`clickhouse_up`、`clickhouse_query_total`、`clickhouse_tcp_connections`、`clickhouse_http_connections`、`clickhouse_memory_tracking`、`clickhouse_delayed_inserts`

## 现象和触发条件

- ClickHouse 不可采集、TCP/HTTP 连接异常、查询吞吐突变、内存跟踪高或延迟插入增加。

## 影响范围

- 分析查询、报表、日志/事件写入可能变慢或失败；延迟插入会造成数据到达延后。

## 所需证据

- `system.metrics`、`system.processes`、`system.query_log`、`system.parts`、服务日志和磁盘/网络趋势。

## 排查步骤

1. 确认可用性、TCP/HTTP 监听、认证和负载均衡路径。
2. 查看运行中查询、慢查询、内存使用和并发连接来源。
3. delayed inserts 高时检查异步插入配置、下游磁盘、分区数量与写入批次。
4. 检查 merge、mutation、复制队列和磁盘空间，识别后台任务压力。

## 建议处置

- 优化高消耗查询、限制并发并改善分区/排序键设计。
- 通过批量写入、合理异步插入和存储扩容降低写入积压。
- 对连接增长修复连接池和异常调用方。

## 风险提示

- 不要直接删除分区、表或复制数据；先确认数据保留和备份策略。

## 恢复验证

- 服务可采集，连接、内存、延迟插入和查询耗时回到基线，关键写入/查询链路正常。

## 升级条件

- 集群不可用、磁盘耗尽、复制异常或关键数据写入中断时，升级处理。
