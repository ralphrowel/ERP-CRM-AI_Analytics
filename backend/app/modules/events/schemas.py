"""Pydantic schemas for Events, Outbox, and Notifications (Roadmap §V1.8)"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OutboxEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    aggregate_type: str
    aggregate_id: int
    payload: dict[str, Any]
    occurred_at: datetime
    available_at: datetime
    processed_at: datetime | None = None
    attempts: int
    last_error: str | None = None
    is_dead_letter: bool


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    message: str
    category: str
    entity_type: str | None = None
    entity_id: int | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class DeadLetterListResponse(BaseModel):
    items: list[OutboxEventOut]
    total: int
