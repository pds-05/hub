from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.monitor_target import MonitorTarget
from app.models.user import User
from app.services.grafana_client import (
    GrafanaClient,
    GrafanaUnauthorizedError,
    GrafanaUnavailableError,
    get_grafana_client,
)

router = APIRouter(prefix="/grafana", tags=["grafana"])


def dashboard_text(dashboard: dict) -> str:
    return f"{dashboard.get('title', '')} {dashboard.get('folder_title', '')} {' '.join(dashboard.get('tags') or [])}".lower()


def dashboard_score(dashboard: dict, keyword_groups: list[list[str]]) -> int:
    text = dashboard_text(dashboard)
    return sum(1 for group in keyword_groups if any(keyword.lower() in text for keyword in group))


def best_dashboard(dashboards: list[dict], keyword_groups: list[list[str]]) -> dict | None:
    scored = [(dashboard_score(dashboard, keyword_groups), dashboard) for dashboard in dashboards]
    scored = [(score, dashboard) for score, dashboard in scored if score > 0]
    if not scored:
        return None
    return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]


def grafana_explore_url(query: str = "up") -> str:
    # Safe fallback when no dashboard matches. Users still land in Grafana with a relevant query hint.
    return f"/explore?left={quote('{\"queries\":[{\"expr\":\"' + query + '\"}],\"range\":{\"from\":\"now-1h\",\"to\":\"now\"}}')}"


def target_keyword_groups(target: MonitorTarget) -> list[list[str]]:
    endpoint_host = target.endpoint.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]
    groups: list[list[str]] = [[target.name], [endpoint_host]]
    if target.target_type == "exporter":
        kind = target.exporter_kind or "exporter"
        groups.append([kind, f"{kind}_exporter", f"{kind} exporter"])
        if kind == "node":
            groups.extend([["node", "node exporter"], ["linux", "server", "主机", "节点"]])
    elif target.target_type == "website":
        groups.extend([["blackbox", "probe", "http", "website", "站点", "网站"]])
    elif target.target_type == "port":
        groups.extend([["blackbox", "tcp", "port", "端口"]])
    return groups


def target_promql(target: MonitorTarget) -> str:
    if target.target_type == "exporter":
        host = target.endpoint.replace("http://", "").replace("https://", "").split("/")[0]
        return f'up{{instance=~".*{host}.*"}}'
    return "probe_success"


def target_view(target: MonitorTarget, dashboards: list[dict]) -> dict:
    matched = best_dashboard(dashboards, target_keyword_groups(target))
    if matched:
        url = matched["url"]
        dashboard = matched
        match_type = "dashboard"
    else:
        url = grafana_explore_url(target_promql(target))
        dashboard = None
        match_type = "explore"
    return {
        "target_id": target.id,
        "target_name": target.name,
        "target_type": target.target_type,
        "exporter_kind": target.exporter_kind,
        "endpoint": target.endpoint,
        "match_type": match_type,
        "url": url,
        "dashboard": dashboard,
        "keywords": target_keyword_groups(target),
    }


def platform_views(dashboards: list[dict]) -> list[dict]:
    definitions = [
        {"key": "cluster", "title": "Kubernetes 集群总览", "keywords": [["cluster", "集群", "多集群"], ["compute", "计算资源"]], "fallback": "/dashboards?query=kubernetes"},
        {"key": "node", "title": "平台节点资源", "keywords": [["node", "节点"], ["compute", "资源"]], "fallback": "/dashboards?query=node"},
        {"key": "pod", "title": "平台 Pod 资源", "keywords": [["pod"], ["compute", "计算资源"]], "fallback": "/dashboards?query=pod"},
        {"key": "namespace", "title": "命名空间资源", "keywords": [["namespace", "命名空间"], ["pod"]], "fallback": "/dashboards?query=namespace"},
        {"key": "prometheus", "title": "Prometheus 监控", "keywords": [["prometheus"]], "fallback": "/dashboards?query=prometheus"},
        {"key": "alertmanager", "title": "Alertmanager 告警", "keywords": [["alertmanager"]], "fallback": "/dashboards?query=alertmanager"},
        {"key": "loki", "title": "Loki 日志", "keywords": [["loki", "logs", "日志"]], "fallback": "/dashboards?query=loki"},
        {"key": "grafana", "title": "Grafana 自身", "keywords": [["grafana"]], "fallback": "/dashboards?query=grafana"},
        {"key": "ingress", "title": "Ingress Nginx", "keywords": [["ingress", "nginx"]], "fallback": "/dashboards?query=ingress"},
    ]
    views = []
    for definition in definitions:
        matched = best_dashboard(dashboards, definition["keywords"])
        views.append({
            "key": definition["key"],
            "title": definition["title"],
            "match_type": "dashboard" if matched else "search",
            "url": matched["url"] if matched else definition["fallback"],
            "dashboard": matched,
            "keywords": definition["keywords"],
        })
    return views


@router.get("/dashboards")
async def list_grafana_dashboards(
    query: str | None = Query(default=None, max_length=100),
    client: GrafanaClient = Depends(get_grafana_client),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        dashboards = await client.dashboards(query=query)
        return {"count": len(dashboards), "dashboards": dashboards}
    except GrafanaUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except GrafanaUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/target-views")
async def list_grafana_target_views(
    db: Session = Depends(get_db),
    client: GrafanaClient = Depends(get_grafana_client),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        dashboards = await client.dashboards()
    except GrafanaUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except GrafanaUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .order_by(MonitorTarget.id.desc())
        .all()
    )
    return {
        "grafana_url": client.base_url,
        "grafana_public_url": client.public_url,
        "role": current_user.role,
        "targets": [target_view(target, dashboards) for target in targets],
        "platform": platform_views(dashboards) if current_user.role == "root" else [],
        "dashboard_count": len(dashboards),
    }


@router.get("/health")
async def grafana_health(
    client: GrafanaClient = Depends(get_grafana_client),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        return await client.health()
    except GrafanaUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except GrafanaUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

