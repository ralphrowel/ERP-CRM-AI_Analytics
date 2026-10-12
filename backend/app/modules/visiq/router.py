"""
Visiq Analytics API Router (Roadmap §V1.6)
Secured endpoints guarded by require("analytics:use") permission.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.visiq.schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    PinnedWidgetResponse,
    PinWidgetRequest,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
    SuggestionsResponse,
)
from app.modules.visiq.service import VisiqService

router = APIRouter(prefix="/visiq", tags=["Visiq AI Analytics"])


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Visiq analytical workspace session",
)
def create_session(
    payload: SessionCreate,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    session = service.create_session(
        name=payload.name, dataset_name=payload.dataset_name, user=context.user
    )
    return SessionResponse(
        id=session.id,
        name=session.name,
        dataset_name=session.dataset_name,
        created_at=session.created_at,
        message_count=len(session.messages),
        pinned_widget_count=len(session.pinned_widgets),
    )


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="List active Visiq workspace sessions",
)
def list_sessions(
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    sessions = service.list_sessions(user=context.user)
    return [
        SessionResponse(
            id=s.id,
            name=s.name,
            dataset_name=s.dataset_name,
            created_at=s.created_at,
            message_count=len(s.messages),
            pinned_widget_count=len(s.pinned_widgets),
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details and conversation history",
)
def get_session(
    session_id: str,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return SessionDetailResponse(
        id=session.id,
        name=session.name,
        dataset_name=session.dataset_name,
        created_at=session.created_at,
        messages=[asdict(m) for m in session.messages],
        pinned_widgets=[asdict(w) for w in session.pinned_widgets],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace session",
)
def delete_session(
    session_id: str,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    deleted = service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


@router.post(
    "/sessions/{session_id}/ask",
    response_model=AskQuestionResponse,
    summary="Ask an analytical business question to Visiq",
)
def ask_question(
    session_id: str,
    payload: AskQuestionRequest,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    session = service.get_session(session_id)
    if not session:
        # Auto-create if first query
        session = service.create_session(name="New Analytics Session", user=context.user)
        session_id = session.id

    res = service.ask(
        session_id=session_id,
        question=payload.question,
        theme=payload.theme,
        user=context.user,
    )
    return AskQuestionResponse(
        question=res["question"],
        refused=res.get("refused", False),
        narrative=res["narrative"],
        tool_called=res.get("tool_called"),
        tool_output=res.get("tool_output"),
        plotly_spec=res.get("plotly_spec"),
        freshness=res.get("freshness"),
        dq_warnings=res.get("dq_warnings", []),
    )


@router.get(
    "/sessions/{session_id}/suggestions",
    response_model=SuggestionsResponse,
    summary="Get 4 starter business questions based on dataset schema",
)
def get_suggestions(
    session_id: str,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    session = service.get_session(session_id)
    dataset_name = session.dataset_name if session else "mart_all"
    suggestions = service.get_suggestions(session_id)
    return SuggestionsResponse(
        session_id=session_id,
        dataset_name=dataset_name,
        suggestions=suggestions,
    )


@router.post(
    "/sessions/{session_id}/widgets/pin",
    response_model=PinnedWidgetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pin a KPI card or chart widget to the executive dashboard",
)
def pin_widget(
    session_id: str,
    payload: PinWidgetRequest,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    widget = service.pin_widget(
        session_id=session_id,
        title=payload.title,
        widget_type=payload.widget_type,
        kpi_id=payload.kpi_id,
        tool_name=payload.tool_name,
        parameters=payload.parameters,
        cached_value=payload.cached_value,
        plotly_spec=payload.plotly_spec,
    )
    return PinnedWidgetResponse(
        id=widget.id,
        session_id=widget.session_id,
        title=widget.title,
        widget_type=widget.widget_type,
        kpi_id=widget.kpi_id,
        tool_name=widget.tool_name,
        parameters=widget.parameters,
        cached_value=widget.cached_value,
        plotly_spec=widget.plotly_spec,
        pinned_at=widget.pinned_at,
    )


@router.get(
    "/sessions/{session_id}/widgets",
    response_model=list[PinnedWidgetResponse],
    summary="List all pinned executive dashboard widgets",
)
def list_pinned_widgets(
    session_id: str,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    widgets = service.get_pinned_widgets(session_id)
    return [
        PinnedWidgetResponse(
            id=w.id,
            session_id=w.session_id,
            title=w.title,
            widget_type=w.widget_type,
            kpi_id=w.kpi_id,
            tool_name=w.tool_name,
            parameters=w.parameters,
            cached_value=w.cached_value,
            plotly_spec=w.plotly_spec,
            pinned_at=w.pinned_at,
        )
        for w in widgets
    ]


@router.delete(
    "/sessions/{session_id}/widgets/{widget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unpin a widget from the executive dashboard",
)
def unpin_widget(
    session_id: str,
    widget_id: str,
    context: Annotated[ScopeContext, Depends(require("analytics:use"))],
    db: Annotated[Session, Depends(get_db)],
):
    service = VisiqService(db)
    unpinned = service.unpin_widget(session_id, widget_id)
    if not unpinned:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
