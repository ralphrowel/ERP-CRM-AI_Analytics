"""Predefined domain state machines built on the unified StateMachine engine (Roadmap V0.7)."""

from app.core.workflow.state_machine import StateMachine
from app.core.workflow.transition import Transition

# ── CRM State Machines ───────────────────────────────────────────────────

lead_state_machine = StateMachine(
    name="LeadLifecycle",
    entity_type="lead",
    transitions=[
        Transition(from_state="new", to_state="contacted", description="Initial outreach made"),
        Transition(from_state="new", to_state="qualified", description="Lead fast-track qualified"),
        Transition(from_state="new", to_state="disqualified", description="Lead disqualified"),
        Transition(from_state="contacted", to_state="qualified", description="Lead qualified"),
        Transition(
            from_state="contacted", to_state="disqualified", description="Lead disqualified"
        ),
        Transition(
            from_state="qualified", to_state="converted", description="Converted to customer"
        ),
        Transition(
            from_state="qualified",
            to_state="disqualified",
            description="Disqualified after qualification",
        ),
        Transition(
            from_state="disqualified", to_state="new", description="Re-opened disqualified lead"
        ),
    ],
)

opportunity_state_machine = StateMachine(
    name="OpportunityPipeline",
    entity_type="opportunity",
    status_attr="stage",
    transitions=[
        Transition(from_state="discovery", to_state="proposal"),
        Transition(from_state="discovery", to_state="lost"),
        Transition(from_state="proposal", to_state="negotiation"),
        Transition(from_state="proposal", to_state="discovery"),
        Transition(from_state="proposal", to_state="lost"),
        Transition(from_state="negotiation", to_state="won"),
        Transition(from_state="negotiation", to_state="proposal"),
        Transition(from_state="negotiation", to_state="lost"),
    ],
)

# ── Sales State Machines ─────────────────────────────────────────────────

quote_state_machine = StateMachine(
    name="QuoteLifecycle",
    entity_type="quote",
    transitions=[
        Transition(from_state="draft", to_state="sent", description="Quote sent to customer"),
        Transition(from_state="sent", to_state="accepted", description="Customer accepted quote"),
        Transition(from_state="sent", to_state="rejected", description="Customer rejected quote"),
        Transition(
            from_state="sent", to_state="expired", description="Quote validity period elapsed"
        ),
        Transition(from_state="draft", to_state="expired", description="Draft quote expired"),
    ],
)

sales_order_state_machine = StateMachine(
    name="SalesOrderLifecycle",
    entity_type="sales_order",
    transitions=[
        Transition(
            from_state="draft",
            to_state="pending_approval",
            description="Awaiting threshold or credit approval",
        ),
        Transition(from_state="draft", to_state="confirmed", description="Order confirmed"),
        Transition(
            from_state="pending_approval",
            to_state="confirmed",
            description="Order approved and confirmed",
        ),
        Transition(
            from_state="pending_approval",
            to_state="draft",
            description="Order approval rejected, returned to draft",
        ),
        Transition(
            from_state="confirmed",
            to_state="on_hold",
            description="Order placed on operational hold",
        ),
        Transition(from_state="on_hold", to_state="confirmed", description="Hold released"),
        Transition(
            from_state="confirmed",
            to_state="partially_shipped",
            description="First shipment dispatched",
        ),
        Transition(from_state="confirmed", to_state="shipped", description="Fully shipped"),
        Transition(
            from_state="partially_shipped",
            to_state="shipped",
            description="Remaining items shipped",
        ),
        Transition(
            from_state="shipped",
            to_state="completed",
            description="Order fully invoiced and shipped",
        ),
        Transition(
            from_state=["draft", "confirmed", "on_hold"],
            to_state="cancelled",
            description="Order cancelled",
        ),
    ],
)

# ── Purchasing State Machines ────────────────────────────────────────────

purchase_order_state_machine = StateMachine(
    name="PurchaseOrderLifecycle",
    entity_type="purchase_order",
    transitions=[
        Transition(
            from_state="draft",
            to_state="pending_approval",
            description="Awaiting spend limit approval",
        ),
        Transition(from_state="draft", to_state="sent", description="PO sent to vendor"),
        Transition(
            from_state="pending_approval", to_state="sent", description="PO approved and sent"
        ),
        Transition(
            from_state="pending_approval",
            to_state="draft",
            description="PO rejected, returned to draft",
        ),
        Transition(
            from_state="sent", to_state="partially_received", description="Partial goods intake"
        ),
        Transition(
            from_state=["sent", "partially_received"],
            to_state="received",
            description="Fully received",
        ),
        Transition(from_state="partially_received", to_state="closed", description="Short-closed"),
        Transition(from_state=["draft", "sent"], to_state="cancelled", description="PO cancelled"),
    ],
)
