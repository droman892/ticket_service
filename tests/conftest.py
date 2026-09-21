from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.config import get_settings
from src.db import get_session
from src.main import app


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


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client for the app, sharing db_session's transaction — so a
    row a test creates directly via the ORM is visible to the request, and
    a row a request creates is visible back in the test, all rolled back
    together.

    Uses httpx.AsyncClient over Starlette's TestClient deliberately:
    TestClient can run the ASGI app in a different event loop than the
    test itself, which breaks an asyncpg connection (bound to the loop
    that created it). AsyncClient with ASGITransport runs everything in
    this test's own event loop.
    """

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)
