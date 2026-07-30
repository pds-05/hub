import sys
import unittest
from types import ModuleType, SimpleNamespace


httpx_stub = ModuleType("httpx")
httpx_stub.AsyncClient = object
sys.modules.setdefault("httpx", httpx_stub)

fastapi_stub = ModuleType("fastapi")
fastapi_stub.APIRouter = lambda *args, **kwargs: SimpleNamespace(
    api_route=lambda *args, **kwargs: (lambda function: function),
    post=lambda *args, **kwargs: (lambda function: function),
    get=lambda *args, **kwargs: (lambda function: function),
)
fastapi_stub.Depends = lambda value=None: value
fastapi_stub.HTTPException = Exception
fastapi_stub.Query = lambda default=None, **kwargs: default
fastapi_stub.Request = object
fastapi_stub.Response = object
fastapi_stub.status = SimpleNamespace(HTTP_403_FORBIDDEN=403, HTTP_502_BAD_GATEWAY=502)
sys.modules.setdefault("fastapi", fastapi_stub)

sqlalchemy_orm_stub = ModuleType("sqlalchemy.orm")
sqlalchemy_orm_stub.Session = object
sys.modules.setdefault("sqlalchemy.orm", sqlalchemy_orm_stub)

config_stub = ModuleType("app.core.config")
config_stub.get_settings = lambda: SimpleNamespace(
    grafana_data_proxy_secret="proxy",
    secret_key="secret",
    prometheus_url="http://prometheus",
    loki_url="http://loki",
    grafana_sso_mode="auth-proxy",
)
sys.modules.setdefault("app.core.config", config_stub)

deps_stub = ModuleType("app.api.deps")
deps_stub.get_current_user = object
sys.modules.setdefault("app.api.deps", deps_stub)

db_stub = ModuleType("app.db.session")
db_stub.get_db = object
sys.modules.setdefault("app.db.session", db_stub)

for module_name, class_name in (
    ("app.models.grafana_target_dashboard", "GrafanaTargetDashboard"),
    ("app.models.monitor_target", "MonitorTarget"),
    ("app.models.user", "User"),
):
    module = ModuleType(module_name)
    setattr(module, class_name, object)
    sys.modules.setdefault(module_name, module)

client_stub = ModuleType("app.services.grafana_client")
client_stub.GrafanaClient = object
client_stub.GrafanaUnauthorizedError = type("GrafanaUnauthorizedError", (Exception,), {})
client_stub.GrafanaUnavailableError = type("GrafanaUnavailableError", (Exception,), {})
client_stub.get_grafana_client = object
sys.modules.setdefault("app.services.grafana_client", client_stub)

provisioner_stub = ModuleType("app.services.grafana_provisioner")
provisioner_stub.GrafanaProvisioningError = type("GrafanaProvisioningError", (Exception,), {})
provisioner_stub.GrafanaProvisioner = object
sys.modules.setdefault("app.services.grafana_provisioner", provisioner_stub)

for module_name, class_name in (
    ("app.services.loki_client", "LokiClient"),
    ("app.services.prometheus_client", "PrometheusClient"),
):
    module = ModuleType(module_name)
    setattr(module, class_name, object)
    sys.modules.setdefault(module_name, module)

from app.api.routes.grafana import (
    _loki_path_allowed,
    _prometheus_path_allowed,
    _scope_loki_params,
    _scope_prometheus_params,
)


class GrafanaProxyTest(unittest.TestCase):
    def test_prometheus_label_values_gets_user_matcher(self) -> None:
        self.assertEqual(
            _scope_prometheus_params("api/v1/label/instance/values", [], 7),
            [("match[]", '{platform_user_id="7"}')],
        )

    def test_prometheus_query_is_scoped(self) -> None:
        self.assertEqual(
            _scope_prometheus_params("api/v1/query", [("query", "up")], 7),
            [("query", 'up{platform_user_id="7"}')],
        )

    def test_loki_label_values_gets_user_selector(self) -> None:
        self.assertEqual(
            _scope_loki_params("loki/api/v1/label/pod/values", [], 7),
            [("query", '{platform_user_id="7"}')],
        )

    def test_loki_series_gets_user_selector(self) -> None:
        self.assertEqual(
            _scope_loki_params("loki/api/v1/series", [], 7),
            [("match[]", '{platform_user_id="7"}')],
        )

    def test_proxy_rejects_mutating_or_admin_paths(self) -> None:
        self.assertFalse(_prometheus_path_allowed("api/v1/admin/tsdb/delete_series"))
        self.assertFalse(_loki_path_allowed("loki/api/v1/push"))


if __name__ == "__main__":
    unittest.main()
