from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    entity_type: str
    description: str | None = None
    threshold_amount: Decimal | None = None
    threshold_pct: Decimal | None = None
    approver_permission: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ApprovalRuleUpdate(BaseModel):
    description: str | None = None
    threshold_amount: Decimal | None = None
    threshold_pct: Decimal | None = None
    approver_permission: str | None = None
    is_active: bool | None = None
    version: int = Field(..., description="Optimistic locking version")


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    rule_code: str
    entity_type: str
    entity_id: int
    status: str
    requested_by: int
    requester_name: str
    requested_at: datetime
    decided_by: int | None = None
    decider_name: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None


class ApprovalDecisionPayload(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(None, max_length=1000)


class PaginatedApprovalRequestsResponse(BaseModel):
    items: list[ApprovalRequestResponse]
    total: int
    page: int
    page_size: int
