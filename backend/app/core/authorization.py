from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.database import get_db
from app.core.errors import ForbiddenException, UnauthorizedException
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
)
from app.modules.organization.models import Employee

ScopeType = Literal["own", "department", "all"]

SCOPE_HIERARCHY: dict[str, int] = {
    "all": 3,
    "department": 2,
    "own": 1,
}


@dataclass
class ScopeContext:
    user: User
    scope: ScopeType
    department_id: int | None = None


def get_user_department_id(db: Session, user_id: int) -> int | None:
    """Retrieves the active employee department ID associated with this user."""
    stmt = select(Employee.department_id).where(
        Employee.user_id == user_id,
        Employee.is_active == True,  # noqa: E712
    )
    return db.execute(stmt).scalar_one_or_none()


def get_user_effective_permissions(db: Session, user: User) -> tuple[list[str], dict[str, ScopeType], int | None]:
    """
    Computes effective roles, permission-to-widest-scope map, and department ID for a user.
    Widest scope resolution rule: 'all' > 'department' > 'own'.
    """
    dept_id = get_user_department_id(db, user.id)

    if user.is_superuser:
        all_perms = db.execute(select(Permission.code)).scalars().all()
        perm_map: dict[str, ScopeType] = dict.fromkeys(all_perms, "all")
        return ["admin"], perm_map, dept_id

    # Query roles assigned to user
    roles_stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    role_codes = list(db.execute(roles_stmt).scalars().all())

    # Query permissions with scopes granted across all user roles
    perm_stmt = (
        select(Permission.code, RolePermission.scope)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
    )
    rows = db.execute(perm_stmt).fetchall()

    perm_map: dict[str, ScopeType] = {}
    for code, scope in rows:
        existing_scope = perm_map.get(code)
        if not existing_scope:
            perm_map[code] = scope
        else:
            if SCOPE_HIERARCHY.get(scope, 0) > SCOPE_HIERARCHY.get(existing_scope, 0):
                perm_map[code] = scope

    return role_codes, perm_map, dept_id


def require(permission_code: str):
    """
    FastAPI dependency declaring that an endpoint requires a specific permission.
    Returns ScopeContext with the caller's widest resolved scope ('all' > 'department' > 'own').
    """
    from app.modules.identity.dependencies import get_current_user_and_session

    def dependency(
        auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
        db: Annotated[Session, Depends(get_db)],
    ) -> ScopeContext:
        user, _ = auth

        if not user.is_active:
            raise UnauthorizedException(detail="User account is deactivated.")

        # Superusers bypass checks with full 'all' scope
        if user.is_superuser:
            dept_id = get_user_department_id(db, user.id)
            return ScopeContext(user=user, scope="all", department_id=dept_id)

        stmt = (
            select(RolePermission.scope)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                UserRole.user_id == user.id,
                Permission.code == permission_code,
            )
        )
        scopes = db.execute(stmt).scalars().all()

        if not scopes:
            raise ForbiddenException(
                detail=f"Permission '{permission_code}' required.",
                code="PERMISSION_DENIED",
            )

        widest_scope: ScopeType = max(scopes, key=lambda s: SCOPE_HIERARCHY.get(s, 0))  # type: ignore[assignment]
        dept_id = get_user_department_id(db, user.id)
        return ScopeContext(user=user, scope=widest_scope, department_id=dept_id)

    return dependency


def apply_scope(query: Select, model: Any, context: ScopeContext, db: Session) -> Select:
    """
    Applies object-level scoping filter on a SQLAlchemy Select query.
    Enforces 'own' vs 'department' vs 'all' constraints across models.
    """
    if context.user.is_superuser or context.scope == "all":
        return query

    if context.scope == "own":
        if hasattr(model, "owner_user_id"):
            return query.where(
                or_(model.owner_user_id == context.user.id, model.created_by == context.user.id)
            )
        elif hasattr(model, "customer_id"):
            from app.modules.crm.models import Customer

            cust_subq = select(Customer.id).where(
                or_(Customer.owner_user_id == context.user.id, Customer.created_by == context.user.id)
            )
            return query.where(
                or_(model.customer_id.in_(cust_subq), model.created_by == context.user.id)
            )
        elif hasattr(model, "created_by"):
            return query.where(model.created_by == context.user.id)
        return query

    if context.scope == "department":
        dept_id = context.department_id or get_user_department_id(db, context.user.id)
        if not dept_id:
            # If user has no department assigned, fallback to own records
            return apply_scope(query, model, ScopeContext(user=context.user, scope="own"), db)

        dept_user_ids = select(Employee.user_id).where(
            Employee.department_id == dept_id,
            Employee.is_active == True,  # noqa: E712
            Employee.user_id.is_not(None),
        )

        if hasattr(model, "owner_user_id"):
            return query.where(
                or_(model.owner_user_id.in_(dept_user_ids), model.created_by.in_(dept_user_ids))
            )
        elif hasattr(model, "customer_id"):
            from app.modules.crm.models import Customer

            cust_subq = select(Customer.id).where(
                or_(Customer.owner_user_id.in_(dept_user_ids), Customer.created_by.in_(dept_user_ids))
            )
            return query.where(
                or_(model.customer_id.in_(cust_subq), model.created_by.in_(dept_user_ids))
            )
        elif hasattr(model, "created_by"):
            return query.where(model.created_by.in_(dept_user_ids))
        return query

    return query
