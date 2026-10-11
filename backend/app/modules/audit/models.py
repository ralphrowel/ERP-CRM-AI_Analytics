"""
Audit Log Model (Roadmap §V0.8)
Tamper-resistant append-only audit trail capturing state modifications,
security events, state machine transitions, and permission changes.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.identity.models import User

AUDIT_ACTIONS = (
    "create",
    "update",
    "transition",
    "login",
    "login_failed",
    "logout",
    "permission_change",
    "export",
    "ai_tool_call",
)


class AuditLog(Base):
    """
    Append-only audit ledger (Roadmap V0.8).
    Captures field-level before/after diffs and system/security actions.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            f"action IN {AUDIT_ACTIONS}",
            name="ck_audit_log_action",
        ),
        Index("ix_audit_log_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_log_actor", "actor_user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # {"credit_limit": ["50000.00", "80000.00"]}
    changes: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(
        String(45).with_variant(INET, "postgresql"), nullable=True
    )

    # Relationships
    actor: Mapped["User | None"] = relationship("User", foreign_keys=[actor_user_id])
