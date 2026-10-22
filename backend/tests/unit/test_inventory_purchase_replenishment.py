"""Unit tests for Milestone V3.2: Automated Purchase Replenishment (PO Drafting from Vendor Sourcing Policies)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import ControllableClock
from app.core.database import get_db
from app.core.errors import BusinessRuleError, NotFoundError
from app.main import app
from app.modules.catalog.models import Product
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.inventory.schemas import (
    AutoGeneratePOsPayload,
    WarehouseCreatePayload,
    WarehouseReorderPolicyCreatePayload,
    WarehouseReorderPolicyUpdatePayload,
)
from app.modules.inventory.service import InventoryService
from app.modules.purchasing.models import (
    PurchaseOrder,
    Supplier,
    SupplierProduct,
)
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
def fulfillment_warehouse(db_session, inv_service):
    wh = inv_service.create_warehouse(
        WarehouseCreatePayload(
            code="WH-NORTH",
            name="North Luzon Depot",
            address="Pampanga Logistics Zone",
            is_active=True,
            is_default=True,
        )
    )
    return wh


@pytest.fixture
def active_supplier_a(db_session):
    sup = Supplier(
        supplier_no="SUP-ALPHA-001",
        name="Alpha Global Distribution Inc.",
        tin="123-456-789-000",
        email="orders@alphaglobal.ph",
        phone="+639171234567",
        address="BGC Taguig City, Metro Manila",
        payment_terms_days=30,
        is_active=True,
    )
    db_session.add(sup)
    db_session.flush()
    return sup


@pytest.fixture
def active_supplier_b(db_session):
    sup = Supplier(
        supplier_no="SUP-BETA-002",
        name="Beta Heavy Hardware Co.",
        tin="987-654-321-000",
        email="sales@betahardware.ph",
        phone="+639189876543",
        address="Subic Freeport Zone, Zambales",
        payment_terms_days=45,
        is_active=True,
    )
    db_session.add(sup)
    db_session.flush()
    return sup


@pytest.fixture
def inactive_supplier(db_session):
    sup = Supplier(
        supplier_no="SUP-INACTIVE-003",
        name="Inactive Trading Corp",
        payment_terms_days=15,
        is_active=False,
    )
    db_session.add(sup)
    db_session.flush()
    return sup


@pytest.fixture
def product_gear(db_session, default_tax_rate):
    prod = Product(
        sku="SKU-GEAR-001",
        name="Industrial Steel Gearbox",
        product_type="stock",
        uom="pc",
        list_price=Decimal("4000.0000"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


@pytest.fixture
def product_bearing(db_session, default_tax_rate):
    prod = Product(
        sku="SKU-BEARING-002",
        name="Heavy Duty Ball Bearing 50mm",
        product_type="stock",
        uom="pc",
        list_price=Decimal("1200.0000"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


@pytest.fixture
def product_belt(db_session, default_tax_rate):
    prod = Product(
        sku="SKU-BELT-003",
        name="V-Belt Drive High Torque",
        product_type="stock",
        uom="pc",
        list_price=Decimal("600.0000"),
        tax_rate_id=default_tax_rate.id,
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()
    return prod


# ── Test Cases ─────────────────────────────────────────────────────────


def test_reorder_policy_preferred_supplier_crud(
    inv_service, fulfillment_warehouse, product_gear, active_supplier_a, inactive_supplier
):
    """Verifies CRUD operations and validation rules for policy preferred suppliers."""
    # 1. Inactive supplier raises BusinessRuleError
    with pytest.raises(BusinessRuleError) as exc_info:
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=fulfillment_warehouse.id,
                product_id=product_gear.id,
                min_qty=Decimal("10.000"),
                max_qty=Decimal("50.000"),
                replenishment_source="purchase",
                preferred_supplier_id=inactive_supplier.id,
            )
        )
    assert exc_info.value.code == "SUPPLIER_INACTIVE"

    # 2. Non-existent supplier raises NotFoundError
    with pytest.raises(NotFoundError):
        inv_service.create_reorder_policy(
            WarehouseReorderPolicyCreatePayload(
                warehouse_id=fulfillment_warehouse.id,
                product_id=product_gear.id,
                min_qty=Decimal("10.000"),
                max_qty=Decimal("50.000"),
                replenishment_source="purchase",
                preferred_supplier_id=99999,
            )
        )

    # 3. Create valid policy with preferred supplier
    created = inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_gear.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("50.000"),
            reorder_quantity=Decimal("20.000"),
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
            lead_time_days=7,
        )
    )
    assert created.preferred_supplier_id == active_supplier_a.id
    assert created.preferred_supplier_code == active_supplier_a.supplier_no
    assert created.preferred_supplier_name == active_supplier_a.name
    assert created.replenishment_source == "purchase"

    # 4. Update policy to unset preferred supplier
    updated = inv_service.update_reorder_policy(
        created.id,
        WarehouseReorderPolicyUpdatePayload(preferred_supplier_id=0),
    )
    assert updated.preferred_supplier_id is None
    assert updated.preferred_supplier_name is None


def test_evaluate_replenishment_suggestions_with_policy_preferred_supplier(
    db_session, inv_service, fulfillment_warehouse, product_gear, active_supplier_a
):
    """Verifies that suggestions prioritize explicit policy preferred supplier."""
    # Create supplier product relationship with known unit cost
    sp = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_gear.id,
        supplier_sku="ALPHA-GEAR-X",
        last_unit_cost=Decimal("2450.0000"),
        lead_time_days=5,
        is_preferred=False,
    )
    db_session.add(sp)
    db_session.flush()

    # Create policy pointing directly to active_supplier_a
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_gear.id,
            min_qty=Decimal("15.000"),
            max_qty=Decimal("50.000"),
            reorder_quantity=Decimal("25.000"),
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
            lead_time_days=7,
        )
    )

    suggestions = inv_service.evaluate_replenishment_suggestions(
        warehouse_id=fulfillment_warehouse.id
    )
    assert len(suggestions) == 1
    s = suggestions[0]

    assert s.product_id == product_gear.id
    assert s.replenishment_source == "purchase"
    assert s.preferred_supplier_id == active_supplier_a.id
    assert s.preferred_supplier_code == active_supplier_a.supplier_no
    assert s.preferred_supplier_name == active_supplier_a.name
    assert s.estimated_unit_cost == Decimal("2450.0000")
    assert s.unfulfillable_reason is None
    assert s.suggested_qty == Decimal("25.000")
    assert s.urgency == "CRITICAL"  # 0 on-hand


def test_evaluate_replenishment_suggestions_supplier_product_fallback(
    db_session,
    inv_service,
    fulfillment_warehouse,
    product_bearing,
    active_supplier_a,
    active_supplier_b,
):
    """Verifies fallback hierarchy when policy does not specify preferred_supplier_id."""
    # Supplier A: not preferred, higher cost
    sp_a = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_bearing.id,
        last_unit_cost=Decimal("800.0000"),
        is_preferred=False,
    )
    # Supplier B: marked as preferred
    sp_b = SupplierProduct(
        supplier_id=active_supplier_b.id,
        product_id=product_bearing.id,
        last_unit_cost=Decimal("780.0000"),
        is_preferred=True,
    )
    db_session.add_all([sp_a, sp_b])
    db_session.flush()

    # Policy with NO preferred_supplier_id
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_bearing.id,
            min_qty=Decimal("20.000"),
            max_qty=Decimal("60.000"),
            replenishment_source="purchase",
            preferred_supplier_id=None,
        )
    )

    suggestions = inv_service.evaluate_replenishment_suggestions(
        warehouse_id=fulfillment_warehouse.id
    )
    assert len(suggestions) == 1
    s = suggestions[0]

    # Should have selected preferred supplier B
    assert s.preferred_supplier_id == active_supplier_b.id
    assert s.preferred_supplier_name == active_supplier_b.name
    assert s.estimated_unit_cost == Decimal("780.0000")
    assert s.unfulfillable_reason is None


def test_evaluate_replenishment_suggestions_unfulfillable_when_no_supplier(
    inv_service, fulfillment_warehouse, product_belt
):
    """Verifies that suggestion flags unfulfillable_reason when no supplier exists."""
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_belt.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("30.000"),
            replenishment_source="purchase",
            preferred_supplier_id=None,
        )
    )

    suggestions = inv_service.evaluate_replenishment_suggestions(
        warehouse_id=fulfillment_warehouse.id
    )
    assert len(suggestions) == 1
    s = suggestions[0]

    assert s.preferred_supplier_id is None
    assert s.unfulfillable_reason == "NO_SUPPLIER_FOR_PRODUCT"


def test_auto_generate_replenishment_pos_grouping_and_financials(
    db_session,
    inv_service,
    fulfillment_warehouse,
    active_supplier_a,
    active_supplier_b,
    product_gear,
    product_bearing,
    product_belt,
):
    """Verifies auto-generating draft POs with grouping by supplier and exact centavo totals."""
    # Product Gear -> Supplier A (Deficit 30 @ 2000.00)
    sp_gear = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_gear.id,
        last_unit_cost=Decimal("2000.0000"),
        is_preferred=True,
    )
    # Product Bearing -> Supplier A (Deficit 40 @ 700.00)
    sp_bearing = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_bearing.id,
        last_unit_cost=Decimal("700.0000"),
        is_preferred=True,
    )
    # Product Belt -> Supplier B (Deficit 50 @ 300.00)
    sp_belt = SupplierProduct(
        supplier_id=active_supplier_b.id,
        product_id=product_belt.id,
        last_unit_cost=Decimal("300.0000"),
        is_preferred=True,
    )
    db_session.add_all([sp_gear, sp_bearing, sp_belt])
    db_session.flush()

    # Policies
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_gear.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("40.000"),  # deficit = 40 - 0 = 40
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
            lead_time_days=10,
        )
    )
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_bearing.id,
            min_qty=Decimal("20.000"),
            max_qty=Decimal("60.000"),  # deficit = 60 - 0 = 60
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
            lead_time_days=5,
        )
    )
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_belt.id,
            min_qty=Decimal("15.000"),
            max_qty=Decimal("50.000"),  # deficit = 50 - 0 = 50
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_b.id,
            lead_time_days=3,
        )
    )

    # Execute auto-generation
    result = inv_service.auto_generate_replenishment_pos(
        AutoGeneratePOsPayload(warehouse_id=fulfillment_warehouse.id),
        current_user_id=1,
    )

    # 2 POs created: 1 for Supplier A (2 items), 1 for Supplier B (1 item)
    assert result.created_pos_count == 2
    assert len(result.purchase_orders) == 2
    assert result.unfulfilled_suggestions_count == 0

    po_a = next(po for po in result.purchase_orders if po.supplier_id == active_supplier_a.id)
    po_b = next(po for po in result.purchase_orders if po.supplier_id == active_supplier_b.id)

    # Check PO A:
    # Gear: 40 * 2000.00 = 80,000.00, Tax = 9,600.00
    # Bearing: 60 * 700.00 = 42,000.00, Tax = 5,040.00
    # Total Subtotal = 122,000.00, Tax = 14,640.00, Grand Total = 136,640.00
    assert po_a.items_count == 2
    assert po_a.status == "draft"
    assert po_a.subtotal == Decimal("122000.0000")
    assert po_a.tax_total == Decimal("14640.0000")
    assert po_a.grand_total == Decimal("136640.0000")
    assert po_a.expected_date is not None

    # Check PO B:
    # Belt: 50 * 300.00 = 15,000.00, Tax = 1,800.00, Grand Total = 16,800.00
    assert po_b.items_count == 1
    assert po_b.status == "draft"
    assert po_b.subtotal == Decimal("15000.0000")
    assert po_b.tax_total == Decimal("1800.0000")
    assert po_b.grand_total == Decimal("16800.0000")

    # Verify gapless PO numbering and persistence in database
    db_po_a = db_session.get(PurchaseOrder, po_a.id)
    assert db_po_a is not None
    assert db_po_a.po_no.startswith("PO-")
    assert len(db_po_a.items) == 2


def test_auto_generate_replenishment_pos_filters_and_unfulfilled(
    db_session,
    inv_service,
    fulfillment_warehouse,
    active_supplier_a,
    product_gear,
    product_belt,
):
    """Verifies filtering by product_ids and reporting unfulfillable suggestions."""
    # Gear has supplier A
    sp_gear = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_gear.id,
        last_unit_cost=Decimal("2000.0000"),
        is_preferred=True,
    )
    db_session.add(sp_gear)
    db_session.flush()

    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_gear.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("30.000"),
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
        )
    )

    # Belt has NO supplier
    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_belt.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("20.000"),
            replenishment_source="purchase",
            preferred_supplier_id=None,
        )
    )

    # Filter to only generate for product_gear
    result = inv_service.auto_generate_replenishment_pos(
        AutoGeneratePOsPayload(
            warehouse_id=fulfillment_warehouse.id,
            product_ids=[product_gear.id],
        )
    )
    assert result.created_pos_count == 1
    assert result.purchase_orders[0].items_count == 1

    # Run without filter: belt should be in unfulfilled_suggestions
    all_result = inv_service.auto_generate_replenishment_pos(
        AutoGeneratePOsPayload(warehouse_id=fulfillment_warehouse.id)
    )
    assert all_result.unfulfilled_suggestions_count == 1
    assert all_result.unfulfilled_suggestions[0].product_id == product_belt.id
    assert all_result.unfulfilled_suggestions[0].unfulfillable_reason == "NO_SUPPLIER_FOR_PRODUCT"


def test_replenishment_pos_fastapi_endpoints(
    db_session,
    inv_service,
    fulfillment_warehouse,
    active_supplier_a,
    product_gear,
):
    """Verifies the REST API endpoint POST /api/v1/inventory/replenishment/auto-generate-pos."""
    sp_gear = SupplierProduct(
        supplier_id=active_supplier_a.id,
        product_id=product_gear.id,
        last_unit_cost=Decimal("1850.0000"),
        is_preferred=True,
    )
    db_session.add(sp_gear)
    db_session.flush()

    inv_service.create_reorder_policy(
        WarehouseReorderPolicyCreatePayload(
            warehouse_id=fulfillment_warehouse.id,
            product_id=product_gear.id,
            min_qty=Decimal("10.000"),
            max_qty=Decimal("40.000"),
            replenishment_source="purchase",
            preferred_supplier_id=active_supplier_a.id,
        )
    )

    auth_user = User(
        id=1,
        email="procurement.officer@example.com",
        password_hash="mock_hash",
        full_name="Procurement Officer",
        is_active=True,
    )

    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/inventory/replenishment/auto-generate-pos",
            json={"warehouse_id": fulfillment_warehouse.id},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["created_pos_count"] == 1
        assert len(data["purchase_orders"]) == 1
        po = data["purchase_orders"][0]
        assert po["supplier_id"] == active_supplier_a.id
        assert po["warehouse_id"] == fulfillment_warehouse.id
        assert po["status"] == "draft"
        assert Decimal(str(po["subtotal"])) > Decimal("0.00")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
