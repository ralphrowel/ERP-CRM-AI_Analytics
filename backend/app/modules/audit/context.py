"""
Audit Context Management
Maintains per-request actor ID, request ID, and IP address for audit log capturing.
"""

import ipaddress
from contextvars import ContextVar
from dataclasses import dataclass


def sanitize_ip_address(ip: str | None) -> str | None:
    """
    Sanitize an IP address string to ensure compatibility with PostgreSQL INET type.
    - Strips whitespace.
    - If the input is 'testclient' or 'localhost', maps to '127.0.0.1'.
    - If input contains a port (e.g., '127.0.0.1:8000' or '[::1]:8000'), strips the port.
    - Validates via ipaddress.ip_address. If valid IPv4 or IPv6, returns the IP string.
    - If invalid or unparseable, returns None.
    """
    if not ip:
        return None
    ip_str = ip.strip()
    if not ip_str:
        return None
    if ip_str in ("testclient", "localhost"):
        return "127.0.0.1"
    if ip_str.startswith("[") and "]" in ip_str:
        ip_str = ip_str.split("]")[0].lstrip("[")
    elif ":" in ip_str and ip_str.count(":") == 1:
        ip_str = ip_str.split(":")[0]

    try:
        ipaddress.ip_address(ip_str)
        return ip_str
    except ValueError:
        return None


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
        ip_address=sanitize_ip_address(ip_address),
    )
    _audit_context_var.set(ctx)
    return ctx


def clear_audit_context() -> None:
    _audit_context_var.set(AuditContext())
