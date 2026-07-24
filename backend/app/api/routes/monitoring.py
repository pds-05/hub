from fastapi import APIRouter, Depends, Query

from app.services.alertmanager_client import AlertmanagerClient, get_alertmanager_client
from app.services.loki_client import LokiClient, get_loki_client
from app.services.prometheus_client import PrometheusClient, get_prometheus_client

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/prometheus/query")
async def prometheus_query(
    query: str = Query(default="up"),
    client: PrometheusClient = Depends(get_prometheus_client),
) -> dict:
    return await client.query(query)


@router.get("/prometheus/targets")
async def prometheus_targets(client: PrometheusClient = Depends(get_prometheus_client)) -> dict:
    return await client.targets()


@router.get("/exporter/node")
async def node_exporter_metrics(
    instance: str = Query(description="Prometheus instance label, for example 172.22.115.207:9100"),
    client: PrometheusClient = Depends(get_prometheus_client),
) -> dict:
    return await client.node_metrics(instance)


@router.get("/exporter/nodes/summary")
async def all_node_exporter_metrics_summary(client: PrometheusClient = Depends(get_prometheus_client)) -> dict:
    return await client.node_metrics_summary()


@router.get("/exporter/nodes/alerts")
async def node_resource_alerts(client: PrometheusClient = Depends(get_prometheus_client)) -> list[dict]:
    return await client.node_resource_alerts()


@router.get("/exporter/nodes")
async def all_node_exporter_metrics(client: PrometheusClient = Depends(get_prometheus_client)) -> list[dict]:
    return await client.all_node_metrics()


@router.get("/loki/query")
async def loki_query(
    query: str = Query(default='{namespace="kube-system"}'),
    limit: int = Query(default=100, ge=1, le=1000),
    minutes: int = Query(default=30, ge=1, le=1440),
    client: LokiClient = Depends(get_loki_client),
) -> dict:
    return await client.query_range(query, limit=limit, minutes=minutes)


@router.get("/alerts")
async def alertmanager_alerts(client: AlertmanagerClient = Depends(get_alertmanager_client)) -> list[dict]:
    return await client.alerts()
