import time

import pytest
from cryptography.fernet import Fernet

from app.auth.security import InvalidSessionToken, SessionTokenService, hash_password, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False
    assert "correct horse battery staple" not in encoded


def test_password_hash_uses_unique_salt():
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_session_token_round_trip():
    service = SessionTokenService(Fernet.generate_key().decode(), ttl_seconds=60)

    token = service.issue(42)

    assert service.decode_user_id(token) == 42


def test_session_token_rejects_tampering():
    service = SessionTokenService(Fernet.generate_key().decode(), ttl_seconds=60)
    token = service.issue(42)
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")

    with pytest.raises(InvalidSessionToken):
        service.decode_user_id(tampered)


def test_session_token_rejects_expired_token():
    service = SessionTokenService(Fernet.generate_key().decode(), ttl_seconds=1)
    token = service.issue(7)
    time.sleep(2)

    with pytest.raises(InvalidSessionToken):
        service.decode_user_id(token)
