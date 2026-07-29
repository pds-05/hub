import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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
