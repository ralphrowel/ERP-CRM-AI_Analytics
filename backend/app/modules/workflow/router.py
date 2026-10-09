from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.workflow.schemas import (
    ApprovalDecisionPayload,
    ApprovalRequestResponse,
    ApprovalRuleResponse,
    ApprovalRuleUpdate,
    PaginatedApprovalRequestsResponse,
)
from app.modules.workflow.service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["Workflow & Approvals"])


def get_workflow_service(db: Session = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


# ── Approval Rules ───────────────────────────────────────────────────────


@router.get("/rules", response_model=list[ApprovalRuleResponse])
def list_approval_rules(
    _: Annotated[ScopeContext, Depends(require("approval_rule:read"))],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    entity_type: str | None = Query(None),
) -> list[ApprovalRuleResponse]:
    return service.list_rules(entity_type=entity_type)


@router.patch("/rules/{rule_id}", response_model=ApprovalRuleResponse)
def update_approval_rule(
    rule_id: int,
    payload: ApprovalRuleUpdate,
    ctx: Annotated[ScopeContext, Depends(require("approval_rule:update"))],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApprovalRuleResponse:
    return service.update_rule(rule_id=rule_id, payload=payload, updater_id=ctx.user.id)


# ── Approval Requests Queue ──────────────────────────────────────────────


@router.get("/requests", response_model=PaginatedApprovalRequestsResponse)
def list_approval_requests(
    _: Annotated[ScopeContext, Depends(require("approval_request:read"))],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    status: str | None = Query(None),
    entity_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedApprovalRequestsResponse:
    items, total = service.list_requests(
        status=status, entity_type=entity_type, page=page, page_size=page_size
    )
    return PaginatedApprovalRequestsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/requests/{request_id}", response_model=ApprovalRequestResponse)
def get_approval_request(
    request_id: int,
    _: Annotated[ScopeContext, Depends(require("approval_request:read"))],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApprovalRequestResponse:
    return service.get_request(request_id)


@router.post("/requests/{request_id}/decide", response_model=ApprovalRequestResponse)
def decide_approval_request(
    request_id: int,
    payload: ApprovalDecisionPayload,
    ctx: Annotated[ScopeContext, Depends(require("approval_request:decide"))],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApprovalRequestResponse:
    return service.decide_request(
        request_id=request_id,
        decision=payload.decision,
        decider=ctx.user,
        comment=payload.comment,
        decider_permissions=ctx.permissions,
    )
