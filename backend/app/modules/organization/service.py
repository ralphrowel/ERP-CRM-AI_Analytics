from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.errors import AppException, ConflictException, NotFoundException
from app.core.numbering import generate_next_number
from app.modules.organization.models import CompanySettings, Department, Employee
from app.modules.organization.schemas import (
    CompanySettingsUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeUpdate,
)


class OrganizationService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

    # --- Company Settings ---
    def get_or_create_settings(self) -> CompanySettings:
        settings = self.db.get(CompanySettings, 1)
        if not settings:
            settings = CompanySettings(
                id=1,
                legal_name="ERP/CRM Learning Enterprise, Inc.",
                trade_name="Learning ERP",
                tin="000-123-456-000",
                address="Metro Manila, Philippines",
                currency_code="PHP",
                timezone="Asia/Manila",
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        return settings

    def update_settings(
        self, data: CompanySettingsUpdate, updater_id: int | None = None
    ) -> CompanySettings:
        settings = self.get_or_create_settings()
        settings.legal_name = data.legal_name
        settings.trade_name = data.trade_name
        settings.tin = data.tin
        settings.address = data.address
        settings.updated_by = updater_id
        self.db.commit()
        self.db.refresh(settings)
        return settings

    # --- Departments ---
    def list_departments(self, include_inactive: bool = False) -> list[Department]:
        stmt = select(Department).order_by(Department.code.asc())
        if not include_inactive:
            stmt = stmt.where(Department.is_active.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def create_department(
        self, data: DepartmentCreate, creator_id: int | None = None
    ) -> Department:
        code_upper = data.code.strip().upper()
        existing = self.db.execute(
            select(Department).where(Department.code == code_upper)
        ).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="DEPARTMENT_CODE_EXISTS",
                title="Bad Request",
                detail=f"Department with code '{code_upper}' already exists.",
            )

        dept = Department(
            code=code_upper,
            name=data.name.strip(),
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def update_department(
        self, department_id: int, data: DepartmentUpdate, updater_id: int | None = None
    ) -> Department:
        dept = self.db.get(Department, department_id)
        if not dept:
            raise NotFoundException(detail="Department not found.")

        if data.name is not None:
            dept.name = data.name.strip()
        if data.is_active is not None:
            dept.is_active = data.is_active

        dept.updated_by = updater_id
        self.db.commit()
        self.db.refresh(dept)
        return dept

    # --- Employees ---
    def list_employees(
        self,
        page: int = 1,
        page_size: int = 25,
        department_id: int | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Employee], int]:
        stmt = select(Employee)
        count_stmt = select(func.count(Employee.id))

        if department_id is not None:
            stmt = stmt.where(Employee.department_id == department_id)
            count_stmt = count_stmt.where(Employee.department_id == department_id)
        if is_active is not None:
            stmt = stmt.where(Employee.is_active == is_active)
            count_stmt = count_stmt.where(Employee.is_active == is_active)

        total = self.db.execute(count_stmt).scalar_one()
        offset = (page - 1) * page_size
        employees = (
            self.db.execute(stmt.order_by(Employee.id.asc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(employees), total

    def get_employee(self, employee_id: int) -> Employee:
        emp = self.db.get(Employee, employee_id)
        if not emp:
            raise NotFoundException(detail="Employee not found.")
        return emp

    def create_employee(self, data: EmployeeCreate, creator_id: int | None = None) -> Employee:
        # Verify department exists and is active
        dept = self.db.get(Department, data.department_id)
        if not dept or not dept.is_active:
            raise AppException(
                status_code=400,
                code="INVALID_DEPARTMENT",
                title="Bad Request",
                detail="Assigned department does not exist or is inactive.",
            )

        if data.termination_date and data.termination_date < data.hire_date:
            raise AppException(
                status_code=400,
                code="INVALID_DATES",
                title="Bad Request",
                detail="Termination date cannot precede hire date.",
            )

        # Generate gapless employee number EMP-0001 per §4.5
        employee_no = generate_next_number(self.db, "employee", clock=self.clock)

        emp = Employee(
            employee_no=employee_no,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            email=str(data.email).strip().lower() if data.email else None,
            phone=data.phone.strip() if data.phone else None,
            department_id=data.department_id,
            job_title=data.job_title.strip() if data.job_title else None,
            manager_id=data.manager_id,
            user_id=data.user_id,
            hire_date=data.hire_date,
            termination_date=data.termination_date,
            is_active=True,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(emp)
        self.db.commit()
        self.db.refresh(emp)
        return emp

    def update_employee(
        self, employee_id: int, data: EmployeeUpdate, updater_id: int | None = None
    ) -> Employee:
        emp = self.get_employee(employee_id)

        # Optimistic locking check (§4.1)
        if emp.version != data.version:
            raise ConflictException(
                detail="Employee record was modified by another user. Please reload."
            )

        hire_date = data.hire_date or emp.hire_date
        term_date = (
            data.termination_date if data.termination_date is not None else emp.termination_date
        )
        if term_date and term_date < hire_date:
            raise AppException(
                status_code=400,
                code="INVALID_DATES",
                title="Bad Request",
                detail="Termination date cannot precede hire date.",
            )

        if data.first_name is not None:
            emp.first_name = data.first_name.strip()
        if data.last_name is not None:
            emp.last_name = data.last_name.strip()
        if data.email is not None:
            emp.email = str(data.email).strip().lower() if data.email else None
        if data.phone is not None:
            emp.phone = data.phone.strip() if data.phone else None
        if data.department_id is not None:
            dept = self.db.get(Department, data.department_id)
            if not dept or not dept.is_active:
                raise AppException(
                    status_code=400,
                    code="INVALID_DEPARTMENT",
                    title="Bad Request",
                    detail="Assigned department does not exist or is inactive.",
                )
            emp.department_id = data.department_id
        if data.job_title is not None:
            emp.job_title = data.job_title.strip() if data.job_title else None
        if data.manager_id is not None:
            emp.manager_id = data.manager_id
        if data.user_id is not None:
            emp.user_id = data.user_id
        if data.hire_date is not None:
            emp.hire_date = data.hire_date
        if data.termination_date is not None:
            emp.termination_date = data.termination_date
        if data.is_active is not None:
            emp.is_active = data.is_active

        emp.version += 1
        emp.updated_by = updater_id
        self.db.commit()
        self.db.refresh(emp)
        return emp

    def deactivate_employee(self, employee_id: int, updater_id: int | None = None) -> Employee:
        emp = self.get_employee(employee_id)
        emp.is_active = False
        emp.version += 1
        emp.updated_by = updater_id
        self.db.commit()
        self.db.refresh(emp)
        return emp
