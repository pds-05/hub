from __future__ import annotations

import ipaddress
import json
import socket
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import get_settings
from app.models.monitor_target import MonitorTarget


class ScrapeConfigError(Exception):
    pass


class ScrapeConfigManager:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.prometheus_scrape_config_enabled
        self.namespace = settings.prometheus_scrape_config_namespace
        self.api_version = settings.prometheus_scrape_config_api_version
        self.kubernetes_api_url = settings.kubernetes_api_url.rstrip("/")
        self.token_path = Path(settings.kubernetes_service_account_token_path)
        self.ca_path = Path(settings.kubernetes_service_account_ca_path)
        self.scrape_interval = settings.prometheus_target_scrape_interval
        self.scrape_timeout = settings.prometheus_target_scrape_timeout
        self.allow_private_targets = settings.prometheus_allow_private_targets
        try:
            self.resource_labels = json.loads(settings.prometheus_scrape_config_labels_json)
        except json.JSONDecodeError as exc:
            raise ScrapeConfigError("PROMETHEUS_SCRAPE_CONFIG_LABELS_JSON is invalid") from exc

    @staticmethod
    def resource_name(target_id: int) -> str:
        return f"monitor-target-{target_id}"

    def _headers(self) -> dict[str, str]:
        try:
            token = self.token_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ScrapeConfigError("Kubernetes ServiceAccount Token 不可用") from exc
        return {"Authorization": f"Bearer {token}"}

    def _verify(self) -> str | bool:
        return str(self.ca_path) if self.ca_path.exists() else True

    def _collection_url(self) -> str:
        return (
            f"{self.kubernetes_api_url}/apis/{self.api_version}/namespaces/"
            f"{self.namespace}/scrapeconfigs"
        )

    def _validate_target_host(self, hostname: str) -> None:
        lowered = hostname.rstrip(".").lower()
        if lowered in {"localhost", "kubernetes.default.svc"} or lowered.endswith((".svc", ".cluster.local", ".local")):
            raise ScrapeConfigError("Exporter 地址不能使用平台内部域名")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
        except socket.gaierror as exc:
            raise ScrapeConfigError("Exporter 域名无法解析") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                raise ScrapeConfigError("Exporter 地址解析到了禁止访问的网络范围")
            if str(ip) == "169.254.169.254":
                raise ScrapeConfigError("禁止访问云服务器元数据地址")
            if ip.is_private and not self.allow_private_targets:
                raise ScrapeConfigError("当前禁止添加私网 Exporter 地址，请使用公网地址；可信专线或测试环境可开启私网目标开关")
    def build_resource(self, target: MonitorTarget) -> dict[str, Any]:
        parsed = urlparse(target.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ScrapeConfigError("Exporter 地址必须是完整的 HTTP 或 HTTPS URL")
        if parsed.username or parsed.password:
            raise ScrapeConfigError("Exporter 地址中不能包含用户名或密码")
        self._validate_target_host(parsed.hostname)

        metadata_labels = {
            **self.resource_labels,
            "app.kubernetes.io/managed-by": "monitor-platform",
            "monitor-platform-managed": "true",
        }
        target_labels = {
            "platform_managed": "true",
            "platform_user_id": str(target.user_id),
            "platform_target_id": str(target.id),
            "platform_target_name": target.name,
            "platform_exporter_kind": target.exporter_kind or "custom",
        }
        spec: dict[str, Any] = {
            "jobName": self.resource_name(target.id),
            "scheme": parsed.scheme,
            "metricsPath": parsed.path or "/metrics",
            "scrapeInterval": self.scrape_interval,
            "scrapeTimeout": self.scrape_timeout,
            "staticConfigs": [{"targets": [parsed.netloc], "labels": target_labels}],
        }
        params = parse_qs(parsed.query, keep_blank_values=True)
        if params:
            spec["params"] = params

        return {
            "apiVersion": self.api_version,
            "kind": "ScrapeConfig",
            "metadata": {
                "name": self.resource_name(target.id),
                "namespace": self.namespace,
                "labels": metadata_labels,
            },
            "spec": spec,
        }

    async def upsert(self, target: MonitorTarget) -> str | None:
        if not self.enabled or target.target_type != "exporter":
            return None

        resource = self.build_resource(target)
        name = self.resource_name(target.id)
        collection_url = self._collection_url()
        item_url = f"{collection_url}/{name}"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                verify=self._verify(),
                headers=self._headers(),
            ) as client:
                existing = await client.get(item_url)
                if existing.status_code == 404:
                    response = await client.post(collection_url, json=resource)
                else:
                    existing.raise_for_status()
                    response = await client.patch(
                        item_url,
                        json={"metadata": resource["metadata"], "spec": resource["spec"]},
                        headers={"Content-Type": "application/merge-patch+json"},
                    )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ScrapeConfigError(f"Prometheus 采集注册失败：{detail}") from exc
        except httpx.HTTPError as exc:
            raise ScrapeConfigError("Kubernetes API 不可用") from exc
        return name

    async def delete(self, target_id: int) -> None:
        if not self.enabled:
            return
        item_url = f"{self._collection_url()}/{self.resource_name(target_id)}"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                verify=self._verify(),
                headers=self._headers(),
            ) as client:
                response = await client.delete(item_url)
                if response.status_code != 404:
                    response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ScrapeConfigError(f"Prometheus 采集配置删除失败：{detail}") from exc
        except httpx.HTTPError as exc:
            raise ScrapeConfigError("Kubernetes API 不可用") from exc


def get_scrape_config_manager() -> ScrapeConfigManager:
    return ScrapeConfigManager()