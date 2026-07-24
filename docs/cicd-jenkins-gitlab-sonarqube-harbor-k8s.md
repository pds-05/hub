# CI/CD 流程说明

目标：Jenkins 从 GitLab 拉取源码，提交 SonarQube 做代码审查，通过后构建镜像，推送到 Harbor，最后发布到 Kubernetes。

## 1. 流程阶段

1. 拉取 GitLab 源码。
2. 后端 Python 语法检查：`python3 -m compileall backend/app`。
3. 前端构建检查：`npm ci && npm run build`。
4. Agent 语法检查：`python3 -m compileall agent/agent.py`。
5. SonarQube 代码审查。
6. SonarQube Quality Gate 门禁。
7. 登录 Harbor。
8. 构建 backend、frontend、agent 三个镜像。
9. 推送镜像到 Harbor。
10. 使用 kubectl 更新 K8s Deployment。

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

内容：上传可以访问 platform 命名空间的 kubeconfig 文件

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

流水线使用：

```bash
kubectl -n platform set image deployment/monitor-backend monitor-backend=<backend-image>
kubectl -n platform set image deployment/monitor-frontend monitor-frontend=<frontend-image>
```

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
