import unittest

from app.services.cluster_agent_config import normalize_agent_public_api_url


class ClusterAgentConfigTest(unittest.TestCase):
    def test_public_api_url_removes_whitespace_and_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_agent_public_api_url(" https://monitor.example.com/api/v1/ "),
            "https://monitor.example.com/api/v1",
        )

    def test_public_api_url_keeps_path(self) -> None:
        self.assertEqual(
            normalize_agent_public_api_url("http://114.55.117.211:30080/api/v1"),
            "http://114.55.117.211:30080/api/v1",
        )


if __name__ == "__main__":
    unittest.main()
