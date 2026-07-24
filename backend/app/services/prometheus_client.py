import httpx

from app.core.config import get_settings


class PrometheusError(Exception):
    pass


class PrometheusUnavailableError(PrometheusError):
    pass


class PrometheusClient:
    def __init__(self) -> None:
        self.base_url = get_settings().prometheus_url.rstrip("/")

    async def query(self, promql: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/api/v1/query", params={"query": promql})
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise PrometheusUnavailableError(f"Prometheus is unavailable at {self.base_url}") from exc

    async def targets(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/api/v1/targets")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise PrometheusUnavailableError(f"Prometheus is unavailable at {self.base_url}") from exc

    async def node_instances(self) -> list[str]:
        data = await self.query('up{job="node-exporter"}')
        result = data.get("data", {}).get("result", [])
        instances = [item.get("metric", {}).get("instance") for item in result]
        return sorted(instance for instance in instances if instance)

    async def node_metrics(self, instance: str, include_raw: bool = True) -> dict:
        queries = {
            "cpu_usage_percent": f'100 - (avg by(instance) (rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[5m])) * 100)',
            "memory_usage_percent": f'(1 - (node_memory_MemAvailable_bytes{{instance="{instance}"}} / node_memory_MemTotal_bytes{{instance="{instance}"}})) * 100',
            "disk_usage_percent": f'(1 - (node_filesystem_avail_bytes{{fstype!~"tmpfs|overlay",mountpoint="/",instance="{instance}"}} / node_filesystem_size_bytes{{fstype!~"tmpfs|overlay",mountpoint="/",instance="{instance}"}})) * 100',
            "load1": f'node_load1{{instance="{instance}"}}',
        }
        results: dict[str, float | None] = {}
        raw: dict[str, dict] = {}
        for key, promql in queries.items():
            data = await self.query(promql)
            if include_raw:
                raw[key] = data
            result = data.get("data", {}).get("result", [])
            if not result:
                results[key] = None
                continue
            results[key] = round(float(result[0]["value"][1]), 2)

        payload = {"instance": instance, "metrics": results}
        if include_raw:
            payload["raw"] = raw
        return payload

    async def all_node_metrics(self) -> list[dict]:
        instances = await self.node_instances()
        return [await self.node_metrics(instance, include_raw=False) for instance in instances]

    async def node_metrics_summary(self) -> dict:
        nodes = await self.all_node_metrics()
        if not nodes:
            return {
                "node_count": 0,
                "avg_cpu_usage_percent": None,
                "avg_memory_usage_percent": None,
                "avg_disk_usage_percent": None,
                "avg_load1": None,
                "max_cpu_node": None,
                "max_memory_node": None,
                "max_disk_node": None,
                "nodes": [],
            }

        def metric_value(node: dict, key: str) -> float | None:
            value = node.get("metrics", {}).get(key)
            return value if isinstance(value, (int, float)) else None

        def average(key: str) -> float | None:
            values = [metric_value(node, key) for node in nodes]
            clean_values = [value for value in values if value is not None]
            if not clean_values:
                return None
            return round(sum(clean_values) / len(clean_values), 2)

        def max_node(key: str) -> str | None:
            clean_nodes = [node for node in nodes if metric_value(node, key) is not None]
            if not clean_nodes:
                return None
            return max(clean_nodes, key=lambda node: metric_value(node, key))["instance"]

        return {
            "node_count": len(nodes),
            "avg_cpu_usage_percent": average("cpu_usage_percent"),
            "avg_memory_usage_percent": average("memory_usage_percent"),
            "avg_disk_usage_percent": average("disk_usage_percent"),
            "avg_load1": average("load1"),
            "max_cpu_node": max_node("cpu_usage_percent"),
            "max_memory_node": max_node("memory_usage_percent"),
            "max_disk_node": max_node("disk_usage_percent"),
            "nodes": nodes,
        }

    async def node_resource_alerts(self) -> list[dict]:
        nodes = await self.all_node_metrics()
        rules = {
            "cpu_usage_percent": {"warning": 80.0, "critical": 90.0, "label": "CPU usage"},
            "memory_usage_percent": {"warning": 80.0, "critical": 90.0, "label": "Memory usage"},
            "disk_usage_percent": {"warning": 85.0, "critical": 95.0, "label": "Disk usage"},
            "load1": {"warning": 4.0, "critical": 8.0, "label": "1m load"},
        }
        alerts: list[dict] = []
        for node in nodes:
            instance = node["instance"]
            metrics = node.get("metrics", {})
            for metric, rule in rules.items():
                value = metrics.get(metric)
                if not isinstance(value, (int, float)):
                    continue
                level = None
                threshold = None
                if value >= rule["critical"]:
                    level = "critical"
                    threshold = rule["critical"]
                elif value >= rule["warning"]:
                    level = "warning"
                    threshold = rule["warning"]
                if level is None:
                    continue
                alerts.append(
                    {
                        "instance": instance,
                        "level": level,
                        "metric": metric,
                        "metric_label": rule["label"],
                        "value": value,
                        "threshold": threshold,
                        "message": f'{instance} {rule["label"]} is high: {value} >= {threshold}',
                    }
                )
        return alerts


def get_prometheus_client() -> PrometheusClient:
    return PrometheusClient()
