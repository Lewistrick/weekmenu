"""Shared pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient
from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError

import src.db_config as db_config_module
from src.app import app
from src.models import User

TEST_DB_CONFIG = {
    "connections": {"default": "sqlite://:memory:"},
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}


async def init_test_db() -> None:
    """Initialize Tortoise against the in-memory test database."""
    try:
        await Tortoise.close_connections()
    except ConfigurationError:
        pass
    await Tortoise.init(config=TEST_DB_CONFIG)
    await Tortoise.generate_schemas(safe=True)


async def close_test_db() -> None:
    """Close any open Tortoise connections."""
    try:
        await Tortoise.close_connections()
    except ConfigurationError:
        pass


@pytest.fixture(autouse=True)
def _use_in_memory_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every test to use the isolated in-memory SQLite database."""
    monkeypatch.setattr(db_config_module, "TORTOISE_CONFIG", TEST_DB_CONFIG)
    monkeypatch.setattr(app, "on_startup", [init_test_db])
    monkeypatch.setattr(app, "on_shutdown", [close_test_db])


@pytest.fixture
async def test_client() -> AsyncIterator[AsyncTestClient]:
    """Provide a test client backed by an in-memory database."""
    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.fixture
async def default_user(test_client: AsyncTestClient) -> User:
    """Create the sole user used as the default recipe owner in tests."""
    return await User.create(username="testuser", email="test@example.com")
