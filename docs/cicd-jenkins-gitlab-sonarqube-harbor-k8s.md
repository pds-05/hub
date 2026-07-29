# CI/CD 流程说明

目标：Jenkins 从 GitLab 拉取源码，提交 SonarQube 做代码审查，通过后构建镜像，推送到 Harbor，最后发布到 Kubernetes。

## 1. 流程阶段

1. 拉取 GitLab 源码。
2. 后端 Python 语法检查、单元测试并生成 `backend/coverage.xml`。
3. 前端构建检查：`npm ci && npm run build`。
4. Agent 语法检查：`python3 -m compileall agent/agent.py`。
5. SonarQube 代码审查。
6. SonarQube Quality Gate 检查；默认告警但不阻断发布，可通过参数开启严格门禁。
7. 登录 Harbor。
8. 构建 backend、frontend、agent 三个镜像。
9. 推送镜像到 Harbor。
10. 检查 Jenkins 部署权限并应用后端 RBAC。
11. 自动配置持续采集、告警评估和后端 ServiceAccount。
12. 使用 kubectl 更新 K8s Deployment；失败时恢复上一版镜像。

## 2. Jenkins 需要准备的插件

- Git plugin
- Pipeline
- Docker Pipeline 或确保 Jenkins 节点能执行 docker 命令
- SonarQube Scanner for Jenkins
- Credentials Binding
- Kubernetes CLI，或者 Jenkins 节点安装 kubectl

## 3. Jenkins 凭据

需要创建两个凭据。

### harbor-admin

类型：Username with password

内容：

- Username：Harbor 用户名，例如 `admin`
- Password：Harbor 密码
- ID：`harbor-admin`

### kubeconfig-platform

类型：Secret file

内容：上传 `platform/jenkins-deployer` ServiceAccount 对应的 kubeconfig 文件。

首次使用时由集群管理员执行一次：

```bash
kubectl apply -f k8s/jenkins-deployer-rbac.yaml
```

该授权只允许 Jenkins 管理 `platform` 中的平台 Deployment、Pod 和 ServiceAccount，以及 `monitoring` 中的 ScrapeConfig 和对应命名空间级 RBAC。完成这次引导后，后续发布无需再手动执行 Kubernetes 配置命令。

ID：`kubeconfig-platform`

## 4. SonarQube 配置

在 Jenkins 系统配置里添加 SonarQube server：

- Name：`sonarqube`
- Server URL：例如 `http://114.55.117.211:19000`
- Token：SonarQube 用户 Token

Jenkinsfile 里使用的是：

```groovy
withSonarQubeEnv('sonarqube')
```

所以 Name 必须叫 `sonarqube`，或者你改 Jenkinsfile 里的名字。

流水线会安装 `backend/requirements-dev.txt` 中的小型测试依赖，自动生成 Python 覆盖率报告并交给 SonarQube。依赖安装设置了超时，网络异常时会退回普通单元测试，避免阻塞发布。参数 `ENFORCE_SONAR_GATE` 默认关闭，质量门失败时仍会继续发布；测试覆盖成熟后可在 Jenkins 构建参数中开启，让质量门重新阻断发布。

## 5. Harbor 镜像地址

当前 Jenkinsfile 使用：

```text
114.55.117.211:18080/monitor-platform/monitor-backend
114.55.117.211:18080/monitor-platform/monitor-frontend
114.55.117.211:18080/monitor-platform/monitor-agent
```

构建后会推送两个标签：

- `${BUILD_NUMBER}-${GIT_COMMIT_SHORT}`
- `latest`

Agent 还会额外推送：

- `v1`

因为平台生成的 Agent 安装 YAML 默认使用 `monitor-agent:v1`。

## 6. Kubernetes 发布方式

流水线会自动完成：

1. 检查 Jenkins 是否具备所需权限。
2. 应用 `k8s/monitor-backend-scrapeconfig-rbac.yaml`。
3. 配置后端持续采集和定时告警环境变量。
4. 将后端绑定到 `monitor-backend` ServiceAccount。
5. 更新前后端镜像并等待滚动发布。
6. 验证后端运行配置和 ScrapeConfig API 权限。
7. 发布失败时恢复上一版前后端镜像。
8. 发布成功后更新 Harbor 的 `latest` 稳定标签。

这要求集群里已有 Deployment：

```text
monitor-backend
monitor-frontend
```

## 7. 第一次使用步骤

1. 把项目推送到 GitLab。
2. 在 Jenkins 新建 Pipeline 项目。
3. Pipeline 选择 Pipeline script from SCM。
4. SCM 选择 Git。
5. 填 GitLab 仓库地址和凭据。
6. Script Path 填：`Jenkinsfile`。
7. 保存后点击 Build Now。

## 8. 注意事项

- Jenkins 运行节点必须能访问 Harbor：`http://114.55.117.211:18080`。
- Jenkins 运行节点必须能执行 Docker build/push。
- 如果 Harbor 是 HTTP，需要在 Jenkins 节点 Docker 配置 insecure registry：

```json
{
  "insecure-registries": ["114.55.117.211:18080"]
}
```

然后重启 Docker：

```bash
systemctl restart docker
```

- Jenkins 运行节点必须能访问 Kubernetes API。
- 如果前端 Nginx 配置出现 BOM 问题，Jenkinsfile 已在构建前执行：

```bash
sed -i '1s/^\xEF\xBB\xBF//' frontend/nginx.conf
```
