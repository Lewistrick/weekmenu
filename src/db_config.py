"""Tortoise ORM configuration for the application database."""

import os

# Prefer DATABASE_URL (Postgres in Docker). Fall back to local SQLite for
# `uv run` without Docker. Tests monkeypatch TORTOISE_CONFIG to in-memory SQLite.
_DEFAULT_SQLITE = "sqlite://src/recipes.sqlite3"
_database_url = (
    os.environ.get("DATABASE_URL", _DEFAULT_SQLITE).strip() or _DEFAULT_SQLITE
)

TORTOISE_CONFIG = {
    "connections": {"default": _database_url},
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}


def is_postgres_url(db_url: str | None = None) -> bool:
    """Return whether a Tortoise connection URL targets PostgreSQL.

    Args:
        db_url: Connection URL to inspect. Defaults to the configured default.

    Returns:
        ``True`` when the URL uses a Postgres/asyncpg scheme.
    """
    url = (db_url or _database_url).lower()
    return url.startswith(("postgres://", "postgresql://", "asyncpg://"))
