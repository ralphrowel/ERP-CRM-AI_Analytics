from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.config import settings
from app.core.errors import (
    AppException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.identity.models import User, UserSession
from app.modules.identity.schemas import UserCreate, UserUpdate


class IdentityService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

    def bootstrap_superuser(self) -> User | None:
        """Creates the initial superuser if no users exist in the system."""
        user_count = self.db.execute(select(func.count(User.id))).scalar_one()
        if user_count == 0:
            user = User(
                email=settings.FIRST_SUPERUSER_EMAIL.lower(),
                password_hash=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
                full_name=settings.FIRST_SUPERUSER_NAME,
                is_active=True,
                is_superuser=True,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return user
        return None

    def authenticate_user(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str]:
        """Authenticates user and returns (user, raw_session_token, raw_csrf_token)."""
        now = self.clock.now()
        normalized_email = email.strip().lower()

        user = self.db.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        ).scalar_one_or_none()

        if user is None:
            raise UnauthorizedException(detail="Invalid email or password.")

        if not user.is_active:
            raise UnauthorizedException(detail="User account is deactivated.")

        # Check account lockout
        if user.locked_until and user.locked_until > now:
            minutes_left = max(1, int((user.locked_until - now).total_seconds() / 60))
            raise UnauthorizedException(
                detail=f"Account is temporarily locked. Try again in {minutes_left} minutes.",
                code="ACCOUNT_LOCKED",
            )

        # Verify password
        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
            self.db.commit()
            raise UnauthorizedException(detail="Invalid email or password.")

        # Reset failed login count and record login time
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now

        # Create session
        raw_session_token = generate_session_token()
        raw_csrf_token = generate_csrf_token()

        session = UserSession(
            user_id=user.id,
            token_hash=hash_token(raw_session_token),
            csrf_token_hash=hash_token(raw_csrf_token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.SESSION_ABSOLUTE_DAYS),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(user)

        return user, raw_session_token, raw_csrf_token

    def validate_session(self, raw_session_token: str) -> tuple[User, UserSession]:
        """Validates session token with sliding idle and absolute expiration."""
        now = self.clock.now()
        token_hash = hash_token(raw_session_token)

        session = self.db.execute(
            select(UserSession).where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        ).scalar_one_or_none()

        if session is None:
            raise UnauthorizedException(detail="Session invalid or expired.")

        # Check sliding idle timeout (e.g. 8 hours)
        idle_limit = timedelta(hours=settings.SESSION_IDLE_HOURS)
        if (now - session.last_seen_at) > idle_limit:
            session.revoked_at = now
            self.db.commit()
            raise UnauthorizedException(detail="Session expired due to inactivity.")

        # Check user status
        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            session.revoked_at = now
            self.db.commit()
            raise UnauthorizedException(detail="User account is deactivated.")

        # Slide idle window
        session.last_seen_at = now
        self.db.commit()

        return user, session

    def logout_session(self, session: UserSession) -> None:
        """Revokes a single user session."""
        session.revoked_at = self.clock.now()
        self.db.commit()

    def revoke_all_user_sessions(self, user_id: int) -> None:
        """Revokes all active sessions for a user (called upon role change or deactivation)."""
        now = self.clock.now()
        sessions = (
            self.db.execute(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        for s in sessions:
            s.revoked_at = now
        self.db.commit()

    def create_user(self, data: UserCreate, creator_id: int | None = None) -> User:
        normalized_email = data.email.strip().lower()
        existing = self.db.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        ).scalar_one_or_none()

        if existing:
            raise AppException(
                status_code=400,
                code="EMAIL_ALREADY_EXISTS",
                title="Bad Request",
                detail="A user with this email address already exists.",
            )

        user = User(
            email=normalized_email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            is_superuser=data.is_superuser,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: int, data: UserUpdate, updater_id: int | None = None) -> User:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found.")

        # Optimistic locking check (Roadmap §4.1)
        if user.version != data.version:
            raise ConflictException(
                detail="User was modified by another session. Please reload and try again."
            )

        if data.email is not None:
            normalized_email = data.email.strip().lower()
            if normalized_email != user.email:
                existing = self.db.execute(
                    select(User).where(
                        func.lower(User.email) == normalized_email,
                        User.id != user_id,
                    )
                ).scalar_one_or_none()
                if existing:
                    raise AppException(
                        status_code=400,
                        code="EMAIL_ALREADY_EXISTS",
                        title="Bad Request",
                        detail="Another user already has this email address.",
                    )
                user.email = normalized_email

        if data.full_name is not None:
            user.full_name = data.full_name

        deactivating = False
        if data.is_active is not None and data.is_active != user.is_active:
            user.is_active = data.is_active
            if not user.is_active:
                deactivating = True

        role_changed = False
        if data.is_superuser is not None and data.is_superuser != user.is_superuser:
            user.is_superuser = data.is_superuser
            role_changed = True

        user.version += 1
        user.updated_by = updater_id
        self.db.commit()
        self.db.refresh(user)

        # Deactivation or role change revokes user sessions immediately
        if deactivating or role_changed:
            self.revoke_all_user_sessions(user_id)

        return user

    def get_users(self, page: int = 1, page_size: int = 25) -> tuple[list[User], int]:
        offset = (page - 1) * page_size
        total = self.db.execute(select(func.count(User.id))).scalar_one()
        users = (
            self.db.execute(select(User).order_by(User.id.asc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return list(users), total
