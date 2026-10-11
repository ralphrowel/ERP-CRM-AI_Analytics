"""
Pydantic Schemas for Audit Logs & Activity Feed (Roadmap §V0.8)
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_user_id: int | None = None
    actor_name: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    changes: dict[str, Any] | None = None
    request_id: str | None = None
    ip_address: str | None = None


class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


class ActivityFeedItemResponse(BaseModel):
    id: str
    source: Literal["audit", "status", "activity"]
    timestamp: datetime
    actor_user_id: int | None = None
    actor_name: str | None = None
    action: str
    title: str
    description: str | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class PaginatedActivityFeedResponse(BaseModel):
    items: list[ActivityFeedItemResponse]
    total: int
    page: int
    page_size: int
