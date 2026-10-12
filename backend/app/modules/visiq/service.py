"""
Visiq Analytics Backend Service (Roadmap §V1.6)
Integrates Visiq conversational agent with ERP session management and audit logging.
"""

from typing import Any

from analytics.db import get_analytics_engine
from analytics.visiq.agent import VisiqAgent
from analytics.visiq.sessions import (
    PinnedWidget,
    SessionManager,
    WorkspaceSession,
)
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.identity.models import User


class VisiqService:
    """Service bridge connecting FastAPI controllers with Visiq analytics engine."""

    def __init__(self, db: Session, analytics_engine: Engine | None = None):
        self.db = db
        self.analytics_engine = analytics_engine or get_analytics_engine()
        self.agent = VisiqAgent(self.analytics_engine)
        self.audit_service = AuditService(db)

    def create_session(
        self, name: str, dataset_name: str = "mart_all", user: User | None = None
    ) -> WorkspaceSession:
        user_id = user.id if user else None
        session = SessionManager.create_session(
            name=name, dataset_name=dataset_name, user_id=user_id
        )
        return session

    def list_sessions(self, user: User | None = None) -> list[WorkspaceSession]:
        user_id = user.id if user and not user.is_superuser else None
        return SessionManager.list_sessions(user_id=user_id)

    def get_session(self, session_id: str) -> WorkspaceSession | None:
        return SessionManager.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        return SessionManager.delete_session(session_id)

    def ask(
        self,
        session_id: str,
        question: str,
        theme: str = "light",
        user: User | None = None,
    ) -> dict[str, Any]:
        """
        Executes an analytical query, appends to session history, and records an audit log.
        """
        # Execute query via Visiq agent
        result = self.agent.ask(question=question, theme=theme, session_id=session_id)

        # Audit log the tool execution (Roadmap §V1.6 Rule 6)
        user_id = user.id if user else None
        self.audit_service.record_event(
            action="ai_tool_call",
            entity_type="analytics_session",
            entity_id=None,
            actor_user_id=user_id,
            changes={
                "session_id": session_id,
                "question": question,
                "tool_called": result.get("tool_called"),
                "refused": result.get("refused", False),
            },
        )
        self.db.commit()

        # Add user message and assistant message to session
        SessionManager.add_message(
            session_id=session_id,
            role="user",
            content=question,
        )
        SessionManager.add_message(
            session_id=session_id,
            role="assistant",
            content=result["narrative"],
            tool_calls=[{"tool": result.get("tool_called"), "output": result.get("tool_output")}]
            if result.get("tool_called")
            else [],
            plotly_spec=result.get("plotly_spec"),
            freshness=result.get("freshness"),
            dq_warnings=result.get("dq_warnings"),
        )

        return result

    def get_suggestions(self, session_id: str) -> list[str]:
        return SessionManager.get_starter_questions(session_id)

    def pin_widget(
        self,
        session_id: str,
        title: str,
        widget_type: str,
        kpi_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        cached_value: Any,
        plotly_spec: dict[str, Any],
    ) -> PinnedWidget:
        return SessionManager.pin_widget(
            session_id=session_id,
            title=title,
            widget_type=widget_type,
            kpi_id=kpi_id,
            tool_name=tool_name,
            parameters=parameters,
            cached_value=cached_value,
            plotly_spec=plotly_spec,
        )

    def unpin_widget(self, session_id: str, widget_id: str) -> bool:
        return SessionManager.unpin_widget(session_id=session_id, widget_id=widget_id)

    def get_pinned_widgets(self, session_id: str) -> list[PinnedWidget]:
        return SessionManager.get_pinned_widgets(session_id=session_id)
