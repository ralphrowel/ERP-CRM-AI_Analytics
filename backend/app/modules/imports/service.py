"""
Import Service (Roadmap §V1.0)
Orchestrates CSV upload into raw TEXT staging tables, row-level validation,
and partial commit execution into operational ERP domain services.
"""

import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.errors import BadRequestException, NotFoundException
from app.modules.catalog.models import Product
from app.modules.catalog.schemas import ProductCreate
from app.modules.catalog.service import CatalogService
from app.modules.crm.models import Customer
from app.modules.crm.schemas import ContactCreate, CustomerAddressCreate, CustomerCreate
from app.modules.crm.service import CRMService
from app.modules.imports.models import (
    ImportBatch,
    ImportStagingContact,
    ImportStagingCustomer,
    ImportStagingProduct,
)
from app.modules.sales.models import TaxRate

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_currency_or_decimal(val: str | None) -> Decimal | None:
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    # Strip PHP, ₱, peso symbols, commas, and extra whitespace
    cleaned = (
        cleaned.replace("₱", "").replace("PHP", "").replace("php", "").replace(",", "").strip()
    )
    try:
        return Decimal(cleaned)
    except InvalidOperation as err:
        raise ValueError(f"Cannot parse decimal value from '{val}'") from err


def clean_int(val: str | None) -> int | None:
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", "").strip()
    try:
        return int(cleaned)
    except ValueError as err:
        raise ValueError(f"Cannot parse integer value from '{val}'") from err


class ImportService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()
        self.crm_service = CRMService(db, clock=self.clock)
        self.catalog_service = CatalogService(db, clock=self.clock)

    def upload_csv(
        self,
        file_name: str,
        file_bytes: bytes,
        entity_type: str,
        user_id: int | None = None,
        source_label: str | None = None,
    ) -> ImportBatch:
        """
        Ingests CSV upload into staging tables as raw text and runs immediate validation.
        """
        if entity_type not in ("customer", "product", "contact"):
            raise BadRequestException(detail=f"Unsupported entity type: '{entity_type}'")

        if not file_bytes:
            raise BadRequestException(detail="Uploaded CSV file is empty.")

        # Compute SHA256 digest (32 bytes)
        file_sha256 = hashlib.sha256(file_bytes).digest()

        # Decode CSV content handling different encodings
        content = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise BadRequestException(
                detail="Failed to decode CSV file content with standard encodings."
            )

        # Parse CSV rows
        f = io.StringIO(content)
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise BadRequestException(detail="CSV header line is missing or malformed.")

        # Create batch record
        batch = ImportBatch(
            entity_type=entity_type,
            file_name=file_name,
            file_sha256=file_sha256,
            source_label=source_label or "csv_upload",
            status="uploaded",
            row_count=0,
            valid_count=0,
            error_count=0,
            committed_count=0,
            uploaded_by=user_id,
            created_at=datetime.now(UTC),
        )
        self.db.add(batch)
        self.db.flush()

        rows = list(reader)
        batch.row_count = len(rows)

        # Normalize field keys to lowercase stripped
        for idx, row in enumerate(rows, start=1):
            normalized_row = {
                (k.strip().lower() if k else f"col_{c_idx}"): (v if v is not None else "")
                for c_idx, (k, v) in enumerate(row.items())
            }

            if entity_type == "customer":
                staging_row = ImportStagingCustomer(
                    batch_id=batch.id,
                    row_number=idx,
                    raw=dict(row),
                    name=normalized_row.get("name"),
                    email=normalized_row.get("email"),
                    phone=normalized_row.get("phone"),
                    tin=normalized_row.get("tin"),
                    city=normalized_row.get("city"),
                    province=normalized_row.get("province"),
                    customer_type=normalized_row.get("customer_type"),
                    payment_terms=normalized_row.get("payment_terms")
                    or normalized_row.get("payment_terms_days"),
                    credit_limit=normalized_row.get("credit_limit"),
                )
                self.db.add(staging_row)

            elif entity_type == "product":
                staging_row = ImportStagingProduct(
                    batch_id=batch.id,
                    row_number=idx,
                    raw=dict(row),
                    sku=normalized_row.get("sku"),
                    name=normalized_row.get("name"),
                    description=normalized_row.get("description"),
                    category_id=normalized_row.get("category_id"),
                    product_type=normalized_row.get("product_type"),
                    uom=normalized_row.get("uom"),
                    list_price=normalized_row.get("list_price"),
                    reorder_point=normalized_row.get("reorder_point"),
                    tax_rate_id=normalized_row.get("tax_rate_id"),
                )
                self.db.add(staging_row)

            elif entity_type == "contact":
                staging_row = ImportStagingContact(
                    batch_id=batch.id,
                    row_number=idx,
                    raw=dict(row),
                    customer_id=normalized_row.get("customer_id")
                    or normalized_row.get("customer_no"),
                    first_name=normalized_row.get("first_name"),
                    last_name=normalized_row.get("last_name"),
                    email=normalized_row.get("email"),
                    phone=normalized_row.get("phone"),
                    job_title=normalized_row.get("job_title"),
                )
                self.db.add(staging_row)

        self.db.flush()

        # Run row-level validation
        self.validate_batch(batch.id)
        self.db.commit()
        return batch

    def validate_batch(self, batch_id: int) -> ImportBatch:
        """
        Validates all staging records in the batch and updates error counts.
        """
        batch = self.db.get(ImportBatch, batch_id)
        if not batch:
            raise NotFoundException(detail=f"Import batch {batch_id} not found.")

        valid_count = 0
        error_count = 0

        if batch.entity_type == "customer":
            rows = (
                self.db.execute(
                    select(ImportStagingCustomer)
                    .where(ImportStagingCustomer.batch_id == batch_id)
                    .order_by(ImportStagingCustomer.row_number.asc())
                )
                .scalars()
                .all()
            )
            for row in rows:
                errors: list[dict[str, Any]] = []

                # Name is mandatory
                if not row.name or not row.name.strip():
                    errors.append({"field": "name", "message": "Customer name is required."})

                # Customer Type validation
                if row.customer_type and row.customer_type.strip():
                    c_type = row.customer_type.strip().lower()
                    if c_type not in ("company", "individual"):
                        errors.append(
                            {
                                "field": "customer_type",
                                "message": f"Customer type must be 'company' or 'individual', got '{row.customer_type}'.",
                            }
                        )

                # Email format
                if row.email and row.email.strip():
                    email_str = row.email.strip()
                    if not EMAIL_REGEX.match(email_str):
                        errors.append(
                            {
                                "field": "email",
                                "message": f"Invalid email format: '{row.email}'.",
                            }
                        )

                # Credit Limit numeric check
                if row.credit_limit and row.credit_limit.strip():
                    try:
                        c_val = clean_currency_or_decimal(row.credit_limit)
                        if c_val is not None and c_val < Decimal("0"):
                            errors.append(
                                {
                                    "field": "credit_limit",
                                    "message": "Credit limit cannot be negative.",
                                }
                            )
                    except ValueError:
                        errors.append(
                            {
                                "field": "credit_limit",
                                "message": f"Credit limit must be a valid non-negative number, got '{row.credit_limit}'.",
                            }
                        )

                # Payment terms check
                if row.payment_terms and row.payment_terms.strip():
                    try:
                        p_val = clean_int(row.payment_terms)
                        if p_val is not None and p_val < 0:
                            errors.append(
                                {
                                    "field": "payment_terms",
                                    "message": "Payment terms cannot be negative.",
                                }
                            )
                    except ValueError:
                        errors.append(
                            {
                                "field": "payment_terms",
                                "message": f"Payment terms must be a valid non-negative integer, got '{row.payment_terms}'.",
                            }
                        )

                row.validation_errors = errors if errors else None
                if errors:
                    error_count += 1
                else:
                    valid_count += 1

        elif batch.entity_type == "product":
            rows = (
                self.db.execute(
                    select(ImportStagingProduct)
                    .where(ImportStagingProduct.batch_id == batch_id)
                    .order_by(ImportStagingProduct.row_number.asc())
                )
                .scalars()
                .all()
            )
            # Preload existing SKUs to catch duplicate collisions
            existing_skus = set(
                self.db.execute(select(Product.sku).where(Product.is_active.is_(True)))
                .scalars()
                .all()
            )
            seen_in_batch: set[str] = set()

            for row in rows:
                errors = []

                if not row.sku or not row.sku.strip():
                    errors.append({"field": "sku", "message": "Product SKU is required."})
                else:
                    sku_clean = row.sku.strip().upper()
                    if sku_clean in existing_skus or sku_clean in seen_in_batch:
                        errors.append(
                            {
                                "field": "sku",
                                "message": f"Duplicate SKU in database or batch: '{row.sku}'.",
                            }
                        )
                    seen_in_batch.add(sku_clean)

                if not row.name or not row.name.strip():
                    errors.append({"field": "name", "message": "Product name is required."})

                if row.product_type and row.product_type.strip():
                    p_type = row.product_type.strip().lower()
                    if p_type not in ("stock", "service"):
                        errors.append(
                            {
                                "field": "product_type",
                                "message": f"Product type must be 'stock' or 'service', got '{row.product_type}'.",
                            }
                        )

                if row.uom and row.uom.strip():
                    uom_val = row.uom.strip().lower()
                    if uom_val not in ("pc", "box", "pack", "kg", "l", "m", "hr"):
                        errors.append(
                            {
                                "field": "uom",
                                "message": f"Invalid unit of measure: '{row.uom}'. Allowed: pc, box, pack, kg, l, m, hr.",
                            }
                        )

                # List price validation
                if not row.list_price or not row.list_price.strip():
                    errors.append({"field": "list_price", "message": "List price is required."})
                else:
                    try:
                        lp = clean_currency_or_decimal(row.list_price)
                        if lp is not None and lp < Decimal("0"):
                            errors.append(
                                {"field": "list_price", "message": "List price cannot be negative."}
                            )
                    except ValueError:
                        errors.append(
                            {
                                "field": "list_price",
                                "message": f"List price must be a valid number, got '{row.list_price}'.",
                            }
                        )

                row.validation_errors = errors if errors else None
                if errors:
                    error_count += 1
                else:
                    valid_count += 1

        elif batch.entity_type == "contact":
            rows = (
                self.db.execute(
                    select(ImportStagingContact)
                    .where(ImportStagingContact.batch_id == batch_id)
                    .order_by(ImportStagingContact.row_number.asc())
                )
                .scalars()
                .all()
            )
            for row in rows:
                errors = []
                if not row.first_name or not row.first_name.strip():
                    errors.append({"field": "first_name", "message": "First name is required."})

                if not row.customer_id or not row.customer_id.strip():
                    errors.append(
                        {
                            "field": "customer_id",
                            "message": "Customer ID or Customer No is required.",
                        }
                    )
                else:
                    target_cust = self._resolve_customer(row.customer_id.strip())
                    if not target_cust:
                        errors.append(
                            {
                                "field": "customer_id",
                                "message": f"Referenced customer '{row.customer_id}' does not exist.",
                            }
                        )

                if row.email and row.email.strip():
                    if not EMAIL_REGEX.match(row.email.strip()):
                        errors.append(
                            {"field": "email", "message": f"Invalid email format: '{row.email}'."}
                        )

                row.validation_errors = errors if errors else None
                if errors:
                    error_count += 1
                else:
                    valid_count += 1

        batch.valid_count = valid_count
        batch.error_count = error_count
        batch.status = "validated"
        self.db.flush()
        return batch

    def commit_batch(self, batch_id: int, user_id: int | None = None) -> ImportBatch:
        """
        Commits all valid, uncommitted staging rows into operational ERP domain services.
        Supports partial commits: rejected rows stay in staging with errors.
        """
        batch = self.db.get(ImportBatch, batch_id)
        if not batch:
            raise NotFoundException(detail=f"Import batch {batch_id} not found.")

        if batch.status == "uploaded":
            self.validate_batch(batch_id)

        committed_in_this_run = 0

        if batch.entity_type == "customer":
            rows = (
                self.db.execute(
                    select(ImportStagingCustomer).where(
                        ImportStagingCustomer.batch_id == batch_id,
                        ImportStagingCustomer.validation_errors.is_(None),
                        ImportStagingCustomer.committed_customer_id.is_(None),
                    )
                )
                .scalars()
                .all()
            )

            for row in rows:
                try:
                    c_type = (row.customer_type or "company").strip().lower()
                    terms = clean_int(row.payment_terms) or 0
                    limit = clean_currency_or_decimal(row.credit_limit)

                    initial_address = None
                    if row.city or row.province:
                        initial_address = CustomerAddressCreate(
                            address_type="billing",
                            line1=row.city or "Main Address",
                            city=row.city or "Manila",
                            province=row.province,
                            country_code="PH",
                        )

                    cust_payload = CustomerCreate(
                        name=row.name.strip() if row.name else "Unnamed",
                        customer_type=c_type if c_type in ("company", "individual") else "company",
                        status="active",
                        tin=row.tin.strip() if row.tin else None,
                        email=row.email.strip().lower() if row.email else None,
                        phone=row.phone.strip() if row.phone else None,
                        payment_terms_days=terms,
                        credit_limit=limit,
                        initial_address=initial_address,
                    )
                    new_cust = self.crm_service.create_customer(cust_payload, creator_id=user_id)
                    row.committed_customer_id = new_cust.id
                    self.db.commit()
                    committed_in_this_run += 1
                except Exception as exc:
                    self.db.rollback()
                    row.validation_errors = [{"field": "commit", "message": str(exc)}]
                    batch.error_count += 1
                    batch.valid_count = max(0, batch.valid_count - 1)
                    self.db.commit()

        elif batch.entity_type == "product":
            rows = (
                self.db.execute(
                    select(ImportStagingProduct).where(
                        ImportStagingProduct.batch_id == batch_id,
                        ImportStagingProduct.validation_errors.is_(None),
                        ImportStagingProduct.committed_product_id.is_(None),
                    )
                )
                .scalars()
                .all()
            )

            # Default tax rate
            default_tax = self.db.execute(
                select(TaxRate.id).where(TaxRate.is_default.is_(True))
            ).scalar_one_or_none()
            if not default_tax:
                default_tax = self.db.execute(select(TaxRate.id).limit(1)).scalar_one_or_none() or 1

            for row in rows:
                try:
                    p_type = (row.product_type or "stock").strip().lower()
                    uom_val = (row.uom or "pc").strip().lower()
                    price = clean_currency_or_decimal(row.list_price) or Decimal("0.00")
                    reorder = clean_currency_or_decimal(row.reorder_point)
                    cat_id = clean_int(row.category_id)
                    tax_id = clean_int(row.tax_rate_id) or default_tax

                    prod_payload = ProductCreate(
                        sku=row.sku.strip().upper() if row.sku else "SKU-UNKNOWN",
                        name=row.name.strip() if row.name else "Unnamed Product",
                        description=row.description,
                        category_id=cat_id,
                        product_type=p_type if p_type in ("stock", "service") else "stock",
                        uom=uom_val
                        if uom_val in ("pc", "box", "pack", "kg", "l", "m", "hr")
                        else "pc",
                        list_price=price,
                        reorder_point=reorder,
                        tax_rate_id=tax_id,
                    )
                    new_prod = self.catalog_service.create_product(prod_payload, creator_id=user_id)
                    row.committed_product_id = new_prod.id
                    self.db.commit()
                    committed_in_this_run += 1
                except Exception as exc:
                    self.db.rollback()
                    row.validation_errors = [{"field": "commit", "message": str(exc)}]
                    batch.error_count += 1
                    batch.valid_count = max(0, batch.valid_count - 1)
                    self.db.commit()

        elif batch.entity_type == "contact":
            rows = (
                self.db.execute(
                    select(ImportStagingContact).where(
                        ImportStagingContact.batch_id == batch_id,
                        ImportStagingContact.validation_errors.is_(None),
                        ImportStagingContact.committed_contact_id.is_(None),
                    )
                )
                .scalars()
                .all()
            )

            for row in rows:
                try:
                    target_cust = self._resolve_customer(
                        row.customer_id.strip() if row.customer_id else ""
                    )
                    if not target_cust:
                        raise ValueError(f"Customer '{row.customer_id}' not found.")

                    contact_payload = ContactCreate(
                        customer_id=target_cust.id,
                        first_name=row.first_name.strip() if row.first_name else "Contact",
                        last_name=row.last_name.strip() if row.last_name else None,
                        job_title=row.job_title.strip() if row.job_title else None,
                        email=row.email.strip().lower() if row.email else None,
                        phone=row.phone.strip() if row.phone else None,
                        is_primary=False,
                    )
                    new_contact = self.crm_service.create_contact(
                        contact_payload, creator_id=user_id
                    )
                    row.committed_contact_id = new_contact.id
                    self.db.commit()
                    committed_in_this_run += 1
                except Exception as exc:
                    self.db.rollback()
                    row.validation_errors = [{"field": "commit", "message": str(exc)}]
                    batch.error_count += 1
                    batch.valid_count = max(0, batch.valid_count - 1)
                    self.db.commit()

        batch.committed_count += committed_in_this_run
        if batch.committed_count >= batch.row_count and batch.row_count > 0:
            batch.status = "committed"
        elif batch.committed_count > 0:
            batch.status = "committed"
        else:
            batch.status = "failed" if batch.error_count == batch.row_count else "validated"

        batch.committed_at = datetime.now(UTC)
        self.db.commit()
        return batch

    def get_batch(self, batch_id: int) -> ImportBatch:
        batch = self.db.get(ImportBatch, batch_id)
        if not batch:
            raise NotFoundException(detail=f"Import batch {batch_id} not found.")
        return batch

    def list_batches(
        self,
        entity_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ImportBatch], int]:
        stmt = select(ImportBatch)
        if entity_type:
            stmt = stmt.where(ImportBatch.entity_type == entity_type)
        if status:
            stmt = stmt.where(ImportBatch.status == status)

        from sqlalchemy import func

        total = self.db.execute(select(func.count(ImportBatch.id))).scalar_one()
        batches = (
            self.db.execute(stmt.order_by(ImportBatch.id.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )
        return list(batches), total

    def get_staging_rows(
        self, batch_id: int, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        batch = self.get_batch(batch_id)
        if batch.entity_type == "customer":
            stmt = select(ImportStagingCustomer).where(ImportStagingCustomer.batch_id == batch_id)
            rows = (
                self.db.execute(
                    stmt.order_by(ImportStagingCustomer.row_number.asc())
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": r.id,
                    "row_number": r.row_number,
                    "name": r.name,
                    "email": r.email,
                    "phone": r.phone,
                    "tin": r.tin,
                    "city": r.city,
                    "province": r.province,
                    "customer_type": r.customer_type,
                    "payment_terms": r.payment_terms,
                    "credit_limit": r.credit_limit,
                    "validation_errors": r.validation_errors,
                    "committed_id": r.committed_customer_id,
                    "raw": r.raw,
                }
                for r in rows
            ]
        elif batch.entity_type == "product":
            stmt = select(ImportStagingProduct).where(ImportStagingProduct.batch_id == batch_id)
            rows = (
                self.db.execute(
                    stmt.order_by(ImportStagingProduct.row_number.asc()).offset(offset).limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": r.id,
                    "row_number": r.row_number,
                    "sku": r.sku,
                    "name": r.name,
                    "description": r.description,
                    "category_id": r.category_id,
                    "product_type": r.product_type,
                    "uom": r.uom,
                    "list_price": r.list_price,
                    "reorder_point": r.reorder_point,
                    "tax_rate_id": r.tax_rate_id,
                    "validation_errors": r.validation_errors,
                    "committed_id": r.committed_product_id,
                    "raw": r.raw,
                }
                for r in rows
            ]
        elif batch.entity_type == "contact":
            stmt = select(ImportStagingContact).where(ImportStagingContact.batch_id == batch_id)
            rows = (
                self.db.execute(
                    stmt.order_by(ImportStagingContact.row_number.asc()).offset(offset).limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": r.id,
                    "row_number": r.row_number,
                    "customer_id": r.customer_id,
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "email": r.email,
                    "phone": r.phone,
                    "job_title": r.job_title,
                    "validation_errors": r.validation_errors,
                    "committed_id": r.committed_contact_id,
                    "raw": r.raw,
                }
                for r in rows
            ]
        return []

    def _resolve_customer(self, identifier: str) -> Customer | None:
        """Resolves customer either by customer_no or numeric id."""
        if identifier.isdigit():
            c = self.db.get(Customer, int(identifier))
            if c:
                return c
        return self.db.execute(
            select(Customer).where(Customer.customer_no == identifier)
        ).scalar_one_or_none()
