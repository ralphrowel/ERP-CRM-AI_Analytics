"""
Audit Context Management
Maintains per-request actor ID, request ID, and IP address for audit log capturing.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class AuditContext:
    actor_user_id: int | None = None
    request_id: str | None = None
    ip_address: str | None = None


_audit_context_var: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def get_audit_context() -> AuditContext:
    ctx = _audit_context_var.get()
    if ctx is None:
        ctx = AuditContext()
        _audit_context_var.set(ctx)
    return ctx


def set_audit_context(
    actor_user_id: int | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> AuditContext:
    ctx = AuditContext(
        actor_user_id=actor_user_id,
        request_id=request_id,
        ip_address=ip_address,
    )
    _audit_context_var.set(ctx)
    return ctx


def clear_audit_context() -> None:
    _audit_context_var.set(AuditContext())
