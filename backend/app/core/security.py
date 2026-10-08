import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Initialize Argon2id password hasher with secure defaults
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, password)
    except VerifyMismatchError:
        return False


def generate_session_token() -> str:
    """Generates a cryptographically strong 32-byte session token."""
    return secrets.token_hex(32)


def generate_csrf_token() -> str:
    """Generates a cryptographically strong CSRF token."""
    return secrets.token_hex(32)


def hash_token(token: str) -> bytes:
    """Computes SHA-256 binary hash of a token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def constant_time_compare(val1: str, val2: str) -> bool:
    """Performs constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))
