from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin
from app.modules.identity.models import User


class ApprovalRule(Base, AuditMixin, VersionMixin):
    """
    Configurable approval rules and thresholds (Roadmap V0.7 §4.7).
    Stored in DB so operational thresholds can be configured dynamically without redeployments.
    """

    __tablename__ = "approval_rules"
    __table_args__ = (
        CheckConstraint(
            "threshold_amount IS NOT NULL OR threshold_pct IS NOT NULL OR approver_permission IS NOT NULL",
            name="ck_approval_rules_has_condition",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)
    threshold_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    approver_permission: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    requests: Mapped[list["ApprovalRequest"]] = relationship(
        "ApprovalRequest", back_populates="rule", cascade="all, delete-orphan"
    )


class ApprovalRequest(Base):
    """
    Instance of an approval workflow request for an entity transition.
    Enforces strict separation of duties: requester cannot decide their own approval request.
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_requests_status",
        ),
        CheckConstraint(
            "decided_by IS NULL OR decided_by <> requested_by",
            name="ck_approval_requests_separation_of_duties",
        ),
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
        Index("ix_approval_requests_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("approval_rules.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    requested_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    rule: Mapped[ApprovalRule] = relationship("ApprovalRule", back_populates="requests")
    requester: Mapped[User] = relationship("User", foreign_keys=[requested_by])
    decider: Mapped[User | None] = relationship("User", foreign_keys=[decided_by])
