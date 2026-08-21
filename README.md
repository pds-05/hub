# 云原生 AIOps 智能运维平台

一个面向 SRE、DevOps 与运维开发场景的云原生监控和故障诊断平台。项目将 Prometheus、Grafana、Loki、Alertmanager 与 Kubernetes 统一接入 Web 控制台，并通过 Dify Agent、LLM 和 Runbook RAG 提供带实时证据的只读运维诊断能力。

> 本项目用于个人学习、工程实践与求职展示。当前部署以低流量演示环境为目标；用于生产环境前，需要进一步完善高可用、备份、密钥管理、容量规划和灾难恢复。

## 核心能力

- **统一监控对象管理**：接入网站、TCP 端口、Prometheus Exporter 和外部 Kubernetes 集群。
- **自动指标采集**：保存 Target 后生成或更新 Prometheus Operator `ScrapeConfig`，将目标纳入持续采集。
- **可用性检测**：支持 HTTP/HTTPS 状态码、响应时间、DNS、TLS、页面关键字和 TCP 连通性检查。
- **多类型 Exporter**：覆盖 Node、MySQL、Nginx、Redis、PostgreSQL、MongoDB、Kafka、RabbitMQ、Elasticsearch、ClickHouse、ZooKeeper、etcd、JMX、Windows、Process、cAdvisor 等场景。
- **外部集群 Agent**：通过独立 Token 和安装清单接入外部 Kubernetes 集群，采集节点、工作负载、Pod、资源、存储、网络、Warning Event 与日志摘要。
- **告警闭环**：支持告警规则、等级、触发与恢复、确认、处置记录、关闭和事件时间线。
- **通知渠道**：支持 SMTP 邮件、钉钉、飞书、企业微信及通用 Webhook，可按告警等级和触发/恢复状态发送。
- **日志查询**：通过 Loki 按命名空间、应用、Pod、容器、级别、关键词和时间范围筛选日志。
- **Grafana 集成**：为监控对象提供指标图表和专属仪表盘，通过平台身份上下文访问 Grafana。
- **受控 AI 诊断**：Dify Agent 按需查询告警、Target、Prometheus、Loki、关联告警、Kubernetes Event、服务依赖和故障时间线。
- **诊断评测与反馈**：保存工具调用审计、证据摘要、评测用例和人工反馈，辅助判断诊断结果是否可信。
- **CI/CD**：Jenkins 完成检查、测试、SonarQube 分析、Docker 构建、Harbor 推送及 Kubernetes 滚动发布。

## 系统架构

```mermaid
flowchart TB
    User["用户浏览器"] --> Ingress["Nginx Ingress + HTTPS"]
    Ingress --> Frontend["React + TypeScript"]
    Frontend --> Backend["FastAPI"]

    Backend --> PostgreSQL[(PostgreSQL)]
    Backend --> Redis[(Redis)]
    Backend --> Prometheus["Prometheus"]
    Backend --> Loki["Loki"]
    Backend --> Grafana["Grafana"]
    Backend --> Alertmanager["Alertmanager"]
    Backend --> K8sAPI["Kubernetes API"]

    ExternalCluster["外部 Kubernetes 集群"] --> Agent["Monitor Agent"]
    Agent --> Backend

    Backend --> Dify["Dify Agent"]
    Dify --> LLM["LLM / DeepSeek"]
    Dify --> Runbook["Runbook RAG"]
    Dify --> Tools["FastAPI 只读诊断工具"]
    Tools --> Backend

    Git["Gitee / GitHub"] --> Jenkins["Jenkins"]
    Jenkins --> Sonar["SonarQube"]
    Jenkins --> Harbor["Harbor"]
    Harbor --> K3s["K3s 集群"]
```

## AI 诊断设计

平台 AI 助手不是直接让模型生成结论，而是由平台控制诊断范围，再由 Agent 在边界内选择只读工具：

```text
用户选择告警或 Target
        ↓
FastAPI 校验用户身份、Target 与告警归属
        ↓
生成短时 diagnosis_token
        ↓
调用 Dify Agent
        ↓
Agent 检索 Runbook，并按需调用只读工具
        ↓
LLM 根据实时证据生成结构化诊断报告
        ↓
平台保存报告、工具审计、评测结果与人工反馈
```

当前工具包括：

| 工具 | 用途 |
| --- | --- |
| `get_alert_context` | 获取当前告警上下文与状态 |
| `get_target_status` | 获取监控对象配置和最近检查状态 |
| `get_target_metrics` | 按白名单查询可用性、响应时间、资源及中间件指标 |
| `search_target_logs` | 查询带 `platform_target_id` 标签的 Target 日志 |
| `get_related_alerts` | 查询时间窗口内的关联告警 |
| `get_kubernetes_events` | 获取用户所属集群的 Kubernetes Warning Event |
| `get_service_dependencies` | 获取用户维护的服务依赖拓扑 |
| `get_incident_timeline` | 汇总告警活动、检查结果和上下文时间线 |

### Agent 安全边界

- 诊断 Token 默认有效期不超过 10 分钟。
- 后端从 Token 获取用户与 Target 范围，不信任模型传入的用户 ID。
- 指标类型、查询时间、日志条数和单次诊断工具调用次数均有限制。
- 工具调用记录参数摘要、耗时、状态和结果摘要。
- 不开放任意 PromQL、LogQL、SQL、Shell 或 `kubectl`。
- Agent 不执行重启、删除、扩缩容或配置变更，只能提供建议命令供人工确认。
- Kubernetes Event 和服务依赖仅作为关联上下文，不被直接当作因果证据。

Runbook 位于 [`docs/runbooks`](docs/runbooks)，目前覆盖节点资源、网站与 TCP、Exporter，以及常见数据库、中间件和 Kubernetes 工作负载故障。

## 技术栈

| 领域 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、Ant Design、ECharts |
| 后端 | Python 3.12、FastAPI、SQLAlchemy、Pydantic、HTTPX |
| 数据与缓存 | PostgreSQL、Redis |
| 可观测性 | Prometheus、Alertmanager、Grafana、Loki、Promtail、Blackbox Exporter |
| AI | Dify Agent、LLM / DeepSeek、Runbook RAG、OpenAPI Tools |
| 云原生 | Docker、Kubernetes、K3s、Helm、Nginx Ingress、cert-manager |
| DevOps | Gitee、GitHub、Jenkins、SonarQube、Harbor |

## 项目结构

```text
.
├── backend/                 # FastAPI API、数据模型、服务和测试
├── frontend/                # React + TypeScript 管理控制台
├── agent/                   # 外部 Kubernetes 集群采集 Agent
├── k8s/                     # RBAC、Exporter 和部署补充清单
├── config/                  # 配置示例
├── docs/                    # 部署、CI/CD、用户手册和 Agent 文档
│   └── runbooks/            # Dify RAG 使用的运维 Runbook
├── Jenkinsfile              # CI/CD Pipeline
└── sonar-project.properties # SonarQube 配置
```

## 本地开发

### 环境要求

- Python 3.12+
- Node.js 22+
- PostgreSQL
- Redis
- 可访问的 Prometheus、Loki 和 Grafana；不使用相关功能时可保留为空或关闭对应开关

### 启动后端

```bash
cd backend
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell 可将复制命令替换为：

```powershell
Copy-Item .env.example .env
```

后端 API 文档：`http://127.0.0.1:8000/docs`

### 启动前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`

前端环境变量示例：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_GRAFANA_URL=http://127.0.0.1:3000/grafana
```

### 配置后端

复制 [`backend/.env.example`](backend/.env.example) 后，至少按本地环境修改：

```env
SECRET_KEY=replace-with-a-long-random-string
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/monitor_platform
REDIS_URL=redis://localhost:6379/0
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
GRAFANA_URL=http://localhost:3000/grafana
```

AI 诊断还需要已发布的 Dify Agent：

```env
DIFY_API_BASE_URL=https://your-dify.example.com/v1
DIFY_APP_API_KEY=replace-with-dify-app-api-key
DIFY_TOOL_SECRET=replace-with-a-separate-random-secret
DIFY_TOOL_PUBLIC_BASE_URL=https://your-platform.example.com/api/v1/assistant/tools
```

SMTP、数据库密码、Webhook Token、LLM API Key 和 Dify Key 均不得提交到 Git。

## Docker 构建

```bash
docker build -t monitor-backend:dev ./backend
docker build -t monitor-frontend:dev ./frontend
docker build -t monitor-agent:dev ./agent
```

前端镜像使用 Node.js 完成 Vite 构建，再由 Nginx 提供静态资源；后端与 Agent 使用 Python 镜像运行。

## Kubernetes 部署

部署前应具备：

- Kubernetes 或 K3s 集群
- Ingress Controller 与 cert-manager
- PostgreSQL、Redis
- Prometheus Operator 及 `ScrapeConfig` CRD
- Prometheus、Alertmanager、Grafana、Loki 与 Promtail
- 可供集群拉取的应用镜像仓库

创建命名空间并应用示例清单：

```bash
kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f backend/k8s/backend.yaml
kubectl apply -f frontend/k8s/frontend.yaml
kubectl apply -f k8s/monitor-backend-scrapeconfig-rbac.yaml
kubectl apply -f k8s/blackbox-exporter.yaml
```

正式部署前，请基于 [`backend/k8s/backend-secret.example.yaml`](backend/k8s/backend-secret.example.yaml) 创建 `monitor-backend-secret`，并修改镜像地址、域名、Service 类型和集群内服务地址。示例清单不能直接视为生产配置。

详细文档：

- [Kubernetes 部署](docs/k8s-deploy.md)
- [外部 Exporter 接入](docs/external-exporter-monitoring.md)
- [用户手册](docs/user-manual.md)
- [AI 诊断升级说明](docs/ai-diagnosis-upgrade.md)

## CI/CD

Jenkins Pipeline 当前执行：

1. 拉取代码并生成不可变镜像标签。
2. 后端、前端和 Agent 的语法检查与单元测试。
3. SonarQube 静态分析与 Quality Gate。
4. 构建 Backend、Frontend 和 Agent 镜像。
5. 推送版本镜像到 Harbor。
6. 检查 Kubernetes 发布权限。
7. 更新 Deployment 镜像并等待滚动发布。
8. 发布失败时尝试恢复上一版本镜像。

流水线所需凭据应保存在 Jenkins Credentials 中，不应写入 `Jenkinsfile` 或仓库。

## 验证与测试

```bash
# 后端语法检查
python -m compileall backend/app

# 后端单元测试（安装 requirements-dev.txt 后）
python -m pytest backend/tests -q

# 前端生产构建
cd frontend
npm ci
npm run build
```

部署后可检查：

```bash
kubectl -n platform get pods
kubectl -n platform rollout status deployment/monitor-backend --timeout=180s
kubectl -n platform rollout status deployment/monitor-frontend --timeout=180s
```

## 当前限制

- 默认示例以单副本和低流量环境为主，不代表高可用部署。
- K3s `local-path` 适合测试场景，不能替代跨节点共享存储和备份方案。
- PostgreSQL、Redis、Prometheus、Loki、Grafana 和 Dify 的高可用与灾备需要单独设计。
- AI 诊断结果是辅助证据和排障建议，不能替代人工确认，也不应直接驱动生产变更。
- Kubernetes Event 与时间相关性不等于根因，需要结合指标、日志和变更记录判断。
- 仓库暂未声明开源许可证；未添加许可证前，默认保留全部权利。

## 安全说明

- 不提交 `.env`、Kubernetes Secret、SMTP 授权码、Webhook Token、LLM Key、Dify Key、Harbor 凭据或 kubeconfig。
- 外部 Exporter 应限制来源地址，优先通过内网、VPN、专线或受控代理接入。
- 公网入口应启用 HTTPS、限流、敏感路径拦截和访问日志审计。
- Agent Token 与平台凭据应按环境隔离并定期轮换。
- 日志和 AI 上下文必须脱敏，避免上传密码、Token、Secret 和不必要的用户数据。

## 项目定位

本项目重点展示以下工程能力：

- Kubernetes 与云原生平台运维
- Prometheus / Grafana / Loki 可观测性体系
- FastAPI 运维平台开发
- 告警、通知与故障处理闭环
- 受控 Agent、RAG 和工具调用在 AIOps 场景中的落地
- Jenkins、SonarQube、Harbor 与 Kubernetes 持续交付
