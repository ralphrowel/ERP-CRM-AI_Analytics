"""Unit Tests for Events, Notifications, and Outbox Automation (Roadmap §V1.8)

Validates Milestone V1.8 Exit Criteria:
1. Killing the worker mid-processing loses no events; on restart they are processed exactly once (idempotent handlers).
2. A failing handler retries with backoff and ends in a visible dead-letter state.
3. No email or notification is sent from within an HTTP request.
4. Scheduled checks engine (daily cron jobs) enqueues accurate outbox events.
5. Notification endpoints and read-receipt lifecycle.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.clock import get_clock
from app.core.database import Base, get_db
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.catalog.models import Product
from app.modules.crm.schemas import CustomerCreate, OpportunityCreate
from app.modules.crm.service import CRMService
from app.modules.events.handlers import EVENT_HANDLER_REGISTRY
from app.modules.events.mailer import EmailDispatcher, clear_sent_emails, get_sent_emails
from app.modules.events.models import MAX_OUTBOX_ATTEMPTS, Notification, OutboxEvent
from app.modules.events.scheduler import ScheduledChecksEngine
from app.modules.events.service import NotificationService, OutboxService
from app.modules.events.worker import OutboxWorker
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole
from app.modules.identity.service import IdentityService
from app.modules.inventory.models import InventoryBalance, Warehouse
from app.modules.purchasing.models import PurchaseOrder, Supplier
from app.modules.sales.models import Invoice, Quote, TaxRate


@pytest.fixture
def events_db() -> Session:
    """Isolated in-memory database seeded with required schemas, roles, and sequences."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed Document Sequences
    seqs = [
        DocumentSequence(
            doc_type="customer", prefix="CUS", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="opportunity", prefix="OPP", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(doc_type="quote", prefix="QT", include_year=True, padding=6, next_value=1),
        DocumentSequence(
            doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="invoice", prefix="INV", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="purchase_order", prefix="PO", include_year=True, padding=6, next_value=1
        ),
    ]
    session.add_all(seqs)

    # Seed Tax Rate
    tr = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    session.add(tr)

    # Seed Standard Roles & Permissions
    r_purchasing = Role(code="purchasing", name="Purchasing")
    r_finance = Role(code="finance", name="Finance")
    r_sales = Role(code="sales", name="Sales")
    session.add_all([r_purchasing, r_finance, r_sales])
    session.flush()

    perm_approve = Permission(
        code="workflow:approve", description="Approve requests", module="workflow"
    )
    session.add(perm_approve)
    session.flush()

    session.add(RolePermission(role_id=r_purchasing.id, permission_id=perm_approve.id, scope="all"))
    session.commit()

    clear_sent_emails()
    return session


@pytest.fixture
def test_users(events_db: Session) -> dict[str, User]:
    """Sets up sample users across purchasing, finance, sales, and admin."""
    r_purch = events_db.execute(select(Role).where(Role.code == "purchasing")).scalar_one()
    r_fin = events_db.execute(select(Role).where(Role.code == "finance")).scalar_one()
    r_sales = events_db.execute(select(Role).where(Role.code == "sales")).scalar_one()

    admin = User(
        email="admin@company.com",
        password_hash=hash_password("Password123!"),
        full_name="Admin Boss",
        is_active=True,
        is_superuser=True,
    )
    purchaser = User(
        email="buyer@company.com",
        password_hash=hash_password("Password123!"),
        full_name="Peter Buyer",
        is_active=True,
    )
    financier = User(
        email="finance@company.com",
        password_hash=hash_password("Password123!"),
        full_name="Fiona Finance",
        is_active=True,
    )
    salesrep = User(
        email="rep@company.com",
        password_hash=hash_password("Password123!"),
        full_name="Sam Rep",
        is_active=True,
    )
    events_db.add_all([admin, purchaser, financier, salesrep])
    events_db.flush()

    events_db.add_all(
        [
            UserRole(user_id=purchaser.id, role_id=r_purch.id),
            UserRole(user_id=financier.id, role_id=r_fin.id),
            UserRole(user_id=salesrep.id, role_id=r_sales.id),
        ]
    )
    events_db.commit()

    return {
        "admin": admin,
        "purchaser": purchaser,
        "financier": financier,
        "salesrep": salesrep,
    }


# =============================================================================
# Exit Criterion 1: Worker crash recovery and idempotent replay
# =============================================================================


def test_worker_crash_recovery_loses_no_events_and_replays_idempotently(
    events_db: Session,
    test_users: dict[str, User],
):
    """
    Roadmap §V1.8 Exit Criterion 1:
    Killing the worker mid-processing loses no events; on restart they are processed exactly once.
    """
    buyer = test_users["purchaser"]

    # Enqueue outbox event
    event = OutboxService.record_event(
        db=events_db,
        event_type="inventory.below_reorder",
        aggregate_type="product",
        aggregate_id=101,
        payload={
            "product_id": 101,
            "product_name": "Industrial Widget X",
            "qty_on_hand": 2.0,
            "reorder_point": 10.0,
        },
    )
    events_db.commit()

    # Verify event is in pending state
    assert event.processed_at is None
    assert event.attempts == 0

    # Simulate worker crash mid-processing:
    # Worker executes handler, creating side effect, but process is "killed" before committing processed_at!
    handler = EVENT_HANDLER_REGISTRY["inventory.below_reorder"]
    mailer = EmailDispatcher()
    handler(events_db, event, mailer)
    events_db.commit()

    # Initial side effect created: 1 notification for purchaser
    notifs_initial = (
        events_db.execute(select(Notification).where(Notification.user_id == buyer.id))
        .scalars()
        .all()
    )
    assert len(notifs_initial) == 1
    assert "Low Stock Alert: Industrial Widget X" in notifs_initial[0].title

    # Worker was terminated before setting event.processed_at:
    # Event remains uncommitted in outbox
    event_refreshed = events_db.get(OutboxEvent, event.id)
    assert event_refreshed.processed_at is None

    # Restart Worker and process batch
    worker = OutboxWorker(db_factory=lambda: events_db, mailer=mailer)
    processed_count = worker.process_batch()
    assert processed_count == 1

    # Verify:
    # 1. Event marked as processed
    events_db.refresh(event_refreshed)
    assert event_refreshed.processed_at is not None

    # 2. Idempotent handler: NO duplicate notifications created (still exactly 1)!
    notifs_after = (
        events_db.execute(select(Notification).where(Notification.user_id == buyer.id))
        .scalars()
        .all()
    )
    assert len(notifs_after) == 1


# =============================================================================
# Exit Criterion 2: Failing handler retries with backoff and enters dead letter
# =============================================================================


def test_failing_handler_exponential_backoff_and_dead_letter_state(
    events_db: Session,
):
    """
    Roadmap §V1.8 Exit Criterion 2:
    A failing handler retries with backoff and ends in a visible dead-letter state.
    """
    clock = get_clock()

    # Register temporary failing handler
    def failing_handler(db, ev, mailer):
        raise ConnectionError("Simulated external gateway timeout")

    EVENT_HANDLER_REGISTRY["test.failing_event"] = failing_handler

    try:
        event = OutboxService.record_event(
            db=events_db,
            event_type="test.failing_event",
            aggregate_type="test",
            aggregate_id=999,
            payload={"test": "data"},
        )
        events_db.commit()

        worker = OutboxWorker(db_factory=lambda: events_db, max_attempts=MAX_OUTBOX_ATTEMPTS)

        # 1. First failure -> attempt 1, rescheduled with exponential backoff (2^1 = 2s)
        worker.process_batch()
        events_db.refresh(event)
        assert event.attempts == 1
        assert event.processed_at is None
        assert "ConnectionError" in event.last_error
        assert event.available_at > event.occurred_at

        # 2. Simulate subsequent retries until max attempts reached (MAX_OUTBOX_ATTEMPTS = 8)
        for i in range(2, MAX_OUTBOX_ATTEMPTS + 1):
            # Advance availability so worker picks it up
            event.available_at = clock.now() - timedelta(seconds=1)
            events_db.commit()
            worker.process_batch()
            events_db.refresh(event)
            assert event.attempts == i

        # 3. VERIFY DEAD-LETTER STATE REACHED
        assert event.is_dead_letter is True
        assert event.processed_at is None
        assert event.attempts == MAX_OUTBOX_ATTEMPTS

        # 4. Verify dead-letter event appears in dead-letter query
        dead_letters, total = OutboxService.list_dead_letters(events_db)
        assert total >= 1
        assert any(d.id == event.id for d in dead_letters)

        # 5. Admin retries dead-letter event
        retried = OutboxService.retry_dead_letter(events_db, event.id)
        assert retried.attempts == 0
        assert retried.last_error is None
        assert retried.is_dead_letter is False

    finally:
        EVENT_HANDLER_REGISTRY.pop("test.failing_event", None)


# =============================================================================
# Exit Criterion 3: No email or notification sent within HTTP request
# =============================================================================


def test_no_email_or_notification_sent_from_within_http_request(
    events_db: Session,
    test_users: dict[str, User],
):
    """
    Roadmap §V1.8 Exit Criterion 3:
    No email or notification is sent from within an HTTP request.
    Domain services and API endpoints strictly append to outbox_events.
    """
    clear_sent_emails()
    user = test_users["salesrep"]

    def override_get_db():
        yield events_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app, client=("127.0.0.1", 50000))

        # 1. Trigger HTTP endpoint requesting password reset
        res = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": user.email},
        )
        assert res.status_code == 200

        # 2. ASSERT: ZERO emails sent, ZERO notifications created inside HTTP request!
        assert len(get_sent_emails()) == 0
        notifs_in_db = events_db.execute(select(Notification)).scalars().all()
        assert len(notifs_in_db) == 0

        # 3. ASSERT: Outbox event was appended transactionally
        outbox_events = (
            events_db.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "password_reset.requested")
            )
            .scalars()
            .all()
        )
        assert len(outbox_events) == 1
        pw_event = outbox_events[0]
        assert pw_event.processed_at is None

        # 4. Now run background worker to process outbox
        mailer = EmailDispatcher()
        worker = OutboxWorker(db_factory=lambda: events_db, mailer=mailer)
        processed = worker.process_batch()
        assert processed == 1

        # 5. Worker processed the event: email dispatched and outbox marked processed!
        sent_emails = get_sent_emails()
        assert len(sent_emails) == 1
        assert sent_emails[0]["to"] == user.email
        assert "Password Reset" in sent_emails[0]["subject"]

        events_db.refresh(pw_event)
        assert pw_event.processed_at is not None

    finally:
        app.dependency_overrides.clear()


# =============================================================================
# Feature Test: Scheduled Business Checks Engine (Daily Cron Checks)
# =============================================================================


def test_scheduled_checks_engine_enqueues_outbox_events(
    events_db: Session,
    test_users: dict[str, User],
):
    """Validates the 5 daily cron checks enqueue proper outbox events and worker processes them."""
    salesrep = test_users["salesrep"]
    clock = get_clock()
    today = clock.now().date()
    yesterday = today - timedelta(days=1)
    future_5_days = today + timedelta(days=5)

    crm = CRMService(events_db)
    cust = crm.create_customer(
        CustomerCreate(
            name="Overdue Corp", customer_type="company", status="active", email="ap@overdue.ph"
        ),
        creator_id=salesrep.id,
    )

    # 1. Overdue Invoice (due yesterday)
    inv = Invoice(
        invoice_no="INV-2026-000099",
        customer_id=cust.id,
        status="issued",
        currency_code="PHP",
        subtotal=Decimal("2000.00"),
        tax_total=Decimal("240.00"),
        grand_total=Decimal("2240.00"),
        balance_due=Decimal("2240.00"),
        due_date=yesterday,
        created_by=salesrep.id,
    )
    events_db.add(inv)

    # 2. Expired Quote (valid_until was yesterday)
    quote = Quote(
        quote_no="QT-2026-000099",
        customer_id=cust.id,
        status="sent",
        valid_until=yesterday,
        currency_code="PHP",
        subtotal=Decimal("1000.00"),
        tax_total=Decimal("120.00"),
        grand_total=Decimal("1120.00"),
        created_by=salesrep.id,
    )
    events_db.add(quote)

    # 3. Opportunity closing in 5 days
    crm.create_opportunity(
        OpportunityCreate(
            name="Q4 Enterprise Deal",
            customer_id=cust.id,
            stage="proposal",
            estimated_amount=Decimal("150000.00"),
            expected_close_date=future_5_days,
            owner_user_id=salesrep.id,
        ),
        creator_id=salesrep.id,
    )

    # Warehouse
    wh = Warehouse(code="WH-MAIN", name="Main Warehouse", is_active=True)
    events_db.add(wh)
    events_db.flush()

    # 4. Delayed Purchase Order (expected_date yesterday)
    supplier = Supplier(
        supplier_no="SUP-2026-000001",
        name="Reliable Parts Corp",
        is_active=True,
        created_by=salesrep.id,
    )
    events_db.add(supplier)
    events_db.flush()

    po = PurchaseOrder(
        po_no="PO-2026-000099",
        supplier_id=supplier.id,
        warehouse_id=wh.id,
        order_date=yesterday,
        status="sent",
        expected_date=yesterday,
        subtotal=Decimal("5000.00"),
        tax_total=Decimal("600.00"),
        grand_total=Decimal("5600.00"),
        created_by=salesrep.id,
    )
    events_db.add(po)

    # 5. Low stock product below reorder point
    tr = events_db.execute(select(TaxRate)).scalars().first()
    prod = Product(
        sku="WIDGET-LOW",
        name="Low Stock Gizmo",
        uom="pc",
        product_type="stock",
        tax_rate_id=tr.id,
        reorder_point=Decimal("20.00"),
        is_active=True,
    )
    events_db.add(prod)
    events_db.flush()

    item = InventoryBalance(
        product_id=prod.id,
        warehouse_id=wh.id,
        qty_on_hand=Decimal("5.000"),
    )
    events_db.add(item)
    events_db.commit()

    # Run scheduled checks
    results = ScheduledChecksEngine.run_all_scheduled_checks(events_db)
    assert results["invoices_past_due"] >= 1
    assert results["quotes_expired"] >= 1
    assert results["opportunities_closing_soon"] >= 1
    assert results["pos_delayed"] >= 1
    assert results["inventory_below_reorder"] >= 1

    # Run OutboxWorker to process all generated events
    mailer = EmailDispatcher()
    worker = OutboxWorker(db_factory=lambda: events_db, mailer=mailer)
    processed = worker.process_batch(batch_size=100)
    assert processed >= 5

    # Verify side effects:
    # A. Quote status persisted to 'expired'
    events_db.refresh(quote)
    assert quote.status == "expired"

    # B. Notifications created for respective users
    notifs = events_db.execute(select(Notification)).scalars().all()
    assert len(notifs) >= 4
    categories = {n.category for n in notifs}
    assert "finance" in categories
    assert "sales" in categories
    assert "purchasing" in categories
    assert "inventory" in categories


# =============================================================================
# Feature Test: Notification Endpoints and Read Receipts
# =============================================================================


def test_notification_endpoints_and_read_receipts(
    events_db: Session,
    test_users: dict[str, User],
):
    """Validates /api/v1/notifications endpoints for listing, badge counts, and marking read."""
    salesrep = test_users["salesrep"]

    # Create 3 sample notifications
    n1 = NotificationService.create_notification(
        db=events_db,
        user_id=salesrep.id,
        title="Welcome to ERP",
        message="Your account is configured.",
        category="system",
    )
    NotificationService.create_notification(
        db=events_db,
        user_id=salesrep.id,
        title="New Lead Assigned",
        message="Lead LD-000001 has been assigned to you.",
        category="sales",
    )
    NotificationService.create_notification(
        db=events_db,
        user_id=salesrep.id,
        title="Opportunity Closing Soon",
        message="Deal closes tomorrow.",
        category="sales",
    )
    events_db.commit()

    # Authenticate salesrep
    identity_svc = IdentityService(events_db)
    _, token, _ = identity_svc.authenticate_user(salesrep.email, "Password123!")

    def override_get_db():
        yield events_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app, client=("127.0.0.1", 50000))
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Check unread count -> 3
        res_count = client.get("/api/v1/notifications/unread-count", headers=headers)
        assert res_count.status_code == 200
        assert res_count.json()["unread_count"] == 3

        # 2. List notifications
        res_list = client.get("/api/v1/notifications", headers=headers)
        assert res_list.status_code == 200
        data = res_list.json()
        assert data["total"] == 3
        assert data["unread_count"] == 3
        assert len(data["items"]) == 3

        # 3. Mark single notification as read
        res_read = client.patch(f"/api/v1/notifications/{n1.id}/read", headers=headers)
        assert res_read.status_code == 200
        assert res_read.json()["is_read"] is True

        res_count2 = client.get("/api/v1/notifications/unread-count", headers=headers)
        assert res_count2.json()["unread_count"] == 2

        # 4. Mark all read
        res_all = client.post("/api/v1/notifications/mark-all-read", headers=headers)
        assert res_all.status_code == 200
        assert res_all.json()["marked_read"] == 2

        res_count3 = client.get("/api/v1/notifications/unread-count", headers=headers)
        assert res_count3.json()["unread_count"] == 0

    finally:
        app.dependency_overrides.clear()
