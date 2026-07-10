"""Tests for database migrations."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from tortoise.backends.sqlite.client import SqliteClient

MIGRATIONS_DIR = Path("migrations/models")
MIGRATION_FILES = sorted(MIGRATIONS_DIR.glob("*.py"))

RECIPE_COLUMNS = {
    "id",
    "name",
    "description",
    "prep_time_minutes",
    "cook_time_minutes",
    "servings",
    "private",
    "enabled",
    "creator_id",
    "imported_from_id",
    "owner_id",
}


def _load_migration(path: Path):
    """Load a migration module from disk."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async def _apply_migration(db_file: Path, migration_path: Path) -> None:
    """Apply a single migration file to the given sqlite database."""
    migration = _load_migration(migration_path)
    client = SqliteClient(connection_name="default", file_path=str(db_file))
    sql = await migration.upgrade(client)
    if sql.strip():
        await client.execute_script(sql)
    await client.close()


@pytest.mark.asyncio
async def test_migrations_create_expected_recipe_columns(tmp_path: Path) -> None:
    """All migrations together should produce the recipe columns defined in models."""
    db_file = tmp_path / "migrated.sqlite3"
    sqlite3.connect(db_file).close()

    for migration_path in MIGRATION_FILES:
        await _apply_migration(db_file, migration_path)

    connection = sqlite3.connect(db_file)
    columns = {
        row[1] for row in connection.execute('PRAGMA table_info("recipe")').fetchall()
    }
    connection.close()

    assert RECIPE_COLUMNS.issubset(columns)
