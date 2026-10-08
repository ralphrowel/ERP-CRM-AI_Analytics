from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.config import settings
from app.modules.identity.dependencies import (
    get_current_user,
    get_current_user_and_session,
    get_identity_service,
    require_superuser,
)
from app.modules.identity.models import User, UserSession
from app.modules.identity.schemas import (
    LoginRequest,
    LoginResponse,
    PaginatedUsersResponse,
    UserCreate,
    UserResponse,
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


@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.get("/users", response_model=PaginatedUsersResponse)
def list_users(
    _: Annotated[User, Depends(require_superuser)],
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
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> UserResponse:
    user = service.create_user(payload, creator_id=current_user.id)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> UserResponse:
    user = service.update_user(user_id, payload, updater_id=current_user.id)
    return UserResponse.model_validate(user)
