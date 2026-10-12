"""AI Assistant Core Service (Roadmap §V1.7)

Features:
- Lead & Customer record summarization with activity aggregation.
- Opportunity stage analysis and next-step recommendations.
- Contextual follow-up email drafting.
- Invoice balance and payment allocation explanation.
- Natural-language scoped record search.
- Interactive conversational copilot with strict prompt-injection defense.
- Guaranteed human-in-the-loop: All mutation proposals are returned as DraftAction.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext
from app.core.clock import get_clock
from app.modules.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    CustomerSummaryResponse,
    DraftAction,
    DraftEmailRequest,
    DraftEmailResponse,
    ExplainInvoiceResponse,
    LeadSummaryResponse,
    OpportunityNextStepsResponse,
    RecordSearchResponse,
)
from app.modules.assistant.security import (
    detect_prompt_injection,
    wrap_untrusted_content,
)
from app.modules.assistant.tools import AIAssistantTools
from app.modules.crm.models import Customer, Lead, Opportunity
from app.modules.identity.models import User
from app.modules.sales.models import Invoice


class AIAssistantService:
    """Orchestrates ERP copilot actions executing as the requesting user."""

    def __init__(self, db: Session, user: User, scope_context: ScopeContext):
        self.db = db
        self.user = user
        self.scope_context = scope_context
        self.tools = AIAssistantTools(db, user, scope_context)
        self.clock = get_clock()

    # ── 1. Lead Summarization ──────────────────────────────────────────────────

    def summarize_lead(self, lead_id: int) -> LeadSummaryResponse:
        """
        Summarizes a lead and chronological interactions.
        Enforces prompt-injection defense on untrusted lead notes.
        """
        lead: Lead = self.tools.get_lead(lead_id)
        activities = self.tools.list_activities(lead_id=lead_id)

        # Wrap untrusted free-text notes into security context
        _ = wrap_untrusted_content(lead.notes, field_name="notes")

        # Synthesize executive summary
        full_name = f"{lead.first_name} {lead.last_name or ''}".strip()
        comp = lead.company_name or "Individual prospect"
        summary = (
            f"Lead {lead.lead_no} ({full_name}) is currently in '{lead.status}' status, "
            f"originating from {lead.source or 'direct inquiry'} for {comp}."
        )

        highlights: list[str] = [
            f"Contact info: {lead.email or 'No email'} | {lead.phone or 'No phone'}",
            f"Total logged interactions: {len(activities)}",
        ]

        if lead.notes:
            # Highlight notes safely without executing any injected commands
            has_injection = detect_prompt_injection(lead.notes)
            if has_injection:
                highlights.append(
                    "Note: Contains external user inquiry (prompt injection attempt neutralized)."
                )
            else:
                snippet = (lead.notes[:120] + "...") if len(lead.notes) > 120 else lead.notes
                highlights.append(f"Recorded notes: {snippet}")

        # Suggested next action
        suggested_action = "Schedule discovery call"
        if lead.status == "new":
            suggested_action = "Initiate first contact via email or phone."
        elif lead.status == "contacted":
            suggested_action = "Qualify budget, timeline, and decision-making criteria."
        elif lead.status == "qualified":
            suggested_action = "Convert lead into Account and create an Opportunity."
        elif lead.status == "disqualified":
            suggested_action = (
                "No active action. Revisit lead in future campaign if status re-opens."
            )

        return LeadSummaryResponse(
            lead_id=lead.id,
            lead_no=lead.lead_no,
            name=full_name,
            company_name=lead.company_name,
            status=lead.status,
            owner_id=lead.owner_user_id,
            summary=summary,
            key_highlights=highlights,
            suggested_next_action=suggested_action,
            activity_count=len(activities),
        )

    # ── 2. Customer Summarization ──────────────────────────────────────────────

    def summarize_customer(self, customer_id: int) -> CustomerSummaryResponse:
        """
        Summarizes customer profile, active opportunities, and interaction history.
        """
        customer: Customer = self.tools.get_customer(customer_id)
        activities = self.tools.list_activities(customer_id=customer_id)

        # Get customer opportunities under scope
        opps = [o for o in customer.opportunities if o.stage not in ("won", "lost")]
        total_pipeline = sum((o.estimated_amount for o in opps), Decimal("0.00"))

        summary = (
            f"Customer {customer.customer_no} ({customer.name}) is an active account "
            f"in status '{customer.status}' ({customer.customer_type}). "
            f"Industry: {customer.industry or 'General'}."
        )

        recent_acts: list[dict[str, Any]] = [
            {
                "type": a.activity_type,
                "subject": a.subject,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities[:5]
        ]

        financials = {
            "payment_terms_days": customer.payment_terms_days,
            "credit_limit": str(customer.credit_limit) if customer.credit_limit else None,
            "open_pipeline_amount": str(total_pipeline),
        }

        return CustomerSummaryResponse(
            customer_id=customer.id,
            customer_no=customer.customer_no,
            name=customer.name,
            status=customer.status,
            summary=summary,
            open_opportunities_count=len(opps),
            total_opportunities_value=str(total_pipeline),
            recent_activities=recent_acts,
            financial_overview=financials,
        )

    # ── 3. Opportunity Next Steps ──────────────────────────────────────────────

    def suggest_opportunity_next_steps(self, opportunity_id: int) -> OpportunityNextStepsResponse:
        """
        Evaluates opportunity stage and activity history to recommend next steps.
        Generates a draft activity for user confirmation.
        """
        opp: Opportunity = self.tools.get_opportunity(opportunity_id)
        _ = self.tools.list_activities(opportunity_id=opportunity_id)

        steps: list[str] = []
        draft: DraftAction | None = None

        if opp.stage == "discovery":
            steps = [
                "Conduct stakeholder discovery session to clarify pain points.",
                "Identify decision makers and technical evaluation criteria.",
                "Determine target implementation timeline and budget allocation.",
            ]
            draft = DraftAction(
                action_type="create_activity",
                title=f"Schedule Discovery Call with {opp.name}",
                description="Drafted follow-up discovery session with primary stakeholders.",
                confirmation_required=True,
                payload={
                    "opportunity_id": opp.id,
                    "customer_id": opp.customer_id,
                    "activity_type": "call",
                    "subject": f"Discovery follow-up: {opp.name}",
                    "due_at": (self.clock.now()).isoformat(),
                },
                explanation="Recommended because opportunity is in early discovery stage.",
            )
        elif opp.stage == "proposal":
            steps = [
                "Prepare and send formal pricing quotation.",
                "Review commercial terms and scope of work with customer.",
                "Confirm receipt and schedule proposal walkthrough.",
            ]
            draft = DraftAction(
                action_type="create_quote",
                title=f"Draft Quote for {opp.name}",
                description="Initialize a quotation based on estimated amount.",
                confirmation_required=True,
                payload={
                    "customer_id": opp.customer_id,
                    "opportunity_id": opp.id,
                    "estimated_amount": str(opp.estimated_amount),
                },
                explanation="Recommended because opportunity is in proposal stage.",
            )
        elif opp.stage == "negotiation":
            steps = [
                "Address customer objections on pricing or payment terms.",
                "Obtain final procurement and legal approval.",
                "Prepare formal sales agreement for signature.",
            ]
            draft = DraftAction(
                action_type="update_opportunity_stage",
                title=f"Prepare Closing: {opp.name}",
                description="Ready to mark opportunity as Won upon customer sign-off.",
                confirmation_required=True,
                payload={
                    "opportunity_id": opp.id,
                    "target_stage": "won",
                },
                explanation="Awaiting customer final sign-off.",
            )
        else:
            steps = [f"Opportunity is closed ({opp.stage}). Archive or conduct post-mortem review."]

        summary = (
            f"Opportunity '{opp.name}' ({opp.opportunity_no}) is in '{opp.stage}' stage "
            f"with estimated value of ₱{opp.estimated_amount:,.2f} "
            f"(probability: {float(opp.probability) * 100:.0f}%)."
        )

        return OpportunityNextStepsResponse(
            opportunity_id=opp.id,
            opportunity_no=opp.opportunity_no,
            name=opp.name,
            stage=opp.stage,
            estimated_amount=str(opp.estimated_amount),
            probability=str(opp.probability),
            summary=summary,
            recommended_steps=steps,
            draft_action=draft,
        )

    # ── 4. Follow-up Email Drafting ────────────────────────────────────────────

    def draft_followup_email(self, req: DraftEmailRequest) -> DraftEmailResponse:
        """
        Drafts a tailored business email. Strict Invariant: Does not send, returns DraftAction.
        """
        recipient_name = "Valued Partner"
        recipient_email: str | None = None
        entity_title = ""

        if req.entity_type == "lead":
            lead = self.tools.get_lead(req.entity_id)
            recipient_name = f"{lead.first_name} {lead.last_name or ''}".strip()
            recipient_email = lead.email
            entity_title = lead.company_name or recipient_name
        elif req.entity_type == "customer":
            cust = self.tools.get_customer(req.entity_id)
            recipient_name = cust.name
            recipient_email = cust.email
            entity_title = cust.name
        elif req.entity_type == "opportunity":
            opp = self.tools.get_opportunity(req.entity_id)
            cust = self.tools.get_customer(opp.customer_id)
            recipient_name = cust.name
            recipient_email = cust.email
            entity_title = opp.name

        subject = f"Follow-up regarding {entity_title}"
        if req.purpose == "quote_intro":
            subject = f"Proposal and Pricing for {entity_title}"
            body = (
                f"Dear {recipient_name},\n\n"
                f"Thank you for taking the time to discuss your requirements. "
                f"We are pleased to share our proposal for {entity_title}.\n\n"
                f"Please let us know if you have any questions or require adjustments.\n\n"
                f"Best regards,\n{self.user.full_name or self.user.email}"
            )
        elif req.purpose == "payment_reminder":
            subject = f"Friendly Reminder: Outstanding Statement for {entity_title}"
            body = (
                f"Dear {recipient_name},\n\n"
                f"This is a friendly reminder regarding your outstanding balance with us. "
                f"Please review the attached statement and let us know if you need assistance.\n\n"
                f"Best regards,\n{self.user.full_name or self.user.email}"
            )
        else:
            body = (
                f"Dear {recipient_name},\n\n"
                f"I hope this note finds you well. I wanted to follow up on our recent discussion "
                f"regarding {entity_title} to see if you have any questions or next steps we can assist with.\n\n"
                f"Looking forward to hearing from you.\n\n"
                f"Best regards,\n{self.user.full_name or self.user.email}"
            )

        draft = DraftAction(
            action_type="send_email",
            title=f"Email Draft: {subject}",
            description=f"Drafted email to {recipient_email or recipient_name}. Requires user review.",
            confirmation_required=True,
            payload={
                "recipient_email": recipient_email,
                "recipient_name": recipient_name,
                "subject": subject,
                "body": body,
                "entity_type": req.entity_type,
                "entity_id": req.entity_id,
            },
            explanation="Draft created per your request. The email is NOT sent until you confirm.",
        )

        return DraftEmailResponse(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            body=body,
            draft_action=draft,
        )

    # ── 5. Invoice Balance Explanation ─────────────────────────────────────────

    def explain_invoice_balance(self, invoice_id: int) -> ExplainInvoiceResponse:
        """
        Explains invoice balance: grand total, applied credits, payments, and remaining due.
        """
        invoice: Invoice = self.tools.get_invoice(invoice_id)
        cust_name = invoice.customer.name if invoice.customer else "Unknown Customer"

        today = self.clock.now().date()
        is_overdue = False
        if invoice.due_date and invoice.due_date < today and invoice.balance_due > Decimal("0.00"):
            is_overdue = True

        narrative = (
            f"Invoice {invoice.invoice_no} for {cust_name} was billed for "
            f"₱{invoice.grand_total:,.2f}. To date, ₱{invoice.amount_paid:,.2f} has been paid "
            f"and ₱{invoice.amount_credited:,.2f} has been credited. "
            f"The remaining balance due is ₱{invoice.balance_due:,.2f}."
        )
        if is_overdue:
            narrative += f" Warning: This invoice is OVERDUE (due date was {invoice.due_date})."
        elif invoice.balance_due == Decimal("0.00"):
            narrative += " This invoice is fully paid and settled."

        line_items = [
            {
                "line_no": item.line_no,
                "description": item.description,
                "quantity": float(item.quantity),
                "unit_price": str(item.unit_price),
                "line_total": str(item.line_total),
            }
            for item in invoice.items
        ]

        payments = [
            {
                "allocation_id": alloc.id,
                "amount": str(alloc.amount),
                "allocated_at": alloc.allocated_at.isoformat() if alloc.allocated_at else None,
            }
            for alloc in (invoice.allocations or [])
        ]

        credits = [
            {
                "credit_note_id": cn.id,
                "credit_note_no": cn.credit_note_no,
                "grand_total": str(cn.grand_total),
            }
            for cn in (invoice.credit_notes or [])
        ]

        return ExplainInvoiceResponse(
            invoice_id=invoice.id,
            invoice_no=invoice.invoice_no,
            customer_name=cust_name,
            status=invoice.status,
            due_date=invoice.due_date.isoformat() if invoice.due_date else None,
            is_overdue=is_overdue,
            grand_total=str(invoice.grand_total),
            amount_paid=str(invoice.amount_paid),
            amount_credited=str(invoice.amount_credited),
            balance_due=str(invoice.balance_due),
            narrative=narrative,
            line_items=line_items,
            payments_applied=payments,
            credits_applied=credits,
        )

    # ── 6. Natural Language Record Search ─────────────────────────────────────

    def search_records(self, query: str, limit: int = 10) -> RecordSearchResponse:
        """Scoped cross-entity search for leads, customers, deals, and invoices."""
        results = self.tools.search_records(query=query, limit=limit)
        return RecordSearchResponse(
            query=query,
            total_found=len(results),
            results=results,
        )

    # ── 7. Interactive Conversational Router ───────────────────────────────────

    def ask(self, req: AssistantChatRequest) -> AssistantChatResponse:
        """
        Processes conversational request with strict prompt-injection defense and draft guarantees.
        """
        msg = req.message.strip()

        # 1. Prompt-Injection Defense on incoming user message
        if detect_prompt_injection(msg):
            return AssistantChatResponse(
                reply=(
                    "I cannot process this request because it contains forbidden administrative "
                    "or system override commands. I am an AI assistant restricted to deterministic "
                    "read-only ERP operations within your permitted scope."
                ),
                refused=True,
                refusal_reason="Prompt injection attempt rejected.",
            )

        msg_lower = msg.lower()
        tool_calls: list[str] = []
        draft_action: DraftAction | None = None
        reply = ""

        # 2. Check for mutation requests (Ensure NO changes commit without user confirmation)
        if any(w in msg_lower for w in ["quote"]) and any(
            w in msg_lower for w in ["create", "generate", "make", "draft", "prepare"]
        ):
            draft_action = DraftAction(
                action_type="create_quote",
                title="Draft New Quotation",
                description="Quotation draft initialized from user instruction.",
                confirmation_required=True,
                payload={
                    "customer_id": req.entity_id if req.entity_type == "customer" else None,
                    "items": [],
                },
                explanation="Quotation draft created. Please review and confirm in the Quotes editor.",
            )
            return AssistantChatResponse(
                reply="I have prepared a draft quotation for your review. No quote has been saved yet.",
                draft_action=draft_action,
                tool_calls=["draft_quote"],
            )

        if any(
            w in msg_lower
            for w in ["call", "activity", "meeting", "task", "follow up", "follow-up"]
        ) and any(w in msg_lower for w in ["schedule", "create", "log", "draft", "set up"]):
            draft_action = DraftAction(
                action_type="create_activity",
                title="Draft New Activity",
                description="Follow-up activity drafted from conversation.",
                confirmation_required=True,
                payload={
                    "activity_type": "call",
                    "subject": "Scheduled follow-up",
                    "entity_type": req.entity_type,
                    "entity_id": req.entity_id,
                },
                explanation="Activity draft prepared. Confirm to add to your calendar.",
            )
            return AssistantChatResponse(
                reply="I have prepared an activity draft for you. Please confirm to schedule it.",
                draft_action=draft_action,
                tool_calls=["draft_activity"],
            )

        # 3. Contextual Entity Queries
        if req.entity_type == "lead" and req.entity_id:
            tool_calls.append("summarize_lead")
            lead_summary = self.summarize_lead(req.entity_id)
            reply = f"{lead_summary.summary}\n\nKey Highlights:\n" + "\n".join(
                f"- {h}" for h in lead_summary.key_highlights
            )
            if lead_summary.suggested_next_action:
                reply += f"\n\nSuggested Next Step: {lead_summary.suggested_next_action}"
            return AssistantChatResponse(
                reply=reply,
                tool_calls=tool_calls,
                entity_context=lead_summary.model_dump(),
            )

        if req.entity_type == "customer" and req.entity_id:
            tool_calls.append("summarize_customer")
            cust_summary = self.summarize_customer(req.entity_id)
            reply = (
                f"{cust_summary.summary}\n\n"
                f"Open Pipeline: {cust_summary.open_opportunities_count} deals "
                f"(₱{cust_summary.total_opportunities_value})."
            )
            return AssistantChatResponse(
                reply=reply,
                tool_calls=tool_calls,
                entity_context=cust_summary.model_dump(),
            )

        if req.entity_type == "opportunity" and req.entity_id:
            tool_calls.append("suggest_opportunity_next_steps")
            opp_summary = self.suggest_opportunity_next_steps(req.entity_id)
            reply = f"{opp_summary.summary}\n\nRecommended Next Steps:\n" + "\n".join(
                f"- {s}" for s in opp_summary.recommended_steps
            )
            return AssistantChatResponse(
                reply=reply,
                draft_action=opp_summary.draft_action,
                tool_calls=tool_calls,
                entity_context=opp_summary.model_dump(),
            )

        if req.entity_type == "invoice" and req.entity_id:
            tool_calls.append("explain_invoice_balance")
            inv_summary = self.explain_invoice_balance(req.entity_id)
            return AssistantChatResponse(
                reply=inv_summary.narrative,
                tool_calls=tool_calls,
                entity_context=inv_summary.model_dump(),
            )

        # 4. General Search or Scoped Lookup
        if any(w in msg_lower for w in ["find", "search", "lookup", "who is", "show me"]):
            clean_search = msg
            for p in ["find ", "search ", "lookup ", "show me "]:
                if msg_lower.startswith(p):
                    clean_search = msg[len(p) :].strip()
                    break
            tool_calls.append("search_records")
            search_res = self.search_records(clean_search, limit=5)
            if search_res.results:
                reply = f"Found {search_res.total_found} matching records in your workspace:\n"
                for r in search_res.results:
                    reply += f"- [{r['type'].upper()}] {r['number']}: {r['title']} (status: {r['status']})\n"
            else:
                reply = (
                    f"No matching records found for '{clean_search}' within your permitted scope."
                )
            return AssistantChatResponse(
                reply=reply,
                tool_calls=tool_calls,
                entity_context=search_res.model_dump(),
            )

        # 5. Fallback Help Guidance
        reply = (
            "I am your ERP Copilot. You can ask me to:\n"
            "- Summarize leads, customers, and opportunities.\n"
            "- Explain invoice balances and payment allocations.\n"
            "- Suggest next steps and draft follow-up emails.\n"
            "- Search records across your authorized accounts."
        )
        return AssistantChatResponse(reply=reply, tool_calls=tool_calls)
