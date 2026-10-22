"""Unit tests for Milestone V3.1: Multi-Warehouse Automated Replenishment & In-Transit Transfer Logistics."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.clock import ControllableClock
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.modules.catalog.models import Product
from app.modules.inventory.models import (
    InventoryBalance,
    InventoryTransaction,
)
from app.modules.inventory.schemas import (
    AutoGenerateTransfersPayload,
    OpeningBalanceItemPayload,
    OpeningBalancesCreatePayload,
    StockTransferCreatePayload,
    StockTransferDispatchPayload,
    StockTransferItemCreatePayload,
    StockTransferReceivePayload,
    WarehouseCreatePayload,
    WarehouseReorderPolicyCreatePayload,
    WarehouseReorderPolicyUpdatePayload,
)
from app.modules.inventory.service import InventoryService
from app.modules.sales.models import TaxRate


@pytest.fixture
def clock():
    return ControllableClock()


@pytest.fixture
def inv_service(db_session, clock):
    return InventoryService(db_session, clock)


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
def hub_warehouse(db_session, inv_service):
    wh = inv_service.create_warehouse(
        WarehouseCreatePayload(
            code="WH-HUB",
            name="Central Distribution Hub",
            address="Metro Manila Central Hub",
            is_active=True,
            is_default=True,
        )
    )
    return wh


@pytest.fixture
def branch_warehouse(db_session, inv_service):
    wh = inv_service.create_warehouse(
        WarehouseCreatePayload(
            code="WH-CEBU",
            name="Cebu Regional Branch",
            address="Cebu City Logistics Depot",
            is_active=True,
            is_default=False,
        )
    )
    return wh


@pytest.fixture
def stock_product(db_session, default_tax_rate):
    prod = Product(
        sku="SKU-REPLEN-001",
        name="Industrial Motor 5HP",
        uom="pc",
        product_type="stock",
        list_price=Decimal("15000.00"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


@pytest.fixture
def second_product(db_session, default_tax_rate):
    prod = Product(
        sku="SKU-REPLEN-002",
        name="Heavy Duty Conveyor Belt",
        uom="m",
        product_type="stock",
        list_price=Decimal("3500.00"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


# ── Tests for Warehouse Reorder Policy CRUD ─────────────────────────
def test_create_and_validate_reorder_policy(
    inv_service, hub_warehouse, branch_warehouse, stock_product
):
    # 1. Invalid: Target warehouse inactive
    inactive_wh = inv_service.create_warehouse(
        WarehouseCreatePayload(code="WH-INACT", name="Inactive Branch", is_active=False)
    )
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=inactive_wh.id,
                product_id=stock_product.id,
                min_qty=Decimal("10.000"),
                max_qty=Decimal("50.000"),
                replenishment_source="purchase",
            )
        )
    assert exc_info.value.code == "WAREHOUSE_INACTIVE"

    # 2. Invalid: max_qty < min_qty
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=branch_warehouse.id,
                product_id=stock_product.id,
                min_qty=Decimal("50.000"),
                max_qty=Decimal("20.000"),
                replenishment_source="purchase",
            )
        )
    assert exc_info.value.code == "INVALID_QUANTITY_RANGE"

    # 3. Invalid: transfer source without source_warehouse_id
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=branch_warehouse.id,
                product_id=stock_product.id,
                min_qty=Decimal("10.000"),
                max_qty=Decimal("50.000"),
                replenishment_source="transfer",
                source_warehouse_id=None,
            )
        )
    assert exc_info.value.code == "SOURCE_WAREHOUSE_REQUIRED"

    # 4. Invalid: source warehouse identical to target warehouse
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=branch_warehouse.id,
                product_id=stock_product.id,
                min_qty=Decimal("10.000"),
                max_qty=Decimal("50.000"),
                replenishment_source="transfer",
                source_warehouse_id=branch_warehouse.id,
            )
        )
    assert exc_info.value.code == "IDENTICAL_WAREHOUSES"

    # 5. Successful creation
    policy = inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=stock_product.id,
            min_qty=Decimal("15.000"),
            max_qty=Decimal("60.000"),
            reorder_quantity=Decimal("30.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
            lead_time_days=3,
        )
    )
    assert policy.warehouse_id == branch_warehouse.id
    assert policy.product_id == stock_product.id
    assert policy.min_qty == Decimal("15.000")
    assert policy.max_qty == Decimal("60.000")
    assert policy.reorder_quantity == Decimal("30.000")
    assert policy.replenishment_source == "transfer"
    assert policy.source_warehouse_id == hub_warehouse.id
    assert policy.lead_time_days == 3
    assert policy.is_active is True

    # 6. Conflict: duplicate policy for (warehouse, product)
    with pytest.raises(ConflictError):
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=branch_warehouse.id,
                product_id=stock_product.id,
                min_qty=Decimal("20.000"),
                max_qty=Decimal("80.000"),
                replenishment_source="purchase",
            )
        )


def test_update_and_delete_reorder_policy(
    inv_service, hub_warehouse, branch_warehouse, stock_product
):
    policy = inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=stock_product.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("40.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
        )
    )

    # Update min/max and lead time
    updated = inv_service.update_reorder_policy(
        policy.id,
        WarehouseReorderPolicyUpdatePayload(
            min_qty=Decimal("20.000"),
            max_qty=Decimal("80.000"),
            lead_time_days=5,
            is_active=False,
        ),
    )
    assert updated.min_qty == Decimal("20.000")
    assert updated.max_qty == Decimal("80.000")
    assert updated.lead_time_days == 5
    assert updated.is_active is False

    # List filtered by is_active
    active_policies = inv_service.list_reorder_policies(is_active=True)
    assert not any(p.id == policy.id for p in active_policies)

    inactive_policies = inv_service.list_reorder_policies(is_active=False)
    assert any(p.id == policy.id for p in inactive_policies)

    # Delete policy
    inv_service.delete_reorder_policy(policy.id)
    with pytest.raises(NotFoundError):
        inv_service.get_reorder_policy(policy.id)


# ── Tests for Replenishment Suggestions ─────────────────────────────
def test_replenishment_suggestions_evaluation(
    inv_service, hub_warehouse, branch_warehouse, stock_product, second_product
):
    # Seed stock in Hub (100 units of prod1, 50 units of prod2)
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=hub_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=stock_product.id,
                    quantity=Decimal("100.000"),
                    unit_cost=Decimal("9500.00"),
                ),
                OpeningBalanceItemPayload(
                    product_id=second_product.id,
                    quantity=Decimal("50.000"),
                    unit_cost=Decimal("2100.00"),
                ),
            ],
        )
    )

    # Seed low stock in Branch: prod1 has 4 units (below min 15), prod2 has 0 units (below min 10)
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=branch_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=stock_product.id,
                    quantity=Decimal("4.000"),
                    unit_cost=Decimal("9500.00"),
                ),
            ],
        )
    )

    # Setup policies:
    # Prod 1: min=15, max=50, reorder_qty=None -> deficit = 50 - 4 = 46. Urgency = HIGH (4 < 15 * 0.5 = 7.5). Source = Hub.
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=stock_product.id,
            min_qty=Decimal("15.000"),
            max_qty=Decimal("50.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
        )
    )

    # Prod 2: min=10, max=30, reorder_qty=25. Available = 0 -> deficit = 30, suggested = 25. Urgency = CRITICAL (0 <= 0).
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=second_product.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("30.000"),
            reorder_quantity=Decimal("25.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
        )
    )

    # Evaluate suggestions
    suggestions = inv_service.evaluate_replenishment_suggestions(warehouse_id=branch_warehouse.id)
    assert len(suggestions) == 2

    # CRITICAL should be sorted first (prod2)
    crit = suggestions[0]
    assert crit.product_id == second_product.id
    assert crit.urgency == "CRITICAL"
    assert crit.qty_available == Decimal("0.000")
    assert crit.suggested_qty == Decimal("25.000")
    assert crit.source_qty_available == Decimal("50.000")
    assert crit.can_fulfill_transfer is True

    # HIGH should be second (prod1)
    high = suggestions[1]
    assert high.product_id == stock_product.id
    assert high.urgency == "HIGH"
    assert high.qty_available == Decimal("4.000")
    assert high.suggested_qty == Decimal("46.000")
    assert high.source_qty_available == Decimal("100.000")
    assert high.can_fulfill_transfer is True


# ── Tests for Auto-Generation of Replenishment Transfers ────────────
def test_auto_generate_replenishment_transfers(
    inv_service, hub_warehouse, branch_warehouse, stock_product, second_product
):
    # Hub has stock
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=hub_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=stock_product.id,
                    quantity=Decimal("80.000"),
                    unit_cost=Decimal("9500.00"),
                ),
                OpeningBalanceItemPayload(
                    product_id=second_product.id,
                    quantity=Decimal("40.000"),
                    unit_cost=Decimal("2100.00"),
                ),
            ],
        )
    )

    # Branch has 0 stock
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=stock_product.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("30.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
        )
    )
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=branch_warehouse.id,
            product_id=second_product.id,
            min_qty=Decimal("5.000"),
            max_qty=Decimal("20.000"),
            replenishment_source="transfer",
            source_warehouse_id=hub_warehouse.id,
        )
    )

    # Auto generate transfers
    result = inv_service.auto_generate_replenishment_transfers(
        AutoGenerateTransfersPayload(warehouse_id=branch_warehouse.id)
    )

    assert result.created_transfers_count == 1
    transfer = result.transfers[0]
    assert transfer.status == "approved"
    assert transfer.from_warehouse_id == hub_warehouse.id
    assert transfer.to_warehouse_id == branch_warehouse.id
    assert len(transfer.items) == 2

    # Verify items quantities match suggested deficits
    item_map = {it.product_id: it.quantity for it in transfer.items}
    assert item_map[stock_product.id] == Decimal("30.000")
    assert item_map[second_product.id] == Decimal("20.000")


# ── Tests for Two-Step In-Transit Stock Transfer Workflow ──────────
def test_two_step_in_transit_workflow_lifecycle(
    db_session, inv_service, hub_warehouse, branch_warehouse, stock_product
):
    # 1. Seed 50 units in Hub at unit cost 9,500.00
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=hub_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=stock_product.id,
                    quantity=Decimal("50.000"),
                    unit_cost=Decimal("9500.00"),
                ),
            ],
        )
    )

    # 2. Create draft transfer of 20 units
    transfer = inv_service.create_stock_transfer(
        StockTransferCreatePayload(
            from_warehouse_id=hub_warehouse.id,
            to_warehouse_id=branch_warehouse.id,
            notes="Transfer Manila Hub to Cebu Branch",
            items=[
                StockTransferItemCreatePayload(
                    product_id=stock_product.id, quantity=Decimal("20.000")
                )
            ],
        )
    )
    assert transfer.status == "draft"

    # 3. Approve transfer
    approved = inv_service.approve_stock_transfer(transfer.id)
    assert approved.status == "approved"
    assert approved.transfer_no is not None
    assert approved.approved_at is not None

    # Hub still has 50 on hand before dispatch
    hub_bal = db_session.execute(
        select(InventoryBalance).where(
            InventoryBalance.product_id == stock_product.id,
            InventoryBalance.warehouse_id == hub_warehouse.id,
        )
    ).scalar_one()
    assert hub_bal.qty_on_hand == Decimal("50.000")

    # 4. Dispatch transfer (Goods leave Hub, in-transit)
    dispatched = inv_service.dispatch_stock_transfer(
        transfer.id,
        payload=StockTransferDispatchPayload(notes="Picked and loaded on 2Go freight truck"),
    )
    assert dispatched.status == "in_transit"
    assert dispatched.dispatched_at is not None

    # Verify Hub balance decreased by 20 -> now 30
    db_session.refresh(hub_bal)
    assert hub_bal.qty_on_hand == Decimal("30.000")

    # Verify Branch balance is STILL 0 (goods are in transit!)
    branch_bal = db_session.execute(
        select(InventoryBalance).where(
            InventoryBalance.product_id == stock_product.id,
            InventoryBalance.warehouse_id == branch_warehouse.id,
        )
    ).scalar_one_or_none()
    assert branch_bal is None or branch_bal.qty_on_hand == Decimal("0.000")

    # Verify transfer_out ledger transaction was recorded
    tx_out = db_session.execute(
        select(InventoryTransaction).where(
            InventoryTransaction.source_id == transfer.id,
            InventoryTransaction.txn_type == "transfer_out",
        )
    ).scalar_one()
    assert tx_out.quantity == Decimal("-20.000")
    assert tx_out.unit_cost == Decimal("9500.00")

    # Cannot cancel an in-transit transfer
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.cancel_stock_transfer(transfer.id)
    assert exc_info.value.code == "INVALID_TRANSITION"

    # 5. Receive transfer at Branch (Goods arrive)
    received = inv_service.receive_stock_transfer(
        transfer.id,
        payload=StockTransferReceivePayload(notes="Freight delivered and inspected without damage"),
    )
    assert received.status == "posted"
    assert received.received_at is not None
    assert received.posted_at is not None

    # Verify Branch balance is now 20 at unit cost 9,500.00
    branch_bal = db_session.execute(
        select(InventoryBalance).where(
            InventoryBalance.product_id == stock_product.id,
            InventoryBalance.warehouse_id == branch_warehouse.id,
        )
    ).scalar_one()
    assert branch_bal.qty_on_hand == Decimal("20.000")
    assert branch_bal.avg_unit_cost == Decimal("9500.00")

    # Verify transfer_in ledger transaction was recorded
    tx_in = db_session.execute(
        select(InventoryTransaction).where(
            InventoryTransaction.source_id == transfer.id,
            InventoryTransaction.txn_type == "transfer_in",
        )
    ).scalar_one()
    assert tx_in.quantity == Decimal("20.000")
    assert tx_in.unit_cost == Decimal("9500.00")


def test_insufficient_stock_prevents_dispatch(
    inv_service, hub_warehouse, branch_warehouse, stock_product
):
    # Only 5 in hub
    inv_service.post_opening_balances(
        OpeningBalancesCreatePayload(
            warehouse_id=hub_warehouse.id,
            items=[
                OpeningBalanceItemPayload(
                    product_id=stock_product.id,
                    quantity=Decimal("5.000"),
                    unit_cost=Decimal("1000.00"),
                )
            ],
        )
    )

    # Request 20
    transfer = inv_service.create_stock_transfer(
        StockTransferCreatePayload(
            from_warehouse_id=hub_warehouse.id,
            to_warehouse_id=branch_warehouse.id,
            items=[
                StockTransferItemCreatePayload(
                    product_id=stock_product.id, quantity=Decimal("20.000")
                )
            ],
        )
    )
    inv_service.approve_stock_transfer(transfer.id)

    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.dispatch_stock_transfer(transfer.id)
    assert exc_info.value.code == "INSUFFICIENT_STOCK"


# ── Tests for FastAPI REST Endpoints ─────────────────────────────────
def test_replenishment_and_transfer_fastapi_endpoints(
    client, inv_service, hub_warehouse, branch_warehouse, stock_product
):
    from app.main import app
    from app.modules.identity.dependencies import get_current_user
    from app.modules.identity.models import User

    auth_user = User(
        email="inv_manager@parity.ph",
        password_hash="mock_hash",
        full_name="Inventory Manager",
        is_active=True,
        is_superuser=True,
    )
    inv_service.db.add(auth_user)
    inv_service.db.flush()
    app.dependency_overrides[get_current_user] = lambda: auth_user

    try:
        # 1. Seed stock in Hub
        inv_service.post_opening_balances(
            OpeningBalancesCreatePayload(
                warehouse_id=hub_warehouse.id,
                items=[
                    OpeningBalanceItemPayload(
                        product_id=stock_product.id,
                        quantity=Decimal("60.000"),
                        unit_cost=Decimal("9500.00"),
                    )
                ],
            )
        )

        # 2. POST /api/v1/inventory/reorder-policies
        res = client.post(
            "/api/v1/inventory/reorder-policies",
            json={
                "warehouse_id": branch_warehouse.id,
                "product_id": stock_product.id,
                "min_qty": "10.000",
                "max_qty": "30.000",
                "replenishment_source": "transfer",
                "source_warehouse_id": hub_warehouse.id,
                "lead_time_days": 2,
                "is_active": True,
            },
        )
        assert res.status_code == 201
        policy_data = res.json()
        assert policy_data["warehouse_id"] == branch_warehouse.id
        assert policy_data["replenishment_source"] == "transfer"
        policy_id = policy_data["id"]

        # 3. GET /api/v1/inventory/reorder-policies
        res = client.get(f"/api/v1/inventory/reorder-policies?warehouse_id={branch_warehouse.id}")
        assert res.status_code == 200
        assert len(res.json()) >= 1

        # 4. GET /api/v1/inventory/replenishment/suggestions
        res = client.get(
            f"/api/v1/inventory/replenishment/suggestions?warehouse_id={branch_warehouse.id}"
        )
        assert res.status_code == 200
        suggestions = res.json()
        assert len(suggestions) == 1
        assert suggestions[0]["product_id"] == stock_product.id
        assert suggestions[0]["can_fulfill_transfer"] is True

        # 5. POST /api/v1/inventory/replenishment/auto-generate
        res = client.post(
            "/api/v1/inventory/replenishment/auto-generate",
            json={"warehouse_id": branch_warehouse.id},
        )
        assert res.status_code == 201
        gen_data = res.json()
        assert gen_data["created_transfers_count"] == 1
        transfer_id = gen_data["transfer_ids"][0]

        # 6. POST /api/v1/stock-transfers/{id}/dispatch
        res = client.post(
            f"/api/v1/stock-transfers/{transfer_id}/dispatch",
            json={"notes": "Dispatched via API test runner"},
        )
        assert res.status_code == 200
        dispatched_transfer = res.json()
        assert dispatched_transfer["status"] == "in_transit"
        assert dispatched_transfer["dispatched_at"] is not None

        # 7. POST /api/v1/stock-transfers/{id}/receive
        res = client.post(
            f"/api/v1/stock-transfers/{transfer_id}/receive",
            json={"notes": "Received at destination depot via API test runner"},
        )
        assert res.status_code == 200
        received_transfer = res.json()
        assert received_transfer["status"] == "posted"
        assert received_transfer["received_at"] is not None

        # 8. DELETE /api/v1/inventory/reorder-policies/{id}
        res = client.delete(f"/api/v1/inventory/reorder-policies/{policy_id}")
        assert res.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)
