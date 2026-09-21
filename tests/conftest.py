from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.config import get_settings


def _alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Run real Alembic migrations against the test DB once per test session.

    This proves the migration files themselves are correct (not just the
    current model definitions), matching FR/Phase 1's "migration applies
    cleanly" requirement.
    """
    settings = get_settings()
    config = _alembic_config(settings.test_database_url)
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """One test = one transaction, rolled back afterward.

    Every test sees a clean, migrated schema without re-running migrations
    or truncating tables between tests.
    """
    settings = get_settings()
    engine = create_async_engine(settings.test_database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
