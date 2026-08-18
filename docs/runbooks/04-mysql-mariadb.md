# MySQL 和 MariaDB 指标异常

## 覆盖告警指标

`mysql_threads_connected`、`mysql_threads_running`、`mysql_questions_total`、`mysql_connections_total`、`mysql_slow_queries_total`、`mysql_aborted_connects_total`、`mysql_innodb_buffer_pool_pages_dirty`、`mysql_slave_lag_seconds`

## 现象和触发条件

- 连接线程、运行线程、连接总数或失败连接持续增长。
- 慢查询、脏页、查询量异常，或主从复制延迟超过阈值。

## 影响范围

- 应用可能获取不到数据库连接、请求变慢或出现写入延迟；复制延迟会导致读到旧数据。

## 所需证据

- 连接数、运行线程、慢查询和复制延迟的趋势；数据库错误日志和应用连接池指标。
- 当前会话、长事务、锁等待、慢 SQL 摘要及最近发布/流量变化。

## 排查步骤

1. 检查 `SHOW GLOBAL STATUS LIKE 'Threads_connected';`、`Threads_running`、`Slow_queries` 和 `Aborted_connects`。
2. 使用 `SHOW PROCESSLIST;` 或 `information_schema.processlist` 定位长时间运行、锁等待和异常来源连接。
3. 检查慢日志、执行计划、索引命中和应用连接池是否泄漏或配置过大。
4. 复制延迟时检查副本 SQL/IO 线程、网络、磁盘 IO、长事务和大批量写入。
5. 脏页持续高时检查写入压力、checkpoint、磁盘延迟和 InnoDB 配置。

## 建议处置

- 优先限制异常调用方、修复慢 SQL/索引和连接池配置。
- 主从延迟时避免读到陈旧副本，必要时将关键读流量切回主库或健康副本。
- 长期建立连接池上限、慢 SQL 治理、容量基线与读写分离监控。

## 风险提示

- 不要直接 `KILL` 会话或重启数据库；先确认事务、业务影响和回滚成本。
- 不要在未核验备份和复制状态前进行主从切换。

## 恢复验证

- 连接、运行线程、慢查询增长率和复制延迟恢复到基线。
- 应用无新增连接超时/数据库错误，关键读写链路正常。

## 升级条件

- 主库不可写、复制中断、连接池大面积耗尽或存在数据一致性风险时，立即升级数据库负责人。
