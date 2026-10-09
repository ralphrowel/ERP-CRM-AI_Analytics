from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.authorization import (
    ScopeContext,
    get_user_effective_permissions,
)
from app.core.database import Base, get_db
from app.core.errors import NotFoundException
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.crm.schemas import CustomerCreate
from app.modules.crm.service import CRMService
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
)
from app.modules.identity.service import IdentityService
from app.modules.organization.models import Department, Employee
from app.modules.sales.models import TaxRate


@pytest.fixture
def rbac_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed sequences
    seqs = [
        DocumentSequence(
            doc_type="customer", prefix="CUS", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(doc_type="lead", prefix="LD", include_year=False, padding=6, next_value=1),
        DocumentSequence(
            doc_type="opportunity", prefix="OPP", include_year=False, padding=6, next_value=1
        ),
        DocumentSequence(doc_type="quote", prefix="QT", include_year=True, padding=6, next_value=1),
        DocumentSequence(
            doc_type="sales_order", prefix="SO", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="invoice", prefix="INV", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="payment", prefix="PAY", include_year=True, padding=6, next_value=1
        ),
        DocumentSequence(
            doc_type="credit_note", prefix="CN", include_year=True, padding=6, next_value=1
        ),
    ]
    session.add_all(seqs)

    # Seed Tax Rate
    tr = TaxRate(
        code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True
    )
    session.add(tr)

    # Seed Permissions Catalog
    perms = [
        Permission(code="customer:read", description="View customers", module="crm"),
        Permission(code="customer:create", description="Create customers", module="crm"),
        Permission(code="customer:update", description="Update customers", module="crm"),
        Permission(code="lead:read", description="View leads", module="crm"),
        Permission(code="lead:create", description="Create leads", module="crm"),
        Permission(code="lead:update", description="Update leads", module="crm"),
        Permission(code="opportunity:read", description="View deals", module="crm"),
        Permission(code="quote:read", description="View quotes", module="sales"),
        Permission(code="quote:create", description="Create quotes", module="sales"),
        Permission(code="invoice:read", description="View invoices", module="sales"),
        Permission(code="invoice:issue", description="Issue invoices", module="sales"),
        Permission(code="role:read", description="View roles", module="identity"),
        Permission(code="role:update", description="Update roles", module="identity"),
        Permission(code="role:assign", description="Assign roles", module="identity"),
    ]
    session.add_all(perms)
    session.flush()

    # Seed Roles
    r_admin = Role(code="admin", name="Admin", is_system=True)
    r_mgr = Role(code="sales_manager", name="Sales Manager", is_system=True)
    r_rep = Role(code="sales_rep", name="Sales Representative", is_system=True)
    r_fin = Role(code="finance", name="Finance", is_system=True)
    session.add_all([r_admin, r_mgr, r_rep, r_fin])
    session.flush()

    # Seed Role Permissions
    perm_dict = {p.code: p.id for p in perms}
    rp = [
        # Sales rep: own scope
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["customer:read"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["customer:create"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["customer:update"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["lead:read"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["lead:create"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["lead:update"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["quote:read"], scope="own"),
        RolePermission(role_id=r_rep.id, permission_id=perm_dict["quote:create"], scope="own"),
        # Sales manager: department scope
        RolePermission(
            role_id=r_mgr.id, permission_id=perm_dict["customer:read"], scope="department"
        ),
        RolePermission(
            role_id=r_mgr.id, permission_id=perm_dict["customer:create"], scope="department"
        ),
        RolePermission(
            role_id=r_mgr.id, permission_id=perm_dict["customer:update"], scope="department"
        ),
        RolePermission(role_id=r_mgr.id, permission_id=perm_dict["lead:read"], scope="department"),
        RolePermission(role_id=r_mgr.id, permission_id=perm_dict["quote:read"], scope="department"),
        # Finance: all scope
        RolePermission(role_id=r_fin.id, permission_id=perm_dict["invoice:read"], scope="all"),
        RolePermission(role_id=r_fin.id, permission_id=perm_dict["invoice:issue"], scope="all"),
    ]
    session.add_all(rp)
    session.commit()
    return session


# =============================================================================
# 1. Widest Scope Resolution Tests
# =============================================================================
def test_widest_scope_resolution_hierarchy(rbac_db: Session):
    """
    Asserts: When a user has multiple roles granting the same permission,
    the widest scope is resolved: 'all' > 'department' > 'own'.
    """
    user = User(
        email="hybrid_sales@example.com",
        password_hash=hash_password("Password123!"),
        full_name="Hybrid Sales",
        is_active=True,
    )
    rbac_db.add(user)
    rbac_db.flush()

    role_rep = rbac_db.query(Role).filter_by(code="sales_rep").one()
    role_mgr = rbac_db.query(Role).filter_by(code="sales_manager").one()

    rbac_db.add(UserRole(user_id=user.id, role_id=role_rep.id))
    rbac_db.add(UserRole(user_id=user.id, role_id=role_mgr.id))
    rbac_db.commit()

    roles, perm_map, _ = get_user_effective_permissions(rbac_db, user)

    assert "sales_rep" in roles
    assert "sales_manager" in roles
    # For customer:read, sales_manager has 'department', sales_rep has 'own'.
    # Widest must resolve to 'department'.
    assert perm_map["customer:read"] == "department"
    assert perm_map["quote:read"] == "department"


def test_widest_scope_resolution_all_overrides_department(rbac_db: Session):
    """Asserts: 'all' scope overrides 'department' and 'own'."""
    user = User(
        email="director@example.com",
        password_hash=hash_password("Password123!"),
        full_name="Director",
        is_active=True,
    )
    rbac_db.add(user)
    rbac_db.flush()

    role_mgr = rbac_db.query(Role).filter_by(code="sales_manager").one()
    # Create custom executive role granting customer:read with scope 'all'
    role_exec = Role(code="executive", name="Executive", is_system=False)
    rbac_db.add(role_exec)
    rbac_db.flush()

    perm_cust = rbac_db.query(Permission).filter_by(code="customer:read").one()
    rbac_db.add(RolePermission(role_id=role_exec.id, permission_id=perm_cust.id, scope="all"))

    rbac_db.add(UserRole(user_id=user.id, role_id=role_mgr.id))
    rbac_db.add(UserRole(user_id=user.id, role_id=role_exec.id))
    rbac_db.commit()

    _, perm_map, _ = get_user_effective_permissions(rbac_db, user)
    assert perm_map["customer:read"] == "all"


# =============================================================================
# 2. Strict IDOR Defense via 404 (Never 403)
# =============================================================================
def test_idor_defense_returns_404_not_403(rbac_db: Session):
    """
    Asserts: Rep A attempting to access Rep B's customer returns 404 Not Found.
    Never 403 Forbidden to prevent customer existence enumeration.
    """
    rep_a = User(
        email="repa@example.com",
        password_hash=hash_password("Password123!"),
        full_name="Rep Alpha",
        is_active=True,
    )
    rep_b = User(
        email="repb@example.com",
        password_hash=hash_password("Password123!"),
        full_name="Rep Beta",
        is_active=True,
    )
    rbac_db.add_all([rep_a, rep_b])
    rbac_db.commit()

    crm = CRMService(rbac_db)
    # Rep B creates a customer
    cust_b = crm.create_customer(CustomerCreate(name="Beta Industries"), creator_id=rep_b.id)

    # Rep A's context: scope 'own'
    ctx_a = ScopeContext(user=rep_a, scope="own")

    # Rep A attempting to get Rep B's customer MUST raise NotFoundException (HTTP 404)
    with pytest.raises(NotFoundException) as exc_info:
        crm.get_customer(cust_b.id, scope_context=ctx_a)
    assert exc_info.value.status_code == 404

    # Rep A listing customers MUST NOT see Rep B's customer
    items, total = crm.list_customers(scope_context=ctx_a)
    assert total == 0
    assert len(items) == 0

    # Rep B's context: scope 'own' can see their own customer
    ctx_b = ScopeContext(user=rep_b, scope="own")
    found = crm.get_customer(cust_b.id, scope_context=ctx_b)
    assert found.id == cust_b.id


# =============================================================================
# 3. Department Scoping Tests
# =============================================================================
def test_department_scoping_isolation(rbac_db: Session):
    """
    Asserts:
    - Sales Manager in Dept 1 sees records owned by reps in Dept 1.
    - Sales Manager in Dept 1 accessing record belonging to Dept 2 returns 404.
    """
    dept_north = Department(code="D_NORTH", name="North Region")
    dept_south = Department(code="D_SOUTH", name="South Region")
    rbac_db.add_all([dept_north, dept_south])
    rbac_db.flush()

    mgr_north = User(
        email="mgr_north@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Mgr North",
        is_active=True,
    )
    rep_north = User(
        email="rep_north@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Rep North",
        is_active=True,
    )
    rep_south = User(
        email="rep_south@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Rep South",
        is_active=True,
    )
    rbac_db.add_all([mgr_north, rep_north, rep_south])
    rbac_db.flush()

    # Link employees to departments
    rbac_db.add(
        Employee(
            user_id=mgr_north.id,
            department_id=dept_north.id,
            employee_no="E01",
            first_name="M",
            last_name="N",
            hire_date=date.today(),
        )
    )
    rbac_db.add(
        Employee(
            user_id=rep_north.id,
            department_id=dept_north.id,
            employee_no="E02",
            first_name="R",
            last_name="N",
            hire_date=date.today(),
        )
    )
    rbac_db.add(
        Employee(
            user_id=rep_south.id,
            department_id=dept_south.id,
            employee_no="E03",
            first_name="R",
            last_name="S",
            hire_date=date.today(),
        )
    )
    rbac_db.commit()

    crm = CRMService(rbac_db)
    cust_north = crm.create_customer(CustomerCreate(name="Northern Corp"), creator_id=rep_north.id)
    cust_south = crm.create_customer(CustomerCreate(name="Southern Corp"), creator_id=rep_south.id)

    # Manager North context: scope 'department', dept_id = dept_north.id
    ctx_mgr = ScopeContext(user=mgr_north, scope="department", department_id=dept_north.id)

    # Manager North CAN see North Corp
    found_north = crm.get_customer(cust_north.id, scope_context=ctx_mgr)
    assert found_north.id == cust_north.id

    # Manager North accessing South Corp returns 404
    with pytest.raises(NotFoundException) as exc_info:
        crm.get_customer(cust_south.id, scope_context=ctx_mgr)
    assert exc_info.value.status_code == 404

    # Manager North listing customers only sees Northern Corp
    customers, total = crm.list_customers(scope_context=ctx_mgr)
    assert total == 1
    assert customers[0].name == "Northern Corp"


# =============================================================================
# 4. Role Permission Segregation & 403 Forbidden
# =============================================================================
def test_permission_denial_returns_403(rbac_db: Session):
    """
    Asserts: When an authenticated user lacks the required permission,
    FastAPI dependency returns HTTP 403 with PERMISSION_DENIED.
    """
    sales_rep = User(
        email="rep_only@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Sales Only",
        is_active=True,
    )
    rbac_db.add(sales_rep)
    rbac_db.flush()

    role_rep = rbac_db.query(Role).filter_by(code="sales_rep").one()
    rbac_db.add(UserRole(user_id=sales_rep.id, role_id=role_rep.id))
    rbac_db.commit()

    # Authenticate and obtain session token
    identity_svc = IdentityService(rbac_db)
    _, raw_token, _ = identity_svc.authenticate_user(sales_rep.email, "Pass123!")

    # Rep has no 'invoice:issue' permission
    def override_get_db():
        yield rbac_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {raw_token}"}
        # Attempt to issue an invoice (endpoint requires 'invoice:issue')
        res = client.post("/api/v1/invoices/999/issue", headers=headers)
        assert res.status_code == 403
        data = res.json()
        assert data["code"] == "PERMISSION_DENIED"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 5. Immediate Session Revocation on Role Changes
# =============================================================================
def test_session_revocation_on_role_assignment(rbac_db: Session):
    """
    Asserts: When a user's roles are updated or unassigned, all active sessions
    are immediately revoked. Subsequent calls return 401 Unauthorized.
    """
    user = User(
        email="target_user@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Target User",
        is_active=True,
    )
    admin = User(
        email="admin_user@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Admin",
        is_superuser=True,
        is_active=True,
    )
    rbac_db.add_all([user, admin])
    rbac_db.flush()

    # Assign initial role
    role_rep = rbac_db.query(Role).filter_by(code="sales_rep").one()
    rbac_db.add(UserRole(user_id=user.id, role_id=role_rep.id))
    rbac_db.commit()

    # User logs in and obtains session token
    identity_svc = IdentityService(rbac_db)
    _, raw_token, _ = identity_svc.authenticate_user(user.email, "Pass123!")

    user_sess = (
        rbac_db.query(UserSession)
        .filter_by(user_id=user.id)
        .order_by(UserSession.id.desc())
        .first()
    )
    assert user_sess is not None
    assert user_sess.revoked_at is None

    # Admin updates user roles using IdentityService
    identity_svc.assign_user_roles(
        user_id=user.id,
        role_ids=[],  # Strip all roles
        assigner_id=admin.id,
    )

    # Session must now be revoked
    rbac_db.refresh(user_sess)
    assert user_sess.revoked_at is not None

    # Authenticating with old token must now fail with 401
    def override_get_db():
        yield rbac_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw_token}"})
        assert res.status_code == 401
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 6. Superuser Emergency Bypass
# =============================================================================
def test_superuser_emergency_bypass(rbac_db: Session):
    """
    Asserts: A superuser bypasses all role requirements and obtains full 'all' scope.
    """
    superuser = User(
        email="root@company.com",
        password_hash=hash_password("Pass123!"),
        full_name="Super Administrator",
        is_superuser=True,
        is_active=True,
    )
    rbac_db.add(superuser)
    rbac_db.commit()

    roles, perm_map, _ = get_user_effective_permissions(rbac_db, superuser)
    assert "admin" in roles
    # Every seeded permission has 'all' scope
    assert perm_map["customer:read"] == "all"
    assert perm_map["invoice:issue"] == "all"


# =============================================================================
# 7. Route Coverage Test
# =============================================================================
def test_route_coverage_declares_authorization():
    """
    Asserts: Every operational route in CRM and Sales router declares
    authentication or permission requirements.
    """
    unprotected_paths = []
    # Public routes that intentionally do not require token auth
    public_whitelist = {
        "/health",
        "/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
    }

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if not path or path in public_whitelist or "docs" in path or "openapi" in path:
            continue

        endpoint = getattr(route, "endpoint", None)
        dependencies = getattr(route, "dependencies", [])

        # Check if the route or its endpoint dependencies declare auth
        has_auth = False
        if dependencies:
            has_auth = True

        if hasattr(endpoint, "__annotations__"):
            annotations = endpoint.__annotations__
            for _arg_name, arg_type in annotations.items():
                if hasattr(arg_type, "__metadata__"):
                    metadata_str = str(arg_type.__metadata__)
                    if any(
                        keyword in metadata_str
                        for keyword in ["require", "get_current_user", "ScopeContext", "User"]
                    ):
                        has_auth = True
                        break

        if not has_auth and methods.intersection({"GET", "POST", "PUT", "PATCH", "DELETE"}):
            unprotected_paths.append(f"{methods} {path}")

    assert len(unprotected_paths) == 0, f"Unprotected operational routes found: {unprotected_paths}"
