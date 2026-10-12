"""Events & Notifications Domain Service (Roadmap §V1.8)"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.core.errors import NotFoundException
from app.modules.events.models import MAX_OUTBOX_ATTEMPTS, Notification, OutboxEvent


class OutboxService:
    """Manages transactional outbox ledger entries."""

    @staticmethod
    def record_event(
        db: Session,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int,
        payload: dict[str, Any],
        available_at: datetime | None = None,
    ) -> OutboxEvent:
        """
        Inserts an event into the outbox ledger within the active database transaction.
        Strict Invariant: No network calls (SMTP, webhooks, push notifications) occur here.
        """
        clock = get_clock()
        now = clock.now()
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=now,
            available_at=available_at or now,
            attempts=0,
            last_error=None,
        )
        db.add(event)
        return event

    @staticmethod
    def list_dead_letters(
        db: Session, page: int = 1, page_size: int = 50
    ) -> tuple[list[OutboxEvent], int]:
        """Queries events that failed processing after reaching maximum attempts."""
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.processed_at.is_(None),
                OutboxEvent.attempts >= MAX_OUTBOX_ATTEMPTS,
            )
            .order_by(OutboxEvent.id.desc())
        )
        count_stmt = select(func.count(OutboxEvent.id)).where(
            OutboxEvent.processed_at.is_(None),
            OutboxEvent.attempts >= MAX_OUTBOX_ATTEMPTS,
        )
        total = db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        events = list(db.execute(stmt.offset(offset).limit(page_size)).scalars().all())
        return events, total

    @staticmethod
    def retry_dead_letter(db: Session, event_id: int) -> OutboxEvent:
        """Resets a dead-letter event to allow worker reprocessing."""
        clock = get_clock()
        event = db.get(OutboxEvent, event_id)
        if not event:
            raise NotFoundException(detail="Outbox event not found.")
        event.attempts = 0
        event.last_error = None
        event.available_at = clock.now()
        event.processed_at = None
        db.commit()
        db.refresh(event)
        return event


class NotificationService:
    """Manages user in-app notifications with deduplication guarantees."""

    @staticmethod
    def create_notification(
        db: Session,
        user_id: int,
        title: str,
        message: str,
        category: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> Notification:
        """
        Creates an in-app notification idempotently.
        Deduplicates if the same unread notification already exists for the entity.
        """
        clock = get_clock()
        now = clock.now()

        # Check existing unread duplicate for this entity
        if entity_type and entity_id:
            existing = db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.entity_type == entity_type,
                    Notification.entity_id == entity_id,
                    Notification.category == category,
                    Notification.title == title,
                    Notification.is_read.is_(False),
                )
            ).scalar_one_or_none()
            if existing:
                return existing

        notif = Notification(
            user_id=user_id,
            title=title.strip(),
            message=message.strip(),
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            is_read=False,
            created_at=now,
        )
        db.add(notif)
        db.flush()
        return notif

    @staticmethod
    def list_notifications(
        db: Session,
        user_id: int,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int, int]:
        """Lists notifications for a user, returning (items, total, unread_count)."""
        base_stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            base_stmt = base_stmt.where(Notification.is_read.is_(False))

        count_stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        if unread_only:
            count_stmt = count_stmt.where(Notification.is_read.is_(False))

        unread_stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )

        total = db.execute(count_stmt).scalar_one()
        unread_count = db.execute(unread_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            db.execute(
                base_stmt.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total, unread_count

    @staticmethod
    def get_unread_count(db: Session, user_id: int) -> int:
        """Returns total unread notification count for user."""
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        return db.execute(stmt).scalar_one()

    @staticmethod
    def mark_as_read(db: Session, notification_id: int, user_id: int) -> Notification:
        """Marks a notification as read."""
        clock = get_clock()
        notif = db.get(Notification, notification_id)
        if not notif or notif.user_id != user_id:
            raise NotFoundException(detail="Notification not found.")
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = clock.now()
            db.commit()
            db.refresh(notif)
        return notif

    @staticmethod
    def mark_all_read(db: Session, user_id: int) -> int:
        """Marks all unread notifications as read for user."""
        clock = get_clock()
        now = clock.now()
        stmt = select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        unread = list(db.execute(stmt).scalars().all())
        for n in unread:
            n.is_read = True
            n.read_at = now
        db.commit()
        return len(unread)
