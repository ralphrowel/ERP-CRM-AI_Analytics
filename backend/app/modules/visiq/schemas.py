"""
Visiq Analytics Request and Response Pydantic Schemas (Roadmap §V1.6)
"""

from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Session name")
    dataset_name: str = Field(
        default="mart_all",
        description="Target dataset (mart_sales, mart_inventory, mart_purchases, mart_all)",
    )


class SessionResponse(BaseModel):
    id: str
    name: str
    dataset_name: str
    created_at: str
    message_count: int
    pinned_widget_count: int


class SessionDetailResponse(BaseModel):
    id: str
    name: str
    dataset_name: str
    created_at: str
    messages: list[dict[str, Any]]
    pinned_widgets: list[dict[str, Any]]


class AskQuestionRequest(BaseModel):
    question: str = Field(
        ..., min_length=2, max_length=1000, description="Natural language question"
    )
    theme: str = Field(default="light", description="Plotly theme: 'light' or 'dark'")


class AskQuestionResponse(BaseModel):
    question: str
    refused: bool
    narrative: str
    tool_called: str | None = None
    tool_output: dict[str, Any] | None = None
    plotly_spec: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    dq_warnings: list[str] = Field(default_factory=list)


class SuggestionsResponse(BaseModel):
    session_id: str
    dataset_name: str
    suggestions: list[str]


class PinWidgetRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    widget_type: str = Field(default="chart", description="'kpi_card' or 'chart'")
    kpi_id: str = Field(default="KPI-001")
    tool_name: str = Field(default="get_metric")
    parameters: dict[str, Any] = Field(default_factory=dict)
    cached_value: Any = None
    plotly_spec: dict[str, Any] = Field(default_factory=dict)


class PinnedWidgetResponse(BaseModel):
    id: str
    session_id: str
    title: str
    widget_type: str
    kpi_id: str
    tool_name: str
    parameters: dict[str, Any]
    cached_value: Any
    plotly_spec: dict[str, Any]
    pinned_at: str
