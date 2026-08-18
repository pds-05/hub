# PostgreSQL 指标异常

## 覆盖告警指标

`postgresql_active_backends`、`postgresql_locks`、`postgresql_deadlocks_total`、`postgresql_transactions_commit_total`、`postgresql_transactions_rollback_total`、`postgresql_blocks_hit_total`、`postgresql_blocks_read_total`、`postgresql_conflicts_total`、`postgresql_temp_bytes_total`

## 现象和触发条件

- 活跃连接、锁、死锁、回滚、临时文件或磁盘读取异常。
- 缓冲命中变差、读盘增多、事务冲突或连接数接近上限。

## 影响范围

- 应用可能出现连接等待、SQL 超时、写入阻塞、接口延迟或事务失败。

## 所需证据

- 活跃会话、锁等待、长事务、慢 SQL、数据库日志和连接池状态。
- 当前 `max_connections`、磁盘空间、IO 延迟、复制/备份任务与最近发布记录。

## 排查步骤

1. 查询 `pg_stat_activity` 定位活跃、空闲事务和长时间等待会话。
2. 查询 `pg_locks` 及阻塞关系，确认锁持有者和受影响 SQL。
3. 检查数据库日志中的 deadlock、timeout、checkpoint、临时文件与连接错误。
4. 对读盘或临时文件高的 SQL 检查执行计划、索引、排序/哈希内存和数据量变化。
5. 对 rollback/conflict 增多的场景检查应用重试、隔离级别和副本冲突。

## 建议处置

- 优先修复长事务、错误重试和慢 SQL；必要时由数据库负责人终止明确无业务价值的会话。
- 调整连接池而不是无限提高 `max_connections`；为高频 SQL 补充索引和分页策略。
- 对临时文件或读盘压力，评估 SQL 优化、内存参数、IO 容量和数据归档。

## 风险提示

- 不要直接终止未知业务事务、重启 PostgreSQL 或删除数据文件。
- 修改隔离级别、连接上限和存储参数要经过容量与回滚评估。

## 恢复验证

- 锁等待、死锁增长、连接数、读盘和临时文件回到基线；应用事务错误消失。

## 升级条件

- 数据库不可连接、写入阻塞、死锁持续、存储耗尽或复制一致性风险时，升级数据库负责人。
