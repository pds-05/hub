# ZooKeeper 可用性、连接和请求积压异常

## 覆盖告警指标

`zookeeper_up`、`zookeeper_approximate_data_size`、`zookeeper_num_alive_connections`、`zookeeper_outstanding_requests`、`zookeeper_znode_count`、`zookeeper_watch_count`

## 现象和触发条件

- ZooKeeper 不可用、未完成请求增多、连接/Watch/ZNode 持续增长或数据体积异常。

## 影响范围

- 依赖 ZooKeeper 的 Kafka、分布式协调、服务发现或配置系统可能出现选举、注册和消费异常。

## 所需证据

- Leader/Follower 状态、延迟、outstanding requests、连接来源、Watch 数、磁盘和 JVM/GC 状态。

## 排查步骤

1. 检查每个节点角色与 quorum，确认是否有节点宕机或网络分区。
2. outstanding requests 高时检查客户端请求突增、慢磁盘、GC 停顿和连接抖动。
3. 连接/Watch/ZNode 高时定位异常客户端，检查是否存在 Watch 泄漏、频繁重连或目录无限增长。
4. 检查事务日志和快照空间，确认磁盘没有接近满。

## 建议处置

- 先恢复 quorum 和网络连通性，随后治理异常客户端和请求模式。
- 对目录、Watch 和连接增长建立配额与生命周期清理策略。

## 风险提示

- 不要手工删除生产 ZNode 或同时重启多个 ZooKeeper 节点。

## 恢复验证

- 集群保持 quorum，未完成请求下降，连接、Watch、ZNode 和磁盘趋势稳定。

## 升级条件

- 失去 quorum、Leader 不稳定、协调服务不可用或影响 Kafka 等关键依赖时，立即升级。
