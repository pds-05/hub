from fastapi import APIRouter

from app.api.routes import alert_events, alert_rules, assistant, assistant_tools, auth, clusters, grafana, health, monitoring, notification_channels, notification_records, platform, targets

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(targets.router)
api_router.include_router(clusters.router)
api_router.include_router(clusters.agent_router)
api_router.include_router(alert_rules.router)
api_router.include_router(alert_events.router)
api_router.include_router(notification_channels.router)
api_router.include_router(notification_records.router)
api_router.include_router(platform.router)
api_router.include_router(monitoring.router)
api_router.include_router(grafana.router)
api_router.include_router(assistant.router)
api_router.include_router(assistant_tools.router)
