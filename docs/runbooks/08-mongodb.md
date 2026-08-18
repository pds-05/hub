# MongoDB 连接、操作与内存异常

## 覆盖告警指标

`mongodb_connections_current`、`mongodb_connections_available`、`mongodb_op_counters_query_total`、`mongodb_op_counters_insert_total`、`mongodb_op_counters_update_total`、`mongodb_op_counters_delete_total`、`mongodb_memory_resident_bytes`、`mongodb_asserts_total`

## 现象和触发条件

- 当前连接接近可用连接上限、操作吞吐异常、常驻内存增长或断言计数增加。

## 影响范围

- 应用可能连接失败、查询变慢、写入积压；副本集异常时还可能影响可用性和一致性。

## 所需证据

- 连接、操作、内存和断言趋势；MongoDB 日志、慢查询、复制集状态和磁盘/CPU 状态。

## 排查步骤

1. 使用 `db.serverStatus()` 关注 connections、opcounters、mem、asserts。
2. 检查 `db.currentOp()`、慢查询 profiler 和应用连接池来源。
3. 确认副本集主从角色、复制延迟、选举记录和磁盘压力。
4. 针对高内存或高操作量，识别大集合扫描、缺失索引、批量任务和热点请求。

## 建议处置

- 修复连接泄漏和慢查询，补齐索引与分页；限制异常批处理。
- 容量不足时按副本集和业务读写模型扩容，避免单纯提高连接上限。

## 风险提示

- 不要在未备份和未评估复制状态时删除集合、重建索引或强制选主。

## 恢复验证

- 连接余量、操作延迟、内存趋势和复制集健康恢复，应用无新增连接或查询错误。

## 升级条件

- 无主节点、复制集不可用、持续断言/数据损坏信号或连接耗尽时，升级数据库负责人。
