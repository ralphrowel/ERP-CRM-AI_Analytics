from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.authorization import get_user_effective_permissions
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
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
)
from app.modules.identity.schemas import (
    AuthMeResponse,
    RoleCreate,
    RolePermissionResponse,
    RoleResponse,
    RoleUpdate,
    UserCreate,
    UserResponse,
    UserRoleAssignmentItem,
    UserUpdate,
)


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

            # Assign admin role if exists
            admin_role = self.db.execute(select(Role).where(Role.code == "admin")).scalar_one_or_none()
            if admin_role:
                user_role = UserRole(user_id=user.id, role_id=admin_role.id)
                self.db.add(user_role)
                self.db.commit()

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
        last_seen = session.last_seen_at
        if last_seen.tzinfo is None and now.tzinfo is not None:
            last_seen = last_seen.replace(tzinfo=now.tzinfo)
        elif last_seen.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=last_seen.tzinfo)

        if (now - last_seen) > idle_limit:
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
        """Revokes all active sessions for a user (called upon role change or deactivation per Roadmap §1388)."""
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

    def get_auth_me(self, user: User) -> AuthMeResponse:
        """Returns caller profile with effective roles, permissions mapped to widest scope, and department ID."""
        roles, perms, dept_id = get_user_effective_permissions(self.db, user)
        return AuthMeResponse(
            user=UserResponse.model_validate(user),
            roles=roles,
            permissions=perms,
            department_id=dept_id,
        )

    # ── User CRUD ──────────────────────────────────────────────────────────
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

        # Assign initial roles if specified
        if data.role_ids:
            for r_id in data.role_ids:
                ur = UserRole(user_id=user.id, role_id=r_id, assigned_by=creator_id)
                self.db.add(ur)
            self.db.commit()

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

        if data.role_ids is not None:
            # Replace user roles
            self.db.execute(delete(UserRole).where(UserRole.user_id == user_id))
            for r_id in data.role_ids:
                self.db.add(UserRole(user_id=user_id, role_id=r_id, assigned_by=updater_id))
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

    # ── RBAC Roles & Permissions Management ────────────────────────────────
    def list_permissions(self, module: str | None = None) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.module.asc(), Permission.code.asc())
        if module:
            stmt = stmt.where(Permission.module == module)
        return list(self.db.execute(stmt).scalars().all())

    def list_roles(self, page: int = 1, page_size: int = 50) -> tuple[list[RoleResponse], int]:
        offset = (page - 1) * page_size
        total = self.db.execute(select(func.count(Role.id))).scalar_one()
        roles = (
            self.db.execute(
                select(Role)
                .options(
                    joinedload(Role.role_permissions).joinedload(RolePermission.permission)
                )
                .order_by(Role.id.asc())
                .offset(offset)
                .limit(page_size)
            )
            .unique()
            .scalars()
            .all()
        )

        items: list[RoleResponse] = []
        for r in roles:
            perm_responses = [
                RolePermissionResponse(
                    permission_id=rp.permission_id,
                    code=rp.permission.code,
                    module=rp.permission.module,
                    description=rp.permission.description,
                    scope=rp.scope,  # type: ignore[arg-type]
                )
                for rp in r.role_permissions
            ]
            items.append(
                RoleResponse(
                    id=r.id,
                    code=r.code,
                    name=r.name,
                    description=r.description,
                    is_system=r.is_system,
                    version=r.version,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    permissions=perm_responses,
                )
            )

        return items, total

    def get_role(self, role_id: int) -> RoleResponse:
        role = (
            self.db.execute(
                select(Role)
                .options(
                    joinedload(Role.role_permissions).joinedload(RolePermission.permission)
                )
                .where(Role.id == role_id)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not role:
            raise NotFoundException(detail="Role not found.")

        perm_responses = [
            RolePermissionResponse(
                permission_id=rp.permission_id,
                code=rp.permission.code,
                module=rp.permission.module,
                description=rp.permission.description,
                scope=rp.scope,  # type: ignore[arg-type]
            )
            for rp in role.role_permissions
        ]

        return RoleResponse(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            version=role.version,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=perm_responses,
        )

    def create_role(self, data: RoleCreate, creator_id: int | None = None) -> RoleResponse:
        normalized_code = data.code.strip().lower()
        existing = self.db.execute(select(Role).where(Role.code == normalized_code)).scalar_one_or_none()
        if existing:
            raise AppException(
                status_code=400,
                code="ROLE_ALREADY_EXISTS",
                title="Bad Request",
                detail=f"A role with code '{normalized_code}' already exists.",
            )

        role = Role(
            code=normalized_code,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            is_system=False,
            created_by=creator_id,
            updated_by=creator_id,
        )
        self.db.add(role)
        self.db.flush()

        for p_input in data.permissions:
            rp = RolePermission(
                role_id=role.id,
                permission_id=p_input.permission_id,
                scope=p_input.scope,
            )
            self.db.add(rp)

        self.db.commit()
        return self.get_role(role.id)

    def update_role(self, role_id: int, data: RoleUpdate, updater_id: int | None = None) -> RoleResponse:
        role = self.db.get(Role, role_id)
        if not role:
            raise NotFoundException(detail="Role not found.")

        if role.version != data.version:
            raise ConflictException(
                detail="Role was modified by another session. Please reload and try again."
            )

        if data.name is not None:
            role.name = data.name.strip()
        if data.description is not None:
            role.description = data.description.strip() if data.description else None

        permissions_changed = False
        if data.permissions is not None:
            # Replace role permissions
            self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            for p_input in data.permissions:
                rp = RolePermission(
                    role_id=role_id,
                    permission_id=p_input.permission_id,
                    scope=p_input.scope,
                )
                self.db.add(rp)
            permissions_changed = True

        role.version += 1
        role.updated_by = updater_id
        self.db.commit()

        # If role permissions were updated, revoke sessions of all users assigned to this role
        if permissions_changed:
            affected_user_ids = (
                self.db.execute(select(UserRole.user_id).where(UserRole.role_id == role_id))
                .scalars()
                .all()
            )
            for uid in affected_user_ids:
                self.revoke_all_user_sessions(uid)

        return self.get_role(role_id)

    def delete_role(self, role_id: int) -> None:
        role = self.db.get(Role, role_id)
        if not role:
            raise NotFoundException(detail="Role not found.")

        if role.is_system:
            raise AppException(
                status_code=400,
                code="CANNOT_DELETE_SYSTEM_ROLE",
                title="Bad Request",
                detail=f"System role '{role.code}' cannot be deleted.",
            )

        # Revoke sessions of users holding this role
        affected_user_ids = (
            self.db.execute(select(UserRole.user_id).where(UserRole.role_id == role_id))
            .scalars()
            .all()
        )
        for uid in affected_user_ids:
            self.revoke_all_user_sessions(uid)

        self.db.delete(role)
        self.db.commit()

    def get_user_roles(self, user_id: int) -> list[UserRoleAssignmentItem]:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found.")

        stmt = (
            select(UserRole)
            .options(joinedload(UserRole.role))
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.assigned_at.asc())
        )
        user_roles = self.db.execute(stmt).scalars().all()

        return [
            UserRoleAssignmentItem(
                role_id=ur.role_id,
                role_code=ur.role.code,
                role_name=ur.role.name,
                assigned_at=ur.assigned_at,
            )
            for ur in user_roles
        ]

    def assign_user_roles(
        self, user_id: int, role_ids: list[int], assigner_id: int | None = None
    ) -> list[UserRoleAssignmentItem]:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found.")

        # Validate that all role_ids exist
        valid_roles = self.db.execute(select(Role.id).where(Role.id.in_(role_ids))).scalars().all()
        if len(valid_roles) != len(set(role_ids)):
            raise AppException(
                status_code=400,
                code="INVALID_ROLE_ID",
                title="Bad Request",
                detail="One or more specified role IDs do not exist.",
            )

        # Clear existing and add new
        self.db.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for r_id in set(role_ids):
            ur = UserRole(user_id=user_id, role_id=r_id, assigned_by=assigner_id)
            self.db.add(ur)

        self.db.commit()

        # Changing a user's roles revokes their sessions immediately (Roadmap §1388)
        self.revoke_all_user_sessions(user_id)

        return self.get_user_roles(user_id)
