"""Database initialization and migration helpers."""

import os

from aerich import Command
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient

from src.category_icons import icon_backfill_sql
from src.db_config import is_postgres_url

# ``generate_schemas`` only creates missing tables, so columns added to existing
# tables after the Postgres database was first created are added here. Each
# statement must be idempotent.
POSTGRES_COLUMN_PATCHES = (
    'ALTER TABLE "grocerylistitem" ADD COLUMN IF NOT EXISTS '
    '"inventory_quantity" DOUBLE PRECISION NOT NULL DEFAULT 0',
    'ALTER TABLE "ingredient" ADD COLUMN IF NOT EXISTS "category_id" INT '
    'REFERENCES "ingredientcategory" ("id") ON DELETE SET NULL',
    'ALTER TABLE "userpreference" ADD COLUMN IF NOT EXISTS '
    '"categories_seeded" BOOLEAN NOT NULL DEFAULT FALSE',
    'ALTER TABLE "ingredientcategory" ADD COLUMN IF NOT EXISTS '
    "\"icon\" TEXT NOT NULL DEFAULT ''",
)

# One-time data fills, run only on the boot that adds their (table, column), so
# later user edits (e.g. clearing an icon) are never overwritten.
POSTGRES_COLUMN_BACKFILLS = {
    ("ingredientcategory", "icon"): icon_backfill_sql,
}


async def _postgres_column_exists(
    connection: BaseDBAsyncClient, table: str, column: str
) -> bool:
    """Return whether a column exists in the connected Postgres database."""
    rows = await connection.execute_query_dict(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = $1 AND column_name = $2",
        [table, column],
    )
    return bool(rows)


def ensure_not_using_production_db_in_tests() -> None:
    """Block accidental production database use while pytest is running."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return

    from src import db_config

    db_url = str(db_config.TORTOISE_CONFIG["connections"]["default"])
    if "recipes.sqlite3" in db_url or is_postgres_url(db_url):
        msg = "Tests must use the in-memory database, not the production database."
        raise RuntimeError(msg)


async def init_database(config: dict) -> None:
    """Initialize Tortoise and bring the schema up to date.

    SQLite (including the in-memory test database) applies aerich migrations.
    PostgreSQL uses ``generate_schemas`` because the checked-in aerich history
    was generated for SQLite dialects.
    """
    await Tortoise.init(config=config)
    db_url = str(config["connections"]["default"])
    if is_postgres_url(db_url):
        await Tortoise.generate_schemas(safe=True)
        connection = Tortoise.get_connection("default")
        pending_backfills = [
            backfill
            for (table, column), backfill in POSTGRES_COLUMN_BACKFILLS.items()
            if not await _postgres_column_exists(connection, table, column)
        ]
        for statement in POSTGRES_COLUMN_PATCHES:
            await connection.execute_script(statement)
        for backfill in pending_backfills:
            await connection.execute_script(backfill())
        return

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
