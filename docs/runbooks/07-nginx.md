# Nginx 连接与请求异常

## 覆盖告警指标

`nginx_active_connections`、`nginx_requests_total`、`nginx_reading`、`nginx_writing`、`nginx_waiting`

## 现象和触发条件

- 活跃、读取、写入或等待连接数异常，或请求总数突增/突降。
- 通常应结合网站响应时间、HTTP 4xx/5xx 和上游应用日志判断。

## 影响范围

- 外部访问入口可能出现排队、超时、5xx、限流或上游连接失败。

## 所需证据

- Nginx `stub_status` 或 exporter 趋势、access/error log、HTTP 状态分布、上游响应时间和后端 Pod/进程状态。

## 排查步骤

1. 检查 `nginx -T`，确认 upstream、超时、限流、代理头和 DNS 解析配置。
2. 查看 access.log/error.log，区分客户端 4xx、Nginx 自身错误和上游 5xx/超时。
3. 高 writing 或 active connections 时检查慢上游、连接泄漏、长连接和流量突增。
4. 高 waiting 时检查 keepalive、并发连接上限、限流以及后端处理能力。
5. 检查 Ingress/Service/Endpoint，确认后端实例 Ready 且没有异常发布。

## 建议处置

- 上游慢或失败时优先恢复应用/依赖，不把所有问题归因于 Nginx。
- 合理调整超时、keepalive、连接上限和限流规则；突发流量可扩容上游并启用降级。
- 长期保存状态码和上游响应时间指标，建立入口到应用的关联诊断。

## 风险提示

- 不要在高峰期无验证重载全量 Nginx 配置。
- 不要仅提高超时掩盖后端性能问题。

## 恢复验证

- 连接和请求趋势稳定，错误日志无新增 5xx/连接失败，平台 HTTP 检测恢复正常。

## 升级条件

- 核心入口 5xx 持续、全站不可用、证书/配置错误影响公网服务时，升级为紧急事件。
