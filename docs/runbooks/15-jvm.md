# JVM 内存、线程与 GC 异常

## 覆盖告警指标

`jvm_memory_used_bytes`、`jvm_memory_committed_bytes`、`jvm_threads_current`、`jvm_gc_collection_seconds_count`、`jvm_gc_collection_seconds_sum`

## 现象和触发条件

- JVM 已用/已提交内存、线程数或 GC 次数/耗时持续上升，常伴随接口延迟、Full GC、OOM 或进程重启。

## 影响范围

- Java 服务可能出现 STW 停顿、请求超时、内存溢出、连接堆积或健康检查失败。

## 所需证据

- Heap 使用曲线、GC pause、线程数、容器内存限制、重启/OOM 日志、应用吞吐与延迟。

## 排查步骤

1. 区分堆内存、非堆、直接内存和容器 cgroup 限制，不能只看 JVM heap。
2. 检查 GC 日志、线程 dump、异常日志和最近部署，确认内存泄漏、线程泄漏或流量突增。
3. 线程高时定位阻塞、连接池等待、死锁和异常重试。
4. GC 高时检查对象分配、缓存、堆大小和 JVM 参数；结合 CPU 指标评估 GC 压力。

## 建议处置

- 优先修复泄漏、阻塞和异常重试；合理设置容器内存和 JVM `-Xmx`，保留 cgroup 余量。
- 对线程池和连接池设置上限、超时与隔离；必要时扩容实例分担流量。

## 风险提示

- 不要仅提高 `-Xmx`，这可能挤占容器/节点内存并导致 OOMKilled。
- 线上抓 heap dump 前要评估暂停和磁盘空间。

## 恢复验证

- GC 耗时/频率、内存和线程趋于稳定，服务无新增 OOM、重启或请求超时。

## 升级条件

- 频繁 Full GC、OOM、线程池耗尽或关键 Java 服务大面积不可用时，升级应用负责人。
