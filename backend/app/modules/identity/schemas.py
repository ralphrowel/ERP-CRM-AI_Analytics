from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth & Users ───────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class LoginResponse(BaseModel):
    user: UserResponse
    csrf_token: str
    message: str = "Login successful"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, description="Password must be at least 12 characters")
    full_name: str = Field(..., min_length=2)
    is_superuser: bool = False
    role_ids: list[int] = Field(default_factory=list, description="Initial roles to assign")


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    role_ids: list[int] | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedUsersResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


# ── RBAC: Permissions & Roles ──────────────────────────────────────────
ScopeType = Literal["own", "department", "all"]


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None = None
    module: str


class RolePermissionResponse(BaseModel):
    permission_id: int
    code: str
    module: str
    description: str | None = None
    scope: ScopeType


class RolePermissionInput(BaseModel):
    permission_id: int
    scope: ScopeType = "all"


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    is_system: bool
    version: int
    created_at: datetime
    updated_at: datetime
    permissions: list[RolePermissionResponse] = Field(default_factory=list)


class RoleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    permissions: list[RolePermissionInput] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    permissions: list[RolePermissionInput] | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedRolesResponse(BaseModel):
    items: list[RoleResponse]
    total: int
    page: int
    page_size: int


class UserRoleAssignmentItem(BaseModel):
    role_id: int
    role_code: str
    role_name: str
    assigned_at: datetime


class UserRolesAssignRequest(BaseModel):
    role_ids: list[int] = Field(..., description="Complete list of role IDs to associate with user")


class AuthMeResponse(BaseModel):
    user: UserResponse
    roles: list[str] = Field(default_factory=list)
    permissions: dict[str, ScopeType] = Field(
        default_factory=dict,
        description="Effective permissions mapped to widest resolved scope (all > department > own)",
    )
    department_id: int | None = None
