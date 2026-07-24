from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification_record import NotificationRecord
from app.models.user import User
from app.schemas.notification_record import NotificationRecordRead, NotificationRecordUpdateStatus, NotificationSendPendingResponse
from app.services.notification_sender import send_notification_record

router = APIRouter(prefix="/notification-records", tags=["notification records"])


def get_owned_record(record_id: int, db: Session, current_user: User) -> NotificationRecord:
    record = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.id == record_id, NotificationRecord.user_id == current_user.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification record not found")
    return record


@router.get("", response_model=list[NotificationRecordRead])
def list_notification_records(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|sent|failed|skipped)$"),
    notification_type: str | None = Query(default=None, pattern="^(triggered|resolved)$"),
    channel_id: int | None = Query(default=None),
    alert_event_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationRecord]:
    query = db.query(NotificationRecord).filter(NotificationRecord.user_id == current_user.id)
    if status_filter:
        query = query.filter(NotificationRecord.status == status_filter)
    if notification_type:
        query = query.filter(NotificationRecord.notification_type == notification_type)
    if channel_id is not None:
        query = query.filter(NotificationRecord.channel_id == channel_id)
    if alert_event_id is not None:
        query = query.filter(NotificationRecord.alert_event_id == alert_event_id)
    return list(query.order_by(NotificationRecord.created_at.desc(), NotificationRecord.id.desc()).limit(limit).all())


@router.get("/pending", response_model=list[NotificationRecordRead])
def list_pending_notification_records(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationRecord]:
    return list(
        db.query(NotificationRecord)
        .filter(NotificationRecord.user_id == current_user.id, NotificationRecord.status == "pending")
        .order_by(NotificationRecord.created_at.asc(), NotificationRecord.id.asc())
        .limit(limit)
        .all()
    )

@router.post("/send-pending", response_model=NotificationSendPendingResponse)
async def send_pending_notification_records(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationSendPendingResponse:
    records = list(
        db.query(NotificationRecord)
        .filter(NotificationRecord.user_id == current_user.id, NotificationRecord.status == "pending")
        .order_by(NotificationRecord.created_at.asc(), NotificationRecord.id.asc())
        .limit(limit)
        .all()
    )
    sent_records: list[NotificationRecord] = []
    for record in records:
        sent_records.append(await send_notification_record(db, record))

    return NotificationSendPendingResponse(
        total=len(sent_records),
        sent=len([record for record in sent_records if record.status == "sent"]),
        failed=len([record for record in sent_records if record.status == "failed"]),
        skipped=len([record for record in sent_records if record.status == "skipped"]),
        records=sent_records,
    )

@router.get("/{record_id}", response_model=NotificationRecordRead)
def get_notification_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationRecord:
    return get_owned_record(record_id, db, current_user)

@router.post("/{record_id}/send", response_model=NotificationRecordRead)
async def send_one_notification_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationRecord:
    record = get_owned_record(record_id, db, current_user)
    if record.status not in {"pending", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or failed notification records can be sent.",
        )
    return await send_notification_record(db, record)

@router.put("/{record_id}/status", response_model=NotificationRecordRead)
def update_notification_record_status(
    record_id: int,
    payload: NotificationRecordUpdateStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationRecord:
    record = get_owned_record(record_id, db, current_user)
    record.status = payload.status
    record.error_message = payload.error_message
    if payload.status == "sent":
        record.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record




