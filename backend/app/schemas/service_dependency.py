from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DependencyType = Literal["runtime", "data", "network", "deployment"]


class ServiceDependencyCreate(BaseModel):
    source_target_id: int = Field(gt=0)
    destination_target_id: int = Field(gt=0)
    dependency_type: DependencyType = "runtime"
    description: str | None = Field(default=None, max_length=1000)


class ServiceDependencyRead(BaseModel):
    id: int
    source_target_id: int
    destination_target_id: int
    dependency_type: DependencyType
    description: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}