from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models import Role


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    # max_length=72 matches bcrypt's own input limit — bcrypt silently
    # truncates anything longer, so we reject it explicitly instead.
    password: str = Field(min_length=8, max_length=72)
    role: Role


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
