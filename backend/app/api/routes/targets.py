from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.monitor_target import MonitorTarget
from app.models.target_check_result import TargetCheckResult
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.monitor_target import (
    MonitorTargetCheckRead,
    MonitorTargetCreate,
    MonitorTargetRead,
    MonitorTargetSummaryRead,
    MonitorTargetUpdate,
)
from app.services.prometheus_client import PrometheusClient, PrometheusError, get_prometheus_client
from app.services.scrape_config_manager import ScrapeConfigError, ScrapeConfigManager, get_scrape_config_manager
from app.services.target_checker import check_monitor_target

router = APIRouter(prefix="/targets", tags=["monitor targets"])


def build_node_summary(nodes: list[dict]) -> dict:
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
        return max(clean_nodes, key=lambda node: metric_value(node, key) or 0)["instance"]

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



def normalize_target_payload(data: dict) -> dict:
    if data.get("target_type") != "exporter":
        data["exporter_kind"] = None
    elif not data.get("exporter_kind"):
        data["exporter_kind"] = "node"
    return data

def latest_checks_by_target(db: Session, user_id: int, target_ids: list[int]) -> dict[int, TargetCheckResult]:
    if not target_ids:
        return {}
    latest_by_target: dict[int, TargetCheckResult] = {}
    rows = (
        db.query(TargetCheckResult)
        .filter(TargetCheckResult.user_id == user_id, TargetCheckResult.target_id.in_(target_ids))
        .order_by(TargetCheckResult.target_id.asc(), TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
        .all()
    )
    for row in rows:
        if row.target_id not in latest_by_target:
            latest_by_target[row.target_id] = row
    return latest_by_target
def get_owned_target(target_id: int, db: Session, current_user: User) -> MonitorTarget:
    target = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.id == target_id, MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target


def to_check_read(check_result: TargetCheckResult) -> MonitorTargetCheckRead:
    return MonitorTargetCheckRead(
        check_id=check_result.id,
        target_id=check_result.target_id,
        status=check_result.status,
        response_time_ms=check_result.response_time_ms,
        message=check_result.message,
        status_code=check_result.status_code,
        details=check_result.details,
        checked_at=check_result.checked_at,
    )


@router.post("", response_model=MonitorTargetRead)
async def create_target(
    payload: MonitorTargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scrape_configs: ScrapeConfigManager = Depends(get_scrape_config_manager),
) -> MonitorTarget:
    target = MonitorTarget(**normalize_target_payload(payload.model_dump()), user_id=current_user.id)
    db.add(target)
    db.commit()
    db.refresh(target)
    try:
        await scrape_configs.upsert(target)
    except ScrapeConfigError as exc:
        db.delete(target)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return target


@router.get("", response_model=list[MonitorTargetRead])
def list_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MonitorTarget]:
    return list(
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None))
        .order_by(MonitorTarget.id.desc())
        .all()
    )


@router.get("/summary", response_model=MonitorTargetSummaryRead)
def target_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonitorTargetSummaryRead:
    targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None)).all()
    target_ids = [target.id for target in targets]
    if not target_ids:
        return MonitorTargetSummaryRead(total=0, up=0, down=0, unknown=0)

    latest_by_target: dict[int, TargetCheckResult] = {}
    rows = (
        db.query(TargetCheckResult)
        .filter(TargetCheckResult.user_id == current_user.id, TargetCheckResult.target_id.in_(target_ids))
        .order_by(TargetCheckResult.target_id.asc(), TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
        .all()
    )
    for row in rows:
        if row.target_id not in latest_by_target:
            latest_by_target[row.target_id] = row

    up = 0
    down = 0
    response_times: list[int] = []
    for target_id in target_ids:
        latest = latest_by_target.get(target_id)
        if latest is None:
            continue
        if latest.status == "up":
            up += 1
        else:
            down += 1
        response_times.append(latest.response_time_ms)

    unknown = len(target_ids) - up - down
    avg_response_time_ms = int(sum(response_times) / len(response_times)) if response_times else None
    return MonitorTargetSummaryRead(
        total=len(target_ids),
        up=up,
        down=down,
        unknown=unknown,
        avg_response_time_ms=avg_response_time_ms,
    )



@router.get("/exporters/summary")
def exporter_kind_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    exporter_targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None), MonitorTarget.target_type == "exporter")
        .order_by(MonitorTarget.id.desc())
        .all()
    )
    target_ids = [target.id for target in exporter_targets]
    latest_by_target = latest_checks_by_target(db, current_user.id, target_ids)
    kinds: dict[str, dict] = {}
    for target in exporter_targets:
        kind = target.exporter_kind or "custom"
        latest = latest_by_target.get(target.id)
        item = kinds.setdefault(kind, {"kind": kind, "total": 0, "up": 0, "down": 0, "unknown": 0, "targets": []})
        status_value = latest.status if latest else "unknown"
        item["total"] += 1
        if status_value == "up":
            item["up"] += 1
        elif status_value == "down":
            item["down"] += 1
        else:
            item["unknown"] += 1
        item["targets"].append({
            "target_id": target.id,
            "name": target.name,
            "endpoint": target.endpoint,
            "status": status_value,
            "response_time_ms": latest.response_time_ms if latest else None,
            "checked_at": latest.checked_at if latest else None,
            "message": latest.message if latest else None,
        })
    return {"total": len(exporter_targets), "kinds": list(kinds.values())}

@router.get("/exporters/resources")
def exporter_resource_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    exporter_targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == current_user.id, MonitorTarget.deleted_at.is_(None), MonitorTarget.target_type == "exporter", MonitorTarget.exporter_kind == "node")
        .order_by(MonitorTarget.id.desc())
        .all()
    )
    nodes: list[dict] = []
    for target in exporter_targets:
        latest = (
            db.query(TargetCheckResult)
            .filter(TargetCheckResult.user_id == current_user.id, TargetCheckResult.target_id == target.id)
            .order_by(TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
            .first()
        )
        metrics = (latest.details or {}).get("node_metrics") if latest else None
        nodes.append({
            "target_id": target.id,
            "name": target.name,
            "instance": target.endpoint,
            "exporter_kind": target.exporter_kind,
            "status": latest.status if latest else "unknown",
            "checked_at": latest.checked_at if latest else None,
            "metrics": metrics or {},
        })
    return build_node_summary(nodes)


@router.get("/{target_id}", response_model=MonitorTargetRead)
def get_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonitorTarget:
    return get_owned_target(target_id, db, current_user)


@router.put("/{target_id}", response_model=MonitorTargetRead)
async def update_target(
    target_id: int,
    payload: MonitorTargetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scrape_configs: ScrapeConfigManager = Depends(get_scrape_config_manager),
) -> MonitorTarget:
    target = get_owned_target(target_id, db, current_user)
    original = {
        "name": target.name,
        "target_type": target.target_type,
        "endpoint": target.endpoint,
        "expected_keyword": target.expected_keyword,
        "exporter_kind": target.exporter_kind,
        "description": target.description,
    }
    was_exporter = target.target_type == "exporter"
    update_data = payload.model_dump(exclude_unset=True)
    if "target_type" not in update_data:
        update_data["target_type"] = target.target_type
    update_data = normalize_target_payload(update_data)
    for field, value in update_data.items():
        setattr(target, field, value)

    db.commit()
    db.refresh(target)
    try:
        if target.target_type == "exporter":
            await scrape_configs.upsert(target)
        elif was_exporter:
            await scrape_configs.delete(target.id)
    except ScrapeConfigError as exc:
        for field, value in original.items():
            setattr(target, field, value)
        db.commit()
        db.refresh(target)
        try:
            if target.target_type == "exporter":
                await scrape_configs.upsert(target)
            else:
                await scrape_configs.delete(target.id)
        except ScrapeConfigError:
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return target


@router.delete("/{target_id}", response_model=MessageResponse)
async def delete_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scrape_configs: ScrapeConfigManager = Depends(get_scrape_config_manager),
) -> MessageResponse:
    target = get_owned_target(target_id, db, current_user)
    try:
        if target.target_type == "exporter":
            await scrape_configs.delete(target.id)
    except ScrapeConfigError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    target.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return MessageResponse(message="Target deleted")


@router.post("/{target_id}/sync")
async def sync_target_collection(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scrape_configs: ScrapeConfigManager = Depends(get_scrape_config_manager),
) -> dict:
    target = get_owned_target(target_id, db, current_user)
    if target.target_type != "exporter":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有 Exporter 类型支持持续采集")
    try:
        resource_name = await scrape_configs.upsert(target)
    except ScrapeConfigError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"target_id": target.id, "resource_name": resource_name, "message": "采集配置已同步"}


@router.get("/{target_id}/metrics")
async def get_target_metrics(
    target_id: int,
    minutes: int = Query(default=60, ge=5, le=1440),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    prometheus: PrometheusClient = Depends(get_prometheus_client),
) -> dict:
    target = get_owned_target(target_id, db, current_user)
    if target.target_type != "exporter":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有 Exporter 类型具有 Prometheus 持续指标")
    try:
        return await prometheus.target_metrics(target, minutes=minutes)
    except PrometheusError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

@router.post("/{target_id}/check", response_model=MonitorTargetCheckRead)
async def check_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonitorTargetCheckRead:
    target = get_owned_target(target_id, db, current_user)
    result = await check_monitor_target(target)
    check_result = TargetCheckResult(
        target_id=target.id,
        user_id=current_user.id,
        status=result.status,
        response_time_ms=result.response_time_ms,
        status_code=result.status_code,
        message=result.message,
        details=result.details,
    )
    db.add(check_result)
    db.commit()
    db.refresh(check_result)
    return to_check_read(check_result)


@router.get("/{target_id}/checks", response_model=list[MonitorTargetCheckRead])
def list_target_checks(
    target_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MonitorTargetCheckRead]:
    target = get_owned_target(target_id, db, current_user)
    rows = (
        db.query(TargetCheckResult)
        .filter(TargetCheckResult.target_id == target.id, TargetCheckResult.user_id == current_user.id)
        .order_by(TargetCheckResult.checked_at.desc(), TargetCheckResult.id.desc())
        .limit(limit)
        .all()
    )
    return [to_check_read(row) for row in rows]




