"""FastAPI Router for AI-Assisted ERP (Roadmap §V1.7)

Endpoints mounted at /api/v1/assistant, guarded by require("assistant:use").
Every tool execution runs strictly AS the requesting user under ScopeContext.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    CustomerSummaryResponse,
    DraftEmailRequest,
    DraftEmailResponse,
    ExplainInvoiceResponse,
    LeadSummaryResponse,
    OpportunityNextStepsResponse,
    RecordSearchResponse,
)
from app.modules.assistant.service import AIAssistantService

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


def get_assistant_service(
    scope_context: Annotated[ScopeContext, Depends(require("assistant:use"))],
    db: Annotated[Session, Depends(get_db)],
) -> AIAssistantService:
    """Instantiates AIAssistantService with caller's user and resolved ScopeContext."""
    return AIAssistantService(db=db, user=scope_context.user, scope_context=scope_context)


@router.post("/chat", response_model=AssistantChatResponse, status_code=status.HTTP_200_OK)
def chat_with_assistant(
    request: AssistantChatRequest,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> AssistantChatResponse:
    """Interactive conversational copilot with prompt-injection defense and draft guarantees."""
    return service.ask(request)


@router.get(
    "/leads/{lead_id}/summary", response_model=LeadSummaryResponse, status_code=status.HTTP_200_OK
)
def get_lead_summary(
    lead_id: int,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> LeadSummaryResponse:
    """Summarizes a lead and interaction history under user's permission scope."""
    return service.summarize_lead(lead_id)


@router.get(
    "/customers/{customer_id}/summary",
    response_model=CustomerSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def get_customer_summary(
    customer_id: int,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> CustomerSummaryResponse:
    """Summarizes customer relationship, deals, and recent activities."""
    return service.summarize_customer(customer_id)


@router.get(
    "/opportunities/{opportunity_id}/next-steps",
    response_model=OpportunityNextStepsResponse,
    status_code=status.HTTP_200_OK,
)
def get_opportunity_next_steps(
    opportunity_id: int,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> OpportunityNextStepsResponse:
    """Analyzes opportunity stage and recommends next actions with a draft activity."""
    return service.suggest_opportunity_next_steps(opportunity_id)


@router.post("/draft-email", response_model=DraftEmailResponse, status_code=status.HTTP_200_OK)
def draft_email(
    request: DraftEmailRequest,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> DraftEmailResponse:
    """Drafts contextual follow-up or reminder email requiring explicit confirmation."""
    return service.draft_followup_email(request)


@router.get(
    "/invoices/{invoice_id}/explain",
    response_model=ExplainInvoiceResponse,
    status_code=status.HTTP_200_OK,
)
def explain_invoice(
    invoice_id: int,
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
) -> ExplainInvoiceResponse:
    """Explains invoice balance, line items, credits, and payment allocations."""
    return service.explain_invoice_balance(invoice_id)


@router.get("/search", response_model=RecordSearchResponse, status_code=status.HTTP_200_OK)
def search_records(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    service: Annotated[AIAssistantService, Depends(get_assistant_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> RecordSearchResponse:
    """Natural-language cross-entity search filtered by user's ScopeContext."""
    return service.search_records(query=q, limit=limit)
