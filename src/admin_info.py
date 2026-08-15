"""Collect technical runtime details for the admin info page."""

import os
import platform
import sys
from typing import Any

from tortoise import Tortoise

from src import db_config
from src.db_config import is_postgres_url
from src.models import Recipe, User


def _redact_database_url(db_url: str) -> str:
    """Return a database URL with the password removed."""
    if "://" not in db_url:
        return db_url
    scheme, rest = db_url.split("://", 1)
    if "@" not in rest:
        return db_url
    userinfo, hostinfo = rest.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    return f"{scheme}://{username}:***@{hostinfo}"


def _row_value(row: Any, key: str = "version") -> str:
    """Extract a scalar from a Tortoise query row (dict or sequence)."""
    if isinstance(row, dict):
        return str(row.get(key) or next(iter(row.values())))
    if isinstance(row, (list, tuple)):
        return str(row[0])
    return str(row)


async def collect_admin_info() -> dict[str, Any]:
    """Gather technical details for the admin info page.

    Returns:
        Mapping of display fields for the admin info template.
    """
    db_url = str(db_config.TORTOISE_CONFIG["connections"]["default"])
    connection = Tortoise.get_connection("default")
    postgres_version = None
    if is_postgres_url(db_url):
        _, rows = await connection.execute_query("SELECT version()")
        if rows:
            postgres_version = _row_value(rows[0])

    return {
        "database_backend": "PostgreSQL" if is_postgres_url(db_url) else "SQLite",
        "database_url": _redact_database_url(db_url),
        "postgres_version": postgres_version,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "debug": os.environ.get("DEBUG", "true").lower() in ("1", "true", "yes"),
        "user_count": await User.all().count(),
        "recipe_count": await Recipe.all().count(),
    }
