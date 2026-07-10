"""Restore recipe data from a legacy SQLite backup into the current schema."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.db_config as db_config  # noqa: E402
from src.database import close_database, init_database  # noqa: E402

DEFAULT_SHOP_FOREGROUND = "#ffffff"
DEFAULT_SHOP_BACKGROUND = "#2563eb"
LEGACY_USERNAME = "_legacy"


def _remove_database_files(target: Path) -> None:
    """Delete the target database and any SQLite sidecar files."""
    for path in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
        if path.exists():
            path.unlink()


def _copy_backup_data(
    backup_path: Path, target_path: Path, owner_id: int
) -> dict[str, int]:
    """Copy legacy rows from the backup into the current database schema."""
    backup = sqlite3.connect(backup_path)
    target = sqlite3.connect(target_path)
    backup.row_factory = sqlite3.Row

    counts: dict[str, int] = {}

    def fetch_backup(query: str) -> list[sqlite3.Row]:
        """Run a read query against the legacy backup database."""
        return list(backup.execute(query))

    try:
        target.execute("BEGIN")

        for row in fetch_backup("SELECT id, name FROM tagcategory ORDER BY id"):
            target.execute(
                "INSERT INTO tagcategory (id, name, owner_id) VALUES (?, ?, ?)",
                (row["id"], row["name"], owner_id),
            )
        counts["tagcategory"] = len(fetch_backup("SELECT id FROM tagcategory"))

        for row in fetch_backup("SELECT id, name, category_id FROM tag ORDER BY id"):
            target.execute(
                "INSERT INTO tag (id, name, category_id, owner_id) VALUES (?, ?, ?, ?)",
                (row["id"], row["name"], row["category_id"], owner_id),
            )
        counts["tag"] = len(fetch_backup("SELECT id FROM tag"))

        for row in fetch_backup("SELECT id, name FROM ingredient ORDER BY id"):
            target.execute(
                "INSERT INTO ingredient (id, name, owner_id) VALUES (?, ?, ?)",
                (row["id"], row["name"], owner_id),
            )
        counts["ingredient"] = len(fetch_backup("SELECT id FROM ingredient"))

        for row in fetch_backup(
            "SELECT id, abbrev, single, plural FROM unit ORDER BY id"
        ):
            target.execute(
                "INSERT INTO unit (id, abbrev, single, plural, owner_id) VALUES (?, ?, ?, ?, ?)",
                (row["id"], row["abbrev"], row["single"], row["plural"], owner_id),
            )
        counts["unit"] = len(fetch_backup("SELECT id FROM unit"))

        for row in fetch_backup(
            """
            SELECT id, name, description, prep_time_minutes, cook_time_minutes,
                   servings, enabled, private
            FROM recipe
            ORDER BY id
            """
        ):
            target.execute(
                """
                INSERT INTO recipe (
                    id, name, description, prep_time_minutes, cook_time_minutes,
                    servings, private, enabled, creator_id, imported_from_id, owner_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    row["id"],
                    row["name"],
                    row["description"],
                    row["prep_time_minutes"],
                    row["cook_time_minutes"],
                    row["servings"],
                    row["private"],
                    row["enabled"],
                    owner_id,
                    owner_id,
                ),
            )
        counts["recipe"] = len(fetch_backup("SELECT id FROM recipe"))

        for row in fetch_backup(
            """
            SELECT id, quantity, ingredient_id, recipe_id, unit_id
            FROM recipeingredient
            ORDER BY id
            """
        ):
            target.execute(
                """
                INSERT INTO recipeingredient (
                    id, quantity, ingredient_id, recipe_id, unit_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["quantity"],
                    row["ingredient_id"],
                    row["recipe_id"],
                    row["unit_id"],
                ),
            )
        counts["recipeingredient"] = len(
            fetch_backup("SELECT id FROM recipeingredient")
        )

        for row in fetch_backup(
            "SELECT id, recipe_id, tag_id FROM recipetag ORDER BY id"
        ):
            target.execute(
                "INSERT INTO recipetag (id, recipe_id, tag_id) VALUES (?, ?, ?)",
                (row["id"], row["recipe_id"], row["tag_id"]),
            )
        counts["recipetag"] = len(fetch_backup("SELECT id FROM recipetag"))

        for row in fetch_backup("SELECT id, name FROM shop ORDER BY id"):
            target.execute(
                """
                INSERT INTO shop (
                    id, name, foreground_color, background_color, owner_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["name"],
                    DEFAULT_SHOP_FOREGROUND,
                    DEFAULT_SHOP_BACKGROUND,
                    owner_id,
                ),
            )
        counts["shop"] = len(fetch_backup("SELECT id FROM shop"))

        for row in fetch_backup(
            """
            SELECT id, ingredient_id, shop_id, user_id
            FROM useringredientshop
            ORDER BY id
            """
        ):
            target.execute(
                """
                INSERT INTO useringredientshop (
                    id, ingredient_id, shop_id, user_id
                ) VALUES (?, ?, ?, ?)
                """,
                (row["id"], row["ingredient_id"], row["shop_id"], owner_id),
            )
        counts["useringredientshop"] = len(
            fetch_backup("SELECT id FROM useringredientshop")
        )

        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        backup.close()
        target.close()

    return counts


async def restore_database(backup_path: Path, target_path: Path) -> dict[str, int]:
    """Rebuild the app database from a legacy backup file."""
    _remove_database_files(target_path)
    await init_database(db_config.TORTOISE_CONFIG)
    await close_database()

    target = sqlite3.connect(target_path)
    try:
        target.execute(
            "INSERT INTO user (username, email, password_hash) VALUES (?, ?, NULL)",
            (LEGACY_USERNAME, ""),
        )
        owner_id = target.execute(
            "SELECT id FROM user WHERE username = ?",
            (LEGACY_USERNAME,),
        ).fetchone()[0]
        target.commit()
    finally:
        target.close()

    counts = _copy_backup_data(backup_path, target_path, owner_id)
    counts["user"] = 1
    return counts


def main() -> None:
    """Restore a legacy SQLite backup into the current application database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "backup",
        type=Path,
        help="Path to the legacy recipes.sqlite3 backup file",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("src/recipes.sqlite3"),
        help="Destination database path (default: src/recipes.sqlite3)",
    )
    args = parser.parse_args()

    if not args.backup.exists():
        msg = f"Backup not found: {args.backup}"
        raise SystemExit(msg)

    counts = asyncio.run(restore_database(args.backup, args.target))
    print(f"Restored database at {args.target}")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    print(
        "Register a new account at /register to claim the restored recipes "
        f"(currently owned by the placeholder user '{LEGACY_USERNAME}')."
    )


if __name__ == "__main__":
    main()
