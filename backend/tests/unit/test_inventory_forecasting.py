"""Unit & Integration Test Suite for Milestone V3.3:
ML Predictive Demand Forecasting & Dynamic Safety Stock Tuning.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import get_clock
from app.main import app
from app.modules.catalog.models import Product, ProductCategory
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.inventory.forecasting import (
    compute_metrics,
    croston_method,
    generate_demand_forecast,
    holt_linear_trend,
    holt_winters,
    simple_moving_average,
    single_exponential_smoothing,
)
from app.modules.inventory.models import (
    WarehouseReorderPolicy,
)
from app.modules.inventory.safety_stock import (
    compute_dynamic_safety_stock,
    evaluate_policy_tuning,
    get_z_score_for_service_level,
)
from app.modules.inventory.schemas import (
    ApplyPolicyTuningPayload,
    OpeningBalanceItemPayload,
    OpeningBalancesCreatePayload,
    WarehouseCreatePayload,
    WarehouseReorderPolicyCreatePayload,
)
from app.modules.inventory.service import InventoryService
from app.modules.sales.models import TaxRate


@pytest.fixture
def test_clock():
    return get_clock()


@pytest.fixture
def inv_service(db_session, test_clock):
    return InventoryService(db=db_session, clock=test_clock)


@pytest.fixture
def default_tax_rate(db_session):
    stmt = select(TaxRate).where(TaxRate.code == "VAT12")
    tr = db_session.execute(stmt).scalar_one_or_none()
    if not tr:
        tr = TaxRate(
            code="VAT12",
            name="Value Added Tax 12%",
            rate=Decimal("0.1200"),
            is_active=True,
            is_default=True,
        )
        db_session.add(tr)
        db_session.flush()
    return tr


@pytest.fixture
def auth_user(db_session):

    user = User(
        email="forecasting.officer@example.com",
        password_hash="mock_hash",
        full_name="Demand Planning Specialist",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_warehouse(inv_service):
    return inv_service.create_warehouse(
        WarehouseCreatePayload(
            code="WH-NORTH",
            name="North Logistics Hub",
            is_default=False,
            address="Pampanga, PH",
        )
    )


@pytest.fixture
def test_product(db_session, default_tax_rate):
    cat = ProductCategory(name="Industrial Equipment")
    db_session.add(cat)
    db_session.flush()

    prod = Product(
        sku="SKU-MOTOR-200",
        name="Heavy Duty Industrial Motor",
        product_type="stock",
        uom="pc",
        category_id=cat.id,
        list_price=Decimal("4500.00"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


# ── 1. Pure-Python Forecasting Mathematics Tests ─────────────────────
def test_pure_python_forecasting_algorithms():
    # Linear upward trend series
    series = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0, 28.0]
    horizon = 5

    # SMA
    sma_fc = simple_moving_average(series, horizon=horizon, window=3)
    assert len(sma_fc) == horizon
    assert abs(sma_fc[0] - 26.0) < 0.01

    # SES
    ses_fit, ses_fc = single_exponential_smoothing(series, horizon=horizon, alpha=0.3)
    assert len(ses_fit) == len(series)
    assert len(ses_fc) == horizon
    assert ses_fc[0] > 0

    # Holt's Linear
    hl_fit, hl_fc = holt_linear_trend(series, horizon=horizon, alpha=0.4, beta=0.2)
    assert len(hl_fit) == len(series)
    assert len(hl_fc) == horizon
    # Trend is strictly increasing
    assert hl_fc[4] > hl_fc[0]

    # Holt-Winters (seasonal)
    seasonal_series = [10, 20, 30, 40, 10, 20, 30, 40, 11, 21, 31, 41, 12, 22, 32, 42]
    hw_fit, hw_fc = holt_winters(seasonal_series, horizon=4, season_length=4)
    assert len(hw_fc) == 4
    # Highest seasonal peak was index 3 (40s), so index 3 should be highest
    assert hw_fc[3] > hw_fc[0]

    # Croston (intermittent/sparse demand)
    sparse_series = [0, 0, 15, 0, 0, 0, 20, 0, 0, 12, 0, 0, 0, 0, 18]
    cr_fit, cr_fc = croston_method(sparse_series, horizon=5, alpha=0.1)
    assert len(cr_fc) == 5
    assert cr_fc[0] > 0.0

    # Metrics evaluation
    metrics = compute_metrics(series, series)
    assert metrics.mae == 0.0
    assert metrics.rmse == 0.0
    assert metrics.mape == 0.0


def test_generate_demand_forecast_orchestration():
    dates = [f"2026-01-{i:02d}" for i in range(1, 31)]
    # Mix with high intermittent zeroes (>50% zeros)
    values = [0.0 if i % 2 == 0 else float(i * 3) for i in range(1, 31)]

    fc_auto = generate_demand_forecast(
        historical_dates=dates,
        historical_values=values,
        horizon_days=14,
        model="auto",
    )
    # Intermittent should select croston
    assert fc_auto.intermittent_ratio >= 0.45
    assert fc_auto.model_name == "croston"
    assert len(fc_auto.forecast_points) == 14
    assert fc_auto.total_forecast_demand > 0

    # Verify confidence bounds
    for pt in fc_auto.forecast_points:
        assert pt.lower_bound <= pt.forecast <= pt.upper_bound


# ── 2. Statistical Safety Stock & ROP Tests ─────────────────────────
def test_statistical_safety_stock_optimization():
    # Z-scores
    assert abs(get_z_score_for_service_level(0.90) - 1.2816) < 0.01
    assert abs(get_z_score_for_service_level(0.95) - 1.6449) < 0.01
    assert abs(get_z_score_for_service_level(0.99) - 2.3263) < 0.01

    # King / Silver calculation
    result = compute_dynamic_safety_stock(
        avg_daily_demand=20.0,
        demand_std_dev=5.0,
        lead_time_days=9,
        lead_time_std_dev=1.0,
        service_level=0.95,
    )

    # Lead time variance = 9 * 25 + 400 * 1 = 225 + 400 = 625 => sqrt(625) = 25
    # SS = 1.6449 * 25 = 41.12
    # ROP = (20 * 9) + 41.12 = 221.12
    assert abs(result["safety_stock"] - 41.12) < 0.5
    assert abs(result["reorder_point"] - 221.12) < 0.5
    assert result["recommended_max"] > result["reorder_point"]

    # Risk evaluation
    rec_under = evaluate_policy_tuning(
        policy_id=1,
        warehouse_id=1,
        warehouse_code="WH-1",
        product_id=1,
        product_sku="SKU-1",
        product_name="Widget",
        current_min_qty=Decimal("50.0"),  # Way below 221 ROP
        current_max_qty=Decimal("150.0"),
        lead_time_days=9,
        avg_daily_demand=20.0,
        demand_std_dev=5.0,
        service_level=0.95,
    )
    assert rec_under.risk_assessment == "UNDERSTOCK_RISK"

    rec_over = evaluate_policy_tuning(
        policy_id=1,
        warehouse_id=1,
        warehouse_code="WH-1",
        product_id=1,
        product_sku="SKU-1",
        product_name="Widget",
        current_min_qty=Decimal("400.0"),  # Way above 221 ROP
        current_max_qty=Decimal("800.0"),
        lead_time_days=9,
        avg_daily_demand=20.0,
        demand_std_dev=5.0,
        service_level=0.95,
    )
    assert rec_over.risk_assessment == "OVERSTOCK_CAPITAL_LOCKED"


# ── 3. Inventory Service Demand Extraction & Forecast Tests ──────────
def test_inventory_service_demand_forecast(inv_service, test_warehouse, test_product, auth_user):
    # Seed opening balance to create inventory transactions
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=test_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=test_product.id,
                    quantity=Decimal("500.000"),
                    unit_cost=Decimal("2500.00"),
                )
            ],
        )
    )

    # Forecast demand
    fc = inv_service.forecast_product_demand(
        warehouse_id=test_warehouse.id,
        product_id=test_product.id,
        horizon_days=30,
        model="auto",
        days_back=60,
    )

    assert fc.warehouse_id == test_warehouse.id
    assert fc.product_id == test_product.id
    assert len(fc.forecast) == 30
    assert len(fc.historical) >= 60
    assert fc.model_name in ("croston", "holt_linear", "ses", "sma", "holt_winters")


# ── 4. Reorder Policy Tuning Evaluation & Application Tests ─────────
def test_inventory_service_policy_recommendation_and_tuning(
    inv_service, test_warehouse, test_product, auth_user, db_session, test_clock
):
    from datetime import timedelta

    from app.modules.inventory.models import InventoryTransaction

    now = test_clock.now()
    # Seed outbound demand so historical demand is positive
    for d in range(1, 10):
        db_session.add(
            InventoryTransaction(
                product_id=test_product.id,
                warehouse_id=test_warehouse.id,
                txn_type="issue",
                quantity=Decimal("-15.000"),
                unit_cost=Decimal("2500.00"),
                total_cost=Decimal("-37500.00"),
                qty_on_hand_after=Decimal("100.000"),
                avg_cost_after=Decimal("2500.00"),
                source_type="shipment",
                source_id=1,
                source_line_id=1,
                occurred_at=now - timedelta(days=d * 3),
                created_at=now - timedelta(days=d * 3),
            )
        )
    db_session.flush()

    # Create static policy with intentionally low min_qty
    created_policy = inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=test_warehouse.id,
            product_id=test_product.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("50.000"),
            reorder_quantity=Decimal("20.000"),
            replenishment_source="purchase",
            lead_time_days=14,
            service_level=Decimal("0.9500"),
        ),
        current_user_id=auth_user.id,
    )
    assert created_policy.service_level == Decimal("0.9500")

    # Generate tuning recommendations
    recommendations = inv_service.recommend_policy_tuning(
        warehouse_id=test_warehouse.id,
        product_ids=[test_product.id],
    )
    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.policy_id == created_policy.id
    assert rec.current_min_qty == Decimal("10.000")
    assert rec.recommended_min_qty > Decimal("0.000")
    assert rec.recommended_safety_stock > Decimal("0.000")

    # Apply tuning
    updated_policy = inv_service.apply_policy_tuning(
        policy_id=created_policy.id,
        payload=ApplyPolicyTuningPayload(
            service_level=Decimal("0.9800"),
            recommended_safety_stock=rec.recommended_safety_stock,
            recommended_min_qty=rec.recommended_min_qty,
            recommended_max_qty=rec.recommended_max_qty,
            recommended_reorder_qty=rec.recommended_reorder_qty,
            tuning_method="holt_linear_king_silver",
        ),
        current_user_id=auth_user.id,
    )

    assert updated_policy.service_level == Decimal("0.9800")
    assert updated_policy.safety_stock == rec.recommended_safety_stock
    assert updated_policy.min_qty == rec.recommended_min_qty
    assert updated_policy.max_qty == rec.recommended_max_qty
    assert updated_policy.tuning_method == "holt_linear_king_silver"
    assert updated_policy.last_tuned_at is not None
    assert updated_policy.version == 2


# ── 5. FastAPI REST Endpoints Tests ──────────────────────────────────
def test_forecasting_fastapi_endpoints(db_session, test_warehouse, test_product, auth_user):
    from app.core.database import get_db

    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    try:
        # Create policy
        policy = WarehouseReorderPolicy(
            warehouse_id=test_warehouse.id,
            product_id=test_product.id,
            min_qty=Decimal("15.000"),
            max_qty=Decimal("60.000"),
            replenishment_source="purchase",
            lead_time_days=10,
            is_active=True,
            service_level=Decimal("0.9500"),
            created_by=auth_user.id,
            updated_by=auth_user.id,
        )
        db_session.add(policy)
        db_session.flush()

        # 1. GET /api/v1/inventory/forecasting/demand
        res_fc = client.get(
            f"/api/v1/inventory/forecasting/demand?warehouse_id={test_warehouse.id}&product_id={test_product.id}&horizon_days=14"
        )
        assert res_fc.status_code == 200
        fc_data = res_fc.json()
        assert fc_data["product_sku"] == test_product.sku
        assert len(fc_data["forecast"]) == 14

        # 2. GET /api/v1/inventory/forecasting/policy-recommendations
        res_rec = client.get(
            f"/api/v1/inventory/forecasting/policy-recommendations?warehouse_id={test_warehouse.id}"
        )
        assert res_rec.status_code == 200
        rec_data = res_rec.json()
        assert len(rec_data) == 1
        assert rec_data[0]["policy_id"] == policy.id

        # 3. POST /api/v1/inventory/reorder-policies/{id}/apply-tuning
        res_apply = client.post(
            f"/api/v1/inventory/reorder-policies/{policy.id}/apply-tuning",
            json={
                "service_level": "0.9900",
                "recommended_safety_stock": "25.000",
                "recommended_min_qty": "75.000",
                "recommended_max_qty": "180.000",
                "recommended_reorder_qty": "50.000",
                "tuning_method": "holt_winters_dynamic",
            },
        )
        assert res_apply.status_code == 200
        applied_data = res_apply.json()
        assert Decimal(str(applied_data["service_level"])) == Decimal("0.9900")
        assert Decimal(str(applied_data["safety_stock"])) == Decimal("25.000")
        assert Decimal(str(applied_data["min_qty"])) == Decimal("75.000")
        assert Decimal(str(applied_data["max_qty"])) == Decimal("180.000")
        assert applied_data["tuning_method"] == "holt_winters_dynamic"
        assert applied_data["last_tuned_at"] is not None

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


# ── 6. Visiq AI Forecast Demand Tool & Agent Tests ───────────────────
def test_visiq_forecast_demand_tool_and_agent(db_session):
    import os

    from analytics.visiq.agent import VisiqAgent
    from analytics.visiq.tools import VisiqTools
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    erp_engine = db_session.get_bind()
    if erp_engine.dialect.name == "postgresql":
        analytics_url = os.getenv(
            "ANALYTICS_DATABASE_URL",
            "postgresql+psycopg://analytics_owner:analytics_owner_password@localhost:5432/erp_analytics",
        )
        try:
            engine = create_engine(analytics_url, pool_pre_ping=True)
            with engine.connect():
                pass
        except Exception:  # noqa: BLE001
            engine = create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
    else:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    # 1. Direct tool execution
    tools = VisiqTools(engine)

    out = tools.forecast_demand(
        product_name_or_sku="SKU-MOTOR-200",
        horizon_days=30,
        model="auto",
    )
    assert out["tool"] == "forecast_demand"
    assert out["horizon_days"] == 30
    assert len(out["forecast_points"]) == 30
    assert "safety_stock_recommendation" in out

    # 2. Agent conversational routing & narrative synthesis
    agent = VisiqAgent(engine)
    response = agent.ask(
        "Forecast demand for Industrial Motor over the next 30 days and recommend safety stock",
        theme="light",
    )
    assert response["refused"] is False
    assert response["tool_called"] == "forecast_demand"
    assert "Predictive Demand Forecast" in response["narrative"]
    assert "Dynamic Safety Stock" in response["narrative"]
    assert response["plotly_spec"] is not None
    assert len(response["plotly_spec"]["data"]) >= 3  # Historical, bounds, forecast
