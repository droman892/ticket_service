from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.config import Settings
from src.core.security import create_access_token, decode_access_token, hash_password, verify_password

_SETTINGS = Settings(
    database_url="postgresql+asyncpg://unused/unused",
    test_database_url="postgresql+asyncpg://unused/unused",
    jwt_secret="test-secret-at-least-32-bytes-long",
)


def test_hash_password_does_not_store_plaintext_and_verifies_correctly() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_round_trips_its_claims() -> None:
    token = create_access_token(user_id=42, role="agent", settings=_SETTINGS)

    payload = decode_access_token(token, _SETTINGS)

    assert payload["sub"] == "42"
    assert payload["role"] == "agent"


def test_expired_token_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": "1", "role": "agent", "iat": now - timedelta(minutes=120), "exp": now - timedelta(minutes=60)},
        _SETTINGS.jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired, _SETTINGS)


def test_token_signed_with_a_different_secret_is_rejected() -> None:
    forged = jwt.encode({"sub": "1", "role": "admin"}, "a-completely-different-32-byte-secret", algorithm="HS256")

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged, _SETTINGS)
