# Kubernetes Intelligent Monitoring Platform Plan

## Project Positioning

This project is a Kubernetes intelligent monitoring and operations platform based on Prometheus, Grafana, Alertmanager, Loki, and a large language model API.

The platform does not replace Prometheus, Grafana, or Alertmanager. It integrates them into one website and adds AI-assisted troubleshooting, alert explanation, PromQL generation, log analysis, and operational guidance.

## Confirmed Technical Stack

### Cloud And Cluster

- Cloud provider: Alibaba Cloud ECS
- Cluster architecture: 1 control-plane node + 2 worker nodes
- Kubernetes distribution: K3s
- Operating system: Ubuntu 22.04 or Ubuntu 24.04

Recommended ECS configuration:

- control-plane: 2 vCPU, 4 GB memory, 80 GB cloud disk
- worker-1: 4 vCPU, 8 GB memory, 100 GB cloud disk
- worker-2: 4 vCPU, 8 GB memory, 100 GB cloud disk

### Application Stack

- Backend: Python + FastAPI
- Frontend: React + TypeScript + Ant Design + ECharts
- Database: PostgreSQL
- Cache / task support: Redis
- Container image build: Docker
- K3s runtime: containerd
- Image registry: Alibaba Cloud ACR or Docker Hub

### Monitoring Stack

- Metrics: Prometheus
- Visualization: Grafana
- Alerting: Alertmanager
- Installation method: Helm + kube-prometheus-stack
- Kubernetes metrics: kube-state-metrics
- Node metrics: node-exporter
- Blackbox probing: blackbox-exporter, optional

### Logging Stack

- Logs: Loki
- Log collector: Promtail
- Query usage: website backend calls Loki API, and AI assistant uses logs for troubleshooting.

### AI Stack

- Large model: external API, such as OpenAI API, Azure OpenAI, Tongyi Qianwen, DeepSeek, Zhipu GLM, or Doubao.
- AI assistant is read-only in the first version.
- Dangerous actions such as deleting pods, restarting workloads, or scaling services require manual confirmation.

### Traffic And Security

- Ingress: Nginx Ingress or K3s default Traefik
- HTTPS: cert-manager + Let's Encrypt
- Domain and DNS: Alibaba Cloud domain + Alibaba Cloud DNS
- Authentication: JWT
- Authorization: RBAC
- Password hashing: bcrypt
- Sensitive configuration: Kubernetes Secret
- Audit: record important user operations

## Deployment Logic

Only self-developed code needs to be packaged by Docker:

- FastAPI backend
- React frontend
- Optional custom AI analysis worker

Third-party middleware is deployed with Helm charts or official images:

- Prometheus
- Grafana
- Alertmanager
- PostgreSQL
- Redis
- Loki
- Promtail
- Nginx Ingress
- cert-manager
- node-exporter
- kube-state-metrics

The image workflow is:

```text
source code
  -> Dockerfile
  -> docker build
  -> docker push to Alibaba Cloud ACR / Docker Hub
  -> K3s pulls image
  -> containerd runs the container as a Pod
```

## Target System Architecture

```text
User browser
  -> Domain + HTTPS
  -> Ingress
  -> React frontend
  -> FastAPI backend
      -> Prometheus API
      -> Grafana API
      -> Alertmanager API
      -> Kubernetes API
      -> Loki API
      -> PostgreSQL
      -> Redis
      -> Large model API

K3s cluster
  -> 1 control-plane node
  -> 2 worker nodes
```

## Main Website Modules

1. Login and user system
2. Cluster overview
3. Node monitoring
4. Pod and workload monitoring
5. Grafana dashboard integration
6. Prometheus metric query
7. Alert center
8. Alert rule management
9. Contact and notification management
10. Log center
11. AI intelligent assistant
12. System settings
13. Audit logs
14. Runbook knowledge base

## AI Assistant Capabilities

The assistant should not be a simple chatbot. It should use monitoring tools and system data.

Main capabilities:

- Explain alerts
- Analyze why a Pod restarts
- Analyze CPU or memory spikes
- Generate PromQL
- Summarize recent error logs
- Recommend troubleshooting steps
- Recommend possible fixes
- Use Runbook knowledge as context

Basic AI workflow:

```text
User question
  -> backend classifies intent
  -> backend queries Prometheus / Kubernetes API / Alertmanager / Loki
  -> backend builds structured context
  -> backend calls large model API
  -> AI returns analysis and suggestions
  -> website displays the result
```

## 12 Project Stages

### Stage 1: Prepare Alibaba Cloud ECS

Goal: Prepare the three cloud servers.

Steps:

1. Buy 3 Alibaba Cloud ECS instances.
2. Choose Ubuntu 22.04 or Ubuntu 24.04.
3. Configure security groups.
4. Allow SSH, HTTP, HTTPS, and required internal K3s communication.
5. Confirm private network connectivity between nodes.
6. Set hostnames:
   - k8s-control-01
   - k8s-worker-01
   - k8s-worker-02

### Stage 2: Build The K3s Cluster

Goal: Create a working Kubernetes cluster.

Steps:

1. Install K3s server on the control-plane node.
2. Get the node token.
3. Install K3s agent on both worker nodes.
4. Join the workers to the control-plane.
5. Verify with `kubectl get nodes`.

Expected result:

```text
k8s-control-01   Ready   control-plane
k8s-worker-01    Ready   worker
k8s-worker-02    Ready   worker
```

### Stage 3: Install Basic Cluster Components

Goal: Make the cluster ready for application deployment.

Steps:

1. Install Helm.
2. Install or configure Ingress Controller.
3. Install cert-manager.
4. Configure StorageClass.
5. Create namespaces:
   - monitoring
   - platform
   - logging
   - ingress

### Stage 4: Install Prometheus, Grafana, And Alertmanager

Goal: Build the monitoring base.

Steps:

1. Add the prometheus-community Helm repository.
2. Install kube-prometheus-stack.
3. Verify Prometheus.
4. Verify Grafana.
5. Verify Alertmanager.
6. Verify kube-state-metrics and node-exporter.
7. Confirm that Kubernetes metrics are collected.

### Stage 5: Install Loki Logging System

Goal: Add log collection and query capability.

Steps:

1. Install Loki.
2. Install Promtail.
3. Confirm Pod logs are collected.
4. Connect Grafana to Loki.
5. Prepare backend API integration with Loki.

First version log features:

- Query by namespace
- Query by pod
- Query by keyword
- Query recent logs by time range

### Stage 6: Design FastAPI Backend

Goal: Build the backend API service.

Recommended modules:

- auth
- users
- clusters
- metrics
- alerts
- rules
- dashboards
- logs
- assistant
- settings
- audit

Backend integrations:

- Prometheus API
- Alertmanager API
- Grafana API
- Kubernetes API
- Loki API
- large model API
- PostgreSQL
- Redis

First version priorities:

1. Login
2. Cluster overview API
3. Node metrics API
4. Pod status API
5. Alert list API
6. AI assistant API

### Stage 7: Design React Frontend

Goal: Build the website UI.

Recommended stack:

- React
- TypeScript
- Ant Design
- ECharts

Main pages:

1. Login page
2. Overview dashboard
3. Monitoring center
4. Alert center
5. Log center
6. AI assistant
7. System management

### Stage 8: Integrate AI Assistant

Goal: Make AI useful for troubleshooting.

Steps:

1. Configure large model API key.
2. Build assistant backend endpoint.
3. Add tool-like backend functions for Prometheus, Kubernetes, Alertmanager, and Loki.
4. Build structured prompt context.
5. Return alert explanation, root cause analysis, PromQL, and repair suggestions.

First version AI scenarios:

- Explain an alert
- Analyze Pod restart
- Analyze CPU or memory spike
- Generate PromQL
- Summarize error logs
- Give troubleshooting steps

### Stage 9: Deploy The Website To K8s

Goal: Run the self-developed website inside the K3s cluster.

Steps:

1. Write backend Dockerfile.
2. Write frontend Dockerfile.
3. Build images with Docker.
4. Push images to Alibaba Cloud ACR or Docker Hub.
5. Write Kubernetes Deployment and Service manifests.
6. Write ConfigMap and Secret.
7. Deploy backend and frontend to the platform namespace.
8. Verify Pods and Services.

### Stage 10: Configure Domain And HTTPS

Goal: Let users access the website through a domain name.

Steps:

1. Buy or prepare a domain.
2. Add DNS record.
3. Point `monitor.example.com` to the public IP.
4. Configure Ingress.
5. Use cert-manager to request HTTPS certificate.
6. Verify `https://monitor.example.com`.

Only the website should be exposed publicly in the first version. Prometheus, Alertmanager, and Kubernetes API should not be directly exposed to the internet.

### Stage 11: Complete Graduation Project Features

Goal: Make the platform look complete.

Recommended features:

1. Alert contact management
2. Alert rule management
3. Monitoring target management
4. Runbook knowledge base
5. Audit logs
6. AI alert analysis
7. AI PromQL generation
8. AI log summary
9. Grafana dashboard embedding
10. Basic role-based permission control

### Stage 12: Prepare Thesis And Defense

Goal: Prepare graduation materials and demo flow.

Thesis chapters:

1. Background
2. Requirement analysis
3. Overall system architecture
4. Kubernetes cluster design
5. Prometheus monitoring module design
6. Grafana visualization module design
7. Alertmanager alerting module design
8. AI assistant module design
9. System implementation
10. System testing
11. Conclusion and future work

Demo flow:

1. Show K3s nodes.
2. Show Prometheus metrics collection.
3. Show Grafana dashboards.
4. Show website overview page.
5. Show node and Pod monitoring.
6. Trigger a test alert.
7. Show alert center.
8. Ask AI to analyze the alert.
9. Ask AI to generate PromQL.
10. Show log-assisted troubleshooting.

## Recommended Execution Timeline

Week 1:

- Buy ECS servers.
- Build K3s cluster.
- Verify `kubectl get nodes`.

Week 2:

- Install Prometheus, Grafana, and Alertmanager.
- Confirm K8s metrics are collected.

Week 3:

- Build FastAPI backend.
- Connect Prometheus API.

Week 4:

- Build React frontend.
- Complete overview and monitoring pages.

Week 5:

- Connect Alertmanager and Kubernetes API.

Week 6:

- Integrate AI assistant.

Week 7:

- Add Loki logs.
- Improve alert analysis.

Week 8:

- Configure domain and HTTPS.
- Prepare thesis and demo.

## Minimum Successful Version

The first successful version should include:

1. User can log in to the website.
2. Website can display K3s cluster metrics.
3. Website can display node and Pod status.
4. Website can display current alerts.
5. Website can embed or link Grafana dashboards.
6. AI assistant can analyze a selected alert or abnormal Pod.

Once these six points are complete, the graduation project has a solid main body.
