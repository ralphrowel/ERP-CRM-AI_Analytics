from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import get_clock
from app.core.errors import (
    BusinessRuleException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.core.status_history import record_status_change
from app.modules.identity.models import User
from app.modules.workflow.models import ApprovalRequest, ApprovalRule
from app.modules.workflow.schemas import (
    ApprovalRequestResponse,
    ApprovalRuleResponse,
    ApprovalRuleUpdate,
)


class WorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Approval Rules ───────────────────────────────────────────────────

    def list_rules(self, entity_type: str | None = None) -> list[ApprovalRuleResponse]:
        stmt = select(ApprovalRule)
        if entity_type:
            stmt = stmt.where(ApprovalRule.entity_type == entity_type)
        stmt = stmt.order_by(ApprovalRule.id.asc())
        rules = self.db.execute(stmt).scalars().all()
        return [ApprovalRuleResponse.model_validate(r) for r in rules]

    def get_rule_by_code(self, code: str) -> ApprovalRule | None:
        return self.db.execute(
            select(ApprovalRule).where(ApprovalRule.code == code)
        ).scalar_one_or_none()

    def update_rule(
        self, rule_id: int, payload: ApprovalRuleUpdate, updater_id: int | None = None
    ) -> ApprovalRuleResponse:
        rule = self.db.get(ApprovalRule, rule_id)
        if not rule:
            raise NotFoundException(f"Approval rule with ID {rule_id} not found.")

        if rule.version != payload.version:
            raise ConflictException(
                "Approval rule was modified by another transaction. Please reload."
            )

        if payload.description is not None:
            rule.description = payload.description
        if payload.threshold_amount is not None:
            rule.threshold_amount = payload.threshold_amount
        if payload.threshold_pct is not None:
            rule.threshold_pct = payload.threshold_pct
        if payload.approver_permission is not None:
            rule.approver_permission = payload.approver_permission
        if payload.is_active is not None:
            rule.is_active = payload.is_active

        rule.version += 1
        rule.updated_by = updater_id
        self.db.flush()
        return ApprovalRuleResponse.model_validate(rule)

    # ── Approval Requests Evaluation ─────────────────────────────────────

    def check_sales_order_approval(
        self,
        order: Any,
        requester_id: int,
        credit_exceeded: bool = False,
    ) -> list[ApprovalRequest]:
        """
        Evaluates Sales Order rules:
        1. SO_DISCOUNT: if discount percentage > threshold_pct
        2. CREDIT_OVERRIDE: if customer credit limit is exceeded
        """
        requests_created: list[ApprovalRequest] = []

        # 1. Discount rule
        disc_rule = self.get_rule_by_code("SO_DISCOUNT")
        if disc_rule and disc_rule.is_active and disc_rule.threshold_pct is not None:
            total_before_disc = order.subtotal + order.discount_total
            if total_before_disc > Decimal("0.00"):
                disc_pct = order.discount_total / total_before_disc
                if disc_pct > disc_rule.threshold_pct:
                    req = self._get_or_create_pending_request(
                        rule=disc_rule,
                        entity_type="sales_order",
                        entity_id=order.id,
                        requester_id=requester_id,
                        comment=f"Order discount rate of {disc_pct * 100:.2f}% exceeds threshold of {disc_rule.threshold_pct * 100:.2f}%.",
                    )
                    requests_created.append(req)

        # 2. Credit override rule
        if credit_exceeded:
            credit_rule = self.get_rule_by_code("CREDIT_OVERRIDE")
            if credit_rule and credit_rule.is_active:
                req = self._get_or_create_pending_request(
                    rule=credit_rule,
                    entity_type="sales_order",
                    entity_id=order.id,
                    requester_id=requester_id,
                    comment="Order confirmation would exceed customer credit limit.",
                )
                requests_created.append(req)

        return requests_created

    def check_purchase_order_approval(
        self,
        order: Any,
        requester_id: int,
    ) -> list[ApprovalRequest]:
        """
        Evaluates Purchase Order rules:
        PO_AMOUNT: grand_total > threshold_amount
        """
        requests_created: list[ApprovalRequest] = []
        rule = self.get_rule_by_code("PO_AMOUNT")
        if rule and rule.is_active and rule.threshold_amount is not None:
            if order.grand_total > rule.threshold_amount:
                req = self._get_or_create_pending_request(
                    rule=rule,
                    entity_type="purchase_order",
                    entity_id=order.id,
                    requester_id=requester_id,
                    comment=f"Purchase order total ₱{order.grand_total:,.2f} exceeds threshold ₱{rule.threshold_amount:,.2f}.",
                )
                requests_created.append(req)

        return requests_created

    def check_stock_adjustment_approval(
        self,
        adjustment_id: int,
        total_abs_value: Decimal,
        requester_id: int,
    ) -> list[ApprovalRequest]:
        """
        Evaluates Stock Adjustment rule:
        ADJ_VALUE: absolute total adjustment value > threshold_amount
        """
        requests_created: list[ApprovalRequest] = []
        rule = self.get_rule_by_code("ADJ_VALUE")
        if rule and rule.is_active and rule.threshold_amount is not None:
            if total_abs_value > rule.threshold_amount:
                req = self._get_or_create_pending_request(
                    rule=rule,
                    entity_type="stock_adjustment",
                    entity_id=adjustment_id,
                    requester_id=requester_id,
                    comment=f"Stock adjustment value ₱{total_abs_value:,.2f} exceeds threshold ₱{rule.threshold_amount:,.2f}.",
                )
                requests_created.append(req)

        return requests_created

    def check_supplier_invoice_exception_approval(
        self,
        invoice_id: int,
        requester_id: int,
        exception_reason: str,
    ) -> list[ApprovalRequest]:
        """
        Evaluates Supplier Invoice rule:
        BILL_EXCEPTION: 3-way match exception requires override approval
        """
        requests_created: list[ApprovalRequest] = []
        rule = self.get_rule_by_code("BILL_EXCEPTION")
        if rule and rule.is_active:
            req = self._get_or_create_pending_request(
                rule=rule,
                entity_type="supplier_invoice",
                entity_id=invoice_id,
                requester_id=requester_id,
                comment=f"Supplier bill 3-way match exception: {exception_reason}",
            )
            requests_created.append(req)

        return requests_created

    def _get_or_create_pending_request(
        self,
        rule: ApprovalRule,
        entity_type: str,
        entity_id: int,
        requester_id: int,
        comment: str,
    ) -> ApprovalRequest:
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.rule_id == rule.id,
            ApprovalRequest.entity_type == entity_type,
            ApprovalRequest.entity_id == entity_id,
            ApprovalRequest.status == "pending",
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

        clock = get_clock()
        req = ApprovalRequest(
            rule_id=rule.id,
            entity_type=entity_type,
            entity_id=entity_id,
            status="pending",
            requested_by=requester_id,
            requested_at=clock.now(),
            comment=comment,
        )
        self.db.add(req)
        self.db.flush()
        return req

    # ── Approval Decision ────────────────────────────────────────────────

    def decide_request(
        self,
        request_id: int,
        decision: str,  # 'approved' | 'rejected'
        decider: User,
        comment: str | None = None,
        decider_permissions: dict[str, str] | None = None,
    ) -> ApprovalRequestResponse:
        stmt = (
            select(ApprovalRequest)
            .options(
                joinedload(ApprovalRequest.rule),
                joinedload(ApprovalRequest.requester),
                joinedload(ApprovalRequest.decider),
            )
            .where(ApprovalRequest.id == request_id)
        )
        req = self.db.execute(stmt).scalar_one_or_none()
        if not req:
            raise NotFoundException(f"Approval request with ID {request_id} not found.")

        if req.status != "pending":
            raise BusinessRuleException(
                code="ALREADY_DECIDED",
                detail=f"Approval request is already '{req.status}' and cannot be decided again.",
            )

        # 1. Strict Separation of Duties: requester cannot decide own request
        if req.requested_by == decider.id:
            raise BusinessRuleException(
                code="SEPARATION_OF_DUTIES_VIOLATION",
                detail="Separation of duties violation: requester cannot approve or reject their own request.",
            )

        # 2. Check decider has required permission
        if not decider.is_superuser:
            perms = decider_permissions or {}
            required_perm = req.rule.approver_permission
            if required_perm not in perms:
                raise ForbiddenException(
                    detail=f"Permission '{required_perm}' required to decide this approval request."
                )

        clock = get_clock()
        req.status = decision
        req.decided_by = decider.id
        req.decided_at = clock.now()
        if comment:
            req.comment = f"{req.comment or ''} [Decision note: {comment}]".strip()

        self.db.flush()

        # Execute document status callbacks
        self._handle_post_decision(req, decision, decider.id)

        return self._to_response(req)

    def _handle_post_decision(self, req: ApprovalRequest, decision: str, decider_id: int) -> None:
        """
        Executes document updates based on approval decisions:
        - Rejection returns document to draft
        - Approval checks if all pending requests are approved, then confirms/advances document
        """
        clock = get_clock()

        if req.entity_type == "sales_order":
            from app.modules.sales.models import SalesOrder

            order = self.db.get(SalesOrder, req.entity_id)
            if not order:
                return

            if decision == "rejected":
                # Return sales order to draft
                order.status = "draft"
                record_status_change(
                    db=self.db,
                    entity_type="sales_order",
                    entity_id=order.id,
                    to_status="draft",
                    from_status="pending_approval",
                    reason=f"Approval rejected by reviewer: {req.comment}",
                    changed_by=decider_id,
                    clock=clock,
                )
            elif decision == "approved":
                # Check if all pending requests for this order are resolved
                has_pending = (
                    self.db.execute(
                        select(func.count(ApprovalRequest.id)).where(
                            ApprovalRequest.entity_type == "sales_order",
                            ApprovalRequest.entity_id == order.id,
                            ApprovalRequest.status == "pending",
                        )
                    ).scalar()
                    or 0
                )
                if has_pending == 0:
                    order.status = "confirmed"
                    record_status_change(
                        db=self.db,
                        entity_type="sales_order",
                        entity_id=order.id,
                        to_status="confirmed",
                        from_status="pending_approval",
                        reason="All approval requests approved.",
                        changed_by=decider_id,
                        clock=clock,
                    )

        elif req.entity_type == "purchase_order":
            from app.modules.purchasing.models import PurchaseOrder

            po = self.db.get(PurchaseOrder, req.entity_id)
            if not po:
                return

            if decision == "rejected":
                po.status = "draft"
                record_status_change(
                    db=self.db,
                    entity_type="purchase_order",
                    entity_id=po.id,
                    to_status="draft",
                    from_status="pending_approval",
                    reason=f"Approval rejected by reviewer: {req.comment}",
                    changed_by=decider_id,
                    clock=clock,
                )
            elif decision == "approved":
                has_pending = (
                    self.db.execute(
                        select(func.count(ApprovalRequest.id)).where(
                            ApprovalRequest.entity_type == "purchase_order",
                            ApprovalRequest.entity_id == po.id,
                            ApprovalRequest.status == "pending",
                        )
                    ).scalar()
                    or 0
                )
                if has_pending == 0:
                    po.status = "sent"
                    po.sent_at = clock.now()
                    record_status_change(
                        db=self.db,
                        entity_type="purchase_order",
                        entity_id=po.id,
                        to_status="sent",
                        from_status="pending_approval",
                        reason="Approval request approved.",
                        changed_by=decider_id,
                        clock=clock,
                    )

        self.db.flush()

    # ── Approval Requests Queries ────────────────────────────────────────

    def list_requests(
        self,
        status: str | None = None,
        entity_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ApprovalRequestResponse], int]:
        stmt = select(ApprovalRequest).options(
            joinedload(ApprovalRequest.rule),
            joinedload(ApprovalRequest.requester),
            joinedload(ApprovalRequest.decider),
        )
        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        if entity_type:
            stmt = stmt.where(ApprovalRequest.entity_type == entity_type)

        total = (
            self.db.execute(
                select(func.count(ApprovalRequest.id)).where(
                    *([ApprovalRequest.status == status] if status else []),
                    *([ApprovalRequest.entity_type == entity_type] if entity_type else []),
                )
            ).scalar()
            or 0
        )

        stmt = (
            stmt.order_by(ApprovalRequest.requested_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = self.db.execute(stmt).scalars().all()
        return [self._to_response(r) for r in items], total

    def get_request(self, request_id: int) -> ApprovalRequestResponse:
        stmt = (
            select(ApprovalRequest)
            .options(
                joinedload(ApprovalRequest.rule),
                joinedload(ApprovalRequest.requester),
                joinedload(ApprovalRequest.decider),
            )
            .where(ApprovalRequest.id == request_id)
        )
        req = self.db.execute(stmt).scalar_one_or_none()
        if not req:
            raise NotFoundException(f"Approval request with ID {request_id} not found.")
        return self._to_response(req)

    def _to_response(self, req: ApprovalRequest) -> ApprovalRequestResponse:
        return ApprovalRequestResponse(
            id=req.id,
            rule_id=req.rule_id,
            rule_code=req.rule.code if req.rule else "",
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            status=req.status,
            requested_by=req.requested_by,
            requester_name=req.requester.full_name if req.requester else f"User {req.requested_by}",
            requested_at=req.requested_at,
            decided_by=req.decided_by,
            decider_name=req.decider.full_name if req.decider else None,
            decided_at=req.decided_at,
            comment=req.comment,
        )
