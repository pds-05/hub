import asyncio
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock


httpx_stub = ModuleType("httpx")
httpx_stub.AsyncClient = object
httpx_stub.HTTPError = Exception
httpx_stub.Response = object
httpx_stub.BasicAuth = object
sys.modules.setdefault("httpx", httpx_stub)

sqlalchemy_stub = ModuleType("sqlalchemy")
sqlalchemy_orm_stub = ModuleType("sqlalchemy.orm")
sqlalchemy_orm_stub.Session = object
sys.modules.setdefault("sqlalchemy", sqlalchemy_stub)
sys.modules.setdefault("sqlalchemy.orm", sqlalchemy_orm_stub)

config_stub = ModuleType("app.core.config")
config_stub.get_settings = lambda: SimpleNamespace(
    grafana_url="http://grafana",
    secret_key="platform-secret",
    grafana_public_url="http://platform/grafana",
    grafana_api_key="",
    grafana_admin_user="admin",
    grafana_admin_password="secret",
    grafana_admin_secret_namespace="monitoring",
    grafana_admin_secret_name="monitoring-grafana",
    kubernetes_api_url="https://kubernetes.default.svc",
    kubernetes_service_account_token_path="/missing/token",
    kubernetes_service_account_ca_path="/missing/ca",
    grafana_provisioning_enabled=True,
    grafana_data_proxy_secret="proxy-secret",
    grafana_data_proxy_url="http://backend/api/v1/grafana/proxy",
    prometheus_url="http://prometheus",
    loki_url="http://loki",
)
sys.modules.setdefault("app.core.config", config_stub)

for module_name, class_name in (
    ("app.models.grafana_platform_credential", "GrafanaPlatformCredential"),
    ("app.models.grafana_target_dashboard", "GrafanaTargetDashboard"),
    ("app.models.grafana_user_context", "GrafanaUserContext"),
    ("app.models.monitor_target", "MonitorTarget"),
    ("app.models.user", "User"),
):
    module = ModuleType(module_name)
    model_class = type(class_name, (), {"user_id": 0, "__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
    setattr(module, class_name, model_class)
    sys.modules.setdefault(module_name, module)

from app.services.grafana_provisioner import GrafanaProvisioner
from app.services.grafana_security import effective_proxy_secret


class GrafanaProvisionerTest(unittest.TestCase):
    def test_grafana_login_uses_immutable_platform_user_id(self) -> None:
        user = SimpleNamespace(id=7, username="alice")
        self.assertEqual(GrafanaProvisioner.grafana_login(user), "platform-user-7")

    def test_dashboard_public_url_uses_stable_uid_path(self) -> None:
        url = GrafanaProvisioner.dashboard_public_url("http://platform/grafana/", "mp-t-7-19", 17)

        self.assertEqual(
            url,
            "http://platform/grafana/d/mp-t-7-19/monitor-platform-target?orgId=17&refresh=30s&kiosk=1",
        )


    def test_regular_user_datasources_use_scoped_backend_proxy(self) -> None:
        provisioner = GrafanaProvisioner()
        user = SimpleNamespace(id=7, role="user")

        datasources = provisioner._datasource_definitions(user)

        proxy_base = provisioner.settings.grafana_data_proxy_url.rstrip("/")
        self.assertEqual(datasources[0]["url"], f"{proxy_base}/prometheus/7")
        self.assertEqual(datasources[1]["url"], f"{proxy_base}/loki/7")
        self.assertEqual(datasources[0]["secureJsonData"]["httpHeaderValue1"], effective_proxy_secret(provisioner.settings))

    def test_rabbitmq_queries_are_scoped_to_user_and_target(self) -> None:
        target = SimpleNamespace(id=19, user_id=7, target_type="exporter", exporter_kind="rabbitmq")

        queries = GrafanaProvisioner.target_queries(target)

        self.assertTrue(queries)
        self.assertTrue(all('platform_user_id="7"' in item["expr"] for item in queries))
        self.assertTrue(all('platform_target_id="19"' in item["expr"] for item in queries))

    def test_regular_user_is_removed_from_root_organization(self) -> None:
        provisioner = GrafanaProvisioner()
        provisioner._ensure_grafana_user = AsyncMock(return_value=(70, "platform-user-7"))
        provisioner._request = AsyncMock(
            side_effect=[
                SimpleNamespace(status_code=200, json=lambda: {"id": 17}, text=""),
                SimpleNamespace(status_code=200, json=lambda: {}, text=""),
                SimpleNamespace(status_code=200, json=lambda: {}, text=""),
                SimpleNamespace(status_code=200, json=lambda: {}, text=""),
                SimpleNamespace(status_code=200, json=lambda: [{"orgId": 1}, {"orgId": 17}], text=""),
                SimpleNamespace(status_code=200, json=lambda: {}, text=""),
            ]
        )
        context_query = SimpleNamespace(filter=lambda *args: SimpleNamespace(first=lambda: None))
        db = SimpleNamespace(query=lambda *args: context_query, add=lambda value: None, commit=lambda: None)
        user = SimpleNamespace(id=7, username="alice", email="alice@example.com", role="user")

        org_id, user_id = asyncio.run(provisioner.ensure_user_org(db, user))

        self.assertEqual((org_id, user_id), (17, 70))
        calls = provisioner._request.await_args_list
        self.assertEqual(calls[2].args, ("PATCH", "/api/orgs/17/users/70"))
        self.assertEqual(calls[2].kwargs["json"], {"role": "Viewer"})
        self.assertEqual(calls[-1].args, ("DELETE", "/api/orgs/1/users/70"))
        self.assertEqual(calls[-2].args, ("GET", "/api/users/70/orgs"))


if __name__ == "__main__":
    unittest.main()
