"""
Import Pydantic Schemas (Roadmap §V1.0)
Defines request payloads and response structures for CSV imports and staging management.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ImportRawPayload(BaseModel):
    entity_type: str
    file_name: str
    csv_content: str
    source_label: str | None = None


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    file_name: str
    file_sha256: str
    source_label: str | None = None
    status: str
    row_count: int
    valid_count: int
    error_count: int
    committed_count: int
    uploaded_by: int | None = None
    created_at: datetime
    committed_at: datetime | None = None

    @field_validator("file_sha256", mode="before")
    @classmethod
    def convert_bytes_to_hex(cls, v: Any) -> str:
        if isinstance(v, bytes):
            return v.hex()
        return str(v)


class StagingCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    row_number: int
    raw: dict[str, Any]
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    tin: str | None = None
    city: str | None = None
    province: str | None = None
    customer_type: str | None = None
    payment_terms: str | None = None
    credit_limit: str | None = None
    validation_errors: list[dict[str, Any]] | None = None
    committed_customer_id: int | None = None


class StagingProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    row_number: int
    raw: dict[str, Any]
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    category_id: str | None = None
    product_type: str | None = None
    uom: str | None = None
    list_price: str | None = None
    reorder_point: str | None = None
    tax_rate_id: str | None = None
    validation_errors: list[dict[str, Any]] | None = None
    committed_product_id: int | None = None


class StagingContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    row_number: int
    raw: dict[str, Any]
    customer_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    validation_errors: list[dict[str, Any]] | None = None
    committed_contact_id: int | None = None


class ImportBatchDetailResponse(BaseModel):
    batch: ImportBatchResponse
    staging_rows: list[dict[str, Any]]
    total_staging_rows: int


class CommitResultResponse(BaseModel):
    batch_id: int
    status: str
    committed_count: int
    error_count: int
    message: str
