from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.notification_channel import NotificationChannel
from app.models.notification_record import NotificationRecord


def config_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def send_email_notification(channel: NotificationChannel, record: NotificationRecord) -> None:
    settings = get_settings()
    config = channel.config or {}
    smtp_host = config.get("smtp_host") or settings.smtp_host
    smtp_port = int(config.get("smtp_port") or settings.smtp_port)
    smtp_username = config.get("smtp_username") or settings.smtp_username
    smtp_password = config.get("smtp_password") or settings.smtp_password
    from_email = config.get("from_email") or settings.smtp_from_email or smtp_username
    use_tls = config_bool(config.get("use_tls"), settings.smtp_use_tls)
    use_ssl = config_bool(config.get("use_ssl"), smtp_port == 465)
    to_address = config.get("to")

    if not smtp_host:
        raise ValueError("SMTP host is not configured. Please configure smtp_host in this email channel or SMTP_HOST in backend env.")
    if not from_email:
        raise ValueError("SMTP from email is not configured. Please configure from_email or smtp_username.")
    if not isinstance(to_address, str) or "@" not in to_address:
        raise ValueError("Email recipient is invalid.")

    message = EmailMessage()
    message["Subject"] = record.title
    message["From"] = from_email
    message["To"] = to_address
    message.set_content(
        f"{record.content}\n\n"
        f"---\n"
        f"通知类型：{record.notification_type}\n"
        f"通知记录 ID：{record.id}\n"
        f"告警事件 ID：{record.alert_event_id}\n"
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(smtp_host, smtp_port, timeout=15) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if smtp_username:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def build_webhook_body(channel: NotificationChannel, record: NotificationRecord) -> dict:
    provider = str(channel.config.get("provider") or channel.channel_type or "generic").lower()
    markdown = f"### {record.title}\n\n{record.content}"
    if provider in {"wecom", "wechat_work", "enterprise_wechat"}:
        return {"msgtype": "markdown", "markdown": {"content": markdown}}
    if provider == "dingtalk":
        return {"msgtype": "markdown", "markdown": {"title": record.title, "text": markdown}}
    if provider == "feishu":
        return {"msg_type": "text", "content": {"text": f"{record.title}\n\n{record.content}"}}
    return {
        "title": record.title,
        "content": record.content,
        "notification_type": record.notification_type,
        "payload": record.payload,
    }


async def send_notification_record(db: Session, record: NotificationRecord) -> NotificationRecord:
    channel = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.id == record.channel_id, NotificationChannel.user_id == record.user_id, NotificationChannel.deleted_at.is_(None))
        .first()
    )
    if channel is None:
        record.status = "failed"
        record.error_message = "Notification channel not found."
        db.commit()
        db.refresh(record)
        return record

    if not channel.enabled:
        record.status = "skipped"
        record.error_message = "Notification channel is disabled."
        db.commit()
        db.refresh(record)
        return record

    if channel.channel_type == "email":
        try:
            send_email_notification(channel, record)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            record.status = "failed"
            record.error_message = str(exc)
            db.commit()
            db.refresh(record)
            return record
        record.status = "sent"
        record.error_message = None
        record.sent_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record

    if channel.channel_type not in {"webhook", "dingtalk", "feishu", "wecom"}:
        record.status = "failed"
        record.error_message = f"Unsupported notification channel type: {channel.channel_type}."
        db.commit()
        db.refresh(record)
        return record

    url = channel.config.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        record.status = "failed"
        record.error_message = "Webhook url is invalid."
        db.commit()
        db.refresh(record)
        return record

    body = build_webhook_body(channel, record)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        record.status = "failed"
        record.error_message = str(exc)
        db.commit()
        db.refresh(record)
        return record

    record.status = "sent"
    record.error_message = None
    record.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record
