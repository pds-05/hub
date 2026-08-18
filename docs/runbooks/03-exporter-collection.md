# Prometheus Exporter 采集异常

## 覆盖告警指标

`metrics_format_invalid`、`exporter_up`、`exporter_metric_count`、`exporter_series_count`

## 现象和触发条件

- Exporter 的 `/metrics` 不可达、采集状态为 down，或响应不是 Prometheus 文本格式。
- 指标数或时序数突降、突增，可能表示 Exporter 配置改变、采集标签变化或采集失败。

## 影响范围

- 中间件或服务器本身可能仍正常，但平台无法获取实时指标，相关图表和告警会失真。

## 所需证据

- Target 的采集状态、Prometheus Targets 中的 `lastError`、最后采集时间和耗时。
- `/metrics` 前几行、Exporter 版本与启动参数、ScrapeConfig 内容及其标签。

## 排查步骤

1. 从平台网络执行 `curl http://host:port/metrics`，确认地址、端口、路径和访问控制。
2. 响应应包含 `# HELP`、`# TYPE` 或合法的 `metric_name value`；HTML 登录页、JSON 错误页都不是有效指标。
3. 在 Prometheus Targets 中核对 job、标签、目标地址、scrape error 与抓取时间。
4. 检查 Exporter 进程/容器是否运行、端口是否监听、证书或认证代理是否拦截。
5. 若指标数变化，比较 Exporter 版本、采集参数和标签；确认是预期变化还是监控缺失。

## 建议处置

- 修正 Target 的 Exporter 地址，通常应指向 `/metrics`。
- 修复 Exporter 进程、网络策略、安全组或 ScrapeConfig 后重新同步采集。
- 对指标名称发生版本变化的 Exporter，同步更新平台指标映射和告警规则。

## 风险提示

- 不要仅通过降低指标数阈值消除告警，应先确认没有发生数据缺失。
- 不向 Dify、浏览器或日志输出 Exporter 的认证凭据。

## 恢复验证

- Prometheus Targets 显示 UP，`lastError` 为空，平台 Target 采集状态不再为待采集或 down。
- 关键指标和时序数恢复到预期范围。

## 升级条件

- 多个 Exporter 同时失联、Prometheus 全局采集失败或关键生产组件无指标超过告警窗口时，升级处理。
