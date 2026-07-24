# Harbor private registry setup

Harbor will be used as the private image registry for this platform.

Recommended first deployment for this lab:

- Host: `k8s-control-01`
- URL: `http://114.55.117.211:18080`
- Registry endpoint: `114.55.117.211:18080`
- Mode: HTTP + insecure registry for quick testing

For production, switch to HTTPS and a real domain later.

## 1. Install Docker and Compose on k8s-control-01

```bash
docker version
docker compose version
```

If Docker is not installed, install Docker first. Harbor offline installer requires Docker Engine and Docker Compose.

## 2. Download Harbor offline installer

```bash
cd /opt
wget https://github.com/goharbor/harbor/releases/download/v2.14.0/harbor-offline-installer-v2.14.0.tgz
tar -zxvf harbor-offline-installer-v2.14.0.tgz
cd harbor
cp harbor.yml.tmpl harbor.yml
```

## 3. Edit harbor.yml

```bash
vi harbor.yml
```

Use these important values:

```yaml
hostname: 114.55.117.211
http:
  port: 18080
# Comment out the whole https section for first HTTP test.
harbor_admin_password: Harbor12345
data_volume: /data/harbor
```

For HTTP test mode, make sure the `https:` block is commented out.

## 4. Install Harbor

```bash
./prepare
./install.sh
```

Check containers:

```bash
docker ps
```

Open:

```text
http://114.55.117.211:18080
```

Default user:

```text
admin
```

Password is the `harbor_admin_password` configured in `harbor.yml`.

## 5. Create Harbor project

In Harbor web UI:

1. Log in as `admin`.
2. Create project: `monitor-platform`.
3. For testing, set it public or create a robot account for image pull.

## 6. Configure Docker client insecure registry

On the machine where you build and push images:

Linux Docker:

```bash
mkdir -p /etc/docker
cat >/etc/docker/daemon.json <<EOF
{
  "insecure-registries": ["114.55.117.211:18080"]
}
EOF
systemctl restart docker
```

Then login:

```bash
docker login 114.55.117.211:18080
```

## 7. Configure K3s nodes to pull from HTTP Harbor

On every K3s node: `k8s-control-01`, `k8s-worker-01`, `k8s-worker-02`:

```bash
mkdir -p /etc/rancher/k3s
cat >/etc/rancher/k3s/registries.yaml <<EOF
mirrors:
  "114.55.117.211:18080":
    endpoint:
      - "http://114.55.117.211:18080"
EOF
```

Restart K3s services:

Control node:

```bash
systemctl restart k3s
```

Worker nodes:

```bash
systemctl restart k3s-agent
```

## 8. Build and push platform images

From the project root on the build machine:

```powershell
docker build -t 114.55.117.211:18080/monitor-platform/monitor-backend:v1 .\backend
docker build -t 114.55.117.211:18080/monitor-platform/monitor-frontend:v1 .\frontend

docker push 114.55.117.211:18080/monitor-platform/monitor-backend:v1
docker push 114.55.117.211:18080/monitor-platform/monitor-frontend:v1
```

## 9. Update Kubernetes YAML image names

Backend:

```yaml
image: 114.55.117.211:18080/monitor-platform/monitor-backend:v1
```

Frontend:

```yaml
image: 114.55.117.211:18080/monitor-platform/monitor-frontend:v1
```

Then apply manifests.