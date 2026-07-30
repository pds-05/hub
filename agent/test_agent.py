import importlib.util
import sys
import types
import unittest
from pathlib import Path


class DummyApi:
    pass


httpx = types.ModuleType("httpx")
httpx.Client = DummyApi
kubernetes = types.ModuleType("kubernetes")
kubernetes.client = types.SimpleNamespace(
    CoreV1Api=DummyApi,
    AppsV1Api=DummyApi,
    NetworkingV1Api=DummyApi,
    CustomObjectsApi=DummyApi,
    VersionApi=DummyApi,
)
kubernetes.config = types.SimpleNamespace()
sys.modules.setdefault("httpx", httpx)
sys.modules.setdefault("kubernetes", kubernetes)

spec = importlib.util.spec_from_file_location("monitor_agent", Path(__file__).with_name("agent.py"))
monitor_agent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(monitor_agent)


class AgentHelpersTest(unittest.TestCase):
    def test_kubernetes_quantities_are_normalized(self) -> None:
        self.assertAlmostEqual(monitor_agent.parse_cpu("250m"), 0.25)
        self.assertEqual(monitor_agent.parse_memory("2Gi"), 2 * 1024**3)

    def test_alerts_include_node_pod_workload_storage_network_and_events(self) -> None:
        snapshot = {
            "nodes": [{"name": "worker-01", "ready": False}],
            "problem_pods": [{"namespace": "prod", "name": "api-1", "phase": "Running", "waiting_reasons": ["CrashLoopBackOff"]}],
            "workloads": {"deployments": [{"kind": "Deployment", "namespace": "prod", "name": "api", "unavailable_replicas": 1}]},
            "storage": {"persistent_volume_claims": [{"namespace": "prod", "name": "data", "phase": "Pending"}]},
            "network": {"services_without_endpoints": [{"namespace": "prod", "name": "api", "type": "ClusterIP"}]},
            "warning_events": [{"namespace": "prod", "resource_kind": "Pod", "resource_name": "api-1", "reason": "FailedMount", "message": "volume mount failed"}],
        }
        alerts = monitor_agent.build_alerts(snapshot)
        alert_types = {item["alert_type"] for item in alerts.values()}
        self.assertEqual(alert_types, {"node_not_ready", "pod_unhealthy", "workload_unavailable", "pvc_unbound", "service_without_endpoint", "kubernetes_warning"})


    def test_alert_change_reporting_accepts_precomputed_alerts(self) -> None:
        sent = []
        original_post = monitor_agent.post
        monitor_agent.post = lambda path, payload: sent.append((path, payload))
        try:
            current = {"new": {"source": "prod/api", "level": "severe", "message": "new alert"}}
            previous = {"old": {"source": "prod/old", "level": "severe", "message": "old alert"}}
            result = monitor_agent.report_alert_changes(current, previous)
        finally:
            monitor_agent.post = original_post
        self.assertEqual(result, current)
        self.assertEqual({item[1]["payload"]["status"] for item in sent}, {"active", "resolved"})

if __name__ == "__main__":
    unittest.main()