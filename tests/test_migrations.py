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

WEEKLY_GROCERY_COLUMNS = {
    "id",
    "quantity",
    "ingredient_id",
    "owner_id",
    "unit_id",
}

USER_PREFERENCE_COLUMNS = {
    "id",
    "user_id",
    "language",
    "default_servings",
    "start_day",
    "include_public",
    "grocery_list_initialized",
}

GROCERY_LIST_ITEM_COLUMNS = {
    "id",
    "user_id",
    "ingredient_id",
    "unit_id",
    "quantity",
    "status",
    "shop_id",
}

TAG_CATEGORY_COLUMNS = {
    "id",
    "name",
    "owner_id",
    "foreground_color",
    "background_color",
}


def _table_columns(db_file: Path, table: str) -> set[str]:
    """Return the column names of a table in the given sqlite database."""
    connection = sqlite3.connect(db_file)
    columns = {
        row[1] for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }
    connection.close()
    return columns


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

    assert RECIPE_COLUMNS.issubset(_table_columns(db_file, "recipe"))


@pytest.mark.asyncio
async def test_migrations_create_weekly_grocery_table(tmp_path: Path) -> None:
    """All migrations together should create the weekly grocery table."""
    db_file = tmp_path / "migrated.sqlite3"
    sqlite3.connect(db_file).close()

    for migration_path in MIGRATION_FILES:
        await _apply_migration(db_file, migration_path)

    assert WEEKLY_GROCERY_COLUMNS.issubset(_table_columns(db_file, "weeklygrocery"))


@pytest.mark.asyncio
async def test_migrations_create_user_state_tables(tmp_path: Path) -> None:
    """All migrations together should create persisted user-state tables."""
    db_file = tmp_path / "migrated.sqlite3"
    sqlite3.connect(db_file).close()

    for migration_path in MIGRATION_FILES:
        await _apply_migration(db_file, migration_path)

    assert USER_PREFERENCE_COLUMNS.issubset(_table_columns(db_file, "userpreference"))
    assert GROCERY_LIST_ITEM_COLUMNS.issubset(
        _table_columns(db_file, "grocerylistitem")
    )
    assert "user_id" in _table_columns(db_file, "weekmenuslot")
    assert "user_id" in _table_columns(db_file, "weekmenutagconstraint")


@pytest.mark.asyncio
async def test_migrations_add_tag_category_colors(tmp_path: Path) -> None:
    """All migrations together should add color columns to tag categories."""
    db_file = tmp_path / "migrated.sqlite3"
    sqlite3.connect(db_file).close()

    for migration_path in MIGRATION_FILES:
        await _apply_migration(db_file, migration_path)

    assert TAG_CATEGORY_COLUMNS.issubset(_table_columns(db_file, "tagcategory"))
