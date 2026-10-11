"""
SQLAlchemy Session Event Listener for Automatic Audit Logging (Roadmap §V0.8)
Captures attribute-level diffs on dirty entities before flush within the same transaction.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.modules.audit.context import get_audit_context, sanitize_ip_address
from app.modules.audit.models import AuditLog

# Fields that must never be recorded in audit logs
EXCLUDED_FIELDS = {
    "password_hash",
    "token_hash",
    "csrf_token_hash",
    "updated_at",
    "version",
    "created_at",
}

# Tables that are excluded from automatic attribute diff logging
EXCLUDED_MODELS = {
    "AuditLog",
    "UserSession",
    "StatusHistory",
    "DocumentSequence",
    "IdempotencyKey",
    "EtlRun",
    "EtlWatermark",
}


def serialize_value(val: Any) -> Any:
    """Serializes Python objects (Decimal, datetime, date) into JSON-compatible values."""
    if val is None:
        return None
    if isinstance(val, (Decimal, float)):
        return str(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, bytes):
        return "<binary>"
    return val


def audit_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """
    SQLAlchemy before_flush hook.
    Inspects dirty entities, computes before/after diffs, and appends AuditLog records.
    """
    if session.info.get("skip_audit"):
        return

    audit_entries: list[AuditLog] = []
    clock = get_clock()
    ctx = get_audit_context()
    now = clock.now()

    # 1. Capture Dirty / Updated Entities
    for obj in session.dirty:
        model_name = obj.__class__.__name__
        if model_name in EXCLUDED_MODELS or model_name.startswith("Etl"):
            continue

        table = getattr(obj, "__table__", None)
        if table is not None and getattr(table, "schema", None) in (
            "etl",
            "raw",
            "staging",
            "dq",
            "mart",
        ):
            continue

        insp = inspect(obj)
        if not insp.has_identity:
            continue

        changes: dict[str, list[Any]] = {}
        for attr in insp.attrs:
            if attr.key in EXCLUDED_FIELDS:
                continue

            hist = attr.history
            if hist.has_changes():
                old_val = hist.deleted[0] if hist.deleted else None
                new_val = hist.added[0] if hist.added else None

                # If entity is persistent in DB and attribute was modified from expired state,
                # hist.deleted may be empty. Query the persisted value without triggering autoflush.
                if old_val is None and insp.persistent and insp.identity:
                    col = getattr(type(obj), attr.key, None)
                    if col is not None:
                        try:
                            from sqlalchemy import select

                            with session.no_autoflush:
                                pk_col = getattr(type(obj), "id", None)
                                if pk_col is not None:
                                    old_val = session.execute(
                                        select(col).where(pk_col == insp.identity[0])
                                    ).scalar()
                        except Exception:
                            pass

                # Normalize compare
                if old_val != new_val:
                    changes[attr.key] = [
                        serialize_value(old_val),
                        serialize_value(new_val),
                    ]

        if changes:
            table_name = getattr(obj, "__tablename__", model_name.lower())
            # Convert plural table names to singular entity_type if appropriate
            entity_type = (
                table_name.rstrip("s")
                if table_name.endswith("s") and not table_name.endswith("ss")
                else table_name
            )
            entity_id = getattr(obj, "id", None)

            # Determine actor: prioritize context, fallback to updated_by
            actor_id = ctx.actor_user_id or getattr(obj, "updated_by", None)
            if actor_id is not None:
                try:
                    from app.modules.identity.models import User

                    with session.no_autoflush:
                        if not session.get(User, actor_id):
                            actor_id = None
                except Exception:
                    pass

            entry = AuditLog(
                occurred_at=now,
                actor_user_id=actor_id,
                action="update",
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
                request_id=ctx.request_id,
                ip_address=sanitize_ip_address(ctx.ip_address),
            )

            audit_entries.append(entry)

    # 2. Add all audit records to current session so they commit atomically
    for entry in audit_entries:
        session.add(entry)


_listener_registered = False


def register_audit_listener(session_factory_or_engine: Any) -> None:
    """Registers the before_flush listener onto a Session class or SessionLocal."""
    global _listener_registered
    if _listener_registered:
        return
    event.listen(Session, "before_flush", audit_before_flush)
    _listener_registered = True
