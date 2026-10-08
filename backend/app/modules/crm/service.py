from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import Clock, get_clock
from app.core.errors import AppException, ConflictException, NotFoundException
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.crm.models import Activity, Contact, Customer, CustomerAddress, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate,
    ContactCreate,
    ContactUpdate,
    CustomerAddressCreate,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerUpdate,
    LeadConvertPayload,
    LeadCreate,
    LeadTransitionPayload,
    LeadUpdate,
    OpportunityCreate,
    OpportunityStage,
    OpportunityTransitionPayload,
    OpportunityUpdate,
    PipelineResponse,
    PipelineStageItem,
)

# Standard opportunity stage probabilities per Roadmap V0.2
STAGE_PROBABILITIES: dict[OpportunityStage, Decimal] = {
    "discovery": Decimal("0.2000"),
    "proposal": Decimal("0.5000"),
    "negotiation": Decimal("0.7500"),
    "won": Decimal("1.0000"),
    "lost": Decimal("0.0000"),
}

# Allowed lead transition matrix
LEAD_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacted", "qualified", "disqualified"},
    "contacted": {"qualified", "disqualified"},
    "qualified": {"converted", "disqualified"},
    "disqualified": {"new"},
    "converted": set(),
}

# Allowed opportunity transition matrix
OPP_ALLOWED_TRANSITIONS: dict[OpportunityStage, set[OpportunityStage]] = {
    "discovery": {"proposal", "lost"},
    "proposal": {"negotiation", "discovery", "lost"},
    "negotiation": {"won", "proposal", "lost"},
    "won": set(),
    "lost": set(),
}


class CRMService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

    # =========================================================================
    # 1. Customers & Addresses
    # =========================================================================
    def list_customers(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        search: str | None = None,
        owner_user_id: int | None = None,
    ) -> tuple[list[Customer], int]:
        stmt = select(Customer).options(selectinload(Customer.addresses))
        count_stmt = select(func.count(Customer.id))

        if status:
            stmt = stmt.where(Customer.status == status)
            count_stmt = count_stmt.where(Customer.status == status)

        if owner_user_id is not None:
            stmt = stmt.where(Customer.owner_user_id == owner_user_id)
            count_stmt = count_stmt.where(Customer.owner_user_id == owner_user_id)

        if search:
            pattern = f"%{search.strip()}%"
            clause = or_(
                Customer.name.ilike(pattern),
                Customer.customer_no.ilike(pattern),
                Customer.email.ilike(pattern),
            )
            stmt = stmt.where(clause)
            count_stmt = count_stmt.where(clause)

        total = self.db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        customers = (
            self.db.execute(stmt.order_by(Customer.id.asc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(customers), total

    def get_customer(self, customer_id: int) -> Customer:
        stmt = (
            select(Customer)
            .where(Customer.id == customer_id)
            .options(selectinload(Customer.addresses), selectinload(Customer.contacts))
        )
        cust = self.db.execute(stmt).scalar_one_or_none()
        if not cust:
            raise NotFoundException(detail="Customer not found.")
        return cust

    def create_customer(self, data: CustomerCreate, creator_id: int | None = None) -> Customer:
        customer_no = generate_next_number(self.db, "customer", clock=self.clock)
        owner_id = data.owner_user_id if data.owner_user_id is not None else creator_id

        customer = Customer(
            customer_no=customer_no,
            name=data.name.strip(),
            customer_type=data.customer_type,
            status=data.status,
            tin=data.tin.strip() if data.tin else None,
            email=str(data.email).strip().lower() if data.email else None,
            phone=data.phone.strip() if data.phone else None,
            website=data.website.strip() if data.website else None,
            industry=data.industry.strip() if data.industry else None,
            payment_terms_days=data.payment_terms_days,
            credit_limit=data.credit_limit,
            owner_user_id=owner_id,
            notes=data.notes,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(customer)
        self.db.flush()

        if data.initial_address:
            addr = CustomerAddress(
                customer_id=customer.id,
                address_type=data.initial_address.address_type,
                line1=data.initial_address.line1.strip(),
                line2=data.initial_address.line2.strip() if data.initial_address.line2 else None,
                barangay=data.initial_address.barangay.strip()
                if data.initial_address.barangay
                else None,
                city=data.initial_address.city.strip(),
                province=data.initial_address.province.strip()
                if data.initial_address.province
                else None,
                postal_code=data.initial_address.postal_code.strip()
                if data.initial_address.postal_code
                else None,
                country_code=data.initial_address.country_code.strip().upper(),
                is_default=True,
                is_active=True,
                created_by=creator_id,
                updated_by=creator_id,
            )
            self.db.add(addr)

        record_status_change(
            db=self.db,
            entity_type="customer",
            entity_id=customer.id,
            to_status=customer.status,
            reason="Initial customer record created",
            changed_by=creator_id,
            clock=self.clock,
        )

        self.db.commit()
        return self.get_customer(customer.id)

    def update_customer(
        self, customer_id: int, data: CustomerUpdate, updater_id: int | None = None
    ) -> Customer:
        customer = self.get_customer(customer_id)
        if customer.version != data.version:
            raise ConflictException(
                detail="Customer record was modified by another transaction. Please reload."
            )

        if data.name is not None:
            customer.name = data.name.strip()
        if data.customer_type is not None:
            customer.customer_type = data.customer_type
        if data.status is not None and data.status != customer.status:
            old_status = customer.status
            customer.status = data.status
            record_status_change(
                db=self.db,
                entity_type="customer",
                entity_id=customer.id,
                from_status=old_status,
                to_status=customer.status,
                reason="Customer status updated",
                changed_by=updater_id,
                clock=self.clock,
            )

        if data.tin is not None:
            customer.tin = data.tin.strip() if data.tin else None
        if data.email is not None:
            customer.email = str(data.email).strip().lower() if data.email else None
        if data.phone is not None:
            customer.phone = data.phone.strip() if data.phone else None
        if data.website is not None:
            customer.website = data.website.strip() if data.website else None
        if data.industry is not None:
            customer.industry = data.industry.strip() if data.industry else None
        if data.payment_terms_days is not None:
            customer.payment_terms_days = data.payment_terms_days
        if data.credit_limit is not None:
            customer.credit_limit = data.credit_limit
        if data.owner_user_id is not None:
            customer.owner_user_id = data.owner_user_id
        if data.notes is not None:
            customer.notes = data.notes

        customer.version += 1
        customer.updated_by = updater_id
        self.db.commit()
        return self.get_customer(customer_id)

    def deactivate_customer(self, customer_id: int, updater_id: int | None = None) -> Customer:
        customer = self.get_customer(customer_id)
        old_status = customer.status
        customer.status = "inactive"
        customer.version += 1
        customer.updated_by = updater_id

        record_status_change(
            db=self.db,
            entity_type="customer",
            entity_id=customer.id,
            from_status=old_status,
            to_status="inactive",
            reason="Deactivated customer account",
            changed_by=updater_id,
            clock=self.clock,
        )

        self.db.commit()
        return self.get_customer(customer_id)

    def add_address(
        self, customer_id: int, data: CustomerAddressCreate, creator_id: int | None = None
    ) -> CustomerAddress:
        self.get_customer(customer_id)
        if data.is_default:
            defaults = (
                self.db.execute(
                    select(CustomerAddress).where(
                        CustomerAddress.customer_id == customer_id,
                        CustomerAddress.address_type == data.address_type,
                        CustomerAddress.is_default.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            for d in defaults:
                d.is_default = False

        address = CustomerAddress(
            customer_id=customer_id,
            address_type=data.address_type,
            line1=data.line1.strip(),
            line2=data.line2.strip() if data.line2 else None,
            barangay=data.barangay.strip() if data.barangay else None,
            city=data.city.strip(),
            province=data.province.strip() if data.province else None,
            postal_code=data.postal_code.strip() if data.postal_code else None,
            country_code=data.country_code.strip().upper(),
            is_default=data.is_default,
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(address)
        self.db.commit()
        self.db.refresh(address)
        return address

    def update_address(
        self, address_id: int, data: CustomerAddressUpdate, updater_id: int | None = None
    ) -> CustomerAddress:
        address = self.db.get(CustomerAddress, address_id)
        if not address:
            raise NotFoundException(detail="Address not found.")

        if data.is_default is True:
            defaults = (
                self.db.execute(
                    select(CustomerAddress).where(
                        CustomerAddress.customer_id == address.customer_id,
                        CustomerAddress.address_type == (data.address_type or address.address_type),
                        CustomerAddress.id != address_id,
                        CustomerAddress.is_default.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            for d in defaults:
                d.is_default = False

        if data.address_type is not None:
            address.address_type = data.address_type
        if data.line1 is not None:
            address.line1 = data.line1.strip()
        if data.line2 is not None:
            address.line2 = data.line2.strip() if data.line2 else None
        if data.barangay is not None:
            address.barangay = data.barangay.strip() if data.barangay else None
        if data.city is not None:
            address.city = data.city.strip()
        if data.province is not None:
            address.province = data.province.strip() if data.province else None
        if data.postal_code is not None:
            address.postal_code = data.postal_code.strip() if data.postal_code else None
        if data.country_code is not None:
            address.country_code = data.country_code.strip().upper()
        if data.is_default is not None:
            address.is_default = data.is_default
        if data.is_active is not None:
            address.is_active = data.is_active

        address.updated_by = updater_id
        self.db.commit()
        self.db.refresh(address)
        return address

    # =========================================================================
    # 2. Contacts
    # =========================================================================
    def list_contacts(self, customer_id: int) -> list[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.customer_id == customer_id, Contact.is_active.is_(True))
            .order_by(Contact.is_primary.desc(), Contact.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def create_contact(self, data: ContactCreate, creator_id: int | None = None) -> Contact:
        self.get_customer(data.customer_id)

        if data.is_primary:
            existing_primaries = (
                self.db.execute(
                    select(Contact).where(
                        Contact.customer_id == data.customer_id,
                        Contact.is_primary.is_(True),
                        Contact.is_active.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            for ep in existing_primaries:
                ep.is_primary = False

        contact = Contact(
            customer_id=data.customer_id,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip() if data.last_name else None,
            job_title=data.job_title.strip() if data.job_title else None,
            email=str(data.email).strip().lower() if data.email else None,
            phone=data.phone.strip() if data.phone else None,
            is_primary=data.is_primary,
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def update_contact(
        self, contact_id: int, data: ContactUpdate, updater_id: int | None = None
    ) -> Contact:
        contact = self.db.get(Contact, contact_id)
        if not contact:
            raise NotFoundException(detail="Contact not found.")

        if contact.version != data.version:
            raise ConflictException(detail="Contact record was modified by another session.")

        if data.is_primary is True:
            existing_primaries = (
                self.db.execute(
                    select(Contact).where(
                        Contact.customer_id == contact.customer_id,
                        Contact.id != contact_id,
                        Contact.is_primary.is_(True),
                        Contact.is_active.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            for ep in existing_primaries:
                ep.is_primary = False

        if data.first_name is not None:
            contact.first_name = data.first_name.strip()
        if data.last_name is not None:
            contact.last_name = data.last_name.strip() if data.last_name else None
        if data.job_title is not None:
            contact.job_title = data.job_title.strip() if data.job_title else None
        if data.email is not None:
            contact.email = str(data.email).strip().lower() if data.email else None
        if data.phone is not None:
            contact.phone = data.phone.strip() if data.phone else None
        if data.is_primary is not None:
            contact.is_primary = data.is_primary
        if data.is_active is not None:
            contact.is_active = data.is_active

        contact.version += 1
        contact.updated_by = updater_id
        self.db.commit()
        self.db.refresh(contact)
        return contact

    # =========================================================================
    # 3. Leads & Lead Conversion
    # =========================================================================
    def list_leads(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        source: str | None = None,
        search: str | None = None,
        owner_user_id: int | None = None,
    ) -> tuple[list[Lead], int]:
        stmt = select(Lead)
        count_stmt = select(func.count(Lead.id))

        if status:
            stmt = stmt.where(Lead.status == status)
            count_stmt = count_stmt.where(Lead.status == status)
        if source:
            stmt = stmt.where(Lead.source == source)
            count_stmt = count_stmt.where(Lead.source == source)
        if owner_user_id is not None:
            stmt = stmt.where(Lead.owner_user_id == owner_user_id)
            count_stmt = count_stmt.where(Lead.owner_user_id == owner_user_id)
        if search:
            pattern = f"%{search.strip()}%"
            clause = or_(
                Lead.lead_no.ilike(pattern),
                Lead.first_name.ilike(pattern),
                Lead.last_name.ilike(pattern),
                Lead.company_name.ilike(pattern),
                Lead.email.ilike(pattern),
            )
            stmt = stmt.where(clause)
            count_stmt = count_stmt.where(clause)

        total = self.db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        leads = (
            self.db.execute(stmt.order_by(Lead.id.desc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(leads), total

    def get_lead(self, lead_id: int) -> Lead:
        lead = self.db.get(Lead, lead_id)
        if not lead:
            raise NotFoundException(detail="Lead not found.")
        return lead

    def create_lead(self, data: LeadCreate, creator_id: int | None = None) -> Lead:
        if not data.email and not data.phone:
            raise AppException(
                status_code=400,
                code="CONTACT_INFO_REQUIRED",
                title="Bad Request",
                detail="A lead must have at least an email or a phone number.",
            )

        lead_no = generate_next_number(self.db, "lead", clock=self.clock)
        owner_id = data.owner_user_id if data.owner_user_id is not None else creator_id

        lead = Lead(
            lead_no=lead_no,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip() if data.last_name else None,
            company_name=data.company_name.strip() if data.company_name else None,
            job_title=data.job_title.strip() if data.job_title else None,
            email=str(data.email).strip().lower() if data.email else None,
            phone=data.phone.strip() if data.phone else None,
            source=data.source,
            status="new",
            owner_user_id=owner_id,
            notes=data.notes,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(lead)
        self.db.flush()

        record_status_change(
            db=self.db,
            entity_type="lead",
            entity_id=lead.id,
            to_status="new",
            reason="Lead captured",
            changed_by=creator_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(lead)
        return lead

    def update_lead(self, lead_id: int, data: LeadUpdate, updater_id: int | None = None) -> Lead:
        lead = self.get_lead(lead_id)
        if lead.version != data.version:
            raise ConflictException(detail="Lead record was modified by another user.")
        if lead.status == "converted":
            raise AppException(
                status_code=400,
                code="LEAD_ALREADY_CONVERTED",
                title="Bad Request",
                detail="A converted lead cannot be modified.",
            )

        if data.first_name is not None:
            lead.first_name = data.first_name.strip()
        if data.last_name is not None:
            lead.last_name = data.last_name.strip() if data.last_name else None
        if data.company_name is not None:
            lead.company_name = data.company_name.strip() if data.company_name else None
        if data.job_title is not None:
            lead.job_title = data.job_title.strip() if data.job_title else None
        if data.email is not None:
            lead.email = str(data.email).strip().lower() if data.email else None
        if data.phone is not None:
            lead.phone = data.phone.strip() if data.phone else None
        if data.source is not None:
            lead.source = data.source
        if data.owner_user_id is not None:
            lead.owner_user_id = data.owner_user_id
        if data.notes is not None:
            lead.notes = data.notes

        lead.version += 1
        lead.updated_by = updater_id
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def transition_lead(
        self, lead_id: int, payload: LeadTransitionPayload, user_id: int | None = None
    ) -> Lead:
        """Transitions lead between statuses according to the state machine matrix."""
        lead = self.get_lead(lead_id)
        from_status = lead.status
        to_status = payload.to_status

        if to_status == "converted":
            raise AppException(
                status_code=400,
                code="INVALID_TRANSITION",
                title="Bad Request",
                detail="Leads can only be converted via the /convert action.",
            )

        allowed = LEAD_ALLOWED_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise AppException(
                status_code=400,
                code="INVALID_LEAD_TRANSITION",
                title="Invalid State Transition",
                detail=f"Cannot transition lead from '{from_status}' to '{to_status}'.",
            )

        if to_status == "disqualified" and not payload.reason:
            raise AppException(
                status_code=400,
                code="REASON_REQUIRED",
                title="Bad Request",
                detail="A disqualification reason is required.",
            )

        lead.status = to_status
        if to_status == "disqualified":
            lead.disqualified_reason = payload.reason
        else:
            lead.disqualified_reason = None

        lead.version += 1
        lead.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="lead",
            entity_id=lead.id,
            from_status=from_status,
            to_status=to_status,
            reason=payload.reason,
            changed_by=user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(lead)
        return lead

    def check_lead_duplicate_customers(self, lead_id: int) -> list[Customer]:
        """Rule 3: Warning check for possible duplicate customer matches."""
        lead = self.get_lead(lead_id)
        conditions = []
        if lead.email:
            conditions.append(func.lower(Customer.email) == lead.email.lower())
        if lead.company_name:
            conditions.append(Customer.name.ilike(f"%{lead.company_name.strip()}%"))

        if not conditions:
            return []

        stmt = select(Customer).where(or_(*conditions)).limit(5)
        return list(self.db.execute(stmt).scalars().all())

    def convert_lead(
        self, lead_id: int, payload: LeadConvertPayload, user_id: int | None = None
    ) -> Lead:
        """
        Rule 1: Lead conversion is one atomic DB transaction:
        - Creates a new prospect Customer (or links existing)
        - Creates a Contact from the lead
        - Optionally creates an Opportunity
        - Sets lead status to 'converted' and records status_history
        Rule 2: Only 'qualified' leads can be converted. Converting twice returns 409 Conflict.
        """
        lead = self.get_lead(lead_id)

        if lead.status == "converted":
            raise ConflictException(
                detail="This lead has already been converted.",
                code="LEAD_ALREADY_CONVERTED",
            )

        if lead.status != "qualified":
            raise AppException(
                status_code=400,
                code="LEAD_NOT_QUALIFIED",
                title="Bad Request",
                detail=f"Only qualified leads can be converted. Current status is '{lead.status}'.",
            )

        now = self.clock.now()

        # 1. Resolve or create customer (prospect)
        if payload.link_existing_customer_id:
            customer = self.db.get(Customer, payload.link_existing_customer_id)
            if not customer:
                raise NotFoundException(detail="Specified customer to link was not found.")
        else:
            cust_name = (
                payload.new_customer_name
                or lead.company_name
                or f"{lead.first_name} {lead.last_name or ''}".strip()
            )
            customer_no = generate_next_number(self.db, "customer", clock=self.clock)
            customer = Customer(
                customer_no=customer_no,
                name=cust_name,
                customer_type="company" if lead.company_name else "individual",
                status="prospect",  # Created as prospect per V2 decision
                email=lead.email,
                phone=lead.phone,
                owner_user_id=lead.owner_user_id or user_id,
                created_by=user_id,
                updated_by=user_id,
            )
            self.db.add(customer)
            self.db.flush()

            record_status_change(
                db=self.db,
                entity_type="customer",
                entity_id=customer.id,
                to_status="prospect",
                reason=f"Created via conversion from lead {lead.lead_no}",
                changed_by=user_id,
                clock=self.clock,
            )

        # 2. Create contact from lead
        contact = Contact(
            customer_id=customer.id,
            first_name=lead.first_name,
            last_name=lead.last_name,
            job_title=lead.job_title,
            email=lead.email,
            phone=lead.phone,
            is_primary=True,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(contact)
        self.db.flush()

        # 3. Create opportunity if requested
        created_opp: Opportunity | None = None
        if payload.create_opportunity:
            opp_name = payload.opportunity_name or f"Deal for {customer.name}"
            opp_no = generate_next_number(self.db, "opportunity", clock=self.clock)
            created_opp = Opportunity(
                opportunity_no=opp_no,
                name=opp_name,
                customer_id=customer.id,
                primary_contact_id=contact.id,
                stage="discovery",
                estimated_amount=payload.opportunity_estimated_amount,
                probability=STAGE_PROBABILITIES["discovery"],
                expected_close_date=payload.expected_close_date,
                source_lead_id=lead.id,
                owner_user_id=lead.owner_user_id or user_id,
                created_by=user_id,
                updated_by=user_id,
            )
            self.db.add(created_opp)
            self.db.flush()

            record_status_change(
                db=self.db,
                entity_type="opportunity",
                entity_id=created_opp.id,
                to_status="discovery",
                reason=f"Opportunity created via lead {lead.lead_no} conversion",
                changed_by=user_id,
                clock=self.clock,
            )

        # 4. Finalize lead conversion
        old_lead_status = lead.status
        lead.status = "converted"
        lead.converted_at = now
        lead.converted_customer_id = customer.id
        lead.converted_contact_id = contact.id
        lead.converted_opportunity_id = created_opp.id if created_opp else None
        lead.version += 1
        lead.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="lead",
            entity_id=lead.id,
            from_status=old_lead_status,
            to_status="converted",
            reason=f"Converted to customer {customer.customer_no}",
            changed_by=user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(lead)
        return lead

    # =========================================================================
    # 4. Opportunities & Pipeline
    # =========================================================================
    def list_opportunities(
        self,
        page: int = 1,
        page_size: int = 25,
        stage: OpportunityStage | None = None,
        customer_id: int | None = None,
        owner_user_id: int | None = None,
    ) -> tuple[list[Opportunity], int]:
        stmt = select(Opportunity)
        count_stmt = select(func.count(Opportunity.id))

        if stage:
            stmt = stmt.where(Opportunity.stage == stage)
            count_stmt = count_stmt.where(Opportunity.stage == stage)
        if customer_id:
            stmt = stmt.where(Opportunity.customer_id == customer_id)
            count_stmt = count_stmt.where(Opportunity.customer_id == customer_id)
        if owner_user_id is not None:
            stmt = stmt.where(Opportunity.owner_user_id == owner_user_id)
            count_stmt = count_stmt.where(Opportunity.owner_user_id == owner_user_id)

        total = self.db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        opps = (
            self.db.execute(stmt.order_by(Opportunity.id.desc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(opps), total

    def get_opportunity(self, opportunity_id: int) -> Opportunity:
        opp = self.db.get(Opportunity, opportunity_id)
        if not opp:
            raise NotFoundException(detail="Opportunity not found.")
        return opp

    def create_opportunity(
        self, data: OpportunityCreate, creator_id: int | None = None
    ) -> Opportunity:
        self.get_customer(data.customer_id)
        opp_no = generate_next_number(self.db, "opportunity", clock=self.clock)
        owner_id = data.owner_user_id if data.owner_user_id is not None else creator_id

        prob = (
            data.probability
            if data.probability is not None
            else STAGE_PROBABILITIES.get(data.stage, Decimal("0.2000"))
        )

        opp = Opportunity(
            opportunity_no=opp_no,
            name=data.name.strip(),
            customer_id=data.customer_id,
            primary_contact_id=data.primary_contact_id,
            stage=data.stage,
            estimated_amount=data.estimated_amount,
            probability=prob,
            expected_close_date=data.expected_close_date,
            source_lead_id=data.source_lead_id,
            owner_user_id=owner_id,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(opp)
        self.db.flush()

        record_status_change(
            db=self.db,
            entity_type="opportunity",
            entity_id=opp.id,
            to_status=opp.stage,
            reason="Opportunity opened",
            changed_by=creator_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(opp)
        return opp

    def update_opportunity(
        self, opportunity_id: int, data: OpportunityUpdate, updater_id: int | None = None
    ) -> Opportunity:
        opp = self.get_opportunity(opportunity_id)
        if opp.version != data.version:
            raise ConflictException(detail="Opportunity was modified by another session.")
        if opp.stage in ("won", "lost"):
            raise AppException(
                status_code=400,
                code="OPPORTUNITY_CLOSED",
                title="Bad Request",
                detail="Closed opportunities cannot be edited.",
            )

        if data.name is not None:
            opp.name = data.name.strip()
        if data.primary_contact_id is not None:
            opp.primary_contact_id = data.primary_contact_id
        if data.estimated_amount is not None:
            opp.estimated_amount = data.estimated_amount
        if data.probability is not None:
            opp.probability = data.probability
        if data.expected_close_date is not None:
            opp.expected_close_date = data.expected_close_date
        if data.owner_user_id is not None:
            opp.owner_user_id = data.owner_user_id

        opp.version += 1
        opp.updated_by = updater_id
        self.db.commit()
        self.db.refresh(opp)
        return opp

    def transition_opportunity(
        self, opportunity_id: int, payload: OpportunityTransitionPayload, user_id: int | None = None
    ) -> Opportunity:
        """
        Enforces opportunity stage machine.
        Rule 4: Won or Lost sets closed_at; Lost requires lost_reason.
        Rule 6: Won opportunity promotes prospect customer to active!
        """
        opp = self.get_opportunity(opportunity_id)
        from_stage = opp.stage
        to_stage = payload.to_stage

        allowed = OPP_ALLOWED_TRANSITIONS.get(from_stage, set())
        if to_stage not in allowed:
            raise AppException(
                status_code=400,
                code="INVALID_STAGE_TRANSITION",
                title="Invalid Stage Transition",
                detail=f"Cannot transition opportunity from '{from_stage}' to '{to_stage}'.",
            )

        if to_stage == "lost" and not payload.lost_reason:
            raise AppException(
                status_code=400,
                code="LOST_REASON_REQUIRED",
                title="Bad Request",
                detail="A valid lost reason is required when marking an opportunity lost.",
            )

        now = self.clock.now()
        opp.stage = to_stage
        opp.probability = STAGE_PROBABILITIES[to_stage]

        if to_stage in ("won", "lost"):
            opp.closed_at = now
            opp.lost_reason = payload.lost_reason if to_stage == "lost" else None
        else:
            opp.closed_at = None
            opp.lost_reason = None

        opp.version += 1
        opp.updated_by = user_id

        record_status_change(
            db=self.db,
            entity_type="opportunity",
            entity_id=opp.id,
            from_status=from_stage,
            to_status=to_stage,
            reason=payload.reason or payload.lost_reason,
            changed_by=user_id,
            clock=self.clock,
        )

        # Rule 6: If won, promote prospect customer to active!
        if to_stage == "won":
            customer = self.db.get(Customer, opp.customer_id)
            if customer and customer.status == "prospect":
                customer.status = "active"
                customer.version += 1
                customer.updated_by = user_id

                record_status_change(
                    db=self.db,
                    entity_type="customer",
                    entity_id=customer.id,
                    from_status="prospect",
                    to_status="active",
                    reason=f"Customer activated via won opportunity {opp.opportunity_no}",
                    changed_by=user_id,
                    clock=self.clock,
                )

        self.db.commit()
        self.db.refresh(opp)
        return opp

    def get_pipeline(self, owner_user_id: int | None = None) -> PipelineResponse:
        """Returns sales pipeline breakdown grouped by stage with weighted totals."""
        stages: list[OpportunityStage] = ["discovery", "proposal", "negotiation", "won", "lost"]
        stage_items: list[PipelineStageItem] = []
        total_pipeline_val = Decimal("0.00")
        total_weighted_val = Decimal("0.00")

        for stage_name in stages:
            stmt = select(Opportunity).where(Opportunity.stage == stage_name)
            if owner_user_id is not None:
                stmt = stmt.where(Opportunity.owner_user_id == owner_user_id)

            opps = list(self.db.execute(stmt.order_by(Opportunity.id.desc())).scalars().all())
            stage_total = sum((o.estimated_amount for o in opps), Decimal("0.00"))
            stage_weighted = sum(
                (o.estimated_amount * o.probability for o in opps), Decimal("0.00")
            )

            if stage_name not in ("won", "lost"):
                total_pipeline_val += stage_total
                total_weighted_val += stage_weighted

            stage_items.append(
                PipelineStageItem(
                    stage=stage_name,
                    count=len(opps),
                    total_amount=stage_total,
                    weighted_amount=stage_weighted,
                    opportunities=opps,
                )
            )

        return PipelineResponse(
            stages=stage_items,
            total_pipeline_value=total_pipeline_val,
            total_weighted_value=total_weighted_val,
        )

    # =========================================================================
    # 5. Activities
    # =========================================================================
    def list_activities(
        self,
        lead_id: int | None = None,
        customer_id: int | None = None,
        opportunity_id: int | None = None,
    ) -> list[Activity]:
        stmt = select(Activity)
        if lead_id:
            stmt = stmt.where(Activity.lead_id == lead_id)
        if customer_id:
            stmt = stmt.where(Activity.customer_id == customer_id)
        if opportunity_id:
            stmt = stmt.where(Activity.opportunity_id == opportunity_id)

        return list(self.db.execute(stmt.order_by(Activity.created_at.desc())).scalars().all())

    def create_activity(self, data: ActivityCreate, creator_id: int | None = None) -> Activity:
        if not any([data.lead_id, data.customer_id, data.contact_id, data.opportunity_id]):
            raise AppException(
                status_code=400,
                code="ACTIVITY_RELATION_REQUIRED",
                title="Bad Request",
                detail="An activity must be linked to at least one CRM entity.",
            )

        activity = Activity(
            activity_type=data.activity_type,
            subject=data.subject.strip(),
            body=data.body.strip() if data.body else None,
            due_at=data.due_at,
            owner_user_id=data.owner_user_id or creator_id,
            lead_id=data.lead_id,
            customer_id=data.customer_id,
            contact_id=data.contact_id,
            opportunity_id=data.opportunity_id,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity

    def complete_activity(self, activity_id: int, user_id: int | None = None) -> Activity:
        act = self.db.get(Activity, activity_id)
        if not act:
            raise NotFoundException(detail="Activity not found.")
        act.completed_at = self.clock.now()
        act.updated_by = user_id
        self.db.commit()
        self.db.refresh(act)
        return act
