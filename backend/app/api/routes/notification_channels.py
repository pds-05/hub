from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification_channel import NotificationChannel
from app.models.notification_record import NotificationRecord
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.notification_channel import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelTestResponse,
    NotificationChannelUpdate,
)
from app.services.notification_sender import send_notification_record

router = APIRouter(prefix="/notification-channels", tags=["notification channels"])


def get_owned_channel(channel_id: int, db: Session, current_user: User) -> NotificationChannel:
    channel = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.id == channel_id, NotificationChannel.user_id == current_user.id, NotificationChannel.deleted_at.is_(None))
        .first()
    )
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    return channel


def validate_channel_config(channel_type: str, config: dict) -> None:
    if channel_type == "email":
        to_address = config.get("to")
        if not isinstance(to_address, str) or "@" not in to_address:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email channel config requires a valid 'to' address.",
            )
        smtp_port = config.get("smtp_port")
        if smtp_port not in (None, ""):
            try:
                int(smtp_port)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Email channel smtp_port must be a number.",
                ) from exc
        return

    if channel_type in {"webhook", "dingtalk", "feishu", "wecom"}:
        url = config.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Webhook-like channel config requires an http or https 'url'.",
            )
        return

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported channel type.")


@router.post("", response_model=NotificationChannelRead)
def create_notification_channel(
    payload: NotificationChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannel:
    validate_channel_config(payload.channel_type, payload.config)
    channel = NotificationChannel(**payload.model_dump(), user_id=current_user.id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("", response_model=list[NotificationChannelRead])
def list_notification_channels(
    enabled: bool | None = Query(default=None),
    channel_type: str | None = Query(default=None, pattern="^(email|webhook|dingtalk|feishu|wecom)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationChannel]:
    query = db.query(NotificationChannel).filter(NotificationChannel.user_id == current_user.id, NotificationChannel.deleted_at.is_(None))
    if enabled is not None:
        query = query.filter(NotificationChannel.enabled == enabled)
    if channel_type:
        query = query.filter(NotificationChannel.channel_type == channel_type)
    return list(query.order_by(NotificationChannel.id.desc()).all())


@router.get("/{channel_id}", response_model=NotificationChannelRead)
def get_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannel:
    return get_owned_channel(channel_id, db, current_user)


@router.put("/{channel_id}", response_model=NotificationChannelRead)
def update_notification_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannel:
    channel = get_owned_channel(channel_id, db, current_user)
    update_data = payload.model_dump(exclude_unset=True)
    next_type = update_data.get("channel_type", channel.channel_type)
    next_config = update_data.get("config", channel.config)
    validate_channel_config(next_type, next_config)
    for field, value in update_data.items():
        setattr(channel, field, value)
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", response_model=MessageResponse)
def delete_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    channel = get_owned_channel(channel_id, db, current_user)
    channel.enabled = False
    channel.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return MessageResponse(message="Notification channel deleted")


@router.post("/{channel_id}/test", response_model=NotificationChannelTestResponse)
async def test_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannelTestResponse:
    channel = get_owned_channel(channel_id, db, current_user)
    validate_channel_config(channel.channel_type, channel.config)
    if not channel.enabled:
        return NotificationChannelTestResponse(
            channel_id=channel.id,
            channel_type=channel.channel_type,
            enabled=channel.enabled,
            ok=False,
            message="Notification channel is disabled.",
        )

    record = NotificationRecord(
        user_id=current_user.id,
        channel_id=channel.id,
        alert_event_id=0,
        notification_type="triggered",
        status="pending",
        title="测试通知：智能运维平台",
        content="这是一条测试通知。收到这封邮件或机器人消息，说明通知渠道可以真实发送。",
        payload={"test": True, "channel_type": channel.channel_type},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    sent_record = await send_notification_record(db, record)
    return NotificationChannelTestResponse(
        channel_id=channel.id,
        channel_type=channel.channel_type,
        enabled=channel.enabled,
        ok=sent_record.status == "sent",
        message=sent_record.error_message or f"Test notification status: {sent_record.status}",
    )
