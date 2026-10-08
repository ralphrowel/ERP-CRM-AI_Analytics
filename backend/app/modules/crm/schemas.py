from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Customer & Address (Existing) ---
class CustomerAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    address_type: Literal["billing", "shipping"]
    line1: str
    line2: str | None = None
    barangay: str | None = None
    city: str
    province: str | None = None
    postal_code: str | None = None
    country_code: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerAddressCreate(BaseModel):
    address_type: Literal["billing", "shipping"]
    line1: str = Field(..., min_length=2)
    line2: str | None = None
    barangay: str | None = None
    city: str = Field(..., min_length=2)
    province: str | None = None
    postal_code: str | None = None
    country_code: str = Field("PH", min_length=2, max_length=2)
    is_default: bool = False


class CustomerAddressUpdate(BaseModel):
    address_type: Literal["billing", "shipping"] | None = None
    line1: str | None = None
    line2: str | None = None
    barangay: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_no: str
    name: str
    customer_type: Literal["company", "individual"]
    status: Literal["prospect", "active", "inactive"]
    tin: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int
    credit_limit: Decimal | None = None
    owner_user_id: int | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    addresses: list[CustomerAddressResponse] = []


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=2)
    customer_type: Literal["company", "individual"] = "company"
    status: Literal["prospect", "active", "inactive"] = "active"
    tin: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int = Field(0, ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    owner_user_id: int | None = None
    notes: str | None = None
    initial_address: CustomerAddressCreate | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    customer_type: Literal["company", "individual"] | None = None
    status: Literal["prospect", "active", "inactive"] | None = None
    tin: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int | None = Field(None, ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    owner_user_id: int | None = None
    notes: str | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedCustomersResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int


# --- Contacts ---
class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    first_name: str
    last_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_primary: bool
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ContactCreate(BaseModel):
    customer_id: int
    first_name: str = Field(..., min_length=1)
    last_name: str | None = None
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    is_primary: bool = False


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    is_primary: bool | None = None
    is_active: bool | None = None
    version: int = Field(..., description="Optimistic locking version")


# --- Leads ---
LeadSource = Literal["website", "referral", "event", "cold_call", "social", "import", "other"]
LeadStatus = Literal["new", "contacted", "qualified", "disqualified", "converted"]


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_no: str
    first_name: str
    last_name: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    source: LeadSource
    status: LeadStatus
    disqualified_reason: str | None = None
    owner_user_id: int | None = None
    converted_at: datetime | None = None
    converted_customer_id: int | None = None
    converted_contact_id: int | None = None
    converted_opportunity_id: int | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    source: LeadSource = "website"
    owner_user_id: int | None = None
    notes: str | None = None


class LeadUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    source: LeadSource | None = None
    owner_user_id: int | None = None
    notes: str | None = None
    version: int = Field(..., description="Optimistic locking version")


class LeadTransitionPayload(BaseModel):
    to_status: LeadStatus
    reason: str | None = None


class LeadConvertPayload(BaseModel):
    # User can either link an existing customer or create a new prospect customer
    link_existing_customer_id: int | None = None
    new_customer_name: str | None = None
    create_opportunity: bool = True
    opportunity_name: str | None = None
    opportunity_estimated_amount: Decimal = Field(Decimal("0.00"), ge=0)
    expected_close_date: date | None = None


class PaginatedLeadsResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    page_size: int


# --- Opportunities ---
OpportunityStage = Literal["discovery", "proposal", "negotiation", "won", "lost"]
LostReason = Literal["price", "competitor", "no_budget", "no_decision", "timing", "other"]


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_no: str
    name: str
    customer_id: int
    primary_contact_id: int | None = None
    stage: OpportunityStage
    estimated_amount: Decimal
    probability: Decimal
    expected_close_date: date | None = None
    closed_at: datetime | None = None
    lost_reason: str | None = None
    source_lead_id: int | None = None
    owner_user_id: int | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class OpportunityCreate(BaseModel):
    name: str = Field(..., min_length=2)
    customer_id: int
    primary_contact_id: int | None = None
    stage: OpportunityStage = "discovery"
    estimated_amount: Decimal = Field(Decimal("0.00"), ge=0)
    probability: Decimal | None = None  # Defaults to stage standard if not specified
    expected_close_date: date | None = None
    source_lead_id: int | None = None
    owner_user_id: int | None = None


class OpportunityUpdate(BaseModel):
    name: str | None = None
    primary_contact_id: int | None = None
    estimated_amount: Decimal | None = Field(None, ge=0)
    probability: Decimal | None = None
    expected_close_date: date | None = None
    owner_user_id: int | None = None
    version: int = Field(..., description="Optimistic locking version")


class OpportunityTransitionPayload(BaseModel):
    to_stage: OpportunityStage
    lost_reason: LostReason | None = None
    reason: str | None = None


class PipelineStageItem(BaseModel):
    stage: OpportunityStage
    count: int
    total_amount: Decimal
    weighted_amount: Decimal
    opportunities: list[OpportunityResponse]


class PipelineResponse(BaseModel):
    stages: list[PipelineStageItem]
    total_pipeline_value: Decimal
    total_weighted_value: Decimal


class PaginatedOpportunitiesResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int


# --- Activities ---
ActivityType = Literal["call", "email", "meeting", "task", "note"]


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_type: ActivityType
    subject: str
    body: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    owner_user_id: int | None = None
    lead_id: int | None = None
    customer_id: int | None = None
    contact_id: int | None = None
    opportunity_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ActivityCreate(BaseModel):
    activity_type: ActivityType
    subject: str = Field(..., min_length=1)
    body: str | None = None
    due_at: datetime | None = None
    owner_user_id: int | None = None
    lead_id: int | None = None
    customer_id: int | None = None
    contact_id: int | None = None
    opportunity_id: int | None = None


# --- Status History ---
class StatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    from_status: str | None = None
    to_status: str
    reason: str | None = None
    changed_by: int | None = None
    changed_at: datetime
