from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import AuditMixin, Base, VersionMixin


class Customer(Base, AuditMixin, VersionMixin):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("customer_type IN ('company', 'individual')", name="ck_customers_type"),
        CheckConstraint("status IN ('prospect', 'active', 'inactive')", name="ck_customers_status"),
        CheckConstraint("payment_terms_days >= 0", name="ck_customers_payment_terms_positive"),
        CheckConstraint(
            "credit_limit IS NULL OR credit_limit >= 0",
            name="ck_customers_credit_limit_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_no: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, default="company")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    tin: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(19, 2), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    addresses: Mapped[list["CustomerAddress"]] = relationship(
        "CustomerAddress", back_populates="customer", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact", back_populates="customer", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(
        "Opportunity", back_populates="customer"
    )


class CustomerAddress(Base, AuditMixin):
    __tablename__ = "customer_addresses"
    __table_args__ = (
        CheckConstraint(
            "address_type IN ('billing', 'shipping')", name="ck_customer_addresses_type"
        ),
        Index(
            "uq_customer_default_address_per_type",
            "customer_id",
            "address_type",
            unique=True,
            postgresql_where=("is_default AND is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address_type: Mapped[str] = mapped_column(String(20), nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barangay: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="PH")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customer: Mapped[Customer] = relationship("Customer", back_populates="addresses")


class Contact(Base, AuditMixin, VersionMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        Index(
            "uq_customer_primary_contact",
            "customer_id",
            unique=True,
            postgresql_where=("is_primary AND is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customer: Mapped[Customer] = relationship("Customer", back_populates="contacts")


class Lead(Base, AuditMixin, VersionMixin):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "source IN ('website', 'referral', 'event', 'cold_call', 'social', 'import', 'other')",
            name="ck_leads_source",
        ),
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'disqualified', 'converted')",
            name="ck_leads_status",
        ),
        CheckConstraint(
            "status <> 'converted' OR (converted_at IS NOT NULL AND converted_customer_id IS NOT NULL)",
            name="ck_leads_converted_consistency",
        ),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_leads_has_contact_info"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lead_no: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="website")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new")
    disqualified_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    converted_contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    converted_opportunity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Opportunity(Base, AuditMixin, VersionMixin):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('discovery', 'proposal', 'negotiation', 'won', 'lost')",
            name="ck_opportunities_stage",
        ),
        CheckConstraint("estimated_amount >= 0", name="ck_opportunities_estimated_amount_positive"),
        CheckConstraint("probability BETWEEN 0 AND 1", name="ck_opportunities_probability_range"),
        CheckConstraint(
            "(stage IN ('won', 'lost')) = (closed_at IS NOT NULL)",
            name="ck_opportunities_closed_at_consistent",
        ),
        CheckConstraint(
            "stage <> 'lost' OR lost_reason IS NOT NULL",
            name="ck_opportunities_lost_reason_required",
        ),
        CheckConstraint(
            "lost_reason IS NULL OR lost_reason IN ('price', 'competitor', 'no_budget', 'no_decision', 'timing', 'other')",
            name="ck_opportunities_lost_reason_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    opportunity_no: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    primary_contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="discovery")
    estimated_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, default=Decimal("0.00")
    )
    probability: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.2000")
    )
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_lead_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="opportunities")
    primary_contact: Mapped[Contact | None] = relationship("Contact")


class Activity(Base, AuditMixin):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('call', 'email', 'meeting', 'task', 'note')",
            name="ck_activities_type",
        ),
        CheckConstraint(
            "num_nonnulls(lead_id, customer_id, contact_id, opportunity_id) >= 1",
            name="ck_activities_at_least_one_relation",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    lead_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True
    )
