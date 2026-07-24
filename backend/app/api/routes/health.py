from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.redis_client import get_redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/dependencies")
def dependency_health_check() -> dict:
    db_ok = False
    redis_ok = False

    with SessionLocal() as db:
        db.execute(text("select 1"))
        db_ok = True

    redis_client = get_redis_client()
    redis_ok = redis_client.ping()

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "postgresql": db_ok,
        "redis": redis_ok,
    }

