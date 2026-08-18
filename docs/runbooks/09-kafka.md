# Kafka Broker、分区和消费积压异常

## 覆盖告警指标

`kafka_brokers`、`kafka_under_replicated_partitions`、`kafka_offline_partitions_count`、`kafka_active_controller_count`、`kafka_topic_partition_current_offset`、`kafka_consumergroup_lag`

## 现象和触发条件

- Broker 数量下降、ISR 不足、离线分区出现、Controller 异常或消费者积压持续增长。

## 影响范围

- 消息生产/消费延迟增大；离线分区或副本不足会降低数据可用性与容灾能力。

## 所需证据

- Broker 健康、控制器状态、分区副本、ISR、磁盘/网络、消费者组 lag 与处理速率。

## 排查步骤

1. 确认是否有 Broker 宕机、网络隔离、磁盘满、GC 停顿或认证错误。
2. 检查受影响 Topic 的分区、leader、ISR、离线分区和副本同步状态。
3. 消费积压时对比生产速率与消费速率，检查消费者实例数、Rebalance、异常重试和下游依赖。
4. Controller 异常时检查元数据服务、控制器日志和集群选举记录。

## 建议处置

- 优先恢复离线 Broker 和副本同步，避免在副本不足时扩大故障面。
- 消费积压可扩容消费者或修复慢消费逻辑，但需确认分区数和消费者组并行度上限。
- 长期设置 Topic 容量、保留策略、磁盘水位和 ISR 告警。

## 风险提示

- 不要随意删除 Topic、重置消费位点或进行分区重分配。
- 位点重置和副本修复可能造成重复消费或消息丢失，必须由业务确认。

## 恢复验证

- 离线分区为零、ISR 恢复、Broker/Controller 正常，lag 持续下降并回到基线。

## 升级条件

- 离线分区、不可用 Topic、数据丢失风险或关键消费者积压导致业务中断时，立即升级。
