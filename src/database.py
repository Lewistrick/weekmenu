"""Database initialization and migration helpers."""

import os

from aerich import Command
from tortoise import Tortoise


def ensure_not_using_production_db_in_tests() -> None:
    """Block accidental production database use while pytest is running."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return

    from src import db_config

    db_url = str(db_config.TORTOISE_CONFIG["connections"]["default"])
    if "recipes.sqlite3" in db_url:
        msg = "Tests must use the in-memory database, not src/recipes.sqlite3."
        raise RuntimeError(msg)


async def init_database(config: dict) -> None:
    """Initialize Tortoise and apply pending aerich migrations."""
    await Tortoise.init(config=config)
    command = Command(
        tortoise_config=config,
        app="models",
        location="./migrations",
    )
    await command.init()
    await command.upgrade()


async def close_database() -> None:
    """Close all open Tortoise database connections."""
    await Tortoise.close_connections()
