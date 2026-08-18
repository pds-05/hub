# AIOps Runbook 知识库

本目录是平台 AI 诊断助手的运维知识源。每篇 Markdown 对应一类可复用的排障路径，而不是为每个指标机械复制一份文档。

## Dify 导入方式

1. 在 Dify 控制台创建知识库，名称填写 `AIOps Runbook`。
2. 选择“导入已有文本”或“上传文件”，一次上传本目录中除本文件外的所有 `.md` 文件。
3. 使用通用高质量分段；分段长度建议 500 到 800 字符，分段重叠 80 到 120 字符。
4. 选择中文检索可用的 Embedding 模型，开启检索测试。
5. 在 Agent 应用中添加“知识检索”能力，知识库选择 `AIOps Runbook`。

## 使用边界

- 文档中的命令仅用于人工核验，Agent 只能提供建议，不能执行 Shell、SQL、kubectl 或任何变更操作。
- 实际结论必须优先使用 Prometheus、Loki、Target 状态和告警上下文等实时证据；Runbook 只提供排障路径。
- 指标标识与 `backend/app/schemas/alert_rule.py` 保持对应。当前所有可创建的告警指标均至少被一篇 Runbook 覆盖。

## 文档索引

- `01-node-resource.md`：节点 CPU、内存、磁盘、负载
- `02-website-tcp-availability.md`：网站、HTTP、TLS、DNS、TCP 可用性
- `03-exporter-collection.md`：Exporter 可用性和采集质量
- `04-mysql-mariadb.md`
- `05-redis.md`
- `06-postgresql.md`
- `07-nginx.md`
- `08-mongodb.md`
- `09-kafka.md`
- `10-rabbitmq.md`
- `11-elasticsearch.md`
- `12-clickhouse.md`
- `13-zookeeper.md`
- `14-etcd.md`
- `15-jvm.md`
- `16-windows.md`
- `17-process.md`
- `18-kubernetes-workload-health.md`：集群 Agent 可上报的 Pod 与 DNS 故障参考
