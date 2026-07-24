from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx

from app.api.deps import require_root_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.services.redis_client import get_redis_client

router = APIRouter(prefix="/platform", tags=["platform"])


async def check_http_service(name: str, url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(url)
        return {
            "name": name,
            "status": "healthy" if response.status_code < 500 else "degraded",
            "message": f"HTTP {response.status_code}",
            "url": url,
        }
    except Exception as exc:
        return {"name": name, "status": "down", "message": str(exc), "url": url}


@router.get("/health")
async def platform_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_user),
) -> dict:
    _ = current_user
    settings = get_settings()
    services: list[dict] = []

    try:
        db.execute(text("select 1"))
        services.append({"name": "PostgreSQL", "status": "healthy", "message": "database connection ok"})
    except Exception as exc:
        services.append({"name": "PostgreSQL", "status": "down", "message": str(exc)})

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        services.append({"name": "Redis", "status": "healthy", "message": "redis ping ok"})
    except Exception as exc:
        services.append({"name": "Redis", "status": "down", "message": str(exc)})

    checks = [
        ("Prometheus", f"{settings.prometheus_url.rstrip('/')}/-/healthy"),
        ("Loki", f"{settings.loki_url.rstrip('/')}/ready"),
        ("Grafana", f"{settings.grafana_url.rstrip('/')}/api/health"),
        ("Harbor", f"{settings.harbor_url.rstrip('/')}/api/v2.0/health"),
    ]
    for name, url in checks:
        services.append(await check_http_service(name, url))

    unhealthy = [item for item in services if item["status"] != "healthy"]
    return {
        "status": "healthy" if not unhealthy else "degraded",
        "services": services,
    }
