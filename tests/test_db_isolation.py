"""Tests that pytest always uses the in-memory database."""

import pytest

import src.db_config as db_config_module
from src.app import app, init_db
from tests.conftest import TEST_DB_CONFIG


def test_autouse_uses_in_memory_database() -> None:
    """Every test should patch Tortoise config to the in-memory database."""
    assert db_config_module.TORTOISE_CONFIG == TEST_DB_CONFIG


def test_app_startup_uses_test_database_hooks() -> None:
    """Litestar startup hooks should point at the test database helpers."""
    assert len(app.on_startup) == 1
    assert app.on_startup[0].__name__ == "init_test_db"
    assert len(app.on_shutdown) == 1
    assert app.on_shutdown[0].__name__ == "close_test_db"


@pytest.mark.asyncio
async def test_init_db_rejects_production_database_during_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production init_db must fail fast if pytest still sees the SQLite file."""
    monkeypatch.setattr(
        "src.db_config.TORTOISE_CONFIG",
        {
            "connections": {"default": "sqlite://src/recipes.sqlite3"},
            "apps": TEST_DB_CONFIG["apps"],
        },
    )

    with pytest.raises(RuntimeError, match="in-memory database"):
        await init_db()


@pytest.mark.asyncio
async def test_module_init_db_patch_does_not_replace_startup_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patching init_db on the module does not update handlers already stored on app."""
    calls: list[str] = []

    async def tracked_init_db() -> None:
        calls.append("patched")

    monkeypatch.setattr("src.app.init_db", tracked_init_db)

    assert len(app.on_startup) == 1
    assert app.on_startup[0].__name__ == "init_test_db"
    assert calls == []
