"""Dynamic Safety Stock, Reorder Point (ROP), and Order Level Optimization.

Implements the classical King/Silver statistical inventory model:
    SS = Z * sqrt(L * sigma_D^2 + D_avg^2 * sigma_L^2)
    ROP = (D_avg * L) + SS
    Max_Qty = ROP + Batch_Qty
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from statistics import NormalDist
from typing import Any


@dataclass
class PolicyTuningRecommendation:
    policy_id: int
    warehouse_id: int
    warehouse_code: str
    product_id: int
    product_sku: str
    product_name: str
    current_min_qty: Decimal
    current_max_qty: Decimal
    current_lead_time_days: int
    current_service_level: float
    recommended_safety_stock: Decimal
    recommended_min_qty: Decimal  # Recommended ROP
    recommended_max_qty: Decimal  # Recommended Target
    recommended_reorder_qty: Decimal
    avg_daily_demand: Decimal
    demand_std_dev: Decimal
    lead_time_std_dev: Decimal
    z_score: float
    forecast_model: str
    risk_assessment: str  # "UNDERSTOCK_RISK", "OVERSTOCK_CAPITAL_LOCKED", "BALANCED"
    variance_reason: str


def get_z_score_for_service_level(service_level: float) -> float:
    """Computes standard normal inverse CDF (z-factor) for target service level.

    Clamped between 50% (0.50) and 99.99% (0.9999).
    """
    clamped_sl = max(0.50, min(0.9999, float(service_level)))
    dist = NormalDist(mu=0.0, sigma=1.0)
    return round(dist.inv_cdf(clamped_sl), 4)


def compute_dynamic_safety_stock(
    avg_daily_demand: float,
    demand_std_dev: float,
    lead_time_days: int,
    lead_time_std_dev: float | None = None,
    service_level: float = 0.95,
) -> dict[str, Any]:
    """Calculates King/Silver dynamic safety stock and reorder point.

    Formula:
        SS = Z * sqrt( L * sigma_D^2 + D_avg^2 * sigma_L^2 )
        ROP = (D_avg * L) + SS
    """
    z = get_z_score_for_service_level(service_level)
    l_lead = max(1.0, float(lead_time_days))
    d_avg = max(0.0, float(avg_daily_demand))
    sigma_d = max(0.0, float(demand_std_dev))

    # If lead time variance not supplied, assume 15% of lead time or min 0.5 days
    sigma_l = float(lead_time_std_dev) if lead_time_std_dev is not None else max(0.5, l_lead * 0.15)

    lead_demand_var = (l_lead * (sigma_d**2)) + ((d_avg**2) * (sigma_l**2))
    std_error_lead_time = math.sqrt(lead_demand_var)

    safety_stock = z * std_error_lead_time
    # Buffer minimum 1 unit if product has active demand
    if d_avg > 0.0 and safety_stock < 1.0:
        safety_stock = 1.0

    rop = (d_avg * l_lead) + safety_stock

    # Recommended review cycle batch size (e.g. 14 days of average demand or minimum 10)
    batch_qty = max(10.0, d_avg * 14.0)
    max_qty = rop + batch_qty

    return {
        "service_level": service_level,
        "z_score": z,
        "safety_stock": round(safety_stock, 3),
        "reorder_point": round(rop, 3),
        "recommended_max": round(max_qty, 3),
        "recommended_batch_qty": round(batch_qty, 3),
        "std_error_lead_time": round(std_error_lead_time, 3),
    }


def evaluate_policy_tuning(
    policy_id: int,
    warehouse_id: int,
    warehouse_code: str,
    product_id: int,
    product_sku: str,
    product_name: str,
    current_min_qty: Decimal,
    current_max_qty: Decimal,
    lead_time_days: int,
    avg_daily_demand: float,
    demand_std_dev: float,
    service_level: float = 0.95,
    forecast_model: str = "holt_linear",
) -> PolicyTuningRecommendation:
    """Evaluates existing policy against dynamic statistical demand model."""
    tuning = compute_dynamic_safety_stock(
        avg_daily_demand=avg_daily_demand,
        demand_std_dev=demand_std_dev,
        lead_time_days=lead_time_days,
        service_level=service_level,
    )

    rec_ss = Decimal(str(tuning["safety_stock"]))
    rec_min = Decimal(str(tuning["reorder_point"]))
    rec_max = Decimal(str(tuning["recommended_max"]))
    rec_batch = Decimal(str(tuning["recommended_batch_qty"]))

    # Compare with current thresholds
    curr_min = current_min_qty
    curr_max = current_max_qty

    # Tolerance of 10%
    if curr_min < rec_min * Decimal("0.85"):
        risk = "UNDERSTOCK_RISK"
        reason = (
            f"Current threshold ({curr_min:.1f}) is below statistical ROP ({rec_min:.1f}). "
            f"Stockout probability exceeds {int((1.0 - service_level) * 100)}% under demand variance."
        )
    elif curr_min > rec_min * Decimal("1.30"):
        risk = "OVERSTOCK_CAPITAL_LOCKED"
        reason = (
            f"Current threshold ({curr_min:.1f}) exceeds recommended ROP ({rec_min:.1f}) by >30%. "
            f"Lowering to recommended level releases holding working capital without compromising {int(service_level * 100)}% service level."
        )
    else:
        risk = "BALANCED"
        reason = f"Current threshold ({curr_min:.1f}) is well-aligned with statistical ROP ({rec_min:.1f})."

    return PolicyTuningRecommendation(
        policy_id=policy_id,
        warehouse_id=warehouse_id,
        warehouse_code=warehouse_code,
        product_id=product_id,
        product_sku=product_sku,
        product_name=product_name,
        current_min_qty=curr_min,
        current_max_qty=curr_max,
        current_lead_time_days=lead_time_days,
        current_service_level=service_level,
        recommended_safety_stock=rec_ss,
        recommended_min_qty=rec_min,
        recommended_max_qty=rec_max,
        recommended_reorder_qty=rec_batch,
        avg_daily_demand=Decimal(str(round(avg_daily_demand, 3))),
        demand_std_dev=Decimal(str(round(demand_std_dev, 3))),
        lead_time_std_dev=Decimal(str(round(max(0.5, lead_time_days * 0.15), 3))),
        z_score=tuning["z_score"],
        forecast_model=forecast_model,
        risk_assessment=risk,
        variance_reason=reason,
    )
