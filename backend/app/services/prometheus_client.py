import asyncio
import time

import httpx

from app.core.config import get_settings
from app.models.monitor_target import MonitorTarget
from app.services.exporter_metric_catalog import ExporterMetricDefinition, definitions_for, render_expression, target_selector


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

    async def query_range(self, promql: str, minutes: int = 60, step: int = 30) -> dict:
        end = int(time.time())
        start = end - minutes * 60
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query_range",
                    params={"query": promql, "start": start, "end": end, "step": step},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise PrometheusUnavailableError(f"Prometheus is unavailable at {self.base_url}") from exc

    @staticmethod
    def _instant_value(payload: dict) -> float | None:
        result = payload.get("data", {}).get("result", [])
        if not result:
            return None
        try:
            return round(float(result[0]["value"][1]), 4)
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @staticmethod
    def _range_values(payload: dict) -> list[list[float]]:
        result = payload.get("data", {}).get("result", [])
        if not result:
            return []
        points: list[list[float]] = []
        for timestamp, raw_value in result[0].get("values", []):
            try:
                points.append([float(timestamp), float(raw_value)])
            except (TypeError, ValueError):
                continue
        return points

    async def metric_names(self, selector: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/label/__name__/values",
                    params=[("match[]", f"{{{selector}}}")],
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PrometheusUnavailableError(f"Prometheus is unavailable at {self.base_url}") from exc
        return sorted(str(item) for item in payload.get("data", []) if item)

    async def _definition_value(
        self,
        definition: ExporterMetricDefinition,
        selector: str,
    ) -> tuple[float | None, str | None]:
        for template in definition.expressions:
            expression = render_expression(template, selector)
            value = self._instant_value(await self.query(expression))
            if value is not None:
                return value, expression
        return None, None

    async def target_metrics(self, target: MonitorTarget, minutes: int = 60) -> dict:
        selector = target_selector(target.user_id, target.id)
        is_blackbox = target.target_type in {"website", "port"}
        status_metric = "probe_success" if is_blackbox else "up"
        up_value = self._instant_value(await self.query(f"{status_metric}{{{selector}}}"))
        metric_names = await self.metric_names(selector)
        series_count = self._instant_value(await self.query(f"count({{{selector}}})"))
        metric_kind = "blackbox" if is_blackbox else target.exporter_kind
        definitions = list(definitions_for(metric_kind))
        if not definitions:
            definitions = [
                ExporterMetricDefinition(
                    key=name,
                    label=name,
                    unit="",
                    expressions=(f"sum({name}{{$selector}})",),
                )
                for name in metric_names[:8]
                if name != "up"
            ]

        async def load_metric(definition: ExporterMetricDefinition) -> dict:
            value, expression = await self._definition_value(definition, selector)
            series: list[list[float]] = []
            if minutes > 0 and expression:
                series = self._range_values(await self.query_range(expression, minutes=minutes))
            return {
                "key": definition.key,
                "label": definition.label,
                "unit": definition.unit,
                "value": value,
                "series": series,
                "promql": expression,
            }

        metrics = await asyncio.gather(*(load_metric(definition) for definition in definitions))

        target_state = None
        try:
            active_targets = (await self.targets()).get("data", {}).get("activeTargets", [])
            target_state = next(
                (
                    item
                    for item in active_targets
                    if str((item.get("labels") or item.get("discoveredLabels") or {}).get("platform_target_id")) == str(target.id)
                    and str((item.get("labels") or item.get("discoveredLabels") or {}).get("platform_user_id")) == str(target.user_id)
                ),
                None,
            )
        except PrometheusError:
            target_state = None

        scrape_status = "pending" if up_value is None else "up" if up_value >= 1 else "down"
        return {
            "target_id": target.id,
            "target_name": target.name,
            "target_type": target.target_type,
            "exporter_kind": metric_kind or "custom",
            "scrape_status": scrape_status,
            "up": up_value,
            "last_scrape_at": target_state.get("lastScrape") if target_state else None,
            "scrape_duration_seconds": target_state.get("lastScrapeDuration") if target_state else None,
            "last_error": target_state.get("lastError") if target_state else None,
            "metric_count": len(metric_names),
            "series_count": int(series_count) if series_count is not None else 0,
            "metric_names": metric_names[:100],
            "metrics": metrics,
        }

    async def target_metric_values(self, target: MonitorTarget) -> dict[str, float | None]:
        payload = await self.target_metrics(target, minutes=0)
        values = {item["key"]: item["value"] for item in payload["metrics"]}
        values.update(
            {
                "up": payload["up"],
                "metric_count": float(payload["metric_count"]),
                "series_count": float(payload["series_count"]),
            }
        )
        return values
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
