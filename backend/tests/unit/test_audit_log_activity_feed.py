"""
Unit tests for Milestone V0.8: Full Audit Log and Activity Feed
Covers:
1. Automatic before_flush diff generation on entity updates.
2. Transaction atomicity: rollback discards audit rows.
3. Excluded/masked fields: password_hash and tokens never logged.
4. Security event auditing: login, login_failed, logout.
5. Permission change auditing: role and role-permission updates.
6. Workflow state machine transition auditing.
7. Activity feed unification (audit_log ∪ status_history ∪ activities).
8. Audit log filtering by actor, action, entity, and date.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.clock import ControllableClock
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.modules.audit.context import sanitize_ip_address, set_audit_context
from app.modules.audit.models import AuditLog
from app.modules.audit.service import AuditService
from app.modules.crm.models import Activity, Customer
from app.modules.identity.models import Permission, Role, User
from app.modules.identity.schemas import RolePermissionInput, RoleUpdate
from app.modules.identity.service import IdentityService
from app.modules.sales.models import TaxRate
from app.modules.sales.schemas import LineItemPayload, SalesOrderCreatePayload
from app.modules.sales.service import SalesService

UTC = UTC


@pytest.fixture
def audit_setup(db_session: Session):
    clock = ControllableClock(initial_time=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC))

    # Seed document sequence
    existing_seq = db_session.query(DocumentSequence).filter_by(doc_type="customer").first()
    if not existing_seq:
        db_session.add(
            DocumentSequence(
                doc_type="customer", prefix="CUS", include_year=False, padding=6, next_value=1
            )
        )

    existing_so_seq = db_session.query(DocumentSequence).filter_by(doc_type="sales_order").first()
    if not existing_so_seq:
        db_session.add(
            DocumentSequence(
                doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
            )
        )

    # Seed users
    admin_user = User(
        email="admin_audit@corp.local",
        password_hash=hash_password("SuperSecure123!"),
        full_name="Audit Administrator",
        is_superuser=True,
        is_active=True,
    )
    sales_rep = User(
        email="rep_audit@corp.local",
        password_hash=hash_password("SalesPass123!"),
        full_name="Sales Rep Bob",
        is_superuser=False,
        is_active=True,
    )
    db_session.add_all([admin_user, sales_rep])
    db_session.flush()

    # Seed customer
    customer = Customer(
        customer_no="CUS000099",
        name="Global Acme Corp",
        customer_type="company",
        status="active",
        payment_terms_days=30,
        credit_limit=Decimal("50000.00"),
        owner_user_id=sales_rep.id,
    )
    db_session.add(customer)

    # Seed tax rate
    tr = db_session.query(TaxRate).filter_by(code="VAT12").first()
    if not tr:
        tr = TaxRate(
            code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
        )
        db_session.add(tr)

    db_session.commit()

    return {
        "clock": clock,
        "admin": admin_user,
        "rep": sales_rep,
        "customer": customer,
        "tax_rate": tr,
    }


# ── 1. Update Diff & Rollback Tests ─────────────────────────────────────────


def test_entity_update_captures_diff_in_audit_log(db_session: Session, audit_setup):
    customer = audit_setup["customer"]
    admin = audit_setup["admin"]

    # Set audit context for current request
    set_audit_context(actor_user_id=admin.id, request_id="REQ-101", ip_address="192.168.1.50")

    # Update customer credit limit and payment terms
    customer.credit_limit = Decimal("80000.00")
    customer.payment_terms_days = 45
    db_session.commit()

    # Verify audit log captured exact before/after values
    logs = (
        db_session.query(AuditLog)
        .filter_by(entity_type="customer", entity_id=customer.id, action="update")
        .all()
    )
    assert len(logs) == 1
    log = logs[0]
    assert log.actor_user_id == admin.id
    assert log.request_id == "REQ-101"
    assert str(log.ip_address) == "192.168.1.50"
    assert "credit_limit" in log.changes
    assert log.changes["credit_limit"] == ["50000.00", "80000.00"]
    assert "payment_terms_days" in log.changes
    assert log.changes["payment_terms_days"] == [30, 45]


def test_transaction_rollback_leaves_no_audit_row(db_session: Session, audit_setup):
    customer = audit_setup["customer"]
    admin = audit_setup["admin"]

    set_audit_context(actor_user_id=admin.id, request_id="REQ-ROLLBACK")

    # Mutate entity but roll back
    customer.credit_limit = Decimal("999999.00")
    db_session.flush()

    # Flush staged the audit row, but rollback must clear it
    db_session.rollback()

    logs = (
        db_session.query(AuditLog)
        .filter_by(entity_type="customer", entity_id=customer.id, action="update")
        .all()
    )
    assert len(logs) == 0


def test_password_hash_and_tokens_excluded_from_audit_changes(db_session: Session, audit_setup):
    rep = audit_setup["rep"]
    admin = audit_setup["admin"]

    set_audit_context(actor_user_id=admin.id, request_id="REQ-PASS-CHANGE")

    # Update rep user password and name
    rep.password_hash = hash_password("NewPassword999!")
    rep.full_name = "Bob Smith Updated"
    db_session.commit()

    logs = (
        db_session.query(AuditLog)
        .filter_by(entity_type="user", entity_id=rep.id, action="update")
        .all()
    )
    assert len(logs) == 1
    log = logs[0]
    assert "full_name" in log.changes
    assert log.changes["full_name"] == ["Sales Rep Bob", "Bob Smith Updated"]
    # Passwords must NEVER be recorded in changes
    assert "password_hash" not in log.changes
    assert "token_hash" not in log.changes


# ── 2. Security Events Tests ────────────────────────────────────────────────


def test_failed_login_records_audit_event(db_session: Session, audit_setup):
    from app.core.errors import UnauthorizedException

    id_svc = IdentityService(db_session, clock=audit_setup["clock"])

    # Attempt login with bad password
    with pytest.raises(UnauthorizedException):
        id_svc.authenticate_user(
            email="rep_audit@corp.local",
            password="WrongPassword!",
            ip_address="203.0.113.15",
        )

    # Verify login_failed audit log
    logs = db_session.query(AuditLog).filter_by(action="login_failed").all()
    assert len(logs) == 1
    log = logs[0]
    assert log.actor_user_id == audit_setup["rep"].id
    assert str(log.ip_address) == "203.0.113.15"
    assert log.changes["reason"] == "invalid_credentials"
    assert log.changes["email"] == "rep_audit@corp.local"


def test_successful_login_and_logout_records_audit_events(db_session: Session, audit_setup):
    id_svc = IdentityService(db_session, clock=audit_setup["clock"])

    # 1. Login
    user, token, _ = id_svc.authenticate_user(
        email="rep_audit@corp.local",
        password="SalesPass123!",
        ip_address="203.0.113.20",
    )
    assert user.id == audit_setup["rep"].id

    login_logs = db_session.query(AuditLog).filter_by(action="login", actor_user_id=user.id).all()
    assert len(login_logs) == 1
    assert str(login_logs[0].ip_address) == "203.0.113.20"

    # 2. Logout
    _, session = id_svc.validate_session(token)
    id_svc.logout_session(session)

    logout_logs = db_session.query(AuditLog).filter_by(action="logout", actor_user_id=user.id).all()
    assert len(logout_logs) == 1
    assert logout_logs[0].actor_user_id == user.id


# ── 3. Permission Changes & Workflow Transitions ────────────────────────────


def test_role_permission_change_records_audit_log(db_session: Session, audit_setup):
    id_svc = IdentityService(db_session, clock=audit_setup["clock"])
    admin = audit_setup["admin"]

    # Create custom role
    p1 = Permission(code="report:view", module="reporting", description="View reports")
    db_session.add(p1)
    db_session.flush()

    role = Role(code="auditor_role", name="Internal Auditor", is_system=False)
    db_session.add(role)
    db_session.commit()

    # Update role permissions
    id_svc.update_role(
        role_id=role.id,
        data=RoleUpdate(
            permissions=[RolePermissionInput(permission_id=p1.id, scope="all")],
            version=role.version,
        ),
        updater_id=admin.id,
    )

    perm_logs = db_session.query(AuditLog).filter_by(action="permission_change").all()
    assert len(perm_logs) >= 1
    assert any(log.entity_id == role.id for log in perm_logs)


def test_sales_order_transition_records_audit_and_history(db_session: Session, audit_setup):
    sales_svc = SalesService(db_session, clock=audit_setup["clock"])
    cust = audit_setup["customer"]
    rep = audit_setup["rep"]

    set_audit_context(actor_user_id=rep.id)

    # Create draft order
    payload = SalesOrderCreatePayload(
        customer_id=cust.id,
        items=[
            LineItemPayload(
                quantity=Decimal("1.000"),
                unit_price=Decimal("1000.0000"),
            )
        ],
    )
    so = sales_svc.create_sales_order(payload, current_user_id=rep.id)
    assert so.status == "draft"

    # Confirm order (triggers transition)
    confirmed_so = sales_svc.confirm_sales_order(so.id, current_user_id=rep.id)
    assert confirmed_so.status == "confirmed"

    # Verify transition audit log: initial creation (None -> draft) and confirmation (draft -> confirmed)
    trans_logs = (
        db_session.query(AuditLog)
        .filter_by(entity_type="sales_order", entity_id=so.id, action="transition")
        .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
        .all()
    )
    assert len(trans_logs) == 2
    assert trans_logs[0].changes == {"status": [None, "draft"]}
    assert trans_logs[1].changes == {"status": ["draft", "confirmed"]}


# ── 4. Activity Feed Unification ────────────────────────────────────────────


def test_activity_feed_unifies_audit_status_and_activities(db_session: Session, audit_setup):
    audit_svc = AuditService(db_session)
    cust = audit_setup["customer"]
    rep = audit_setup["rep"]

    # 1. Audit Log: direct field update
    set_audit_context(actor_user_id=rep.id)
    cust.name = "Global Acme Corporation International"
    db_session.commit()

    # 2. CRM Activity: phone call logged
    act = Activity(
        customer_id=cust.id,
        activity_type="call",
        subject="Quarterly Account Review",
        body="Client requested a 20% discount on upcoming machinery orders.",
        owner_user_id=rep.id,
    )
    db_session.add(act)
    db_session.commit()

    # Fetch combined activity feed
    feed_items, total = audit_svc.get_entity_activity_feed(
        entity_type="customer",
        entity_id=cust.id,
    )

    assert total >= 2
    sources = {item.source for item in feed_items}
    assert "audit" in sources
    assert "activity" in sources

    # Verify chronologically sorted (newest first)
    for i in range(len(feed_items) - 1):
        assert feed_items[i].timestamp >= feed_items[i + 1].timestamp


# ── 5. Audit Log Filtering ──────────────────────────────────────────────────


def test_audit_log_filtering_by_actor_and_action(db_session: Session, audit_setup):
    audit_svc = AuditService(db_session)
    admin = audit_setup["admin"]
    rep = audit_setup["rep"]

    # Seed different audit logs
    audit_svc.record_event(
        action="export",
        actor_user_id=admin.id,
        entity_type="customer",
        entity_id=1,
        changes={"format": "csv", "count": 100},
    )
    audit_svc.record_event(
        action="create",
        actor_user_id=rep.id,
        entity_type="quote",
        entity_id=5,
    )
    db_session.commit()

    # Filter by action='export'
    items, total = audit_svc.list_audit_logs(action="export")
    assert total >= 1
    assert all(it.action == "export" for it in items)

    # Filter by actor_user_id=rep.id
    items_rep, total_rep = audit_svc.list_audit_logs(actor_user_id=rep.id)
    assert total_rep >= 1
    assert all(it.actor_user_id == rep.id for it in items_rep)


def test_sanitize_ip_address_postgres_inet_compatibility():
    # TestClient default host string
    assert sanitize_ip_address("testclient") == "127.0.0.1"
    assert sanitize_ip_address("localhost") == "127.0.0.1"

    # Valid IPv4 and IPv6
    assert sanitize_ip_address("192.168.1.1") == "192.168.1.1"
    assert sanitize_ip_address("10.0.0.1") == "10.0.0.1"
    assert sanitize_ip_address("::1") == "::1"
    assert sanitize_ip_address("2001:db8::1") == "2001:db8::1"

    # Stripping port numbers
    assert sanitize_ip_address("127.0.0.1:8000") == "127.0.0.1"
    assert sanitize_ip_address("[::1]:8080") == "::1"

    # Invalid / empty strings return None
    assert sanitize_ip_address(None) is None
    assert sanitize_ip_address("") is None
    assert sanitize_ip_address("   ") is None
    assert sanitize_ip_address("invalid-hostname-not-ip") is None
