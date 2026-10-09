from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, apply_scope, require
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ForbiddenException, UnauthorizedException
from app.core.security import hash_token
from app.modules.identity.models import User, UserSession
from app.modules.identity.service import IdentityService

__all__ = [
    "IdentityService",
    "ScopeContext",
    "apply_scope",
    "get_current_user",
    "get_current_user_and_session",
    "get_identity_service",
    "require",
    "require_superuser",
]


def get_identity_service(db: Annotated[Session, Depends(get_db)]) -> IdentityService:
    return IdentityService(db)


def get_current_user_and_session(
    request: Request,
    service: Annotated[IdentityService, Depends(get_identity_service)],
    erp_session: Annotated[str | None, Cookie(alias=settings.SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> tuple[User, UserSession]:
    """
    Validates session cookie or Bearer token, and CSRF token on mutating requests per Roadmap §4.9.
    """
    token = erp_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token:
        raise UnauthorizedException(detail="Authentication required.")

    user, session = service.validate_session(token)

    # CSRF protection on mutating HTTP methods (enforced for browser cookie sessions)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if erp_session and not request.url.path.endswith("/auth/login"):
            if not x_csrf_token or hash_token(x_csrf_token) != session.csrf_token_hash:
                raise ForbiddenException(
                    detail="Invalid or missing CSRF token.",
                    code="CSRF_VALIDATION_FAILED",
                )

    return user, session


def get_current_user(
    auth: Annotated[tuple[User, UserSession], Depends(get_current_user_and_session)],
) -> User:
    return auth[0]


def require_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Superuser authorization check for emergency bootstrap and root tasks."""
    if not current_user.is_superuser:
        raise ForbiddenException(detail="Superuser access required.")
    return current_user
