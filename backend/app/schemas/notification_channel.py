from datetime import datetime

from pydantic import BaseModel, Field


class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    channel_type: str = Field(pattern="^(email|webhook|dingtalk|feishu|wecom)$")
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    description: str | None = None


class NotificationChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    channel_type: str | None = Field(default=None, pattern="^(email|webhook|dingtalk|feishu|wecom)$")
    config: dict | None = None
    enabled: bool | None = None
    description: str | None = None


class NotificationChannelRead(BaseModel):
    id: int
    user_id: int
    name: str
    channel_type: str
    config: dict
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationChannelTestResponse(BaseModel):
    channel_id: int
    channel_type: str
    enabled: bool
    ok: bool
    message: str
