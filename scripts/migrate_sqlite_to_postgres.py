"""Copy application data from a SQLite file into PostgreSQL.

Creates the Postgres schema via Tortoise, then copies rows table-by-table while
preserving primary keys and converting SQLite integer booleans.
"""

import argparse
import asyncio
import sqlite3
from pathlib import Path

from tortoise import Tortoise

from src.db_config import TORTOISE_CONFIG, is_postgres_url

# Insert order respects foreign keys. ``recipe`` is loaded in two passes so
# ``imported_from_id`` self-references can be applied after base rows exist.
TABLE_COPY_ORDER = (
    "user",
    "unit",
    "ingredient",
    "tagcategory",
    "tag",
    "shop",
    "recipe",
    "recipeingredient",
    "recipetag",
    "weeklygrocery",
    "userpreference",
    "weekmenuslot",
    "weekmenutagconstraint",
    "grocerylistitem",
    "useringredientshop",
    "uitext",
)

BOOLEAN_COLUMNS: dict[str, frozenset[str]] = {
    "user": frozenset({"is_admin", "must_change_password"}),
    "recipe": frozenset({"private", "enabled"}),
    "userpreference": frozenset({"include_public", "grocery_list_initialized"}),
    "weekmenuslot": frozenset({"pinned"}),
}


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier for PostgreSQL."""
    return '"' + name.replace('"', '""') + '"'


def _convert_row(
    table: str, columns: list[str], row: tuple, *, null_imported_from: bool
) -> tuple:
    """Convert one SQLite row for Postgres insertion."""
    bool_cols = BOOLEAN_COLUMNS.get(table, frozenset())
    values: list[object] = []
    for column, value in zip(columns, row, strict=True):
        if null_imported_from and column == "imported_from_id":
            values.append(None)
        elif column in bool_cols:
            values.append(bool(value) if value is not None else None)
        else:
            values.append(value)
    return tuple(values)


async def _copy_table(
    sqlite_conn: sqlite3.Connection,
    table: str,
    *,
    null_imported_from: bool = False,
) -> int:
    """Copy all rows of one table from SQLite into the open Postgres connection."""
    cursor = sqlite_conn.execute(f"SELECT * FROM [{table}]")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    if not rows:
        return 0

    col_sql = ", ".join(_quote_ident(column) for column in columns)
    placeholders = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    table_sql = _quote_ident(table)
    sql = f"INSERT INTO {table_sql} ({col_sql}) VALUES ({placeholders})"

    connection = Tortoise.get_connection("default")
    for row in rows:
        values = _convert_row(
            table, columns, row, null_imported_from=null_imported_from
        )
        await connection.execute_query(sql, list(values))
    return len(rows)


async def _apply_recipe_imported_from(sqlite_conn: sqlite3.Connection) -> int:
    """Set ``recipe.imported_from_id`` values after base recipe rows exist."""
    rows = sqlite_conn.execute(
        "SELECT id, imported_from_id FROM recipe WHERE imported_from_id IS NOT NULL"
    ).fetchall()
    if not rows:
        return 0

    connection = Tortoise.get_connection("default")
    for recipe_id, imported_from_id in rows:
        await connection.execute_query(
            'UPDATE "recipe" SET "imported_from_id" = $1 WHERE "id" = $2',
            [imported_from_id, recipe_id],
        )
    return len(rows)


async def _reset_sequences() -> None:
    """Align Postgres identity sequences with the maximum inserted id per table."""
    connection = Tortoise.get_connection("default")
    for table in TABLE_COPY_ORDER:
        table_sql = _quote_ident(table)
        await connection.execute_query(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX("id") FROM {table_sql}), 1),
                true
            )
            """
        )


async def migrate(sqlite_path: Path, postgres_url: str) -> dict[str, int]:
    """Create the Postgres schema and copy all application data from SQLite.

    Args:
        sqlite_path: Path to the source SQLite database file.
        postgres_url: Tortoise/asyncpg Postgres connection URL.

    Returns:
        Mapping of table name to number of rows copied (plus imported_from updates).
    """
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    if not is_postgres_url(postgres_url):
        raise ValueError(f"Expected a Postgres DATABASE_URL, got: {postgres_url}")

    config = {
        "connections": {"default": postgres_url},
        "apps": {
            "models": {
                "models": ["src.models", "aerich.models"],
                "default_connection": "default",
            }
        },
    }
    await Tortoise.init(config=config)
    await Tortoise.generate_schemas(safe=False)

    counts: dict[str, int] = {}
    with sqlite3.connect(sqlite_path) as sqlite_conn:
        sqlite_conn.row_factory = None
        for table in TABLE_COPY_ORDER:
            counts[table] = await _copy_table(
                sqlite_conn,
                table,
                null_imported_from=(table == "recipe"),
            )
        counts["recipe.imported_from"] = await _apply_recipe_imported_from(sqlite_conn)

    await _reset_sequences()
    await Tortoise.close_connections()
    return counts


def main() -> None:
    """CLI entry point for SQLite → Postgres data migration."""
    parser = argparse.ArgumentParser(
        description="Copy Weekmenu data from SQLite into PostgreSQL."
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path("data/recipes.sqlite3"),
        help="Source SQLite database path",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres URL (default: DATABASE_URL from the environment / db_config)",
    )
    args = parser.parse_args()
    postgres_url = args.database_url or str(TORTOISE_CONFIG["connections"]["default"])
    counts = asyncio.run(migrate(args.sqlite, postgres_url))
    total = sum(counts.values())
    for table, count in counts.items():
        print(f"{table}: {count}")
    print(f"Copied {total} row operation(s) into Postgres.")


if __name__ == "__main__":
    main()
