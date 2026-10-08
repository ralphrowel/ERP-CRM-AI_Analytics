from app.core.security import (
    constant_time_compare,
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hashing():
    pw = "SuperSecurePassword123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_token_generation_and_hashing():
    token = generate_session_token()
    assert len(token) == 64  # 32 bytes hex encoded = 64 characters

    token_hash = hash_token(token)
    assert len(token_hash) == 32  # SHA-256 binary digest = 32 bytes
    assert hash_token(token) == token_hash

    csrf = generate_csrf_token()
    assert len(csrf) == 64


def test_constant_time_compare():
    assert constant_time_compare("abc", "abc") is True
    assert constant_time_compare("abc", "abd") is False
