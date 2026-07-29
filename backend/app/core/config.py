from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "K8s Intelligent Monitoring Platform"
    api_prefix: str = "/api/v1"
    debug: bool = False
    secret_key: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    database_url: str = Field(
        default="postgresql+psycopg://monitor_admin:monitor123@postgresql.platform.svc:5432/monitor_platform",
        description="SQLAlchemy database URL.",
    )
    redis_url: str = "redis://:redis123@redis.platform.svc:6379/0"

    prometheus_url: str = "http://monitoring-ack-prometheus-prometheus.monitoring.svc:9090"
    prometheus_scrape_config_enabled: bool = False
    prometheus_scrape_config_namespace: str = "monitoring"
    prometheus_scrape_config_api_version: str = "monitoring.coreos.com/v1alpha1"
    prometheus_scrape_config_labels_json: str = '{"release":"monitoring"}'
    prometheus_target_scrape_interval: str = "30s"
    prometheus_target_scrape_timeout: str = "10s"
    prometheus_allow_private_targets: bool = False
    target_alert_evaluation_enabled: bool = False
    target_alert_evaluation_interval_seconds: int = 60
    kubernetes_api_url: str = "https://kubernetes.default.svc"
    kubernetes_service_account_token_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    kubernetes_service_account_ca_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    alertmanager_url: str = "http://monitoring-ack-prometheus-alertmanager.monitoring.svc:9093"
    loki_url: str = "http://loki-gateway.logging.svc.cluster.local"
    grafana_url: str = "http://monitoring-grafana.monitoring.svc.cluster.local:80"
    grafana_public_url: str = "http://114.55.117.211:31000"
    grafana_api_key: str = ""
    harbor_url: str = "http://114.55.117.211:18080"
    agent_public_api_url: str = "http://114.55.117.211:30080/api/v1"

    ai_api_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = "deepseek-v4-flash"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    cors_origins: List[AnyHttpUrl] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()









