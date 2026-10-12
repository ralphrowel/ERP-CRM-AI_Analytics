"""FastAPI Router for Notifications & Event Automation (Roadmap §V1.8)

Mounted under:
- /api/v1/notifications (User in-app notifications)
- /api/v1/events (Outbox dead-letter queue & scheduled checks)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenException
from app.modules.events.scheduler import ScheduledChecksEngine
from app.modules.events.schemas import (
    DeadLetterListResponse,
    NotificationListResponse,
    NotificationOut,
    OutboxEventOut,
    UnreadCountResponse,
)
from app.modules.events.service import NotificationService, OutboxService
from app.modules.identity.dependencies import get_current_user_and_session
from app.modules.identity.models import User, UserSession

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])
events_router = APIRouter(prefix="/events", tags=["Events & Outbox"])


# ── Notifications Endpoints ───────────────────────────────────────────────────


@notifications_router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
)
def list_my_notifications(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
    unread_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationListResponse:
    """Lists notifications for the current authenticated user."""
    user, _ = auth
    items, total, unread_count = NotificationService.list_notifications(
        db=db,
        user_id=user.id,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )
    return NotificationListResponse(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


@notifications_router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
)
def get_my_unread_count(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
) -> UnreadCountResponse:
    """Returns total unread notification count for notification badge."""
    user, _ = auth
    count = NotificationService.get_unread_count(db=db, user_id=user.id)
    return UnreadCountResponse(unread_count=count)


@notifications_router.patch(
    "/{notification_id}/read",
    response_model=NotificationOut,
    status_code=status.HTTP_200_OK,
)
def mark_notification_as_read(
    notification_id: int,
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationOut:
    """Marks a single notification as read."""
    user, _ = auth
    notif = NotificationService.mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=user.id,
    )
    return NotificationOut.model_validate(notif)


@notifications_router.post(
    "/mark-all-read",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
)
def mark_all_notifications_as_read(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    """Marks all user notifications as read."""
    user, _ = auth
    updated_count = NotificationService.mark_all_read(db=db, user_id=user.id)
    return {"marked_read": updated_count}


# ── Events & Outbox Monitoring Endpoints (Admin / Superuser) ──────────────────


@events_router.get(
    "/dead-letter",
    response_model=DeadLetterListResponse,
    status_code=status.HTTP_200_OK,
)
def list_dead_letter_events(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DeadLetterListResponse:
    """Lists dead-letter events that failed after maximum retry attempts."""
    user, _ = auth
    if not user.is_superuser:
        raise ForbiddenException(detail="Administrator access required for dead-letter queue.")

    events, total = OutboxService.list_dead_letters(db=db, page=page, page_size=page_size)
    return DeadLetterListResponse(
        items=[OutboxEventOut.model_validate(e) for e in events],
        total=total,
    )


@events_router.post(
    "/{event_id}/retry",
    response_model=OutboxEventOut,
    status_code=status.HTTP_200_OK,
)
def retry_dead_letter_event(
    event_id: int,
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
) -> OutboxEventOut:
    """Resets attempts for a dead-letter event to allow worker reprocessing."""
    user, _ = auth
    if not user.is_superuser:
        raise ForbiddenException(detail="Administrator access required to retry events.")

    event = OutboxService.retry_dead_letter(db=db, event_id=event_id)
    return OutboxEventOut.model_validate(event)


@events_router.post(
    "/run-scheduled-checks",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
)
def run_scheduled_checks(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    """Manually triggers scheduled daily business rule checks."""
    user, _ = auth
    if not user.is_superuser:
        raise ForbiddenException(detail="Administrator access required.")

    return ScheduledChecksEngine.run_all_scheduled_checks(db=db)
