import unittest
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import Mock

# Keep this unit test independent from runtime packages installed in the app image.
httpx_stub = ModuleType("httpx")
httpx_stub.AsyncClient = object
httpx_stub.HTTPStatusError = Exception
httpx_stub.HTTPError = Exception
sys.modules.setdefault("httpx", httpx_stub)

config_stub = ModuleType("app.core.config")
config_stub.get_settings = lambda: None
sys.modules.setdefault("app.core.config", config_stub)

model_stub = ModuleType("app.models.monitor_target")
model_stub.MonitorTarget = object
sys.modules.setdefault("app.models.monitor_target", model_stub)

from app.services.scrape_config_manager import ScrapeConfigManager


class ScrapeConfigManagerTest(unittest.TestCase):
    def test_build_resource_uses_operator_scheme(self) -> None:
        manager = ScrapeConfigManager.__new__(ScrapeConfigManager)
        manager.api_version = "monitoring.coreos.com/v1alpha1"
        manager.namespace = "monitoring"
        manager.resource_labels = {"release": "monitoring"}
        manager.scrape_interval = "30s"
        manager.scrape_timeout = "10s"
        manager._validate_target_host = Mock()
        target = SimpleNamespace(
            id=19,
            user_id=7,
            name="rabbitmq-production",
            endpoint="http://example.com:15692/metrics",
            exporter_kind="rabbitmq",
        )

        resource = manager.build_resource(target)

        self.assertEqual(resource["metadata"]["name"], "monitor-target-19")
        self.assertEqual(resource["spec"]["scheme"], "HTTP")
        self.assertEqual(resource["spec"]["metricsPath"], "/metrics")
        self.assertEqual(
            resource["spec"]["staticConfigs"][0]["targets"],
            ["example.com:15692"],
        )
        manager._validate_target_host.assert_called_once_with("example.com")


if __name__ == "__main__":
    unittest.main()
