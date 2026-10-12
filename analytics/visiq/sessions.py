"""
Visiq Workspace Sessions & State Management (Roadmap §V1.6)
Manages curated dataset registration, isolated conversation histories,
starter business suggestions, and executive dashboard widget pinning.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar


@dataclass
class PinnedWidget:
    id: str
    session_id: str
    title: str
    widget_type: str  # "kpi_card" | "chart"
    kpi_id: str
    tool_name: str
    parameters: dict[str, Any]
    cached_value: Any
    plotly_spec: dict[str, Any]
    pinned_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class VisiqMessage:
    id: str
    role: str  # "user" | "assistant"
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    plotly_spec: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    dq_warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class WorkspaceSession:
    id: str
    name: str
    dataset_name: str  # "mart_sales" | "mart_inventory" | "mart_purchases" | "mart_all"
    created_by_user_id: int | None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    messages: list[VisiqMessage] = field(default_factory=list)
    pinned_widgets: list[PinnedWidget] = field(default_factory=list)


DATASET_CATALOG: dict[str, dict[str, Any]] = {
    "mart_sales": {
        "name": "mart_sales",
        "description": "Sales orders, invoices, credit notes, customer and product dimensions.",
        "fact_tables": ["fact_sales_line"],
        "starter_questions": [
            "What was our total net revenue for the last month?",
            "Why did gross margin change across product categories?",
            "Who are our top 5 customers by sales revenue?",
            "How does revenue break down across Luzon, Visayas, and Mindanao?",
        ],
    },
    "mart_inventory": {
        "name": "mart_inventory",
        "description": "Daily stock balances, valuation, and stockout events.",
        "fact_tables": ["fact_inventory_daily"],
        "starter_questions": [
            "What is our current total warehouse inventory valuation?",
            "Which products experienced stockout events?",
            "What are our top 5 products by quantity on hand?",
            "What is our estimated days of inventory on hand (DIOH)?",
        ],
    },
    "mart_purchases": {
        "name": "mart_purchases",
        "description": "Procurement purchase orders, spend commitments, and supplier delivery.",
        "fact_tables": ["fact_purchase_line"],
        "starter_questions": [
            "What is our total procurement purchase order spend?",
            "What is the on-time delivery rate across suppliers?",
            "Who are our top 5 suppliers by spend volume?",
            "How does purchase spend break down by product category?",
        ],
    },
    "mart_all": {
        "name": "mart_all",
        "description": "Enterprise complete analytical star schema and data quality mart.",
        "fact_tables": [
            "fact_sales_line",
            "fact_opportunity_stage",
            "fact_inventory_daily",
            "fact_purchase_line",
            "fact_ar_allocation",
        ],
        "starter_questions": [
            "Why did revenue decrease last month?",
            "What is our overall sales win rate and pipeline value?",
            "What are the top 5 revenue-generating products?",
            "What is our current data quality health score?",
        ],
    },
}


class SessionManager:
    """In-memory thread-safe workspace session store for Visiq."""

    _sessions: ClassVar[dict[str, WorkspaceSession]] = {}

    @classmethod
    def create_session(
        cls,
        name: str,
        dataset_name: str = "mart_all",
        user_id: int | None = None,
    ) -> WorkspaceSession:
        if dataset_name not in DATASET_CATALOG:
            dataset_name = "mart_all"

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = WorkspaceSession(
            id=session_id,
            name=name,
            dataset_name=dataset_name,
            created_by_user_id=user_id,
        )
        cls._sessions[session_id] = session
        return session

    @classmethod
    def get_session(cls, session_id: str) -> WorkspaceSession | None:
        return cls._sessions.get(session_id)

    @classmethod
    def list_sessions(cls, user_id: int | None = None) -> list[WorkspaceSession]:
        if user_id is not None:
            return [
                s
                for s in cls._sessions.values()
                if s.created_by_user_id == user_id or s.created_by_user_id is None
            ]
        return list(cls._sessions.values())

    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        if session_id in cls._sessions:
            del cls._sessions[session_id]
            return True
        return False

    @classmethod
    def add_message(
        cls,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        plotly_spec: dict[str, Any] | None = None,
        freshness: dict[str, Any] | None = None,
        dq_warnings: list[str] | None = None,
    ) -> VisiqMessage:
        session = cls.get_session(session_id)
        if not session:
            session = cls.create_session(
                name=f"Session {session_id}", dataset_name="mart_all"
            )
            cls._sessions[session_id] = session

        msg = VisiqMessage(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            plotly_spec=plotly_spec,
            freshness=freshness,
            dq_warnings=dq_warnings or [],
        )
        session.messages.append(msg)
        return msg

    @classmethod
    def get_starter_questions(cls, session_id: str) -> list[str]:
        session = cls.get_session(session_id)
        dataset_name = session.dataset_name if session else "mart_all"
        meta = DATASET_CATALOG.get(dataset_name, DATASET_CATALOG["mart_all"])
        return meta["starter_questions"]

    @classmethod
    def pin_widget(
        cls,
        session_id: str,
        title: str,
        widget_type: str,
        kpi_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        cached_value: Any,
        plotly_spec: dict[str, Any],
    ) -> PinnedWidget:
        session = cls.get_session(session_id)
        if not session:
            session = cls.create_session(name="Default Session")
            cls._sessions[session_id] = session

        widget = PinnedWidget(
            id=f"wgt_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            title=title,
            widget_type=widget_type,
            kpi_id=kpi_id,
            tool_name=tool_name,
            parameters=parameters,
            cached_value=cached_value,
            plotly_spec=plotly_spec,
        )
        session.pinned_widgets.append(widget)
        return widget

    @classmethod
    def unpin_widget(cls, session_id: str, widget_id: str) -> bool:
        session = cls.get_session(session_id)
        if not session:
            return False
        orig_len = len(session.pinned_widgets)
        session.pinned_widgets = [
            w for w in session.pinned_widgets if w.id != widget_id
        ]
        return len(session.pinned_widgets) < orig_len

    @classmethod
    def get_pinned_widgets(cls, session_id: str) -> list[PinnedWidget]:
        session = cls.get_session(session_id)
        return session.pinned_widgets if session else []
