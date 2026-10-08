from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.status_history import StatusHistory, get_entity_history
from app.modules.crm.models import Activity, Contact, Customer, CustomerAddress, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityResponse,
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    LeadConvertPayload,
    LeadCreate,
    LeadResponse,
    LeadTransitionPayload,
    LeadUpdate,
    OpportunityCreate,
    OpportunityResponse,
    OpportunityStage,
    OpportunityTransitionPayload,
    OpportunityUpdate,
    PaginatedCustomersResponse,
    PaginatedLeadsResponse,
    PaginatedOpportunitiesResponse,
    PipelineResponse,
    StatusHistoryResponse,
)
from app.modules.crm.service import CRMService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter(prefix="", tags=["CRM Core"])


def get_crm_service(db: Annotated[Session, Depends(get_db)]) -> CRMService:
    return CRMService(db)


# =============================================================================
# 1. Customers & Addresses
# =============================================================================
@router.get("/customers", response_model=PaginatedCustomersResponse)
def list_customers(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    owner_user_id: int | None = Query(None),
) -> PaginatedCustomersResponse:
    customers, total = service.list_customers(
        page=page, page_size=page_size, status=status, search=search, owner_user_id=owner_user_id
    )
    return PaginatedCustomersResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Customer:
    return service.get_customer(customer_id)


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Customer:
    return service.create_customer(payload, creator_id=current_user.id)


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Customer:
    return service.update_customer(customer_id, payload, updater_id=current_user.id)


@router.post("/customers/{customer_id}/deactivate", response_model=CustomerResponse)
def deactivate_customer(
    customer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Customer:
    return service.deactivate_customer(customer_id, updater_id=current_user.id)


@router.post(
    "/customers/{customer_id}/addresses",
    response_model=CustomerAddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_address(
    customer_id: int,
    payload: CustomerAddressCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> CustomerAddress:
    return service.add_address(customer_id, payload, creator_id=current_user.id)


@router.patch("/customers/addresses/{address_id}", response_model=CustomerAddressResponse)
def update_customer_address(
    address_id: int,
    payload: CustomerAddressUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> CustomerAddress:
    return service.update_address(address_id, payload, updater_id=current_user.id)


# =============================================================================
# 2. Contacts
# =============================================================================
@router.get("/customers/{customer_id}/contacts", response_model=list[ContactResponse])
def list_contacts(
    customer_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> list[Contact]:
    return service.list_contacts(customer_id)


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Contact:
    return service.create_contact(payload, creator_id=current_user.id)


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    payload: ContactUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Contact:
    return service.update_contact(contact_id, payload, updater_id=current_user.id)


# =============================================================================
# 3. Leads & Lead Conversion
# =============================================================================
@router.get("/leads", response_model=PaginatedLeadsResponse)
def list_leads(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    source: str | None = Query(None),
    search: str | None = Query(None),
    owner_user_id: int | None = Query(None),
) -> PaginatedLeadsResponse:
    leads, total = service.list_leads(
        page=page,
        page_size=page_size,
        status=status,
        source=source,
        search=search,
        owner_user_id=owner_user_id,
    )
    return PaginatedLeadsResponse(
        items=[LeadResponse.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Lead:
    return service.get_lead(lead_id)


@router.post("/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Lead:
    return service.create_lead(payload, creator_id=current_user.id)


@router.patch("/leads/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Lead:
    return service.update_lead(lead_id, payload, updater_id=current_user.id)


@router.post("/leads/{lead_id}/transition", response_model=LeadResponse)
def transition_lead(
    lead_id: int,
    payload: LeadTransitionPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Lead:
    return service.transition_lead(lead_id, payload, user_id=current_user.id)


@router.get("/leads/{lead_id}/duplicates", response_model=list[CustomerResponse])
def check_lead_duplicates(
    lead_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> list[Customer]:
    return service.check_lead_duplicate_customers(lead_id)


@router.post("/leads/{lead_id}/convert", response_model=LeadResponse)
def convert_lead(
    lead_id: int,
    payload: LeadConvertPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Lead:
    return service.convert_lead(lead_id, payload, user_id=current_user.id)


# =============================================================================
# 4. Opportunities & Pipeline
# =============================================================================
@router.get("/opportunities/pipeline", response_model=PipelineResponse)
def get_opportunity_pipeline(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
    owner_user_id: int | None = Query(None),
) -> PipelineResponse:
    return service.get_pipeline(owner_user_id=owner_user_id)


@router.get("/opportunities", response_model=PaginatedOpportunitiesResponse)
def list_opportunities(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    stage: OpportunityStage | None = Query(None),
    customer_id: int | None = Query(None),
    owner_user_id: int | None = Query(None),
) -> PaginatedOpportunitiesResponse:
    opps, total = service.list_opportunities(
        page=page,
        page_size=page_size,
        stage=stage,
        customer_id=customer_id,
        owner_user_id=owner_user_id,
    )
    return PaginatedOpportunitiesResponse(
        items=[OpportunityResponse.model_validate(o) for o in opps],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(
    opportunity_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Opportunity:
    return service.get_opportunity(opportunity_id)


@router.post(
    "/opportunities", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED
)
def create_opportunity(
    payload: OpportunityCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Opportunity:
    return service.create_opportunity(payload, creator_id=current_user.id)


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Opportunity:
    return service.update_opportunity(opportunity_id, payload, updater_id=current_user.id)


@router.post("/opportunities/{opportunity_id}/transition", response_model=OpportunityResponse)
def transition_opportunity(
    opportunity_id: int,
    payload: OpportunityTransitionPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Opportunity:
    return service.transition_opportunity(opportunity_id, payload, user_id=current_user.id)


# =============================================================================
# 5. Activities
# =============================================================================
@router.get("/activities", response_model=list[ActivityResponse])
def list_activities(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
    lead_id: int | None = Query(None),
    customer_id: int | None = Query(None),
    opportunity_id: int | None = Query(None),
) -> list[Activity]:
    return service.list_activities(
        lead_id=lead_id, customer_id=customer_id, opportunity_id=opportunity_id
    )


@router.post("/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ActivityCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Activity:
    return service.create_activity(payload, creator_id=current_user.id)


@router.post("/activities/{activity_id}/complete", response_model=ActivityResponse)
def complete_activity(
    activity_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CRMService, Depends(get_crm_service)],
) -> Activity:
    return service.complete_activity(activity_id, user_id=current_user.id)


# =============================================================================
# 6. Status History
# =============================================================================
@router.get("/history/{entity_type}/{entity_id}", response_model=list[StatusHistoryResponse])
def get_status_history(
    entity_type: str,
    entity_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[StatusHistory]:
    return get_entity_history(db, entity_type=entity_type, entity_id=entity_id)
