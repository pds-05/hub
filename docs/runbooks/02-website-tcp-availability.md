# 网站、HTTP、TLS、DNS 与 TCP 可用性异常

## 覆盖告警指标

`status_down`、`response_time_ms`、`http_status_code`、`tls_days_remaining`、`dns_failed`、`tls_failed`、`keyword_mismatch`

## 现象和触发条件

- 网站、HTTP/HTTPS 健康检查或 TCP 端口检测为 down。
- HTTP 返回 400 到 599；平台默认将这些状态码判为异常。
- 响应时间超过阈值、DNS 无法解析、TLS 握手或证书校验失败、页面未包含预期关键字。

## 影响范围

- 外部用户可能无法访问网站、API、数据库端口或中间件端口。
- 关键字不匹配可能是页面变更，也可能是登录页、错误页或灰度页替代了正常页面。

## 所需证据

- Target 类型、目标地址、最近检测状态、HTTP 状态码、响应时间、DNS/TLS/关键字检测明细。
- 从平台后端网络视角执行的连通性结果，而不是只看个人电脑浏览器的访问结果。

## 排查步骤

1. 核对 Target 地址、协议、端口、路径和预期关键字是否仍正确。
2. HTTP/HTTPS 使用 `curl -I URL` 与 `curl -v URL`，确认 DNS、连接、TLS、重定向、状态码和响应内容。
3. TCP 使用 `nc -vz host port` 或 `Test-NetConnection host -Port port`，确认端口是否可达。
4. DNS 失败时用 `nslookup domain` 或 `dig domain` 比对公网/内网解析和 DNS 记录。
5. TLS 异常时用 `openssl s_client -connect domain:443 -servername domain` 检查证书链、SNI、域名和过期时间。
6. HTTP 5xx 优先检查反向代理、应用日志和依赖；4xx 优先检查路径、认证、路由、访问策略与健康检查地址。

## 建议处置

- 网络不可达：检查安全组、防火墙、路由、NAT、Service、Ingress、Endpoint 与目标监听进程。
- 响应慢：区分 DNS、建立连接、TLS、上游处理或依赖调用耗时，再针对性处理。
- 证书临期：提前续签；若使用 cert-manager，检查 Certificate、Order、Challenge 和 Ingress TLS Secret。
- 关键字不匹配：先确认业务页面是否正常变更，再更新规则；若是错误页，继续排查应用和上游依赖。

## 风险提示

- 不要为了让探测恢复而把健康检查改成始终返回 200。
- 证书、DNS 或公网访问变更前须评估缓存和传播时间。

## 恢复验证

- 从平台侧和实际用户网络侧均验证目标。
- 连续两个采集周期 `status_down=0`，HTTP 状态、响应时间、TLS 与关键字检测恢复正常。

## 升级条件

- 公网核心入口不可用、证书即将过期且续签失败、或多个区域同时 DNS/网络异常时，升级为紧急事件。
