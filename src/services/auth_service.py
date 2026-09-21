import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..core.security import create_access_token, verify_password
from ..models import User
from ..repositories import user_repository

# bcrypt is deliberately slow (~100ms). If we only ran it when a matching
# user existed, "unknown username" requests would return noticeably faster
# than "wrong password" requests, letting an attacker enumerate valid
# usernames purely by timing. Checking the submitted password against this
# fixed dummy hash when no user is found keeps the response time roughly
# constant either way.
_DUMMY_HASH = bcrypt.hashpw(b"no-such-user", bcrypt.gensalt()).decode("utf-8")


class AuthenticationError(Exception):
    """Raised for any login failure. Deliberately generic: callers must not
    distinguish 'unknown user' from 'wrong password' from 'deactivated'
    (FR1, FR20) — that distinction is exactly what a generic 401 hides."""


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    user = await user_repository.get_by_username(session, username)
    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(password, password_hash)

    if user is None or not user.is_active or not password_ok:
        raise AuthenticationError()
    return user


def issue_token(user: User, settings: Settings) -> str:
    return create_access_token(user_id=user.id, role=user.role.value, settings=settings)
