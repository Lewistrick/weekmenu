"""Tests for recipes missing a description."""

import sqlite3
from pathlib import Path

import pytest
from litestar.testing import AsyncTestClient

from scripts.clear_todo_descriptions import clear_todo_descriptions
from src.models import Recipe, User


@pytest.mark.asyncio
async def test_missing_description_page_lists_empty_descriptions(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Owned recipes with an empty description should be listed; others should not."""
    missing = await Recipe.create(
        name="Needs description",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )
    await Recipe.create(
        name="Has description",
        description="Already filled in",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )
    other = await User.create(
        username="other_user",
        email="other@example.com",
        password_hash="x",
    )
    await Recipe.create(
        name="Other owner empty",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=other,
    )

    response = await test_client.get("/recipes/missing-description")

    assert response.status_code == 200
    assert "Find recipes that still need a description" in response.text
    assert missing.name in response.text
    assert f'href="/recipes/view/{missing.id}"' in response.text
    assert 'class="recipe-link"' in response.text
    assert "Has description" not in response.text
    assert "Other owner empty" not in response.text


@pytest.mark.asyncio
async def test_missing_description_page_empty_state(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """When every owned recipe has a description, show the empty message."""
    await Recipe.create(
        name="Complete recipe",
        description="Steps go here",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

    response = await test_client.get("/recipes/missing-description")

    assert response.status_code == 200
    assert "Every recipe has a description." in response.text


def test_clear_todo_descriptions_exact_match(tmp_path: Path) -> None:
    """Only exact ``todo`` descriptions should be cleared to empty strings."""
    db_path = tmp_path / "recipes.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE recipe (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO recipe (id, name, description) VALUES (?, ?, ?)",
            [
                (1, "A", "todo"),
                (2, "B", "Todo"),
                (3, "C", "todo later"),
                (4, "D", "real steps"),
            ],
        )
        conn.commit()

    updated = clear_todo_descriptions(db_path)

    assert updated == 1
    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT id, description FROM recipe").fetchall())
    assert rows[1] == ""
    assert rows[2] == "Todo"
    assert rows[3] == "todo later"
    assert rows[4] == "real steps"
