"""Idempotent Event Handlers (Roadmap §V1.8)

Dispatches side effects for outbox events asynchronously:
- In-app notification creation
- Email notifications via EmailDispatcher
- State updates (e.g. quote expiration)
"""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.core.status_history import record_status_change
from app.modules.events.mailer import EmailDispatcher
from app.modules.events.models import OutboxEvent
from app.modules.events.service import NotificationService
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole
from app.modules.sales.models import Quote

logger = logging.getLogger("app.modules.events.handlers")


def get_users_with_permission(db: Session, permission_code: str) -> list[User]:
    """Retrieves all active users with the given permission code or superuser privilege."""
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == permission_code, User.is_active.is_(True))
    )
    matched = list(db.execute(stmt).scalars().all())
    su_stmt = select(User).where(User.is_superuser.is_(True), User.is_active.is_(True))
    superusers = list(db.execute(su_stmt).scalars().all())
    return list({u.id: u for u in (matched + superusers)}.values())


def get_users_with_role(db: Session, role_code: str) -> list[User]:
    """Retrieves all active users assigned the given role code or superuser privilege."""
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == role_code, User.is_active.is_(True))
    )
    matched = list(db.execute(stmt).scalars().all())
    su_stmt = select(User).where(User.is_superuser.is_(True), User.is_active.is_(True))
    superusers = list(db.execute(su_stmt).scalars().all())
    return list({u.id: u for u in (matched + superusers)}.values())


# ── Domain Event Handlers ────────────────────────────────────────────────────


def handle_inventory_below_reorder(
    db: Session, event: OutboxEvent, mailer: EmailDispatcher
) -> None:
    """Roadmap §1.8: Notify Purchasing; suggest PO when stock is below reorder point."""
    p = event.payload
    product_name = p.get("product_name", f"Product #{p.get('product_id')}")
    qty_on_hand = p.get("qty_on_hand", 0.0)
    reorder_point = p.get("reorder_point", 0.0)

    purchasers = get_users_with_role(db, "purchasing")
    for user in purchasers:
        NotificationService.create_notification(
            db=db,
            user_id=user.id,
            title=f"Low Stock Alert: {product_name}",
            message=(
                f"Stock level ({qty_on_hand}) is below reorder point ({reorder_point}). "
                "Suggested action: Create Purchase Order."
            ),
            category="inventory",
            entity_type="product",
            entity_id=p.get("product_id"),
        )


def handle_approval_request_created(
    db: Session, event: OutboxEvent, mailer: EmailDispatcher
) -> None:
    """Roadmap §1.8: Notify approvers when a new approval request is opened."""
    p = event.payload
    perm = p.get("approver_permission", "workflow:approve")
    doc_no = p.get("document_no", f"Request #{p.get('approval_request_id')}")
    entity_type = p.get("entity_type", "document")

    approvers = get_users_with_permission(db, perm)
    for approver in approvers:
        NotificationService.create_notification(
            db=db,
            user_id=approver.id,
            title=f"Approval Required: {doc_no}",
            message=f"A new {entity_type} ({doc_no}) requires your review and approval.",
            category="approval",
            entity_type=entity_type,
            entity_id=p.get("entity_id"),
        )
        if approver.email:
            mailer.send(
                to_email=approver.email,
                subject=f"Action Required: Approve {doc_no}",
                body=(
                    f"Dear {approver.full_name},\n\n"
                    f"A new {entity_type} ({doc_no}) has been submitted for approval.\n"
                    "Please log into the ERP to review and decide on this request.\n"
                ),
            )


def handle_password_reset_requested(
    db: Session, event: OutboxEvent, mailer: EmailDispatcher
) -> None:
    """Roadmap §1.8: Email reset link asynchronously without blocking HTTP request."""
    p = event.payload
    email = p.get("email")
    reset_token = p.get("reset_token")
    full_name = p.get("full_name", "User")

    if email and reset_token:
        mailer.send(
            to_email=email,
            subject="ERP Account Password Reset",
            body=(
                f"Dear {full_name},\n\n"
                "We received a request to reset your ERP password. "
                f"Your reset token is: {reset_token}\n\n"
                "If you did not request this, please ignore this email.\n"
            ),
        )


def handle_invoice_past_due(db: Session, event: OutboxEvent, mailer: EmailDispatcher) -> None:
    """Roadmap §1.8: Daily invoice past due reminder to owner + Finance + optional customer email."""
    p = event.payload
    inv_no = p.get("invoice_no")
    cust_name = p.get("customer_name", "Customer")
    balance_due = p.get("balance_due", "0.00")
    inv_id = p.get("invoice_id")

    recipients: set[int] = set()
    if p.get("owner_id"):
        recipients.add(p["owner_id"])

    finance_users = get_users_with_role(db, "finance")
    for u in finance_users:
        recipients.add(u.id)

    for uid in recipients:
        NotificationService.create_notification(
            db=db,
            user_id=uid,
            title=f"Invoice Overdue: {inv_no}",
            message=f"Invoice {inv_no} for {cust_name} is overdue (balance due: ₱{balance_due}).",
            category="finance",
            entity_type="invoice",
            entity_id=inv_id,
        )

    cust_email = p.get("customer_email")
    if cust_email:
        mailer.send(
            to_email=cust_email,
            subject=f"Statement Reminder: Invoice {inv_no} is Past Due",
            body=(
                f"Dear {cust_name},\n\n"
                f"This is a friendly reminder that Invoice {inv_no} with an outstanding balance "
                f"of ₱{balance_due} is past due.\n"
                "Please arrange for settlement at your earliest convenience.\n"
            ),
        )


def handle_quote_expired(db: Session, event: OutboxEvent, mailer: EmailDispatcher) -> None:
    """Roadmap §1.8: Daily: quotes past valid_until -> persist expired status idempotently."""
    clock = get_clock()
    p = event.payload
    quote_id = p.get("quote_id")
    quote = db.get(Quote, quote_id)
    if quote and quote.status == "sent":
        quote.status = "expired"
        record_status_change(
            db=db,
            entity_type="quote",
            entity_id=quote.id,
            from_status="sent",
            to_status="expired",
            reason=f"Quote expired past valid_until date ({p.get('valid_until')})",
            clock=clock,
        )
        db.flush()


def handle_opportunity_closing_soon(
    db: Session, event: OutboxEvent, mailer: EmailDispatcher
) -> None:
    """Roadmap §1.8: Daily: opportunities closing in 7 days -> notify owner."""
    p = event.payload
    owner_id = p.get("owner_id")
    name = p.get("name", "Deal")
    days = p.get("days_remaining", 7)
    amt = p.get("estimated_amount", "0.00")

    if owner_id:
        NotificationService.create_notification(
            db=db,
            user_id=owner_id,
            title=f"Deal Closing Soon: {name}",
            message=f"Opportunity '{name}' (₱{amt}) is scheduled to close in {days} days.",
            category="sales",
            entity_type="opportunity",
            entity_id=p.get("opportunity_id"),
        )


def handle_po_delayed(db: Session, event: OutboxEvent, mailer: EmailDispatcher) -> None:
    """Roadmap §1.8: Daily: POs past expected_date not received -> notify Purchasing."""
    p = event.payload
    po_no = p.get("po_no")
    supplier = p.get("supplier_name", "Vendor")
    exp_date = p.get("expected_date")

    purchasers = get_users_with_role(db, "purchasing")
    for u in purchasers:
        NotificationService.create_notification(
            db=db,
            user_id=u.id,
            title=f"Delayed PO: {po_no}",
            message=f"Purchase order {po_no} from {supplier} has passed expected date ({exp_date}).",
            category="purchasing",
            entity_type="purchase_order",
            entity_id=p.get("po_id"),
        )


# Handler registry mapping event_type to callable
EVENT_HANDLER_REGISTRY: dict[str, Callable[[Session, OutboxEvent, EmailDispatcher], None]] = {
    "inventory.below_reorder": handle_inventory_below_reorder,
    "approval_request.created": handle_approval_request_created,
    "password_reset.requested": handle_password_reset_requested,
    "sales.invoice_past_due": handle_invoice_past_due,
    "sales.quote_expired": handle_quote_expired,
    "crm.opportunity_closing_soon": handle_opportunity_closing_soon,
    "purchasing.po_delayed": handle_po_delayed,
}
