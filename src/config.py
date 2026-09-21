from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env.

    Never hardcode secrets here — every field is expected to come from
    the environment (see .env.example for the shape).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    test_database_url: str
    jwt_secret: str
    jwt_ttl_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
