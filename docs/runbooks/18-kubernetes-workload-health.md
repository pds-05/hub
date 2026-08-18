# Kubernetes Pod 与集群工作负载健康参考

## 适用范围

本篇用于集群 Agent 已上报的 Warning Event、Pod 健康和 CoreDNS 异常。它不是当前“自定义告警规则”中的 metric 枚举，但可被 Dify 用于解释集群监控报告。

## 现象和触发条件

- Pod 处于 Pending、Failed、CrashLoopBackOff、ImagePullBackOff，或重启次数持续增长。
- 出现调度失败、探针失败、卷挂载失败、无 Endpoint Service、CoreDNS 解析异常等 Warning Event。

## 影响范围

- 工作负载不可用、发布失败、服务发现失败或上下游请求超时。

## 所需证据

- Pod phase、container waiting reason、restart count、事件、节点资源、PVC/PV、Service Endpoint、镜像仓库和应用日志。

## 排查步骤

1. Pending：检查 `kubectl describe pod` 中的调度事件、Requests/Limits、污点、亲和性、PVC 绑定和节点资源。
2. CrashLoopBackOff：检查上一轮容器日志、退出码、探针配置、环境变量、依赖连接和 OOMKilled。
3. ImagePullBackOff：检查镜像名/标签、仓库连通性、imagePullSecret、节点 DNS 与镜像加速配置。
4. 探针失败：确认健康检查路径、端口、启动时间、应用依赖与 timeout 阈值。
5. DNS/CoreDNS：检查 CoreDNS Pod、Endpoint、上游 DNS、NetworkPolicy 和工作负载内的解析结果。

## 建议处置

- 先修复配置、镜像、依赖或资源不足，再考虑重建 Pod。
- 将持续性 Warning Event 纳入告警，并为关键服务补充正确的 Requests/Limits、探针与 PDB。

## 风险提示

- 不要通过删除 Pod 反复掩盖 CrashLoop 或 ImagePull 根因。
- 不要在不了解 PVC 和 StatefulSet 语义时删除有状态 Pod/卷。

## 恢复验证

- Pod 持续 Ready，Deployment/StatefulSet 可用副本达到期望值，事件不再重复，Service Endpoint 恢复。

## 升级条件

- 控制面、CoreDNS、关键存储/网络组件异常，或核心工作负载大面积不可用时，升级为紧急事件。
