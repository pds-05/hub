from datetime import datetime

from pydantic import BaseModel, Field


class NotificationRecordRead(BaseModel):
    id: int
    user_id: int
    channel_id: int
    alert_event_id: int | None
    notification_type: str
    status: str
    title: str
    content: str
    payload: dict
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationRecordUpdateStatus(BaseModel):
    status: str = Field(pattern="^(pending|sent|failed|skipped)$")
    error_message: str | None = None

class NotificationSendPendingResponse(BaseModel):
    total: int
    sent: int
    failed: int
    skipped: int
    records: list[NotificationRecordRead]


