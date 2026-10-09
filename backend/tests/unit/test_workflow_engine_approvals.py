from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import ControllableClock
from app.core.errors import (
    BusinessRuleError,
    ConflictException,
    ForbiddenException,
)
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.core.status_history import get_entity_history
from app.core.workflow.exceptions import (
    GuardViolationError,
)
from app.core.workflow.state_machine import StateMachine
from app.core.workflow.transition import Transition
from app.modules.catalog.models import Product
from app.modules.crm.models import Customer
from app.modules.identity.models import Permission, Role, RolePermission, User
from app.modules.inventory.models import Warehouse
from app.modules.purchasing.models import PurchaseOrder, PurchaseOrderItem, Supplier
from app.modules.purchasing.service import PurchasingService
from app.modules.sales.models import SalesOrder, TaxRate
from app.modules.sales.schemas import LineItemPayload, SalesOrderCreatePayload
from app.modules.sales.service import SalesService
from app.modules.workflow.models import ApprovalRequest, ApprovalRule
from app.modules.workflow.schemas import ApprovalRuleUpdate
from app.modules.workflow.service import WorkflowService

UTC = UTC


@pytest.fixture
def wf_setup(db_session: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))

    # Document sequences
    existing_seqs = {s.doc_type for s in db_session.query(DocumentSequence).all()}
    for dt, pfx, yr, pad in [
        ("customer", "CUS", False, 6),
        ("quote", "QT", True, 6),
        ("sales_order", "SO", True, 6),
        ("purchase_order", "PO", True, 6),
        ("supplier", "SUP", False, 6),
    ]:
        if dt not in existing_seqs:
            db_session.add(
                DocumentSequence(
                    doc_type=dt, prefix=pfx, include_year=yr, padding=pad, next_value=1
                )
            )

    # Tax Rate
    tr = db_session.query(TaxRate).filter_by(code="VAT12").first()
    if not tr:
        tr = TaxRate(
            code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
        )
        db_session.add(tr)
        db_session.flush()

    # Product
    prod = Product(
        sku="ITEM-01",
        name="Industrial Machine",
        uom="pc",
        list_price=Decimal("10000.0000"),
        tax_rate_id=tr.id,
        product_type="stock",
        is_active=True,
    )
    db_session.add(prod)

    # Customer
    cust = Customer(
        customer_no="CUS000001",
        name="Alpha Corporation",
        customer_type="company",
        status="active",
        payment_terms_days=30,
        credit_limit=Decimal("50000.00"),
    )
    db_session.add(cust)

    # Supplier
    sup = Supplier(
        supplier_no="SUP000001",
        name="Mega Parts Supply",
        payment_terms_days=30,
        address="789 Supplier Blvd, Metro Manila",
        is_active=True,
    )
    db_session.add(sup)

    # Warehouse
    wh = db_session.query(Warehouse).filter_by(code="WH-MAIN").first()
    if not wh:
        wh = Warehouse(
            code="WH-MAIN",
            name="Main Warehouse",
            address="123 Warehouse Way, Industrial District",
            is_active=True,
            is_default=True,
        )
        db_session.add(wh)
    db_session.flush()

    # Users
    rep_user = User(
        email="rep@corp.local",
        password_hash=hash_password("Pass123!"),
        full_name="Sales Rep Alice",
        is_active=True,
    )
    mgr_user = User(
        email="mgr@corp.local",
        password_hash=hash_password("Pass123!"),
        full_name="Sales Manager Bob",
        is_active=True,
    )
    db_session.add_all([rep_user, mgr_user])
    db_session.flush()

    # Permissions & Roles
    p_so_approve = Permission(
        code="sales_order:approve", module="sales", description="Approve SO discounts"
    )
    p_credit_ovr = Permission(
        code="credit:override", module="sales", description="Override credit limit"
    )
    p_po_approve = Permission(
        code="purchase_order:approve", module="purchasing", description="Approve PO amounts"
    )
    db_session.add_all([p_so_approve, p_credit_ovr, p_po_approve])
    db_session.flush()

    role_mgr = Role(code="sales_mgr_role", name="Sales Manager", is_system=False)
    db_session.add(role_mgr)
    db_session.flush()

    db_session.add_all(
        [
            RolePermission(role_id=role_mgr.id, permission_id=p_so_approve.id, scope="all"),
            RolePermission(role_id=role_mgr.id, permission_id=p_credit_ovr.id, scope="all"),
            RolePermission(role_id=role_mgr.id, permission_id=p_po_approve.id, scope="all"),
        ]
    )

    # Initial Approval Rules
    rule_disc = ApprovalRule(
        code="SO_DISCOUNT",
        entity_type="sales_order",
        description="Order discount > 15%",
        threshold_pct=Decimal("0.1500"),
        approver_permission="sales_order:approve",
        is_active=True,
    )
    rule_credit = ApprovalRule(
        code="CREDIT_OVERRIDE",
        entity_type="sales_order",
        description="Customer credit limit exceeded",
        threshold_amount=None,
        approver_permission="credit:override",
        is_active=True,
    )
    rule_po = ApprovalRule(
        code="PO_AMOUNT",
        entity_type="purchase_order",
        description="PO amount > ₱100,000",
        threshold_amount=Decimal("100000.00"),
        approver_permission="purchase_order:approve",
        is_active=True,
    )
    db_session.add_all([rule_disc, rule_credit, rule_po])
    db_session.commit()

    return {
        "clock": clock,
        "rep_user": rep_user,
        "mgr_user": mgr_user,
        "customer": cust,
        "product": prod,
        "supplier": sup,
        "warehouse": wh,
        "rule_disc": rule_disc,
        "rule_credit": rule_credit,
        "rule_po": rule_po,
    }


# ── 1. Generic State Machine Engine Tests ────────────────────────────────


def test_state_machine_engine_basic_transition_and_history(db_session: Session, wf_setup):
    class MockDocument:
        id = 101
        status = "draft"

    doc = MockDocument()

    machine = StateMachine(
        name="TestDocLifecycle",
        entity_type="mock_doc",
        transitions=[
            Transition(from_state="draft", to_state="submitted"),
            Transition(from_state="submitted", to_state="approved"),
        ],
    )

    assert machine.can_transition(doc, "submitted") is True
    assert machine.can_transition(doc, "approved") is False

    # Execute transition
    machine.trigger(doc, "submitted", db=db_session, user_id=wf_setup["rep_user"].id)
    db_session.flush()

    assert doc.status == "submitted"
    history = get_entity_history(db_session, "mock_doc", 101)
    assert len(history) == 1
    assert history[0].from_status == "draft"
    assert history[0].to_status == "submitted"
    assert history[0].changed_by == wf_setup["rep_user"].id


def test_state_machine_engine_guard_blocks_transition(db_session: Session):
    class MockOrder:
        id = 202
        status = "draft"
        is_valid = False

    order = MockOrder()

    def check_is_valid(entity, ctx, db):
        if not entity.is_valid:
            return False, "Order cannot be confirmed because is_valid is False."
        return True, None

    machine = StateMachine(
        name="GuardedMachine",
        entity_type="mock_order",
        transitions=[
            Transition(
                from_state="draft",
                to_state="confirmed",
                guards=[check_is_valid],
            ),
        ],
    )

    with pytest.raises(GuardViolationError) as exc:
        machine.trigger(order, "confirmed", db=db_session)
    assert "is_valid is False" in str(exc.value)
    assert order.status == "draft"  # State preserved


def test_state_machine_engine_permission_check(db_session: Session, wf_setup):
    class MockDoc:
        id = 303
        status = "draft"

    doc = MockDoc()

    class FakeContext:
        user = wf_setup["rep_user"]
        permissions = {"doc:view"}  # Lacks doc:approve

    machine = StateMachine(
        name="SecureMachine",
        entity_type="mock_doc",
        transitions=[
            Transition(from_state="draft", to_state="approved", permission="doc:approve"),
        ],
    )

    with pytest.raises(ForbiddenException):
        machine.trigger(doc, "approved", db=db_session, context=FakeContext())


# ── 2. Approval Workflow Business Logic Tests ────────────────────────────


def test_sales_order_discount_threshold_approval_flow(db_session: Session, wf_setup):
    clock = wf_setup["clock"]
    sales_svc = SalesService(db_session, clock=clock)
    cust = wf_setup["customer"]
    rep_user = wf_setup["rep_user"]

    # Create order with 20% discount (₱2,000 discount on ₱10,000 subtotal)
    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("10000.0000"),
                discount_amount=Decimal("2000.00"),  # 20% discount > 15% threshold
            )
        ],
    )
    so = sales_svc.create_sales_order(payload, current_user_id=rep_user.id)
    assert so.status == "draft"

    # Confirming order triggers approval requirement
    with pytest.raises(BusinessRuleError) as exc:
        sales_svc.confirm_sales_order(so.id, current_user_id=rep_user.id)
    assert exc.value.code == "APPROVAL_REQUIRED"

    # Verify order is placed into pending_approval state
    reloaded_so = db_session.get(SalesOrder, so.id)
    assert reloaded_so.status == "pending_approval"

    # Verify ApprovalRequest created in DB
    req = (
        db_session.query(ApprovalRequest)
        .filter_by(entity_type="sales_order", entity_id=so.id)
        .first()
    )
    assert req is not None
    assert req.status == "pending"
    assert req.requested_by == rep_user.id
    assert req.rule.code == "SO_DISCOUNT"


def test_separation_of_duties_requester_cannot_approve_own_request(db_session: Session, wf_setup):
    wf_svc = WorkflowService(db_session)
    rep_user = wf_setup["rep_user"]

    # Create pending request requested by rep_user
    req = ApprovalRequest(
        rule_id=wf_setup["rule_disc"].id,
        entity_type="sales_order",
        entity_id=999,
        status="pending",
        requested_by=rep_user.id,
    )
    db_session.add(req)
    db_session.commit()

    # Rep tries to approve their own request -> blocked by Separation of Duties
    with pytest.raises(BusinessRuleError) as exc:
        wf_svc.decide_request(
            request_id=req.id,
            decision="approved",
            decider=rep_user,
            comment="I approve myself",
            decider_permissions={"sales_order:approve": "all"},
        )
    assert exc.value.code == "SEPARATION_OF_DUTIES_VIOLATION"
    assert req.status == "pending"


def test_different_user_approves_order_and_confirms(db_session: Session, wf_setup):
    clock = wf_setup["clock"]
    sales_svc = SalesService(db_session, clock=clock)
    wf_svc = WorkflowService(db_session)
    cust = wf_setup["customer"]
    rep_user = wf_setup["rep_user"]
    mgr_user = wf_setup["mgr_user"]

    # Create high-discount order
    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("10000.0000"),
                discount_amount=Decimal("2500.00"),  # 25% discount
            )
        ],
    )
    so = sales_svc.create_sales_order(payload, current_user_id=rep_user.id)

    with pytest.raises(BusinessRuleError):
        sales_svc.confirm_sales_order(so.id, current_user_id=rep_user.id)

    assert so.status == "pending_approval"
    req = (
        db_session.query(ApprovalRequest)
        .filter_by(entity_type="sales_order", entity_id=so.id)
        .first()
    )

    # Manager approves the request
    wf_svc.decide_request(
        request_id=req.id,
        decision="approved",
        decider=mgr_user,
        comment="Authorized VIP client discount.",
        decider_permissions={"sales_order:approve": "all"},
    )

    db_session.commit()
    reloaded_so = db_session.get(SalesOrder, so.id)
    assert req.status == "approved"
    assert reloaded_so.status == "confirmed"


def test_rejection_returns_document_to_draft(db_session: Session, wf_setup):
    clock = wf_setup["clock"]
    sales_svc = SalesService(db_session, clock=clock)
    wf_svc = WorkflowService(db_session)
    cust = wf_setup["customer"]
    rep_user = wf_setup["rep_user"]
    mgr_user = wf_setup["mgr_user"]

    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("10000.0000"),
                discount_amount=Decimal("3000.00"),  # 30% discount
            )
        ],
    )
    so = sales_svc.create_sales_order(payload, current_user_id=rep_user.id)
    with pytest.raises(BusinessRuleError):
        sales_svc.confirm_sales_order(so.id, current_user_id=rep_user.id)

    req = (
        db_session.query(ApprovalRequest)
        .filter_by(entity_type="sales_order", entity_id=so.id)
        .first()
    )

    # Manager rejects the request
    wf_svc.decide_request(
        request_id=req.id,
        decision="rejected",
        decider=mgr_user,
        comment="Discount exceeds maximum authorized budget.",
        decider_permissions={"sales_order:approve": "all"},
    )

    db_session.commit()
    reloaded_so = db_session.get(SalesOrder, so.id)
    assert req.status == "rejected"
    assert reloaded_so.status == "draft"  # Returned to draft


def test_purchase_order_spend_threshold_approval(db_session: Session, wf_setup):
    purch_svc = PurchasingService(db_session)
    wf_svc = WorkflowService(db_session)
    sup = wf_setup["supplier"]
    mgr_user = wf_setup["mgr_user"]

    # Create PO with total > ₱100,000 (₱150,000)
    po = PurchaseOrder(
        po_no="PO2026-00001",
        supplier_id=sup.id,
        warehouse_id=wf_setup["warehouse"].id,
        status="draft",
        order_date=date(2026, 3, 1),
        subtotal=Decimal("150000.00"),
        tax_total=Decimal("0.00"),
        grand_total=Decimal("150000.00"),
        created_by=wf_setup["rep_user"].id,
    )
    db_session.add(po)
    db_session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        line_no=1,
        product_id=wf_setup["product"].id,
        description="Generator Component",
        uom="pc",
        quantity=Decimal("1.000"),
        unit_cost=Decimal("150000.00"),
        tax_rate_id=wf_setup["product"].tax_rate_id,
        tax_rate=Decimal("0.0000"),
        line_net=Decimal("150000.00"),
        line_tax=Decimal("0.00"),
        line_total=Decimal("150000.00"),
    )
    db_session.add(po_item)
    db_session.commit()

    # Sending PO triggers PO_AMOUNT approval rule
    with pytest.raises(Exception) as exc:
        purch_svc.send_purchase_order(po.id, user_id=wf_setup["rep_user"].id)
    assert exc.value.code == "APPROVAL_REQUIRED"

    assert po.status == "pending_approval"
    req = (
        db_session.query(ApprovalRequest)
        .filter_by(entity_type="purchase_order", entity_id=po.id)
        .first()
    )
    assert req is not None

    # Purchasing manager approves
    wf_svc.decide_request(
        request_id=req.id,
        decision="approved",
        decider=mgr_user,
        comment="Approved capital expenditure.",
        decider_permissions={"purchase_order:approve": "all"},
    )
    db_session.commit()

    reloaded_po = db_session.get(PurchaseOrder, po.id)
    assert reloaded_po.status == "sent"


def test_dynamic_threshold_update_without_deploy(db_session: Session, wf_setup):
    wf_svc = WorkflowService(db_session)
    sales_svc = SalesService(db_session, clock=wf_setup["clock"])
    rule_disc = wf_setup["rule_disc"]
    cust = wf_setup["customer"]

    # Admin updates threshold from 15% to 30% dynamically in DB
    updated_rule = wf_svc.update_rule(
        rule_id=rule_disc.id,
        payload=ApprovalRuleUpdate(
            threshold_pct=Decimal("0.3000"),  # 30%
            version=rule_disc.version,
        ),
        updater_id=wf_setup["mgr_user"].id,
    )
    db_session.commit()
    assert updated_rule.threshold_pct == Decimal("0.3000")

    # Order with 20% discount now confirms directly without needing approval!
    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("10000.0000"),
                discount_amount=Decimal("2000.00"),  # 20% <= 30%
            )
        ],
    )
    so = sales_svc.create_sales_order(payload)
    confirmed_so = sales_svc.confirm_sales_order(so.id)
    assert confirmed_so.status == "confirmed"


def test_concurrency_conflict_on_rule_update(db_session: Session, wf_setup):
    wf_svc = WorkflowService(db_session)
    rule = wf_setup["rule_disc"]

    # Stale version update raises ConflictException
    with pytest.raises(ConflictException):
        wf_svc.update_rule(
            rule_id=rule.id,
            payload=ApprovalRuleUpdate(
                threshold_pct=Decimal("0.5000"),
                version=rule.version + 999,  # Stale version
            ),
        )
