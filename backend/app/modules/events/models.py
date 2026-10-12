"""Event Outbox and Notification Models (Roadmap §V1.8)

Provides:
1. Transactional Outbox pattern for guaranteed at-least-once side-effect delivery.
2. User In-App Notification Ledger.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.identity.models import User

MAX_OUTBOX_ATTEMPTS = 8


class OutboxEvent(Base):
    """
    Transactional Outbox Table (Roadmap §V1.8).
    Written in the same atomic database transaction as operational state modifications.
    Polled and dispatched asynchronously by the background worker.
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_poll", "processed_at", "available_at", "attempts"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_processed(self) -> bool:
        return self.processed_at is not None

    @property
    def is_dead_letter(self) -> bool:
        return self.processed_at is None and self.attempts >= MAX_OUTBOX_ATTEMPTS

    @property
    def is_pending(self) -> bool:
        return self.processed_at is None and self.attempts < MAX_OUTBOX_ATTEMPTS


class Notification(Base):
    """
    User In-App Notification Record (Roadmap §V1.8).
    Created asynchronously by the worker handlers, never inside the HTTP request cycle.
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # 'inventory', 'sales', etc.
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
