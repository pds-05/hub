import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.alert_events import evaluate_target_alert_events
from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.monitor_target import MonitorTarget
from app.models.user import User
from app.services.grafana_provisioner import GrafanaProvisioner, GrafanaProvisioningError, provision_target_safely
from app.services.prometheus_client import PrometheusClient
from app.services.scrape_config_manager import ScrapeConfigError, get_scrape_config_manager

settings = get_settings()
logger = logging.getLogger(__name__)


async def evaluate_target_alerts_forever() -> None:
    while True:
        await asyncio.sleep(settings.target_alert_evaluation_interval_seconds)
        try:
            with SessionLocal() as db:
                users = db.query(User).filter(User.is_active.is_(True)).all()
                prometheus = PrometheusClient()
                for user in users:
                    try:
                        await evaluate_target_alert_events(db=db, current_user=user, prometheus=prometheus)
                    except Exception:
                        db.rollback()
                        logger.exception("Scheduled target alert evaluation failed for user %s", user.id)
        except Exception:
            logger.exception("Scheduled target alert evaluation failed")


app = FastAPI(title=settings.app_name, debug=settings.debug)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    manager = get_scrape_config_manager()
    if manager.enabled:
        with SessionLocal() as db:
            targets = (
                db.query(MonitorTarget)
                .filter(MonitorTarget.deleted_at.is_(None), MonitorTarget.target_type.in_(["exporter", "website", "port"]))
                .all()
            )
            for target in targets:
                try:
                    await manager.upsert(target)
                except ScrapeConfigError:
                    # A single invalid external target must not stop the platform from starting.
                    continue
    if settings.grafana_provisioning_enabled:
        with SessionLocal() as db:
            try:
                await GrafanaProvisioner().ensure_api_token(db)
                users = {user.id: user for user in db.query(User).filter(User.is_active.is_(True)).all()}
                targets = db.query(MonitorTarget).filter(MonitorTarget.deleted_at.is_(None)).all()
                for target in targets:
                    user = users.get(target.user_id)
                    if user is not None:
                        await provision_target_safely(db, target, user)
            except GrafanaProvisioningError:
                logger.warning("Grafana automatic provisioning is not ready", exc_info=True)
    if settings.target_alert_evaluation_enabled:
        app.state.target_alert_task = asyncio.create_task(evaluate_target_alerts_forever())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "target_alert_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app.include_router(api_router, prefix=settings.api_prefix)


