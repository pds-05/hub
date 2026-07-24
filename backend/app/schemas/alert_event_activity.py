from datetime import datetime

from pydantic import BaseModel, Field


class AlertEventActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AlertEventActivityCreate(BaseModel):
    action: str = Field(pattern="^(note|ack|resolve|status)$")
    note: str | None = Field(default=None, max_length=1000)


class AlertEventActivityRead(BaseModel):
    id: int
    user_id: int
    event_id: int
    action: str
    note: str | None
    actor: str
    created_at: datetime

    model_config = {"from_attributes": True}

