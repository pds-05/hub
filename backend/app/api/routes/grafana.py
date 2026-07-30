from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.grafana_target_dashboard import GrafanaTargetDashboard
from app.models.monitor_target import MonitorTarget
from app.models.user import User
from app.services.grafana_client import (
    GrafanaClient,
    GrafanaUnauthorizedError,
    GrafanaUnavailableError,
    get_grafana_client,
)
from app.services.grafana_provisioner import GrafanaProvisioningError, GrafanaProvisioner
from app.services.grafana_security import effective_proxy_secret

router = APIRouter(prefix="/grafana", tags=["grafana"])
settings = get_settings()


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


def platform_views(dashboards: list[dict]) -> list[dict]:
    definitions = [
        {"key": "cluster", "title": "Kubernetes 集群总览", "keywords": [["cluster", "集群"], ["compute", "计算资源"]]},
        {"key": "node", "title": "平台节点资源", "keywords": [["node", "节点"], ["compute", "资源"]]},
        {"key": "pod", "title": "平台 Pod 资源", "keywords": [["pod"], ["compute", "计算资源"]]},
        {"key": "namespace", "title": "命名空间资源", "keywords": [["namespace", "命名空间"], ["pod"]]},
        {"key": "prometheus", "title": "Prometheus 监控", "keywords": [["prometheus"]]},
        {"key": "alertmanager", "title": "Alertmanager 告警", "keywords": [["alertmanager"]]},
        {"key": "loki", "title": "Loki 日志", "keywords": [["loki", "logs", "日志"]]},
        {"key": "grafana", "title": "Grafana 自身", "keywords": [["grafana"]]},
        {"key": "ingress", "title": "Ingress Nginx", "keywords": [["ingress", "nginx"]]},
    ]
    views = []
    for definition in definitions:
        matched = best_dashboard(dashboards, definition["keywords"])
        views.append({
            "key": definition["key"],
            "title": definition["title"],
            "match_type": "dashboard" if matched else "search",
            "url": matched["url"] if matched else f"/dashboards?query={definition['key']}",
            "dashboard": matched,
            "keywords": definition["keywords"],
        })
    return views


def target_view(target: MonitorTarget, record: GrafanaTargetDashboard | None) -> dict[str, Any]:
    return {
        "target_id": target.id,
        "target_name": target.name,
        "target_type": target.target_type,
        "exporter_kind": target.exporter_kind,
        "endpoint": target.endpoint,
        "match_type": "provisioned" if record else "pending",
        "url": record.public_url if record else "",
        "dashboard": {
            "uid": record.dashboard_uid,
            "title": f"{target.name} - 专属监控",
            "url": record.public_url,
            "full_url": record.public_url,
            "folder_title": "我的监控对象",
            "tags": [f"platform-user-{target.user_id}", f"platform-target-{target.id}"],
            "is_starred": False,
        } if record else None,
        "keywords": [],
    }


def _check_proxy_secret(request: Request) -> None:
    expected = effective_proxy_secret(settings)
    actual = request.headers.get("X-Monitor-Proxy-Secret", "")
    if not expected or actual != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grafana 数据代理认证失败")


def _inject_prometheus_user_scope(value: Any, user_id: int) -> Any:
    if not isinstance(value, str):
        return value
    from app.services.promql_scope import scope_promql

    return scope_promql(value, user_id)


def _inject_loki_user_scope(value: Any, user_id: int) -> Any:
    if not isinstance(value, str):
        return value
    from app.services.logql_scope import scope_logql

    return scope_logql(value, user_id)


PROMETHEUS_QUERY_PATHS = {"api/v1/query", "api/v1/query_range", "api/v1/series", "api/v1/metadata"}
LOKI_QUERY_PATHS = {"loki/api/v1/query", "loki/api/v1/query_range", "loki/api/v1/series", "loki/api/v1/labels"}


def _scoped_matcher(value: str, user_id: int) -> str:
    from app.services.promql_scope import scope_promql

    return scope_promql(value, user_id)


def _scope_prometheus_params(path: str, pairs: list[tuple[str, str]], user_id: int) -> list[tuple[str, str]]:
    scoped: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "query":
            value = str(_inject_prometheus_user_scope(value, user_id))
        elif key in {"match", "match[]"}:
            value = _scoped_matcher(value, user_id)
        scoped.append((key, value))
    if path.startswith("api/v1/label/") and not any(key in {"match", "match[]"} for key, _ in scoped):
        scoped.append(("match[]", f'{{platform_user_id="{user_id}"}}'))
    if path == "api/v1/series" and not any(key in {"match", "match[]"} for key, _ in scoped):
        scoped.append(("match[]", f'{{platform_user_id="{user_id}"}}'))
    return scoped


def _scope_loki_params(path: str, pairs: list[tuple[str, str]], user_id: int) -> list[tuple[str, str]]:
    scoped = [
        (key, str(_inject_loki_user_scope(value, user_id)) if key in {"query", "match", "match[]"} else value)
        for key, value in pairs
    ]
    if (path == "loki/api/v1/labels" or path.startswith("loki/api/v1/label/")) and not any(
        key in {"query", "match", "match[]"} for key, _ in scoped
    ):
        scoped.append(("query", f'{{platform_user_id="{user_id}"}}'))
    if path == "loki/api/v1/series" and not any(key in {"query", "match", "match[]"} for key, _ in scoped):
        scoped.append(("match[]", f'{{platform_user_id="{user_id}"}}'))
    return scoped


def _prometheus_path_allowed(path: str) -> bool:
    return path in PROMETHEUS_QUERY_PATHS or (
        path.startswith("api/v1/label/") and path.endswith("/values")
    )


def _loki_path_allowed(path: str) -> bool:
    return path in LOKI_QUERY_PATHS or (
        path.startswith("loki/api/v1/label/") and path.endswith("/values")
    )


@router.api_route("/proxy/prometheus/{user_id}/{path:path}", methods=["GET", "POST"])
async def grafana_prometheus_proxy(user_id: int, path: str, request: Request) -> Response:
    _check_proxy_secret(request)
    if not _prometheus_path_allowed(path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grafana Prometheus 代理只允许只读查询接口")

    from urllib.parse import parse_qsl, urlencode

    params = _scope_prometheus_params(path, list(request.query_params.multi_items()), user_id)
    content = await request.body()
    headers = {"Content-Type": request.headers.get("content-type", "application/x-www-form-urlencoded")}
    if content and "application/x-www-form-urlencoded" in headers["Content-Type"]:
        content = urlencode(
            _scope_prometheus_params(path, parse_qsl(content.decode("utf-8"), keep_blank_values=True), user_id),
            doseq=True,
        ).encode("utf-8")
    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method,
            f"{settings.prometheus_url.rstrip('/')}/{path}",
            params=params,
            content=content,
            headers=headers,
        )
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))


@router.api_route("/proxy/loki/{user_id}/{path:path}", methods=["GET", "POST"])
async def grafana_loki_proxy(user_id: int, path: str, request: Request) -> Response:
    _check_proxy_secret(request)
    if not _loki_path_allowed(path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grafana Loki 代理只允许只读查询接口")

    from urllib.parse import parse_qsl, urlencode

    params = _scope_loki_params(path, list(request.query_params.multi_items()), user_id)
    content = await request.body()
    headers = {"Content-Type": request.headers.get("content-type", "application/x-www-form-urlencoded")}
    if content and "application/x-www-form-urlencoded" in headers["Content-Type"]:
        content = urlencode(
            _scope_loki_params(path, parse_qsl(content.decode("utf-8"), keep_blank_values=True), user_id),
            doseq=True,
        ).encode("utf-8")
    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method,
            f"{settings.loki_url.rstrip('/')}/{path}",
            params=params,
            content=content,
            headers=headers,
        )
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))

@router.post("/provision")
async def provision_grafana(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    provisioner = GrafanaProvisioner()
    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .order_by(MonitorTarget.id.asc())
        .all()
    )
    created = []
    try:
        for target in targets:
            result = await provisioner.ensure_target_dashboard(db, target, current_user)
            created.append({"target_id": target.id, "url": result.url, "uid": result.uid})
    except GrafanaProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"count": len(created), "dashboards": created}


@router.post("/targets/{target_id}/provision")
async def provision_target_dashboard(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    target = (
        db.query(MonitorTarget)
        .filter(
            MonitorTarget.id == target_id,
            MonitorTarget.user_id == current_user.id,
            MonitorTarget.deleted_at.is_(None),
        )
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="监控对象不存在")
    try:
        result = await GrafanaProvisioner().ensure_target_dashboard(db, target, current_user)
    except GrafanaProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"target_id": target.id, "dashboard_url": result.url, "uid": result.uid}

@router.get("/dashboards")
async def list_grafana_dashboards(
    query: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    client: GrafanaClient = Depends(get_grafana_client),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role == "root":
        try:
            dashboards = await client.dashboards(query=query)
            return {"count": len(dashboards), "dashboards": dashboards}
        except GrafanaUnauthorizedError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except GrafanaUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    needle = (query or "").strip().lower()
    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .order_by(MonitorTarget.id.desc())
        .all()
    )
    records = {
        row.target_id: row
        for row in db.query(GrafanaTargetDashboard)
        .filter(GrafanaTargetDashboard.user_id == current_user.id)
        .all()
    }
    dashboards = [
        target_view(target, records[target.id])["dashboard"]
        for target in targets
        if target.id in records and (not needle or needle in target.name.lower())
    ]
    return {"count": len(dashboards), "dashboards": dashboards}

@router.get("/target-views")
async def list_grafana_target_views(
    db: Session = Depends(get_db),
    client: GrafanaClient = Depends(get_grafana_client),
    current_user: User = Depends(get_current_user),
) -> dict:
    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .order_by(MonitorTarget.id.desc())
        .all()
    )
    records = {
        row.target_id: row
        for row in db.query(GrafanaTargetDashboard)
        .filter(GrafanaTargetDashboard.user_id == current_user.id)
        .all()
    }
    dashboards = []
    if current_user.role == "root":
        try:
            dashboards = await client.dashboards()
        except (GrafanaUnauthorizedError, GrafanaUnavailableError):
            dashboards = []
    return {
        "grafana_url": client.base_url,
        "grafana_public_url": client.public_url,
        "role": current_user.role,
        "targets": [target_view(target, records.get(target.id)) for target in targets],
        "platform": platform_views(dashboards) if current_user.role == "root" else [],
        "dashboard_count": len(records) + (len(dashboards) if current_user.role == "root" else 0),
        "isolation": "per-user-organization-and-scoped-datasource",
        "sso_mode": settings.grafana_sso_mode,
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
