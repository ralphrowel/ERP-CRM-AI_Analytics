"""Deterministic Read-Only Assistant Tools (Roadmap §V1.7)

Design Invariants:
1. Every tool wraps existing domain service functions or scoped queries.
2. Runs AS the requesting user using ScopeContext (own vs department vs all).
3. Strictly read-only: No tool mutates any database record.
4. Every tool invocation logs an audit trail event with action='ai_tool_call'.
"""

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.authorization import ScopeContext, apply_scope
from app.modules.audit.service import AuditService
from app.modules.crm.models import Activity, Customer, Lead, Opportunity
from app.modules.crm.service import CRMService
from app.modules.identity.models import User
from app.modules.sales.models import Invoice, SalesOrder
from app.modules.sales.service import SalesService


class AIAssistantTools:
    """Tool execution layer for AI Assistant operating under user scope."""

    def __init__(self, db: Session, user: User, scope_context: ScopeContext):
        self.db = db
        self.user = user
        self.scope_context = scope_context
        self.crm_service = CRMService(db)
        self.sales_service = SalesService(db)
        self.audit_service = AuditService(db)

    def _record_tool_audit(
        self,
        tool_name: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        args: dict[str, Any] | None = None,
    ) -> None:
        """Records an audit log entry for this AI tool execution."""
        self.audit_service.record_event(
            action="ai_tool_call",
            actor_user_id=self.user.id,
            entity_type=entity_type or "assistant",
            entity_id=entity_id,
            changes={"tool": tool_name, "args": args or {}},
        )

    # ── CRM Tools ─────────────────────────────────────────────────────────────

    def get_lead(self, lead_id: int) -> Lead:
        """Retrieves a lead record under user scope. Raises NotFoundException if unauthorized."""
        self._record_tool_audit(
            "get_lead", entity_type="lead", entity_id=lead_id, args={"lead_id": lead_id}
        )
        return self.crm_service.get_lead(lead_id, scope_context=self.scope_context)

    def get_customer(self, customer_id: int) -> Customer:
        """Retrieves customer record under user scope. Raises NotFoundException if unauthorized."""
        self._record_tool_audit(
            "get_customer",
            entity_type="customer",
            entity_id=customer_id,
            args={"customer_id": customer_id},
        )
        return self.crm_service.get_customer(customer_id, scope_context=self.scope_context)

    def get_opportunity(self, opportunity_id: int) -> Opportunity:
        """Retrieves opportunity record under user scope. Raises NotFoundException if unauthorized."""
        self._record_tool_audit(
            "get_opportunity",
            entity_type="opportunity",
            entity_id=opportunity_id,
            args={"opportunity_id": opportunity_id},
        )
        return self.crm_service.get_opportunity(opportunity_id, scope_context=self.scope_context)

    def list_activities(
        self,
        lead_id: int | None = None,
        customer_id: int | None = None,
        opportunity_id: int | None = None,
    ) -> list[Activity]:
        """
        Lists chronological CRM activities for an entity after verifying user has access
        to the parent entity under their ScopeContext.
        """
        if lead_id:
            self.crm_service.get_lead(lead_id, scope_context=self.scope_context)
        if customer_id:
            self.crm_service.get_customer(customer_id, scope_context=self.scope_context)
        if opportunity_id:
            self.crm_service.get_opportunity(opportunity_id, scope_context=self.scope_context)

        self._record_tool_audit(
            "list_activities",
            entity_type="lead" if lead_id else ("customer" if customer_id else "opportunity"),
            entity_id=lead_id or customer_id or opportunity_id,
            args={"lead_id": lead_id, "customer_id": customer_id, "opportunity_id": opportunity_id},
        )
        return self.crm_service.list_activities(
            lead_id=lead_id, customer_id=customer_id, opportunity_id=opportunity_id
        )

    # ── Sales & Finance Tools ─────────────────────────────────────────────────

    def get_invoice(self, invoice_id: int) -> Invoice:
        """Retrieves invoice with lines, customer, payments, and credit notes under user scope."""
        self._record_tool_audit(
            "get_invoice",
            entity_type="invoice",
            entity_id=invoice_id,
            args={"invoice_id": invoice_id},
        )
        return self.sales_service.get_invoice(invoice_id, scope_context=self.scope_context)

    def get_sales_order(self, order_id: int) -> SalesOrder:
        """Retrieves sales order under user scope."""
        self._record_tool_audit(
            "get_sales_order",
            entity_type="sales_order",
            entity_id=order_id,
            args={"order_id": order_id},
        )
        stmt = (
            select(SalesOrder)
            .where(SalesOrder.id == order_id)
            .options(selectinload(SalesOrder.items), selectinload(SalesOrder.customer))
        )
        if self.scope_context:
            stmt = apply_scope(stmt, SalesOrder, self.scope_context, self.db)
        so = self.db.execute(stmt).scalar_one_or_none()
        if not so:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Sales order with ID {order_id} not found.")
        return so

    # ── Cross-Entity Scoped Search ───────────────────────────────────────────

    def search_records(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Executes natural-language search across Leads, Customers, Opportunities, and Invoices.
        Filters strictly by the requesting user's ScopeContext.
        """
        self._record_tool_audit("search_records", args={"query": query, "limit": limit})
        pattern = f"%{query.strip()}%"
        results: list[dict[str, Any]] = []

        # 1. Search Leads
        lead_stmt = (
            select(Lead)
            .where(
                or_(
                    Lead.lead_no.ilike(pattern),
                    Lead.first_name.ilike(pattern),
                    Lead.last_name.ilike(pattern),
                    Lead.company_name.ilike(pattern),
                    Lead.email.ilike(pattern),
                )
            )
            .limit(limit)
        )
        if self.scope_context:
            lead_stmt = apply_scope(lead_stmt, Lead, self.scope_context, self.db)
        leads = self.db.execute(lead_stmt).scalars().all()
        for lead_rec in leads:
            results.append(
                {
                    "type": "lead",
                    "id": lead_rec.id,
                    "number": lead_rec.lead_no,
                    "title": f"{lead_rec.first_name} {lead_rec.last_name or ''} ({lead_rec.company_name or 'Individual'})".strip(),
                    "status": lead_rec.status,
                    "owner_id": lead_rec.owner_user_id,
                }
            )

        # 2. Search Customers
        cust_stmt = (
            select(Customer)
            .where(
                or_(
                    Customer.customer_no.ilike(pattern),
                    Customer.name.ilike(pattern),
                    Customer.email.ilike(pattern),
                )
            )
            .limit(limit)
        )
        if self.scope_context:
            cust_stmt = apply_scope(cust_stmt, Customer, self.scope_context, self.db)
        customers = self.db.execute(cust_stmt).scalars().all()
        for c in customers:
            results.append(
                {
                    "type": "customer",
                    "id": c.id,
                    "number": c.customer_no,
                    "title": c.name,
                    "status": c.status,
                    "owner_id": c.owner_user_id,
                }
            )

        # 3. Search Opportunities
        opp_stmt = (
            select(Opportunity)
            .where(
                or_(
                    Opportunity.opportunity_no.ilike(pattern),
                    Opportunity.name.ilike(pattern),
                )
            )
            .limit(limit)
        )
        if self.scope_context:
            opp_stmt = apply_scope(opp_stmt, Opportunity, self.scope_context, self.db)
        opps = self.db.execute(opp_stmt).scalars().all()
        for o in opps:
            results.append(
                {
                    "type": "opportunity",
                    "id": o.id,
                    "number": o.opportunity_no,
                    "title": o.name,
                    "status": o.stage,
                    "owner_id": o.owner_user_id,
                }
            )

        # 4. Search Invoices
        inv_stmt = (
            select(Invoice)
            .where(
                or_(
                    Invoice.invoice_no.ilike(pattern),
                )
            )
            .limit(limit)
        )
        if self.scope_context:
            inv_stmt = apply_scope(inv_stmt, Invoice, self.scope_context, self.db)
        invoices = self.db.execute(inv_stmt).scalars().all()
        for i in invoices:
            results.append(
                {
                    "type": "invoice",
                    "id": i.id,
                    "number": i.invoice_no,
                    "title": f"Invoice {i.invoice_no} ({i.status})",
                    "status": i.status,
                    "owner_id": i.created_by,
                }
            )

        return results[:limit]
