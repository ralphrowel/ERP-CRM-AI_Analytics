"""
Audit & Activity Feed Service (Roadmap §V0.8)
Provides unified querying across AuditLog, StatusHistory, and Activities,
plus explicit event recording for security and workflow operations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import get_clock
from app.core.status_history import StatusHistory
from app.modules.audit.context import get_audit_context
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import (
    ActivityFeedItemResponse,
    AuditLogResponse,
)
from app.modules.crm.models import Activity
from app.modules.identity.models import User


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    # ── Explicit Event Recorders ─────────────────────────────────────────────

    def record_event(
        self,
        action: str,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        changes: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Explicitly records an audit entry into the active database session."""
        clock = get_clock()
        ctx = get_audit_context()
        entry = AuditLog(
            occurred_at=occurred_at or clock.now(),
            actor_user_id=actor_user_id if actor_user_id is not None else ctx.actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            request_id=request_id or ctx.request_id,
            ip_address=ip_address or ctx.ip_address,
        )
        self.db.add(entry)
        return entry

    def record_security_event(
        self,
        action: str,  # 'login', 'login_failed', 'logout'
        actor_user_id: int | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Records authentication and session security events."""
        return self.record_event(
            action=action,
            actor_user_id=actor_user_id,
            entity_type="user",
            entity_id=actor_user_id,
            changes=details,
            request_id=request_id,
            ip_address=ip_address,
        )

    def record_permission_change(
        self,
        actor_user_id: int | None,
        role_id: int,
        changes: dict[str, Any],
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Records security role and permission policy updates."""
        return self.record_event(
            action="permission_change",
            actor_user_id=actor_user_id,
            entity_type="role",
            entity_id=role_id,
            changes=changes,
            request_id=request_id,
            ip_address=ip_address,
        )

    # ── Audit Log Querying ───────────────────────────────────────────────────

    def list_audit_logs(
        self,
        actor_user_id: int | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLogResponse], int]:
        stmt = select(AuditLog).options(joinedload(AuditLog.actor))

        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if date_from:
            stmt = stmt.where(AuditLog.occurred_at >= date_from)
        if date_to:
            stmt = stmt.where(AuditLog.occurred_at <= date_to)

        # Count total
        count_stmt = select(func.count(AuditLog.id))
        if actor_user_id is not None:
            count_stmt = count_stmt.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            count_stmt = count_stmt.where(AuditLog.action == action)
        if entity_type:
            count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            count_stmt = count_stmt.where(AuditLog.entity_id == entity_id)
        if date_from:
            count_stmt = count_stmt.where(AuditLog.occurred_at >= date_from)
        if date_to:
            count_stmt = count_stmt.where(AuditLog.occurred_at <= date_to)

        total = self.db.execute(count_stmt).scalar() or 0

        stmt = (
            stmt.order_by(AuditLog.occurred_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = self.db.execute(stmt).scalars().all()

        results = [
            AuditLogResponse(
                id=log.id,
                occurred_at=log.occurred_at,
                actor_user_id=log.actor_user_id,
                actor_name=log.actor.full_name
                if log.actor
                else ("System" if not log.actor_user_id else None),
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                changes=log.changes,
                request_id=log.request_id,
                ip_address=log.ip_address,
            )
            for log in items
        ]
        return results, total

    # ── Activity Feed (audit_log ∪ status_history ∪ activities) ─────────────

    def get_entity_activity_feed(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ActivityFeedItemResponse], int]:
        feed_items: list[ActivityFeedItemResponse] = []

        # 1. Audit Logs for entity
        audit_logs = (
            self.db.execute(
                select(AuditLog)
                .options(joinedload(AuditLog.actor))
                .where(
                    AuditLog.entity_type == entity_type,
                    AuditLog.entity_id == entity_id,
                )
            )
            .scalars()
            .all()
        )

        for a in audit_logs:
            title = f"Record {a.action.capitalize()}"
            if a.action == "update" and a.changes:
                changed_cols = ", ".join(a.changes.keys())
                title = f"Updated fields: {changed_cols}"

            feed_items.append(
                ActivityFeedItemResponse(
                    id=f"audit-{a.id}",
                    source="audit",
                    timestamp=a.occurred_at,
                    actor_user_id=a.actor_user_id,
                    actor_name=a.actor.full_name
                    if a.actor
                    else ("System" if not a.actor_user_id else None),
                    action=a.action,
                    title=title,
                    description=None,
                    changes=a.changes,
                    metadata={"request_id": a.request_id, "ip_address": a.ip_address},
                )
            )

        # 2. Status History for entity
        status_entries = (
            self.db.execute(
                select(StatusHistory).where(
                    StatusHistory.entity_type == entity_type,
                    StatusHistory.entity_id == entity_id,
                )
            )
            .scalars()
            .all()
        )

        # Lookup actor names for status history
        actor_ids = {s.changed_by for s in status_entries if s.changed_by}
        users_map: dict[int, str] = {}
        if actor_ids:
            users = self.db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all()
            users_map = {u.id: u.full_name for u in users}

        for s in status_entries:
            feed_items.append(
                ActivityFeedItemResponse(
                    id=f"status-{s.id}",
                    source="status",
                    timestamp=s.changed_at,
                    actor_user_id=s.changed_by,
                    actor_name=users_map.get(s.changed_by, "System" if not s.changed_by else None),
                    action="transition",
                    title=f"Status: {s.from_status or 'draft'} → {s.to_status}",
                    description=s.reason,
                    changes={"status": [s.from_status, s.to_status]},
                    metadata={"reason": s.reason},
                )
            )

        # 3. CRM Activities linked to entity (if entity is CRM-related)
        activity_filter = None
        if entity_type == "customer":
            activity_filter = Activity.customer_id == entity_id
        elif entity_type == "lead":
            activity_filter = Activity.lead_id == entity_id
        elif entity_type == "opportunity":
            activity_filter = Activity.opportunity_id == entity_id
        elif entity_type == "contact":
            activity_filter = Activity.contact_id == entity_id

        if activity_filter is not None:
            activities = self.db.execute(select(Activity).where(activity_filter)).scalars().all()
            act_user_ids = {act.owner_user_id for act in activities if act.owner_user_id}
            act_users_map: dict[int, str] = {}
            if act_user_ids:
                u_list = (
                    self.db.execute(select(User).where(User.id.in_(act_user_ids))).scalars().all()
                )
                act_users_map = {u.id: u.full_name for u in u_list}

            for act in activities:
                feed_items.append(
                    ActivityFeedItemResponse(
                        id=f"activity-{act.id}",
                        source="activity",
                        timestamp=act.created_at,
                        actor_user_id=act.owner_user_id,
                        actor_name=act_users_map.get(act.owner_user_id),
                        action=act.activity_type,
                        title=f"{act.activity_type.capitalize()}: {act.subject}",
                        description=act.body,
                        changes=None,
                        metadata={
                            "due_at": act.due_at.isoformat() if act.due_at else None,
                            "completed_at": act.completed_at.isoformat()
                            if act.completed_at
                            else None,
                        },
                    )
                )

        # Sort all items by timestamp descending
        feed_items.sort(key=lambda x: x.timestamp, reverse=True)
        total = len(feed_items)

        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_items = feed_items[start_idx:end_idx]

        return paged_items, total
