from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from ..config import Settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, user_id: int, role: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (or a subclass, e.g. ExpiredSignatureError)
    on any invalid, tampered, or expired token — callers should catch that
    base class rather than individual subclasses."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
