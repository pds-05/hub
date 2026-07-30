import unittest

from app.services.logql_scope import scope_logql
from app.services.promql_scope import scope_promql


class GrafanaScopeTest(unittest.TestCase):
    def test_promql_adds_user_scope(self) -> None:
        self.assertEqual(
            scope_promql('sum(up{job="node"})', 7),
            'sum(up{job="node",platform_user_id="7"})',
        )

    def test_promql_keeps_matching_user_scope(self) -> None:
        query = 'probe_success{platform_user_id="7",platform_target_id="19"}'
        self.assertEqual(scope_promql(query, 7), query)

    def test_promql_rejects_other_user(self) -> None:
        with self.assertRaises(ValueError):
            scope_promql('up{platform_user_id="8"}', 7)

    def test_promql_scopes_bare_and_explicit_selectors(self) -> None:
        self.assertEqual(
            scope_promql('up + sum(rate(http_requests_total{job="api"}[5m]))', 7),
            'up{platform_user_id="7"} + sum(rate(http_requests_total{job="api",platform_user_id="7"}[5m]))',
        )

    def test_promql_does_not_rewrite_grouping_labels_or_strings(self) -> None:
        self.assertEqual(
            scope_promql('sum by (instance) (rate(http_requests_total{path=~"/api/v1/users"}[5m]))', 7),
            'sum by (instance) (rate(http_requests_total{path=~"/api/v1/users",platform_user_id="7"}[5m]))',
        )


    def test_logql_adds_user_scope(self) -> None:
        self.assertEqual(
            scope_logql('{namespace="production"} |= "error"', 7),
            '{namespace="production",platform_user_id="7"} |= "error"',
        )

    def test_logql_rejects_other_user(self) -> None:
        with self.assertRaises(ValueError):
            scope_logql('{platform_user_id="8"}', 7)

    def test_logql_scopes_every_stream_selector(self) -> None:
        self.assertEqual(
            scope_logql('sum(rate({app="api"}[5m])) / sum(rate({app="worker"}[5m]))', 7),
            'sum(rate({app="api",platform_user_id="7"}[5m])) / '
            'sum(rate({app="worker",platform_user_id="7"}[5m]))',
        )


if __name__ == "__main__":
    unittest.main()