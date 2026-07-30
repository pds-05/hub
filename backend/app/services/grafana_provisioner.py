from __future__ import annotations

import base64
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.grafana_platform_credential import GrafanaPlatformCredential
from app.models.grafana_target_dashboard import GrafanaTargetDashboard
from app.models.grafana_user_context import GrafanaUserContext
from app.models.monitor_target import MonitorTarget
from app.models.user import User
from app.services.exporter_metric_catalog import definitions_for, render_expression, target_selector
from app.services.grafana_runtime import get_api_token, set_api_token
from app.services.grafana_security import effective_proxy_secret

logger = logging.getLogger(__name__)


class GrafanaProvisioningError(Exception):
    pass


@dataclass(frozen=True)
class GrafanaDashboardResult:
    uid: str
    url: str
    dashboard: dict[str, Any]
    org_id: int
    grafana_login: str


class GrafanaProvisioner:
    service_account_name = "monitor-platform"
    token_name = "monitor-platform-runtime"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.grafana_url.rstrip("/")
        self.public_url = self.settings.grafana_public_url.rstrip("/")
        self._admin_credentials_cache: tuple[str, str] | None = None

    @staticmethod
    def grafana_login(user: User) -> str:
        return f"platform-user-{user.id}"

    @staticmethod
    def dashboard_public_url(public_url: str, uid: str, org_id: int) -> str:
        """Build a stable URL from the dashboard UID instead of Grafana's display slug."""
        base_url = public_url.rstrip("/")
        query = urlencode({"orgId": org_id, "refresh": "30s", "kiosk": "1"})
        return f"{base_url}/d/{uid}/monitor-platform-target?{query}"

    async def _admin_credentials(self) -> tuple[str, str]:
        if self._admin_credentials_cache is not None:
            return self._admin_credentials_cache

        username = self.settings.grafana_admin_user.strip()
        password = self.settings.grafana_admin_password.strip()
        if username and password:
            self._admin_credentials_cache = (username, password)
            return self._admin_credentials_cache
        if username or password:
            raise GrafanaProvisioningError("Grafana 管理员账号和密码必须同时配置")

        token_path = Path(self.settings.kubernetes_service_account_token_path)
        ca_path = Path(self.settings.kubernetes_service_account_ca_path)
        if not token_path.exists():
            raise GrafanaProvisioningError("未配置 Grafana 管理员凭据，且无法读取 Kubernetes ServiceAccount Token")

        namespace = self.settings.grafana_admin_secret_namespace
        secret_name = self.settings.grafana_admin_secret_name
        url = f"{self.settings.kubernetes_api_url.rstrip('/')}/api/v1/namespaces/{namespace}/secrets/{secret_name}"
        headers = {"Authorization": f"Bearer {token_path.read_text(encoding='utf-8').strip()}"}
        verify: str | bool = str(ca_path) if ca_path.exists() else True
        try:
            async with httpx.AsyncClient(timeout=10, verify=verify, headers=headers) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise GrafanaProvisioningError("无法从 Kubernetes 读取 Grafana 管理员凭据") from exc
        if response.status_code >= 400:
            raise GrafanaProvisioningError(
                f"读取 Kubernetes Grafana Secret 失败：HTTP {response.status_code} {response.text[:300]}"
            )

        data = response.json().get("data") or {}
        try:
            username = base64.b64decode(data["admin-user"]).decode("utf-8").strip()
            password = base64.b64decode(data["admin-password"]).decode("utf-8").strip()
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            raise GrafanaProvisioningError("Kubernetes Grafana Secret 缺少有效的管理员账号或密码") from exc
        if not username or not password:
            raise GrafanaProvisioningError("Kubernetes Grafana Secret 中的管理员账号或密码为空")
        self._admin_credentials_cache = (username, password)
        return self._admin_credentials_cache
    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        org_id: int | None = None,
        use_admin_credentials: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if org_id is not None:
            headers["X-Grafana-Org-Id"] = str(org_id)
        auth = None
        if use_admin_credentials:
            auth = await self._admin_credentials()
            headers.pop("Authorization", None)
        try:
            async with httpx.AsyncClient(timeout=20, auth=auth) as client:
                return await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GrafanaProvisioningError(f"无法连接 Grafana：{self.base_url}") from exc

    @staticmethod
    def _raise_for_grafana(response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            raise GrafanaProvisioningError(f"{action}失败：HTTP {response.status_code} {response.text[:300]}")

    async def ensure_api_token(self, db: Session | None = None) -> str:
        configured = self.settings.grafana_api_key.strip()
        if configured:
            set_api_token(configured)
            return configured

        if db is not None:
            stored = db.query(GrafanaPlatformCredential).filter(
                GrafanaPlatformCredential.name == self.token_name
            ).first()
            if stored and stored.token:
                response = await self._request("GET", "/api/user", token=stored.token)
                if response.status_code < 400:
                    set_api_token(stored.token)
                    return stored.token
                db.delete(stored)
                db.commit()

        response = await self._request(
            "GET",
            "/api/serviceaccounts/search",
            use_admin_credentials=True,
            params={"query": self.service_account_name, "perpage": 100},
        )
        self._raise_for_grafana(response, "查询 Grafana 服务账号")
        account = next(
            (
                row
                for row in response.json().get("serviceAccounts", [])
                if row.get("name") == self.service_account_name
            ),
            None,
        )
        if account is None:
            response = await self._request(
                "POST",
                "/api/serviceaccounts",
                use_admin_credentials=True,
                json={"name": self.service_account_name, "role": "Admin"},
            )
            self._raise_for_grafana(response, "创建 Grafana 服务账号")
            account = response.json()

        account_id = int(account["id"])
        response = await self._request(
            "GET",
            f"/api/serviceaccounts/{account_id}/tokens",
            use_admin_credentials=True,
        )
        if response.status_code < 400:
            for existing in response.json():
                if existing.get("name") == self.token_name and existing.get("id"):
                    await self._request(
                        "DELETE",
                        f"/api/serviceaccounts/{account_id}/tokens/{existing['id']}",
                        use_admin_credentials=True,
                    )

        response = await self._request(
            "POST",
            f"/api/serviceaccounts/{account_id}/tokens",
            use_admin_credentials=True,
            json={"name": self.token_name, "secondsToLive": 0},
        )
        self._raise_for_grafana(response, "创建 Grafana API Token")
        token = str(response.json().get("key") or "").strip()
        if not token:
            raise GrafanaProvisioningError("Grafana Token 创建成功，但响应中没有返回 Token")
        if db is not None:
            stored = db.query(GrafanaPlatformCredential).filter(
                GrafanaPlatformCredential.name == self.token_name
            ).first()
            if stored is None:
                db.add(GrafanaPlatformCredential(name=self.token_name, token=token))
            else:
                stored.token = token
            db.commit()
        set_api_token(token)
        return token
    async def _ensure_grafana_user(self, user: User) -> tuple[int, str]:
        login = self.grafana_login(user)
        response = await self._request(
            "GET",
            "/api/users/lookup",
            use_admin_credentials=True,
            params={"loginOrEmail": login},
        )
        user_exists = response.status_code != 404
        if not user_exists:
            response = await self._request(
                "POST",
                "/api/admin/users",
                use_admin_credentials=True,
                json={
                    "name": user.username,
                    "login": login,
                    "email": user.email,
                    "password": secrets.token_urlsafe(32),
                },
            )
        self._raise_for_grafana(response, "创建 Grafana 用户")
        payload = response.json()
        grafana_user_id = int(payload.get("id") or payload.get("userId"))
        if user_exists:
            response = await self._request(
                "PUT",
                f"/api/users/{grafana_user_id}",
                use_admin_credentials=True,
                json={"name": user.username, "email": user.email, "login": login},
            )
            self._raise_for_grafana(response, "更新 Grafana 用户")
        return grafana_user_id, login

    async def ensure_user_org(self, db: Session, user: User) -> tuple[int, int]:
        context = db.query(GrafanaUserContext).filter(GrafanaUserContext.user_id == user.id).first()
        grafana_user_id, grafana_login = await self._ensure_grafana_user(user)
        role = "Admin" if user.role == "root" else "Viewer"

        if user.role == "root":
            org_id = 1
        else:
            org_name = f"monitor-platform-user-{user.id}"
            response = await self._request(
                "GET",
                f"/api/orgs/name/{org_name}",
                use_admin_credentials=True,
            )
            if response.status_code == 404:
                response = await self._request(
                    "POST",
                    "/api/orgs",
                    use_admin_credentials=True,
                    json={"name": org_name},
                )
            self._raise_for_grafana(response, "创建 Grafana 用户组织")
            payload = response.json()
            org_id = int(payload.get("orgId") or payload.get("id"))

        response = await self._request(
            "POST",
            f"/api/orgs/{org_id}/users",
            use_admin_credentials=True,
            json={"loginOrEmail": grafana_login, "role": role},
        )
        if response.status_code not in {200, 201, 409}:
            self._raise_for_grafana(response, "将 Grafana 用户加入组织")

        response = await self._request(
            "PATCH",
            f"/api/orgs/{org_id}/users/{grafana_user_id}",
            use_admin_credentials=True,
            json={"role": role},
        )
        if response.status_code not in {200, 404}:
            self._raise_for_grafana(response, "\u540c\u6b65 Grafana \u7528\u6237\u7ec4\u7ec7\u89d2\u8272")

        response = await self._request(
            "POST",
            f"/api/users/{grafana_user_id}/using/{org_id}",
            use_admin_credentials=True,
        )
        if response.status_code not in {200, 201, 404}:
            self._raise_for_grafana(response, "切换 Grafana 用户默认组织")

        if user.role != "root":
            response = await self._request(
                "GET",
                f"/api/users/{grafana_user_id}/orgs",
                use_admin_credentials=True,
            )
            self._raise_for_grafana(response, "查询 Grafana 用户组织")
            for membership in response.json():
                membership_org_id = int(membership.get("orgId") or membership.get("id") or 0)
                if not membership_org_id or membership_org_id == org_id:
                    continue
                response = await self._request(
                    "DELETE",
                    f"/api/orgs/{membership_org_id}/users/{grafana_user_id}",
                    use_admin_credentials=True,
                )
                if response.status_code not in {200, 404}:
                    self._raise_for_grafana(response, "移除普通用户的其他 Grafana 组织权限")

        if context is None:
            context = GrafanaUserContext(
                user_id=user.id,
                org_id=org_id,
                grafana_user_id=grafana_user_id,
                grafana_login=grafana_login,
            )
            db.add(context)
        else:
            context.org_id = org_id
            context.grafana_user_id = grafana_user_id
            context.grafana_login = grafana_login
        db.commit()
        return org_id, grafana_user_id

    async def ensure_user_context(self, db: Session, user: User) -> tuple[int, int]:
        org_id, grafana_user_id = await self.ensure_user_org(db, user)
        await self.ensure_datasources(await self.ensure_api_token(db), org_id, user)
        return org_id, grafana_user_id
    def _datasource_definitions(self, user: User) -> list[dict[str, Any]]:
        if user.role == "root":
            prometheus_url = self.settings.prometheus_url
            loki_url = self.settings.loki_url
            secure_json_data: dict[str, str] = {}
            json_headers: dict[str, str] = {}
        else:
            proxy_secret = effective_proxy_secret(self.settings)
            proxy_base = self.settings.grafana_data_proxy_url.rstrip("/")
            prometheus_url = f"{proxy_base}/prometheus/{user.id}"
            loki_url = f"{proxy_base}/loki/{user.id}"
            json_headers = {"httpHeaderName1": "X-Monitor-Proxy-Secret"}
            secure_json_data = {"httpHeaderValue1": proxy_secret}

        suffix = "root" if user.role == "root" else f"u-{user.id}"
        return [
            {
                "uid": f"mp-prom-{suffix}",
                "name": "Monitor Platform Prometheus",
                "type": "prometheus",
                "url": prometheus_url,
                "access": "proxy",
                "isDefault": True,
                "editable": False,
                "jsonData": {"httpMethod": "POST", "manageAlerts": False, **json_headers},
                "secureJsonData": secure_json_data,
            },
            {
                "uid": f"mp-loki-{suffix}",
                "name": "Monitor Platform Loki",
                "type": "loki",
                "url": loki_url,
                "access": "proxy",
                "isDefault": False,
                "editable": False,
                "jsonData": {"maxLines": 1000, **json_headers},
                "secureJsonData": secure_json_data,
            },
        ]

    async def ensure_datasources(self, token: str, org_id: int, user: User) -> dict[str, dict[str, Any]]:
        del token
        result: dict[str, dict[str, Any]] = {}
        for definition in self._datasource_definitions(user):
            response = await self._request(
                "GET",
                f"/api/datasources/uid/{definition['uid']}",
                org_id=org_id,
                use_admin_credentials=True,
            )
            if response.status_code == 404:
                response = await self._request(
                    "POST",
                    "/api/datasources",
                    org_id=org_id,
                    use_admin_credentials=True,
                    json=definition,
                )
                self._raise_for_grafana(response, f"创建 Grafana 数据源 {definition['name']}")
                payload = response.json().get("datasource") or response.json()
            else:
                self._raise_for_grafana(response, f"查询 Grafana 数据源 {definition['name']}")
                current = response.json()
                response = await self._request(
                    "PUT",
                    f"/api/datasources/uid/{definition['uid']}",
                    org_id=org_id,
                    use_admin_credentials=True,
                    json={**definition, "id": current.get("id")},
                )
                self._raise_for_grafana(response, f"更新 Grafana 数据源 {definition['name']}")
                payload = response.json().get("datasource") or response.json()
            result[definition["type"]] = {**definition, **payload}
        return result
    @staticmethod
    def _unit(unit: str) -> str:
        return {
            "%": "percent",
            "bytes": "bytes",
            "s": "s",
            "days": "d",
            "cores": "short",
        }.get(unit, "short")

    @staticmethod
    def target_queries(target: MonitorTarget) -> list[dict[str, str]]:
        selector = target_selector(target.user_id, target.id)
        if target.target_type in {"website", "port"}:
            kind = "blackbox"
        else:
            kind = target.exporter_kind or "custom"

        definitions = list(definitions_for(kind))
        queries = [
            {
                "key": definition.key,
                "title": definition.label,
                "unit": GrafanaProvisioner._unit(definition.unit),
                "expr": render_expression(definition.expressions[0], selector),
            }
            for definition in definitions
            if definition.expressions
        ]
        if target.target_type == "port":
            queries = [item for item in queries if item["key"] != "probe_http_status_code"]
            queries.append(
                {
                    "key": "probe_tcp_connect_duration_seconds",
                    "title": "TCP 建立连接耗时",
                    "unit": "s",
                    "expr": f"max(probe_tcp_connect_duration_seconds{{{selector}}})",
                }
            )
        if target.target_type == "exporter":
            queries.insert(
                0,
                {
                    "key": "up",
                    "title": "Exporter 在线状态",
                    "unit": "short",
                    "expr": f"max(up{{{selector}}})",
                },
            )
        return queries

    @staticmethod
    def _panel(index: int, query: dict[str, str], datasource_uid: str) -> dict[str, Any]:
        return {
            "id": index + 1,
            "type": "timeseries",
            "title": query["title"],
            "gridPos": {"h": 8, "w": 12, "x": (index % 2) * 12, "y": (index // 2) * 8},
            "datasource": {"type": "prometheus", "uid": datasource_uid},
            "targets": [
                {
                    "refId": chr(65 + (index % 26)),
                    "expr": query["expr"],
                    "legendFormat": "{{instance}}",
                }
            ],
            "fieldConfig": {"defaults": {"unit": query["unit"]}, "overrides": []},
            "options": {
                "legend": {"displayMode": "list", "placement": "bottom"},
                "tooltip": {"mode": "multi"},
            },
        }

    async def ensure_target_dashboard(
        self,
        db: Session,
        target: MonitorTarget,
        user: User,
    ) -> GrafanaDashboardResult:
        if not self.settings.grafana_provisioning_enabled:
            raise GrafanaProvisioningError("Grafana 自动配置已关闭")
        token = await self.ensure_api_token(db)
        org_id, _ = await self.ensure_user_org(db, user)
        datasources = await self.ensure_datasources(token, org_id, user)
        datasource_uid = str(datasources["prometheus"]["uid"])
        uid = f"mp-t-{target.user_id}-{target.id}"[:40]
        queries = self.target_queries(target)
        panels = [self._panel(index, query, datasource_uid) for index, query in enumerate(queries)]
        dashboard = {
            "uid": uid,
            "title": f"{target.name} - 专属监控",
            "description": "由智能运维监控平台自动创建，查询范围已固定到当前用户和监控对象。",
            "tags": ["monitor-platform", f"platform-user-{target.user_id}", f"platform-target-{target.id}"],
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 1,
            "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "panels": panels,
        }
        response = await self._request(
            "POST",
            "/api/dashboards/db",
            org_id=org_id,
            use_admin_credentials=True,
            json={
                "dashboard": dashboard,
                "folderId": 0,
                "overwrite": True,
                "message": "monitor-platform automatic provisioning",
            },
        )
        self._raise_for_grafana(response, "创建 Grafana Target 仪表盘")
        dashboard_url = self.dashboard_public_url(self.public_url, uid, org_id)

        record = db.query(GrafanaTargetDashboard).filter(GrafanaTargetDashboard.target_id == target.id).first()
        if record is None:
            record = GrafanaTargetDashboard(
                user_id=target.user_id,
                target_id=target.id,
                dashboard_uid=uid,
                public_url=dashboard_url,
                access_token="",
            )
            db.add(record)
        else:
            record.user_id = target.user_id
            record.dashboard_uid = uid
            record.public_url = dashboard_url
            record.access_token = ""
        db.commit()
        return GrafanaDashboardResult(
            uid=uid,
            url=dashboard_url,
            dashboard=dashboard,
            org_id=org_id,
            grafana_login=self.grafana_login(user),
        )

    async def delete_target_dashboard(self, db: Session, target_id: int) -> None:
        record = db.query(GrafanaTargetDashboard).filter(GrafanaTargetDashboard.target_id == target_id).first()
        if record is None:
            return
        context = db.query(GrafanaUserContext).filter(GrafanaUserContext.user_id == record.user_id).first()
        try:
            await self.ensure_api_token(db)
            response = await self._request(
                "DELETE",
                f"/api/dashboards/uid/{record.dashboard_uid}",
                org_id=context.org_id if context else None,
                use_admin_credentials=True,
            )
            if response.status_code not in {200, 404}:
                self._raise_for_grafana(response, "删除 Grafana Target 仪表盘")
        finally:
            db.delete(record)
            db.commit()


async def provision_target_safely(db: Session, target: MonitorTarget, user: User) -> str | None:
    try:
        result = await GrafanaProvisioner().ensure_target_dashboard(db, target, user)
        return result.url
    except GrafanaProvisioningError:
        db.rollback()
        logger.warning("Grafana provisioning failed for target %s", target.id, exc_info=True)
        return None
