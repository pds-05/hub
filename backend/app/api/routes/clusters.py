from datetime import datetime, timezone
import secrets
from textwrap import dedent

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.cluster_agent import ClusterAgentHeartbeat, ClusterAgentReport
from app.models.managed_cluster import ManagedCluster
from app.models.user import User
from app.schemas.common import MessageResponse
from app.services.cluster_agent_config import normalize_agent_public_api_url
from app.schemas.managed_cluster import (
    ClusterAgentAck,
    ClusterAgentHeartbeatRead,
    ClusterAgentReportRead,
    ClusterHeartbeatIn,
    ClusterReportIn,
    ManagedClusterCreate,
    ManagedClusterInstallRead,
    ManagedClusterRead,
    ManagedClusterUpdate,
)

router = APIRouter(prefix="/clusters", tags=["clusters"])
agent_router = APIRouter(prefix="/agent", tags=["cluster agent"])


def new_agent_token() -> str:
    return secrets.token_urlsafe(48)


def get_owned_cluster(cluster_id: int, db: Session, current_user: User) -> ManagedCluster:
    cluster = (
        db.query(ManagedCluster)
        .filter(ManagedCluster.id == cluster_id, ManagedCluster.user_id == current_user.id, ManagedCluster.deleted_at.is_(None))
        .first()
    )
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    return cluster


def get_agent_cluster(agent_token: str | None, db: Session) -> ManagedCluster:
    token = (agent_token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent token is required")
    cluster = (
        db.query(ManagedCluster)
        .filter(ManagedCluster.agent_token == token, ManagedCluster.deleted_at.is_(None))
        .first()
    )
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")
    return cluster


def platform_api_url() -> str:
    return normalize_agent_public_api_url(get_settings().agent_public_api_url)


def build_agent_manifest(cluster: ManagedCluster) -> str:
    api_url = platform_api_url()
    return dedent(f"""
    apiVersion: v1
    kind: Namespace
    metadata:
      name: monitor-agent
    ---
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: monitor-agent
      namespace: monitor-agent
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    metadata:
      name: monitor-agent-reader-{cluster.id}
    rules:
      - apiGroups: [""]
        resources: ["nodes", "pods", "services", "endpoints", "namespaces"]
        verbs: ["get", "list", "watch"]
      - apiGroups: ["apps"]
        resources: ["deployments", "statefulsets", "daemonsets"]
        verbs: ["get", "list", "watch"]
      - apiGroups: ["metrics.k8s.io"]
        resources: ["nodes", "pods"]
        verbs: ["get", "list"]
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRoleBinding
    metadata:
      name: monitor-agent-reader-{cluster.id}
    subjects:
      - kind: ServiceAccount
        name: monitor-agent
        namespace: monitor-agent
    roleRef:
      kind: ClusterRole
      name: monitor-agent-reader-{cluster.id}
      apiGroup: rbac.authorization.k8s.io
    ---
    apiVersion: v1
    kind: Secret
    metadata:
      name: monitor-agent-token
      namespace: monitor-agent
    type: Opaque
    stringData:
      AGENT_TOKEN: "{cluster.agent_token}"
    ---
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: monitor-agent-config
      namespace: monitor-agent
    data:
      PLATFORM_API_URL: "{api_url}"
      CLUSTER_NAME: "{cluster.name}"
      HEARTBEAT_INTERVAL_SECONDS: "30"
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: monitor-agent
      namespace: monitor-agent
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: monitor-agent
      template:
        metadata:
          labels:
            app: monitor-agent
        spec:
          serviceAccountName: monitor-agent
          containers:
            - name: monitor-agent
              image: 114.55.117.211:18080/monitor-platform/monitor-agent:v1
              imagePullPolicy: IfNotPresent
              envFrom:
                - configMapRef:
                    name: monitor-agent-config
                - secretRef:
                    name: monitor-agent-token
    """).strip()


@router.post("", response_model=ManagedClusterRead)
def create_cluster(
    payload: ManagedClusterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManagedCluster:
    cluster = ManagedCluster(**payload.model_dump(), user_id=current_user.id, agent_token=new_agent_token())
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


@router.get("", response_model=list[ManagedClusterRead])
def list_clusters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ManagedCluster]:
    return list(
        db.query(ManagedCluster)
        .filter(ManagedCluster.user_id == current_user.id, ManagedCluster.deleted_at.is_(None))
        .order_by(ManagedCluster.id.desc())
        .all()
    )


@router.get("/{cluster_id}", response_model=ManagedClusterRead)
def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManagedCluster:
    return get_owned_cluster(cluster_id, db, current_user)


@router.put("/{cluster_id}", response_model=ManagedClusterRead)
def update_cluster(
    cluster_id: int,
    payload: ManagedClusterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManagedCluster:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cluster, field, value)
    db.commit()
    db.refresh(cluster)
    return cluster


@router.delete("/{cluster_id}", response_model=MessageResponse)
def delete_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    cluster.deleted_at = datetime.now(timezone.utc)
    cluster.status = "deleted"
    db.commit()
    return MessageResponse(message="Cluster deleted")


@router.post("/{cluster_id}/rotate-token", response_model=ManagedClusterRead)
def rotate_cluster_token(
    cluster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManagedCluster:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    cluster.agent_token = new_agent_token()
    cluster.status = "pending"
    db.commit()
    db.refresh(cluster)
    return cluster


@router.get("/{cluster_id}/install", response_model=ManagedClusterInstallRead)
def get_cluster_install(
    cluster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManagedClusterInstallRead:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    manifest = build_agent_manifest(cluster)
    command = "cat <<'EOF' | kubectl apply -f -\n" + manifest + "\nEOF"
    return ManagedClusterInstallRead(
        cluster_id=cluster.id,
        agent_token=cluster.agent_token,
        platform_api_url=platform_api_url(),
        manifest=manifest,
        install_command=command,
    )


@router.get("/{cluster_id}/heartbeats", response_model=list[ClusterAgentHeartbeatRead])
def list_cluster_heartbeats(
    cluster_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClusterAgentHeartbeat]:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    return list(
        db.query(ClusterAgentHeartbeat)
        .filter(ClusterAgentHeartbeat.cluster_id == cluster.id)
        .order_by(ClusterAgentHeartbeat.created_at.desc(), ClusterAgentHeartbeat.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/{cluster_id}/reports", response_model=list[ClusterAgentReportRead])
def list_cluster_reports(
    cluster_id: int,
    report_type: str | None = Query(default=None, pattern="^(metric|log|alert)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClusterAgentReport]:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    query = db.query(ClusterAgentReport).filter(ClusterAgentReport.cluster_id == cluster.id)
    if report_type:
        query = query.filter(ClusterAgentReport.report_type == report_type)
    return list(query.order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc()).limit(limit).all())


@agent_router.post("/heartbeat", response_model=ClusterAgentAck)
def agent_heartbeat(
    payload: ClusterHeartbeatIn,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> ClusterAgentAck:
    cluster = get_agent_cluster(x_agent_token or authorization, db)
    now = datetime.now(timezone.utc)
    heartbeat = ClusterAgentHeartbeat(cluster_id=cluster.id, **payload.model_dump())
    db.add(heartbeat)
    cluster.status = payload.status or "online"
    cluster.agent_version = payload.agent_version
    cluster.node_count = payload.node_count
    cluster.pod_count = payload.pod_count
    cluster.last_heartbeat_at = now
    db.commit()
    return ClusterAgentAck(ok=True, message="heartbeat accepted")


@agent_router.post("/reports", response_model=ClusterAgentAck)
def agent_report(
    payload: ClusterReportIn,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> ClusterAgentAck:
    cluster = get_agent_cluster(x_agent_token or authorization, db)
    report = ClusterAgentReport(cluster_id=cluster.id, **payload.model_dump())
    db.add(report)
    if payload.report_type == "metric":
        cluster.metrics_count += 1
    elif payload.report_type == "log":
        cluster.logs_count += 1
    elif payload.report_type == "alert":
        cluster.alerts_count += 1
    db.commit()
    return ClusterAgentAck(ok=True, message="report accepted")


