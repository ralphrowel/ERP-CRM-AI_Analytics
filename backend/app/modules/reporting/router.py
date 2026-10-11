from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.reporting.schemas import (
    ARAgingResponse,
    ExecutiveSummaryResponse,
    InventoryReportResponse,
    PipelineReportResponse,
    ProcurementReportResponse,
    RevenueReportResponse,
)
from app.modules.reporting.service import ReportingService

router = APIRouter(prefix="/reporting", tags=["Operational Reporting & Analytics"])


def get_reporting_service(db: Annotated[Session, Depends(get_db)]) -> ReportingService:
    return ReportingService(db)


@router.get("/summary", response_model=ExecutiveSummaryResponse)
def get_executive_summary(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:read"))],
    period_start: date | None = Query(None, description="Start date of report period (inclusive)"),
    period_end: date | None = Query(None, description="End date of report period (inclusive)"),
    as_of_date: date | None = Query(None, description="Calculation snapshot date"),
) -> ExecutiveSummaryResponse:
    """Executive KPI scorecard and summary metrics across all operational domains."""
    return service.get_executive_summary(
        context=context,
        period_start=period_start,
        period_end=period_end,
        as_of_date=as_of_date,
    )


@router.get("/revenue", response_model=RevenueReportResponse)
def get_revenue_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:read"))],
    period_start: date | None = Query(None, description="Start date of report period (inclusive)"),
    period_end: date | None = Query(None, description="End date of report period (inclusive)"),
) -> RevenueReportResponse:
    """Net revenue, credit notes, COGS, and gross margin trends by month."""
    return service.get_revenue_report(
        context=context,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/ar-aging", response_model=ARAgingResponse)
def get_ar_aging_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:financial"))],
    as_of_date: date | None = Query(None, description="Calculation snapshot date"),
) -> ARAgingResponse:
    """Accounts receivable aging breakdown into 5 standard aging buckets and customer matrices."""
    return service.get_ar_aging_report(
        context=context,
        as_of_date=as_of_date,
    )


@router.get("/pipeline", response_model=PipelineReportResponse)
def get_pipeline_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:sales"))],
    period_start: date | None = Query(None, description="Start date of cohort period (inclusive)"),
    period_end: date | None = Query(None, description="End date of cohort period (inclusive)"),
) -> PipelineReportResponse:
    """Sales pipeline distribution by stage, weighted pipeline, win rate, and sales velocity."""
    return service.get_pipeline_report(
        context=context,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/inventory", response_model=InventoryReportResponse)
def get_inventory_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:inventory"))],
    as_of_date: date | None = Query(None, description="Calculation snapshot date"),
) -> InventoryReportResponse:
    """Inventory valuation across warehouses and active low-stock reorder alerts."""
    return service.get_inventory_report(
        context=context,
        as_of_date=as_of_date,
    )


@router.get("/procurement", response_model=ProcurementReportResponse)
def get_procurement_report(
    service: Annotated[ReportingService, Depends(get_reporting_service)],
    context: Annotated[ScopeContext, Depends(require("report:purchasing"))],
    period_start: date | None = Query(None, description="Start date of report period (inclusive)"),
    period_end: date | None = Query(None, description="End date of report period (inclusive)"),
) -> ProcurementReportResponse:
    """Procurement spend ranking by supplier and on-time delivery performance."""
    return service.get_procurement_report(
        context=context,
        period_start=period_start,
        period_end=period_end,
    )
