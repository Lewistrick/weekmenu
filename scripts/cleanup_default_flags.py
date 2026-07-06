"""Remove test recipes accidentally written to the production SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "src" / "recipes.sqlite3"
TEST_RECIPE_NAME = "Default Flags"


def main() -> None:
    """Delete recipes created by integration tests from the app database."""
    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH}")
        return

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name FROM recipe WHERE name = ?",
            (TEST_RECIPE_NAME,),
        ).fetchall()
        if not rows:
            print(f"No recipes named '{TEST_RECIPE_NAME}' found.")
            return

        conn.execute("DELETE FROM recipe WHERE name = ?", (TEST_RECIPE_NAME,))
        conn.commit()
        print(f"Deleted {len(rows)} recipe(s) named '{TEST_RECIPE_NAME}': {rows}")


if __name__ == "__main__":
    main()
