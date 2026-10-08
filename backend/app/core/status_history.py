from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.clock import Clock, get_clock
from app.core.database import Base


class StatusHistory(Base):
    """
    Centralized status transition history log (Roadmap §4.6 & ADR-0007).
    Tracks every state machine transition for leads, opportunities, customers, quotes, orders, and invoices.
    """

    __tablename__ = "status_history"
    __table_args__ = (Index("ix_status_history_lookup", "entity_type", "entity_id", "changed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def record_status_change(
    db: Session,
    entity_type: str,
    entity_id: int,
    to_status: str,
    from_status: str | None = None,
    reason: str | None = None,
    changed_by: int | None = None,
    clock: Clock | None = None,
) -> StatusHistory:
    """
    Records a state transition inside the caller's active database transaction.
    """
    current_clock = clock or get_clock()
    history = StatusHistory(
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        changed_by=changed_by,
        changed_at=current_clock.now(),
    )
    db.add(history)
    return history


def get_entity_history(
    db: Session,
    entity_type: str,
    entity_id: int,
) -> list[StatusHistory]:
    """Retrieves chronological transition history for an entity."""
    stmt = (
        select(StatusHistory)
        .where(
            StatusHistory.entity_type == entity_type,
            StatusHistory.entity_id == entity_id,
        )
        .order_by(StatusHistory.changed_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
