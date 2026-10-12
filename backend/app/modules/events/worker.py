"""Outbox Background Worker (Roadmap §V1.8)

Poller and dispatcher:
- Polls outbox_events with SELECT ... FOR UPDATE SKIP LOCKED (Postgres)
- Executes idempotent handlers with exponential backoff retry
- Marks dead-letter state after 8 failed attempts
- Guaranteed crash-recovery: mid-processing termination loses no events
"""

import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.core.database import SessionLocal
from app.modules.events.handlers import EVENT_HANDLER_REGISTRY
from app.modules.events.mailer import EmailDispatcher
from app.modules.events.models import MAX_OUTBOX_ATTEMPTS, OutboxEvent

logger = logging.getLogger("app.modules.events.worker")


class OutboxWorker:
    """Processes pending transactional outbox events with exponential backoff."""

    def __init__(
        self,
        db_factory: Any = SessionLocal,
        mailer: EmailDispatcher | None = None,
        max_attempts: int = MAX_OUTBOX_ATTEMPTS,
    ):
        self.db_factory = db_factory
        self.mailer = mailer or EmailDispatcher()
        self.max_attempts = max_attempts

    def process_batch(self, batch_size: int = 50) -> int:
        """
        Polls and executes a batch of pending events.
        Returns count of successfully processed events.
        """
        clock = get_clock()
        now = clock.now()
        processed_count = 0

        db = self.db_factory() if callable(self.db_factory) else self.db_factory
        try:
            # 1. Poll eligible pending events
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.processed_at.is_(None),
                    OutboxEvent.available_at <= now,
                    OutboxEvent.attempts < self.max_attempts,
                )
                .order_by(OutboxEvent.available_at.asc())
                .limit(batch_size)
            )

            # Apply SKIP LOCKED on PostgreSQL engines for concurrent worker safety
            if db.bind and db.bind.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)

            events = list(db.execute(stmt).scalars().all())
            if not events:
                return 0

            # 2. Process each event with isolated transaction semantics
            for event in events:
                success = self._process_single_event(db, event.id)
                if success:
                    processed_count += 1
        finally:
            if self.db_factory == SessionLocal and hasattr(db, "close"):
                db.close()

        return processed_count

    def _process_single_event(self, db: Session, event_id: int) -> bool:
        """Executes handler for an event, tracking retries and errors."""
        clock = get_clock()
        now = clock.now()

        event = db.get(OutboxEvent, event_id)
        if not event or event.processed_at is not None or event.attempts >= self.max_attempts:
            return False

        handler = EVENT_HANDLER_REGISTRY.get(event.event_type)
        if not handler:
            # Unknown event type: record error and mark dead letter
            event.attempts = self.max_attempts
            event.last_error = f"No registered handler for event_type '{event.event_type}'."
            db.commit()
            return False

        try:
            # Execute handler within atomic subtransaction
            handler(db, event, self.mailer)
            event.processed_at = clock.now()
            event.last_error = None
            db.commit()
            logger.info("Successfully processed outbox event %d (%s)", event.id, event.event_type)
            return True
        except Exception as exc:
            db.rollback()
            # Reload event after rollback to update attempt and error state
            event = db.get(OutboxEvent, event_id)
            if not event:
                return False

            event.attempts += 1
            event.last_error = f"{type(exc).__name__}: {str(exc)}"

            if event.attempts < self.max_attempts:
                # Exponential backoff: 2s, 4s, 8s, 16s, 32s, 64s, 128s...
                backoff_sec = min(2**event.attempts, 3600)
                event.available_at = now + timedelta(seconds=backoff_sec)
                logger.warning(
                    "Outbox event %d (%s) failed attempt %d/%d; retrying in %ds: %s",
                    event.id,
                    event.event_type,
                    event.attempts,
                    self.max_attempts,
                    backoff_sec,
                    exc,
                )
            else:
                logger.error(
                    "Outbox event %d (%s) reached max attempts (%d); marked as DEAD-LETTER: %s",
                    event.id,
                    event.event_type,
                    self.max_attempts,
                    exc,
                )

            db.commit()
            return False

    def run_forever(self, poll_interval: float = 1.0, max_iterations: int | None = None) -> None:
        """Daemon worker loop."""
        iteration = 0
        logger.info("Starting OutboxWorker daemon...")
        while True:
            if max_iterations is not None and iteration >= max_iterations:
                break
            try:
                processed = self.process_batch()
                if processed == 0:
                    time.sleep(poll_interval)
            except Exception as exc:
                logger.error("Outbox worker loop error: %s", exc)
                time.sleep(poll_interval)
            iteration += 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    worker = OutboxWorker()
    worker.run_forever()
