import unittest
from types import SimpleNamespace

from app.services.grafana_security import effective_proxy_secret


class GrafanaSecurityTest(unittest.TestCase):
    def test_configured_proxy_secret_has_priority(self) -> None:
        settings = SimpleNamespace(grafana_data_proxy_secret="configured", secret_key="platform")
        self.assertEqual(effective_proxy_secret(settings), "configured")

    def test_proxy_secret_is_deterministically_derived(self) -> None:
        settings = SimpleNamespace(grafana_data_proxy_secret="", secret_key="platform")
        first = effective_proxy_secret(settings)
        second = effective_proxy_secret(settings)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, settings.secret_key)


if __name__ == "__main__":
    unittest.main()
