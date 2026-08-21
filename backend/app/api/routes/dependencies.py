from sqlalchemy import or_
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.monitor_target import MonitorTarget
from app.models.service_dependency import ServiceDependency
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.service_dependency import ServiceDependencyCreate, ServiceDependencyRead

router = APIRouter(prefix="/dependencies", tags=["service dependencies"])


def _owned_target(db: Session, user_id: int, target_id: int) -> MonitorTarget:
    target = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.id == target_id, MonitorTarget.user_id == user_id, MonitorTarget.deleted_at.is_(None))
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target


@router.post("", response_model=ServiceDependencyRead, status_code=status.HTTP_201_CREATED)
def create_dependency(
    payload: ServiceDependencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ServiceDependency:
    if payload.source_target_id == payload.destination_target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A target cannot depend on itself")
    _owned_target(db, current_user.id, payload.source_target_id)
    _owned_target(db, current_user.id, payload.destination_target_id)
    existing = (
        db.query(ServiceDependency)
        .filter(
            ServiceDependency.user_id == current_user.id,
            ServiceDependency.source_target_id == payload.source_target_id,
            ServiceDependency.destination_target_id == payload.destination_target_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This dependency already exists")
    dependency = ServiceDependency(user_id=current_user.id, **payload.model_dump())
    db.add(dependency)
    db.commit()
    db.refresh(dependency)
    return dependency


@router.get("", response_model=list[ServiceDependencyRead])
def list_dependencies(
    target_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ServiceDependency]:
    query = db.query(ServiceDependency).filter(ServiceDependency.user_id == current_user.id)
    if target_id is not None:
        _owned_target(db, current_user.id, target_id)
        query = query.filter(or_(ServiceDependency.source_target_id == target_id, ServiceDependency.destination_target_id == target_id))
    return list(query.order_by(ServiceDependency.created_at.desc(), ServiceDependency.id.desc()).all())


@router.delete("/{dependency_id}", response_model=MessageResponse)
def delete_dependency(
    dependency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    dependency = (
        db.query(ServiceDependency)
        .filter(ServiceDependency.id == dependency_id, ServiceDependency.user_id == current_user.id)
        .first()
    )
    if dependency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found")
    db.delete(dependency)
    db.commit()
    return MessageResponse(message="Dependency deleted")