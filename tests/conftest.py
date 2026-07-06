"""Shared pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient
from tortoise import Tortoise

import src.app as app_module
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


@pytest.fixture
async def test_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncTestClient]:
    """Provide a test client backed by an in-memory database."""

    async def init_test_db() -> None:
        await Tortoise.init(config=TEST_DB_CONFIG)
        await Tortoise.generate_schemas(safe=True)

    monkeypatch.setattr(app_module, "TORTOISE_CONFIG", TEST_DB_CONFIG)
    monkeypatch.setattr(app_module, "init_db", init_test_db)

    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.fixture
async def default_user(test_client: AsyncTestClient) -> User:
    """Create the sole user used as the default recipe owner in tests."""
    return await User.create(username="testuser", email="test@example.com")
