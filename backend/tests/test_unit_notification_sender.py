from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.notification_record import NotificationRecord
from app.schemas.notification_record import NotificationRecordRead
from app.services.notification_sender import send_email_notification


def test_notification_record_allows_test_notification_without_alert_event() -> None:
    assert NotificationRecord.__table__.c.alert_event_id.nullable is True


def test_test_email_labels_missing_alert_event() -> None:
    channel = MagicMock()
    channel.config = {
        "to": "recipient@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "smtp_username": "sender@example.com",
        "smtp_password": "authorization-code",
        "use_ssl": True,
    }
    record = MagicMock()
    record.title = "测试通知"
    record.content = "测试内容"
    record.notification_type = "triggered"
    record.id = 1
    record.alert_event_id = None

    smtp = MagicMock()
    with patch("app.services.notification_sender.smtplib.SMTP_SSL") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = smtp
        send_email_notification(channel, record)

    message = smtp.send_message.call_args.args[0]
    assert "告警事件 ID：测试通知" in message.get_content()


def test_notification_read_allows_missing_alert_event() -> None:
    record = NotificationRecordRead(
        id=1,
        user_id=1,
        channel_id=1,
        alert_event_id=None,
        notification_type='triggered',
        status='pending',
        title='测试通知',
        content='测试内容',
        payload={},
        error_message=None,
        created_at=datetime.now(timezone.utc),
        sent_at=None,
    )
    assert record.alert_event_id is None
