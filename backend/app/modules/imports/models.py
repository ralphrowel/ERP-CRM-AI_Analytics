"""
Import Staging & Batch Models (Roadmap §V1.0)
Captures uploaded CSV rows into raw TEXT staging tables with row-level validation.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.catalog.models import Product
    from app.modules.crm.models import Contact, Customer
    from app.modules.identity.models import User

BATCH_STATUSES = ("uploaded", "validated", "committed", "failed", "cancelled")
ENTITY_TYPES = ("customer", "product", "contact")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            f"entity_type IN {ENTITY_TYPES}",
            name="ck_import_batches_entity_type",
        ),
        CheckConstraint(
            f"status IN {BATCH_STATUSES}",
            name="ck_import_batches_status",
        ),
        Index("ix_import_batches_entity_type", "entity_type"),
        Index("ix_import_batches_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    uploader: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by])
    staging_customers: Mapped[list["ImportStagingCustomer"]] = relationship(
        "ImportStagingCustomer", back_populates="batch", cascade="all, delete-orphan"
    )
    staging_products: Mapped[list["ImportStagingProduct"]] = relationship(
        "ImportStagingProduct", back_populates="batch", cascade="all, delete-orphan"
    )
    staging_contacts: Mapped[list["ImportStagingContact"]] = relationship(
        "ImportStagingContact", back_populates="batch", cascade="all, delete-orphan"
    )


class ImportStagingCustomer(Base):
    __tablename__ = "import_staging_customers"
    __table_args__ = (Index("ix_import_staging_customers_batch_id", "batch_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    tin: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    province: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_limit: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    committed_customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="staging_customers")
    committed_customer: Mapped["Customer | None"] = relationship(
        "Customer", foreign_keys=[committed_customer_id]
    )


class ImportStagingProduct(Base):
    __tablename__ = "import_staging_products"
    __table_args__ = (Index("ix_import_staging_products_batch_id", "batch_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    sku: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    uom: Mapped[str | None] = mapped_column(Text, nullable=True)
    list_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    reorder_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_rate_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    committed_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="staging_products")
    committed_product: Mapped["Product | None"] = relationship(
        "Product", foreign_keys=[committed_product_id]
    )


class ImportStagingContact(Base):
    __tablename__ = "import_staging_contacts"
    __table_args__ = (Index("ix_import_staging_contacts_batch_id", "batch_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    committed_contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="staging_contacts")
    committed_contact: Mapped["Contact | None"] = relationship(
        "Contact", foreign_keys=[committed_contact_id]
    )
