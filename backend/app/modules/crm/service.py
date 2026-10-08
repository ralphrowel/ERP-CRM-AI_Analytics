from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import Clock, get_clock
from app.core.errors import ConflictException, NotFoundException
from app.core.numbering import generate_next_number
from app.modules.crm.models import Customer, CustomerAddress
from app.modules.crm.schemas import (
    CustomerAddressCreate,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerUpdate,
)


class CustomerService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

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
            search_filter = f"%{search.strip()}%"
            term_clause = or_(
                Customer.name.ilike(search_filter),
                Customer.customer_no.ilike(search_filter),
                Customer.email.ilike(search_filter),
            )
            stmt = stmt.where(term_clause)
            count_stmt = count_stmt.where(term_clause)

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
            .options(selectinload(Customer.addresses))
        )
        customer = self.db.execute(stmt).scalar_one_or_none()
        if not customer:
            raise NotFoundException(detail="Customer not found.")
        return customer

    def create_customer(self, data: CustomerCreate, creator_id: int | None = None) -> Customer:
        # Generate gapless customer number CUS-000001 (Roadmap §4.5)
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

        self.db.commit()
        return self.get_customer(customer.id)

    def update_customer(
        self, customer_id: int, data: CustomerUpdate, updater_id: int | None = None
    ) -> Customer:
        customer = self.get_customer(customer_id)

        # Optimistic locking check (Roadmap §4.1)
        if customer.version != data.version:
            raise ConflictException(
                detail="Customer record was modified by another transaction. Please reload."
            )

        if data.name is not None:
            customer.name = data.name.strip()
        if data.customer_type is not None:
            customer.customer_type = data.customer_type
        if data.status is not None:
            customer.status = data.status
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
        customer.status = "inactive"
        customer.version += 1
        customer.updated_by = updater_id
        self.db.commit()
        return self.get_customer(customer_id)

    def add_address(
        self, customer_id: int, data: CustomerAddressCreate, creator_id: int | None = None
    ) -> CustomerAddress:
        self.get_customer(customer_id)

        # If marked default, unset existing default for this address type
        if data.is_default:
            existing_defaults = (
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
            for addr in existing_defaults:
                addr.is_default = False

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
            raise NotFoundException(detail="Customer address not found.")

        if data.is_default is True:
            existing_defaults = (
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
            for existing in existing_defaults:
                existing.is_default = False

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
