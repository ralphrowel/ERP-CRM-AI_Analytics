from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.authorization import ScopeContext, require
from app.core.config import settings
from app.modules.identity.dependencies import (
    get_current_user,
    get_current_user_and_session,
    get_identity_service,
)
from app.modules.identity.models import User, UserSession
from app.modules.identity.schemas import (
    AuthMeResponse,
    LoginRequest,
    LoginResponse,
    PaginatedRolesResponse,
    PaginatedUsersResponse,
    PermissionResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    UserCreate,
    UserResponse,
    UserRoleAssignmentItem,
    UserRolesAssignRequest,
    UserUpdate,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="", tags=["Identity & Auth"])


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> LoginResponse:
    ip = request.client.host if request.client else None
    agent = request.headers.get("User-Agent")

    user, session_token, csrf_token = service.authenticate_user(
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=agent,
    )

    # Set httpOnly, Secure, SameSite=Lax session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_ABSOLUTE_DAYS * 86400,
        path="/",
    )

    # Set readable csrf token cookie for SPA double-submit pattern
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_ABSOLUTE_DAYS * 86400,
        path="/",
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
        message="Login successful.",
    )


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
def logout(
    response: Response,
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> dict[str, str]:
    _, session = auth
    service.logout_session(session)

    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")
    return {"message": "Logged out successfully."}


@router.get("/auth/me", response_model=AuthMeResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> AuthMeResponse:
    return service.get_auth_me(current_user)


# ── Users Management ───────────────────────────────────────────────────
@router.get("/users", response_model=PaginatedUsersResponse)
def list_users(
    _: Annotated[ScopeContext, Depends(require("user:read"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> PaginatedUsersResponse:
    users, total = service.get_users(page=page, page_size=page_size)
    return PaginatedUsersResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    ctx: Annotated[ScopeContext, Depends(require("user:create"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> UserResponse:
    user = service.create_user(payload, creator_id=ctx.user.id)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    ctx: Annotated[ScopeContext, Depends(require("user:update"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> UserResponse:
    user = service.update_user(user_id, payload, updater_id=ctx.user.id)
    return UserResponse.model_validate(user)


# ── Roles & Permissions Management ─────────────────────────────────────
@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(
    _: Annotated[ScopeContext, Depends(require("role:read"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
    module: str | None = Query(None),
) -> list[PermissionResponse]:
    perms = service.list_permissions(module=module)
    return [PermissionResponse.model_validate(p) for p in perms]


@router.get("/roles", response_model=PaginatedRolesResponse)
def list_roles(
    _: Annotated[ScopeContext, Depends(require("role:read"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedRolesResponse:
    roles, total = service.list_roles(page=page, page_size=page_size)
    return PaginatedRolesResponse(
        items=roles,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    ctx: Annotated[ScopeContext, Depends(require("role:create"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> RoleResponse:
    return service.create_role(payload, creator_id=ctx.user.id)


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    _: Annotated[ScopeContext, Depends(require("role:read"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> RoleResponse:
    return service.get_role(role_id)


@router.put("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    ctx: Annotated[ScopeContext, Depends(require("role:update"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> RoleResponse:
    return service.update_role(role_id, payload, updater_id=ctx.user.id)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    _: Annotated[ScopeContext, Depends(require("role:delete"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> None:
    service.delete_role(role_id)


# ── User Roles Assignment ──────────────────────────────────────────────
@router.get("/users/{user_id}/roles", response_model=list[UserRoleAssignmentItem])
def get_user_roles(
    user_id: int,
    _: Annotated[ScopeContext, Depends(require("user:read"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> list[UserRoleAssignmentItem]:
    return service.get_user_roles(user_id)


@router.put("/users/{user_id}/roles", response_model=list[UserRoleAssignmentItem])
def assign_user_roles(
    user_id: int,
    payload: UserRolesAssignRequest,
    ctx: Annotated[ScopeContext, Depends(require("role:assign"))],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> list[UserRoleAssignmentItem]:
    return service.assign_user_roles(user_id, payload.role_ids, assigner_id=ctx.user.id)
