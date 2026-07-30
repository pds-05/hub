from datetime import datetime, timezone
import hashlib
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
    ClusterOverviewRead,
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
        resources: ["nodes", "pods", "pods/log", "services", "endpoints", "namespaces", "events", "persistentvolumes", "persistentvolumeclaims"]
        verbs: ["get", "list", "watch"]
      - apiGroups: ["apps"]
        resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
        verbs: ["get", "list", "watch"]
      - apiGroups: ["networking.k8s.io"]
        resources: ["ingresses"]
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
      AGENT_VERSION: "v2"
      LOG_NAMESPACES: ""
      LOG_TAIL_LINES: "80"
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
              imagePullPolicy: Always
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


@router.get("/{cluster_id}/overview", response_model=ClusterOverviewRead)
def get_cluster_overview(
    cluster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClusterOverviewRead:
    cluster = get_owned_cluster(cluster_id, db, current_user)
    heartbeat = (
        db.query(ClusterAgentHeartbeat)
        .filter(ClusterAgentHeartbeat.cluster_id == cluster.id)
        .order_by(ClusterAgentHeartbeat.created_at.desc(), ClusterAgentHeartbeat.id.desc())
        .first()
    )
    metric = (
        db.query(ClusterAgentReport)
        .filter(ClusterAgentReport.cluster_id == cluster.id, ClusterAgentReport.report_type == "metric")
        .order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc())
        .first()
    )
    alerts = list(
        db.query(ClusterAgentReport)
        .filter(ClusterAgentReport.cluster_id == cluster.id, ClusterAgentReport.report_type == "alert")
        .order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc())
        .limit(500)
        .all()
    )
    logs = list(
        db.query(ClusterAgentReport)
        .filter(ClusterAgentReport.cluster_id == cluster.id, ClusterAgentReport.report_type == "log")
        .order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc())
        .limit(500)
        .all()
    )
    return ClusterOverviewRead(cluster=cluster, heartbeat=heartbeat, snapshot=metric.payload if metric else {}, alerts=alerts, logs=logs)

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


def report_fingerprint(payload: ClusterReportIn) -> str:
    explicit = str(payload.payload.get("fingerprint") or "").strip()
    if explicit:
        return explicit
    value = "|".join([payload.report_type, payload.source or "", payload.level or "", payload.message or ""])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def update_report(report: ClusterAgentReport, payload: ClusterReportIn, now: datetime) -> None:
    report.source = payload.source
    report.level = payload.level
    report.message = payload.message
    report.payload = payload.payload
    report.created_at = now


@agent_router.post("/heartbeat", response_model=ClusterAgentAck)
def agent_heartbeat(
    payload: ClusterHeartbeatIn,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> ClusterAgentAck:
    cluster = get_agent_cluster(x_agent_token or authorization, db)
    now = datetime.now(timezone.utc)
    heartbeat = (
        db.query(ClusterAgentHeartbeat)
        .filter(ClusterAgentHeartbeat.cluster_id == cluster.id)
        .order_by(ClusterAgentHeartbeat.id.desc())
        .first()
    )
    if heartbeat is None:
        heartbeat = ClusterAgentHeartbeat(cluster_id=cluster.id)
        db.add(heartbeat)
    else:
        db.query(ClusterAgentHeartbeat).filter(
            ClusterAgentHeartbeat.cluster_id == cluster.id,
            ClusterAgentHeartbeat.id != heartbeat.id,
        ).delete(synchronize_session=False)
    for field, value in payload.model_dump().items():
        setattr(heartbeat, field, value)
    heartbeat.created_at = now
    cluster.status = payload.status or "online"
    cluster.agent_version = payload.agent_version
    cluster.node_count = payload.node_count
    cluster.pod_count = payload.pod_count
    cluster.last_heartbeat_at = now
    cluster.alerts_count = sum(
        1
        for item in db.query(ClusterAgentReport).filter(
            ClusterAgentReport.cluster_id == cluster.id,
            ClusterAgentReport.report_type == "alert",
        ).all()
        if (item.payload or {}).get("status") == "active"
    )
    db.commit()
    return ClusterAgentAck(ok=True, message="current heartbeat updated")


@agent_router.post("/reports", response_model=ClusterAgentAck)
def agent_report(
    payload: ClusterReportIn,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> ClusterAgentAck:
    cluster = get_agent_cluster(x_agent_token or authorization, db)
    now = datetime.now(timezone.utc)
    query = db.query(ClusterAgentReport).filter(ClusterAgentReport.cluster_id == cluster.id, ClusterAgentReport.report_type == payload.report_type)

    if payload.report_type == "metric":
        report = query.order_by(ClusterAgentReport.id.desc()).first()
        if report is None:
            report = ClusterAgentReport(cluster_id=cluster.id, report_type="metric")
            db.add(report)
        else:
            query.filter(ClusterAgentReport.id != report.id).delete(synchronize_session=False)
        update_report(report, payload, now)
        active_fingerprints = payload.payload.get("active_alert_fingerprints")
        if isinstance(active_fingerprints, list):
            active_set = {str(value) for value in active_fingerprints}
            alert_rows = db.query(ClusterAgentReport).filter(
                ClusterAgentReport.cluster_id == cluster.id,
                ClusterAgentReport.report_type == "alert",
            ).all()
            for alert in alert_rows:
                alert_payload = dict(alert.payload or {})
                if alert_payload.get("status") == "active" and str(alert_payload.get("fingerprint") or "") not in active_set:
                    alert.payload = {**alert_payload, "status": "resolved", "resolved_at": now.isoformat()}
                    alert.created_at = now
            cluster.alerts_count = sum(
                1 for alert in alert_rows if str((alert.payload or {}).get("fingerprint") or "") in active_set
            )
        cluster.metrics_count = 1
    else:
        fingerprint = report_fingerprint(payload)
        report = None
        for candidate in query.order_by(ClusterAgentReport.id.desc()).limit(500).all():
            if str((candidate.payload or {}).get("fingerprint") or "") == fingerprint:
                report = candidate
                break
        if report is None:
            report = ClusterAgentReport(cluster_id=cluster.id, **payload.model_dump())
            report.payload = {**payload.payload, "fingerprint": fingerprint}
            db.add(report)
        else:
            update_report(report, payload, now)
            report.payload = {**payload.payload, "fingerprint": fingerprint}

        if payload.report_type == "log":
            db.flush()
            log_rows = query.order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc()).all()
            for stale in log_rows[500:]:
                db.delete(stale)
            db.flush()
            cluster.logs_count = min(query.count(), 500)
        else:
            db.flush()
            alert_rows = query.order_by(ClusterAgentReport.created_at.desc(), ClusterAgentReport.id.desc()).all()
            for stale in alert_rows[500:]:
                db.delete(stale)
            db.flush()
            cluster.alerts_count = sum(
                1 for item in query.all() if (item.payload or {}).get("status") == "active"
            )

    db.commit()
    return ClusterAgentAck(ok=True, message="current report updated")


