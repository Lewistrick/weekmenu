"""Shared pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient
from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from pathlib import Path

import src.db_config as db_config_module
from src.app import app
from src.database import close_database, init_database
from src.models import User
import src.user_settings as user_settings_module

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
    """Initialize Tortoise and apply migrations against the in-memory test database."""
    try:
        await Tortoise.close_connections()
    except ConfigurationError:
        pass
    await init_database(TEST_DB_CONFIG)


async def close_test_db() -> None:
    """Close any open Tortoise connections."""
    await close_database()


@pytest.fixture(autouse=True)
def _use_in_memory_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every test to use the isolated in-memory SQLite database."""
    monkeypatch.setattr(db_config_module, "TORTOISE_CONFIG", TEST_DB_CONFIG)
    monkeypatch.setattr(app, "on_startup", [init_test_db])
    monkeypatch.setattr(app, "on_shutdown", [close_test_db])


@pytest.fixture(autouse=True)
def _use_temp_user_settings_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Write per-user settings files to a pytest temp directory."""
    monkeypatch.setattr(
        user_settings_module, "USER_SETTINGS_DIR", tmp_path / "user_settings"
    )


DEFAULT_USERNAME = "testuser"
DEFAULT_PASSWORD = "secret123"
DEFAULT_EMAIL = "test@example.com"


async def register_user(
    client: AsyncTestClient,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
    email: str = DEFAULT_EMAIL,
) -> None:
    """Register (and thereby log in) a user through the client."""
    await client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": password,
            "email": email,
        },
    )


@pytest.fixture
async def anon_client() -> AsyncIterator[AsyncTestClient]:
    """Provide an unauthenticated test client backed by an in-memory database."""
    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.fixture
async def test_client() -> AsyncIterator[AsyncTestClient]:
    """Provide a test client that is already logged in as the default user."""
    async with AsyncTestClient(app=app) as client:
        await register_user(client)
        yield client


@pytest.fixture
async def default_user(test_client: AsyncTestClient) -> User:
    """Return the default user that ``test_client`` is authenticated as."""
    return await User.get(username=DEFAULT_USERNAME)
