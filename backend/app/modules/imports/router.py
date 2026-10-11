"""
Import Router (Roadmap §V1.0)
Exposes endpoints for CSV file upload, staging review, validation, and partial commits.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.imports.schemas import (
    CommitResultResponse,
    ImportBatchDetailResponse,
    ImportBatchResponse,
    ImportRawPayload,
)
from app.modules.imports.service import ImportService

router = APIRouter(prefix="/imports", tags=["Legacy & CSV Data Import Engine"])


def get_import_service(db: Annotated[Session, Depends(get_db)]) -> ImportService:
    return ImportService(db)


@router.post(
    "/upload",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV file for staging and validation",
)
async def upload_csv_file(
    file: Annotated[UploadFile, File(...)],
    entity_type: Annotated[
        str, Form(description="Target entity: 'customer', 'product', 'contact'")
    ],
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:upload"))],
    source_label: Annotated[str | None, Form()] = None,
) -> ImportBatchResponse:
    content = await file.read()
    batch = service.upload_csv(
        file_name=file.filename or "uploaded.csv",
        file_bytes=content,
        entity_type=entity_type.strip().lower(),
        user_id=context.user.id if context.user else None,
        source_label=source_label,
    )
    return ImportBatchResponse.model_validate(batch)


@router.post(
    "/upload-raw",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload raw CSV string content for staging and validation",
)
def upload_raw_csv(
    payload: ImportRawPayload,
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:upload"))],
) -> ImportBatchResponse:
    content_bytes = payload.csv_content.encode("utf-8")
    batch = service.upload_csv(
        file_name=payload.file_name,
        file_bytes=content_bytes,
        entity_type=payload.entity_type.strip().lower(),
        user_id=context.user.id if context.user else None,
        source_label=payload.source_label,
    )
    return ImportBatchResponse.model_validate(batch)


@router.get(
    "/batches",
    response_model=list[ImportBatchResponse],
    summary="List all import batches with filter and pagination",
)
def list_batches(
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:read"))],
    entity_type: str | None = Query(None, description="Filter by entity type"),
    status_filter: str | None = Query(None, alias="status", description="Filter by batch status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ImportBatchResponse]:
    batches, _ = service.list_batches(
        entity_type=entity_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [ImportBatchResponse.model_validate(b) for b in batches]


@router.get(
    "/batches/{batch_id}",
    response_model=ImportBatchDetailResponse,
    summary="Get import batch status and inspection staging rows",
)
def get_batch_details(
    batch_id: int,
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:read"))],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ImportBatchDetailResponse:
    batch = service.get_batch(batch_id)
    staging_rows = service.get_staging_rows(batch_id, limit=limit, offset=offset)
    return ImportBatchDetailResponse(
        batch=ImportBatchResponse.model_validate(batch),
        staging_rows=staging_rows,
        total_staging_rows=batch.row_count,
    )


@router.post(
    "/batches/{batch_id}/validate",
    response_model=ImportBatchResponse,
    summary="Trigger re-validation on an import batch",
)
def validate_batch(
    batch_id: int,
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:upload"))],
) -> ImportBatchResponse:
    batch = service.validate_batch(batch_id)
    return ImportBatchResponse.model_validate(batch)


@router.post(
    "/batches/{batch_id}/commit",
    response_model=CommitResultResponse,
    summary="Commit valid staged rows into operational ERP domain tables",
)
def commit_batch(
    batch_id: int,
    service: Annotated[ImportService, Depends(get_import_service)],
    context: Annotated[ScopeContext, Depends(require("import:commit"))],
) -> CommitResultResponse:
    batch = service.commit_batch(batch_id, user_id=context.user.id if context.user else None)
    return CommitResultResponse(
        batch_id=batch.id,
        status=batch.status,
        committed_count=batch.committed_count,
        error_count=batch.error_count,
        message=f"Successfully committed {batch.committed_count} rows into ERP core. {batch.error_count} rows retained with errors.",
    )
