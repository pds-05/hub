from string import Template

from sqlalchemy.orm import Session

from app.models.alert_event import AlertEvent
from app.models.notification_channel import NotificationChannel
from app.models.notification_record import NotificationRecord


def event_template_values(event: AlertEvent, notification_type: str) -> dict[str, str]:
    return {
        "id": str(event.id),
        "rule_name": event.rule_name,
        "level": event.level,
        "status": event.status,
        "notification_type": notification_type,
        "instance": event.instance,
        "metric": event.metric,
        "operator": event.operator,
        "value": str(event.value),
        "threshold": str(event.threshold),
        "message": event.message or "",
        "trigger_count": str(event.trigger_count),
    }


def render_template(template: str, values: dict[str, str]) -> str:
    try:
        return Template(template).safe_substitute(values)
    except ValueError:
        return template


def channel_allows_event(channel: NotificationChannel, event: AlertEvent, notification_type: str) -> bool:
    config = channel.config or {}
    if notification_type == "triggered" and config.get("notify_on_triggered", True) is False:
        return False
    if notification_type == "resolved" and config.get("notify_on_resolved", True) is False:
        return False

    levels = config.get("levels") or ["general", "severe", "urgent"]
    if isinstance(levels, str):
        levels = [levels]
    return event.level in levels


def build_notification_content(channel: NotificationChannel, event: AlertEvent, notification_type: str) -> tuple[str, str]:
    config = channel.config or {}
    values = event_template_values(event, notification_type)
    if notification_type == "resolved":
        title_template = config.get("resolved_title_template") or "告警已恢复：$rule_name"
        content_template = config.get("resolved_content_template") or (
            "实例：$instance\n指标：$metric\n最后值：$value\n等级：$level\n消息：$message"
        )
    else:
        title_template = config.get("title_template") or "告警触发：$rule_name"
        content_template = config.get("content_template") or (
            "实例：$instance\n指标：$metric\n条件：$value $operator $threshold\n等级：$level\n消息：$message"
        )
    return render_template(str(title_template), values), render_template(str(content_template), values)


def create_notification_records_for_event(
    db: Session,
    event: AlertEvent,
    notification_type: str,
) -> list[NotificationRecord]:
    channels = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.user_id == event.user_id, NotificationChannel.deleted_at.is_(None), NotificationChannel.enabled.is_(True))
        .all()
    )
    records: list[NotificationRecord] = []
    for channel in channels:
        if not channel_allows_event(channel, event, notification_type):
            continue

        existing = (
            db.query(NotificationRecord)
            .filter(
                NotificationRecord.user_id == event.user_id,
                NotificationRecord.channel_id == channel.id,
                NotificationRecord.alert_event_id == event.id,
                NotificationRecord.notification_type == notification_type,
            )
            .first()
        )
        if existing is not None:
            continue

        title, content = build_notification_content(channel, event, notification_type)
        record = NotificationRecord(
            user_id=event.user_id,
            channel_id=channel.id,
            alert_event_id=event.id,
            notification_type=notification_type,
            status="pending",
            title=title,
            content=content,
            payload={
                "channel_type": channel.channel_type,
                "channel_config": channel.config,
                "event": {
                    "id": event.id,
                    "rule_id": event.rule_id,
                    "rule_name": event.rule_name,
                    "level": event.level,
                    "status": event.status,
                    "instance": event.instance,
                    "metric": event.metric,
                    "operator": event.operator,
                    "value": event.value,
                    "threshold": event.threshold,
                    "message": event.message,
                    "trigger_count": event.trigger_count,
                },
            },
        )
        db.add(record)
        records.append(record)
    return records
