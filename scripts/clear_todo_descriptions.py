"""Clear recipe descriptions that are exactly the placeholder ``todo``."""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB_PATHS = (
    Path("data/recipes.sqlite3"),
    Path("src/recipes.sqlite3"),
)


def clear_todo_descriptions(db_path: Path) -> int:
    """Set ``description`` to empty string where it is exactly ``todo``.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of recipe rows updated.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE recipe SET description = '' WHERE description = ?",
            ("todo",),
        )
        conn.commit()
        return cursor.rowcount


def _resolve_db_path(explicit: Path | None) -> Path:
    """Pick the database path from an explicit argument or known defaults."""
    if explicit is not None:
        return explicit
    for candidate in DEFAULT_DB_PATHS:
        if candidate.exists():
            return candidate
    return DEFAULT_DB_PATHS[0]


def main() -> None:
    """Run the one-time ``todo`` description cleanup against the app database."""
    parser = argparse.ArgumentParser(
        description='Set recipe descriptions that are exactly "todo" to empty.'
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path (default: data/recipes.sqlite3 or src/recipes.sqlite3)",
    )
    args = parser.parse_args()
    db_path = _resolve_db_path(args.db)
    if not db_path.exists():
        print(f"No database found at {db_path}")
        return

    updated = clear_todo_descriptions(db_path)
    print(f"Cleared {updated} recipe description(s) from {db_path}")


if __name__ == "__main__":
    main()
