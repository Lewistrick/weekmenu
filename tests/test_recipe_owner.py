"""Tests for recipe owner backfill and defaults."""

import pytest
from litestar.testing import AsyncTestClient
from tortoise import Tortoise

from src.app import _ensure_recipe_owners
from src.models import Recipe, User


@pytest.mark.asyncio
async def test_get_by_username_returns_matching_user(
    test_client: AsyncTestClient,
) -> None:
    """Looking up a username should return the matching user or None."""
    assert await User.get_by_username("does-not-exist") is None

    created = await User.create(username="solo", email="solo@example.com")
    found = await User.get_by_username("solo")
    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_ensure_recipe_owners_backfills_null_owner(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Recipes without an owner should be assigned to the first user."""
    conn = Tortoise.get_connection("default")
    await conn.execute_query("DROP TABLE recipe")
    await conn.execute_query(
        """
        CREATE TABLE recipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            prep_time_minutes INT NOT NULL,
            cook_time_minutes INT NOT NULL,
            servings INT NOT NULL,
            owner_id INT,
            private BOOLEAN NOT NULL DEFAULT 1,
            enabled BOOLEAN NOT NULL DEFAULT 1
        )
        """
    )
    await conn.execute_query(
        "INSERT INTO recipe (name, description, prep_time_minutes, cook_time_minutes, servings, owner_id) "
        "VALUES ('Legacy', 'Old recipe', 5, 10, 2, NULL)"
    )

    await _ensure_recipe_owners(conn)

    recipe = await Recipe.get(name="Legacy")
    owner = await recipe.owner
    assert owner.id == default_user.id
