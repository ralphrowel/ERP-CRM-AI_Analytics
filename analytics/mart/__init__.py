"""
Analytical Data Mart Package (Roadmap §V1.4)
Star schema models, builder, grain verification, and SCD Type 2 tracking.
"""

from analytics.mart.builder import MartBuilder
from analytics.mart.models import (
    DimCustomer,
    DimDate,
    DimEmployee,
    DimProduct,
    DimSourceSystem,
    DimSupplier,
    DimWarehouse,
    FactArAllocation,
    FactInventoryDaily,
    FactOpportunityStage,
    FactPurchaseLine,
    FactSalesLine,
)
from analytics.mart.scd_lesson import run_scd_discovery_lesson

__all__ = [
    "DimCustomer",
    "DimDate",
    "DimEmployee",
    "DimProduct",
    "DimSourceSystem",
    "DimSupplier",
    "DimWarehouse",
    "FactArAllocation",
    "FactInventoryDaily",
    "FactOpportunityStage",
    "FactPurchaseLine",
    "FactSalesLine",
    "MartBuilder",
    "run_scd_discovery_lesson",
]
