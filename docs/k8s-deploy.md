# Deploy backend and frontend to Kubernetes

This project is deployed as two images:

- `monitor-backend`: FastAPI service, internal ClusterIP only.
- `monitor-frontend`: Nginx static frontend, proxies `/api/` to backend inside Kubernetes.

Replace these placeholders before building:

- `<REGISTRY_NAMESPACE>`: your image namespace, for example `registry.cn-hangzhou.aliyuncs.com/my-namespace`.
- `<TAG>`: image version, for example `v1`.

## 1. Build images on Windows

Run from `C:\Users\asus\Documents\New project`:

```powershell
docker build -t <REGISTRY_NAMESPACE>/monitor-backend:<TAG> .\backend
docker build -t <REGISTRY_NAMESPACE>/monitor-frontend:<TAG> .\frontend
```

## 2. Push images

```powershell
docker login registry.cn-hangzhou.aliyuncs.com
docker push <REGISTRY_NAMESPACE>/monitor-backend:<TAG>
docker push <REGISTRY_NAMESPACE>/monitor-frontend:<TAG>
```

## 3. Update Kubernetes YAML image names

Edit:

- `backend/k8s/backend.yaml`
- `frontend/k8s/frontend.yaml`

Set image fields to:

```yaml
image: <REGISTRY_NAMESPACE>/monitor-backend:<TAG>
image: <REGISTRY_NAMESPACE>/monitor-frontend:<TAG>
```

## 4. Put secrets into Kubernetes

Do not write real secrets into git. Use commands like this on `k8s-control-01`:

```bash
kubectl -n platform create secret generic monitor-backend-secret \
  --from-literal=SECRET_KEY='replace-with-long-random-string' \
  --from-literal=DATABASE_URL='postgresql+psycopg://monitor_admin:monitor123@postgresql.platform.svc.cluster.local:5432/monitor_platform' \
  --from-literal=REDIS_URL='redis://:redis123@redis.platform.svc.cluster.local:6379/0' \
  --from-literal=AI_API_KEY='your-deepseek-api-key' \
  --dry-run=client -o yaml | kubectl apply -f -
```

If SMTP is enabled, add these literals too:

```bash
--from-literal=SMTP_HOST='smtp.example.com'
--from-literal=SMTP_PORT='587'
--from-literal=SMTP_USERNAME='your-email@example.com'
--from-literal=SMTP_PASSWORD='your-smtp-auth-code'
--from-literal=SMTP_FROM_EMAIL='your-email@example.com'
--from-literal=SMTP_USE_TLS='true'
```

## 5. Apply manifests

```bash
kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f backend/k8s/backend.yaml
kubectl apply -f frontend/k8s/frontend.yaml
```

## 6. Check status

```bash
kubectl get pods -n platform -o wide
kubectl get svc -n platform
kubectl logs -n platform deploy/monitor-backend --tail=100
kubectl logs -n platform deploy/monitor-frontend --tail=100
```

## 7. Open platform

The frontend service is exposed by NodePort `30080`:

```text
http://114.55.117.211:30080
```

If the cloud security group does not allow `30080`, open TCP port `30080` first.