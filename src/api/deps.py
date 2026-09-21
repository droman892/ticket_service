from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..core.security import decode_access_token
from ..db import get_session
from ..models import Role, User
from ..repositories import user_repository

# auto_error=False is required here: FastAPI's HTTPBearer, with its default
# auto_error=True, raises 403 (not 401) when the Authorization header is
# missing entirely. FR2 requires 401 for a missing/invalid/expired token,
# so we take control of that response ourselves instead.
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError:
        raise _UNAUTHORIZED

    user = await user_repository.get_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def require_role(*roles: Role) -> Callable[[User], Awaitable[User]]:
    async def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
        return user

    return check_role
