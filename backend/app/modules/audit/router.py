"""
FastAPI Router for Audit Log & Activity Feed (Roadmap §V0.8)
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.audit.schemas import (
    PaginatedActivityFeedResponse,
    PaginatedAuditLogResponse,
)
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit & Activity Feed"])


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("/logs", response_model=PaginatedAuditLogResponse)
def list_audit_logs(
    _: Annotated[ScopeContext, Depends(require("audit:read"))],
    service: Annotated[AuditService, Depends(get_audit_service)],
    actor_user_id: int | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedAuditLogResponse:
    items, total = service.list_audit_logs(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return PaginatedAuditLogResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/feed/{entity_type}/{entity_id}", response_model=PaginatedActivityFeedResponse)
def get_entity_activity_feed(
    entity_type: str,
    entity_id: int,
    _: Annotated[ScopeContext, Depends(require(None))],  # Any authenticated user
    service: Annotated[AuditService, Depends(get_audit_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedActivityFeedResponse:
    items, total = service.get_entity_activity_feed(
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedActivityFeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
