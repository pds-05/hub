from __future__ import annotations

from typing import Any


RUNBOOKS: dict[str, dict[str, list[str] | str]] = {
    "cpu_usage_percent": {
        "title": "CPU 使用率过高",
        "symptoms": [
            "节点 CPU 使用率持续高于阈值。",
            "服务响应变慢，Pod 调度或健康检查可能受影响。",
        ],
        "checks": [
            "kubectl top nodes",
            "kubectl top pods -A --sort-by=cpu",
            "top -o %CPU 或 pidstat 1 5",
            "PromQL: 100 - avg by(instance)(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100",
        ],
        "actions": [
            "定位高 CPU 的 Pod、进程或任务。",
            "确认是否有最近发布、批处理任务、异常重试或流量突增。",
            "必要时临时扩容副本、限制异常任务、回滚最近版本。",
            "长期方案是补充 HPA、资源 requests/limits 和容量规划。",
        ],
    },
    "memory_usage_percent": {
        "title": "内存使用率过高",
        "symptoms": [
            "节点可用内存不足。",
            "Pod 可能出现 OOMKilled 或频繁重启。",
        ],
        "checks": [
            "kubectl top nodes",
            "kubectl top pods -A --sort-by=memory",
            "kubectl get pods -A | findstr /i OOMKilled",
            "free -h",
            "PromQL: (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        ],
        "actions": [
            "定位内存占用最高的 Pod 或进程。",
            "检查是否存在内存泄漏、缓存失控或批量任务。",
            "为关键服务设置合理 requests/limits。",
            "必要时扩容节点或迁移部分工作负载。",
        ],
    },
    "disk_usage_percent": {
        "title": "磁盘使用率过高",
        "symptoms": [
            "根分区或数据分区空间不足。",
            "容器日志、镜像、PVC 数据可能占满磁盘。",
        ],
        "checks": [
            "df -h",
            "du -xh /var/lib/rancher /var/lib/containerd /var/log --max-depth=1",
            "kubectl get pvc -A",
            "journalctl --disk-usage",
            "PromQL: (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100",
        ],
        "actions": [
            "清理无用镜像、旧日志和临时文件。",
            "检查 Loki、Prometheus、数据库等组件的数据保留策略。",
            "扩容 PVC 或迁移数据盘。",
            "为日志增加轮转和保留周期。",
        ],
    },
    "load1": {
        "title": "系统负载过高",
        "symptoms": [
            "系统 load average 高于 CPU 核数。",
            "请求延迟升高，节点操作变慢。",
        ],
        "checks": [
            "uptime",
            "top 或 htop",
            "iostat -x 1 5",
            "vmstat 1 5",
            "PromQL: node_load1",
        ],
        "actions": [
            "区分 CPU 饱和、IO wait、内存 swap 或进程阻塞。",
            "如果 IO wait 高，检查磁盘和数据库写入压力。",
            "如果 CPU 高，按 CPU Runbook 定位进程和 Pod。",
            "必要时扩容节点或迁移高负载服务。",
        ],
    },
    "response_time_ms": {
        "title": "响应时间过高",
        "symptoms": [
            "网站或接口可访问但响应慢。",
            "用户访问体验下降，可能伴随 5xx 或超时。",
        ],
        "checks": [
            "curl -w '@curl-format.txt' -o /dev/null -s URL",
            "检查 Ingress/Nginx 上游响应时间。",
            "查看应用日志和慢 SQL。",
            "检查依赖服务 Redis/PostgreSQL/外部 API。",
        ],
        "actions": [
            "先判断慢在 DNS、连接、TLS、后端处理还是下载阶段。",
            "检查最近发布、流量突增和依赖服务状态。",
            "必要时扩容应用副本或回滚异常版本。",
        ],
    },
    "tls_days_remaining": {
        "title": "HTTPS 证书即将过期或异常",
        "symptoms": [
            "TLS 证书剩余天数低于阈值。",
            "用户浏览器可能提示证书风险。",
        ],
        "checks": [
            "openssl s_client -connect domain:443 -servername domain < /dev/null 2>/dev/null | openssl x509 -noout -dates",
            "kubectl get secret -A | findstr tls",
            "检查 cert-manager Certificate 和 Order 状态。",
        ],
        "actions": [
            "续期或重新签发证书。",
            "检查 DNS、Ingress 和 cert-manager 是否正常。",
            "确认新证书已被 Ingress 加载。",
        ],
    },
    "http_down": {
        "title": "HTTP/网站不可用",
        "symptoms": [
            "目标网站检测为 down。",
            "可能出现 5xx、超时、DNS 失败或关键字不匹配。",
        ],
        "checks": [
            "curl -I URL",
            "curl -v URL",
            "nslookup domain 或 dig domain",
            "kubectl get ingress,svc,pod -A",
            "kubectl logs -n <namespace> <pod>",
        ],
        "actions": [
            "先区分 DNS、网络、TLS、Ingress、后端服务还是应用自身问题。",
            "如果是 5xx，优先查看应用日志和上游服务。",
            "如果是超时，检查安全组、防火墙、Service、Endpoint 和 Pod readiness。",
            "如果关键字不匹配，确认页面内容是否变更或应用返回了错误页面。",
        ],
    },
    "tcp_down": {
        "title": "TCP 端口不可达",
        "symptoms": [
            "端口检测失败，服务可能未监听或网络不可达。",
        ],
        "checks": [
            "nc -vz host port",
            "Test-NetConnection host -Port port",
            "ss -lntp 或 netstat -lntp",
            "检查云安全组、防火墙和 Kubernetes Service。",
        ],
        "actions": [
            "确认服务进程正在监听目标端口。",
            "确认目标地址、端口和协议填写正确。",
            "检查安全组、防火墙、NAT、Ingress/Service 路由。",
        ],
    },
    "exporter_down": {
        "title": "Exporter 异常",
        "symptoms": [
            "Exporter 不可访问或 /metrics 格式不正确。",
            "Prometheus 无法采集对应指标。",
        ],
        "checks": [
            "curl http://host:port/metrics | head",
            "Prometheus Targets 页面查看 scrape error。",
            "kubectl get servicemonitor,pod,svc -A",
        ],
        "actions": [
            "确认 exporter 进程运行并监听端口。",
            "确认 /metrics 返回 Prometheus 文本格式，包含 # HELP 或 # TYPE。",
            "检查 Prometheus scrape 配置、ServiceMonitor 标签和网络策略。",
        ],
    },
    "status_down": {
        "title": "目标不可用",
        "symptoms": ["网站、端口或 Exporter 最新检测为 down。"],
        "checks": ["确认 target 地址和端口填写正确。", "从后端所在机器执行 curl、nc 或 Test-NetConnection。", "检查安全组、防火墙、DNS、Ingress、Service 和目标进程。"],
        "actions": ["先区分是网络不可达、服务未监听、应用错误还是探测路径错误。", "如果是生产服务，先恢复访问路径或切换备用实例。", "修复后重新执行目标检测并观察告警是否恢复。"],
    },
    "http_status_code": {
        "title": "HTTP 状态码异常",
        "symptoms": ["目标返回 4xx 或 5xx 状态码。"],
        "checks": ["curl -I URL", "curl -v URL", "检查 Ingress/Nginx access log 和应用错误日志。"],
        "actions": ["5xx 优先检查后端应用、依赖和最近发布。", "4xx 优先检查路由、认证、路径和防盗链规则。", "确认健康检查 URL 是否应该返回 200。"],
    },
    "dns_failed": {
        "title": "DNS 解析失败",
        "symptoms": ["域名无法解析，网站检测失败。"],
        "checks": ["nslookup domain", "dig domain", "检查本机 /etc/resolv.conf 或 Windows DNS 配置。"],
        "actions": ["确认域名记录存在且未过期。", "检查内外网 DNS 是否一致。", "必要时临时切换到可用解析记录。"],
    },
    "tls_failed": {
        "title": "TLS 握手或证书异常",
        "symptoms": ["HTTPS 握手失败或证书校验失败。"],
        "checks": ["openssl s_client -connect host:443 -servername host", "检查证书链、SNI、域名匹配和过期时间。"],
        "actions": ["重新签发或替换证书。", "检查 Ingress/网关是否加载了正确 secret。", "修复后用浏览器和 curl 双重验证。"],
    },
    "keyword_mismatch": {
        "title": "页面关键字不匹配",
        "symptoms": ["页面可访问但没有出现预期关键字。"],
        "checks": ["curl URL 查看实际响应内容。", "确认是否跳转到登录页、错误页或灰度页面。"],
        "actions": ["如果页面内容正常变更，更新 target 的 expected_keyword。", "如果返回错误页，继续排查应用日志和上游依赖。"],
    },
    "metrics_format_invalid": {
        "title": "Exporter Metrics 格式异常",
        "symptoms": ["/metrics 可访问但不是 Prometheus 文本格式。"],
        "checks": ["curl http://host:port/metrics | head", "确认响应包含 # HELP、# TYPE 或 metric_name value。"],
        "actions": ["确认 exporter 地址路径是否填写为 /metrics。", "检查 exporter 版本、启动参数和认证代理。", "修复后在 Prometheus Targets 中确认 scrape 成功。"],
    },
    "mysql": {
        "title": "MySQL / MariaDB 故障排查",
        "symptoms": ["连接数过高、慢查询增多、QPS 异常或 buffer pool 命中率下降。"],
        "checks": ["SHOW PROCESSLIST;", "SHOW GLOBAL STATUS LIKE 'Threads_connected';", "SHOW GLOBAL STATUS LIKE 'Slow_queries';", "检查 mysqld_exporter /metrics 和数据库错误日志。"],
        "actions": ["先定位慢 SQL、锁等待和连接池是否耗尽。", "必要时临时扩容连接池或限制异常调用方。", "长期优化索引、SQL、缓存和容量。"],
    },
    "redis": {
        "title": "Redis 故障排查",
        "symptoms": ["内存过高、命中率下降、连接数过高、持久化或主从异常。"],
        "checks": ["redis-cli INFO", "redis-cli CLIENT LIST", "redis-cli SLOWLOG GET 10", "检查 redis_exporter 指标。"],
        "actions": ["确认 maxmemory、淘汰策略和大 key。", "检查慢命令、阻塞命令和连接泄漏。", "必要时扩容、拆分热点 key 或修复主从。"],
    },
    "nginx": {
        "title": "Nginx 故障排查",
        "symptoms": ["5xx 增多、连接数异常、上游超时或请求延迟升高。"],
        "checks": ["查看 access.log/error.log。", "nginx -T", "检查 upstream 状态、连接数和 Ingress 事件。"],
        "actions": ["区分 Nginx 自身问题和 upstream 应用问题。", "检查超时、限流、body size、DNS 和后端 endpoint。", "必要时临时摘除异常 upstream。"],
    },
    "postgresql": {
        "title": "PostgreSQL 故障排查",
        "symptoms": ["连接数过高、锁等待、慢查询、事务堆积或复制延迟。"],
        "checks": ["select * from pg_stat_activity;", "select * from pg_locks;", "检查 pg_stat_database 和 postgres_exporter 指标。"],
        "actions": ["定位长事务、锁等待和慢 SQL。", "检查连接池和 max_connections。", "必要时终止异常会话并优化 SQL/索引。"],
    },}


def select_runbooks(context: dict[str, Any]) -> list[dict[str, Any]]:
    context_type = context.get("context_type")
    latest_check = context.get("latest_check") or {}
    target = context.get("target") or {}
    exporter_kind = target.get("exporter_kind")
    alert_summary = context.get("alert_summary") or {}
    selected_alert = context.get("selected_alert") or {}
    recent_alerts = context.get("recent_alerts") or []
    selected: dict[str, dict[str, Any]] = {}

    if context_type in {"alert", "analysis_session"} and selected_alert:
        metric = selected_alert.get("metric")
        if metric in RUNBOOKS:
            selected[metric] = RUNBOOKS[metric]
        return [{"key": key, **value} for key, value in list(selected.items())[:2]]

    for event in recent_alerts:
        metric = event.get("metric")
        if metric in RUNBOOKS:
            selected[metric] = RUNBOOKS[metric]

    if exporter_kind in RUNBOOKS:
        selected[str(exporter_kind)] = RUNBOOKS[str(exporter_kind)]

    target_type = target.get("target_type")
    details = latest_check.get("details") or {}
    if latest_check.get("status") == "down":
        if target_type == "website":
            selected["http_down"] = RUNBOOKS["http_down"]
        elif target_type == "exporter":
            selected["exporter_down"] = RUNBOOKS["exporter_down"]
        elif target_type == "port":
            selected["tcp_down"] = RUNBOOKS["tcp_down"]
    if details.get("metrics_format_ok") is False:
        selected["exporter_down"] = RUNBOOKS["exporter_down"]
    if details.get("tls_ok") is False or details.get("tls_days_remaining") is not None:
        selected["tls_days_remaining"] = RUNBOOKS["tls_days_remaining"]

    active_by_level = alert_summary.get("active_by_level") or {}
    if active_by_level and not selected:
        for metric in ["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent", "load1"]:
            selected[metric] = RUNBOOKS[metric]
            if len(selected) >= 2:
                break

    return [{"key": key, **value} for key, value in list(selected.items())[:4]]




