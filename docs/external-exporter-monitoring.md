# 外部 Exporter 持续监控

平台现在支持把用户保存的 Prometheus Exporter 地址自动注册为 `ScrapeConfig`：

```text
用户添加 Exporter Target
→ 后端创建 ScrapeConfig
→ Prometheus 每 30 秒持续采集
→ 平台按 user_id + target_id 隔离查询
→ 页面展示实时值和历史曲线
→ 后台每 60 秒评估告警规则并发送通知
```

## 支持范围

通用采集适用于所有 Exporter 类型，包括 Node、MySQL、Nginx、Redis、PostgreSQL、MongoDB、Kafka、RabbitMQ、Elasticsearch、ClickHouse、ZooKeeper、etcd、Blackbox、cAdvisor、Windows、Process、JMX 和自定义 Exporter。

平台为常见中间件提供核心指标卡片。自定义 Exporter 会自动展示发现到的前 8 个指标，并列出全部已发现指标名称。

## 网络要求

生产环境默认只接受公网 Exporter 地址：

```env
PROMETHEUS_ALLOW_PRIVATE_TARGETS=false
```

这样可以阻止普通用户通过采集功能访问平台 localhost、Kubernetes Service、云元数据和私网资源。

当平台与客户环境通过 VPN、专线或可信 VPC 互通时，可以改为：

```env
PROMETHEUS_ALLOW_PRIVATE_TARGETS=true
```

只应在平台用户和目标网络均可信时开启。

## Prometheus Operator

后端通过 Kubernetes API 管理 `monitoring` 命名空间中的 `ScrapeConfig`。先应用：

```bash
kubectl apply -f k8s/monitor-backend-scrapeconfig-rbac.yaml
```

Deployment 必须使用：

```yaml
spec:
  template:
    spec:
      serviceAccountName: monitor-backend
```

ConfigMap 需要启用：

```yaml
PROMETHEUS_SCRAPE_CONFIG_ENABLED: "true"
PROMETHEUS_SCRAPE_CONFIG_NAMESPACE: "monitoring"
PROMETHEUS_SCRAPE_CONFIG_API_VERSION: "monitoring.coreos.com/v1alpha1"
PROMETHEUS_SCRAPE_CONFIG_LABELS_JSON: '{"release":"monitoring"}'
PROMETHEUS_TARGET_SCRAPE_INTERVAL: "30s"
PROMETHEUS_TARGET_SCRAPE_TIMEOUT: "10s"
TARGET_ALERT_EVALUATION_ENABLED: "true"
TARGET_ALERT_EVALUATION_INTERVAL_SECONDS: "60"
```

`PROMETHEUS_SCRAPE_CONFIG_LABELS_JSON` 必须匹配 Prometheus CR 的 `scrapeConfigSelector`。如果集群使用的不是 `release=monitoring`，需要按实际标签调整。

## 验证

查看平台生成的采集配置：

```bash
kubectl get scrapeconfig -n monitoring -l monitor-platform-managed=true
```

查看一个 Target 的配置：

```bash
kubectl get scrapeconfig -n monitoring monitor-target-TARGET_ID -o yaml
```

查询 Prometheus 是否采集成功：

```bash
kubectl exec -n monitoring prometheus-monitoring-ack-prometheus-prometheus-0 -c prometheus -- \
  wget -qO- 'http://127.0.0.1:9090/api/v1/query?query=up%7Bplatform_target_id%3D%22TARGET_ID%22%7D'
```

页面中选择 Target 后，可以点击“同步采集”，等待约 30 秒，再点击“刷新指标”。