"""Tests for recipe view and edit display."""

import re

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, RecipeTag, Tag, TagCategory, User


def _servings_input_value(html: str) -> str | None:
    """Return the value rendered in the recipe-view servings input, if any."""
    match = re.search(r'id="view-recipe-servings"[^>]*\bvalue="([^"]*)"', html)
    return match.group(1) if match else None


@pytest.mark.asyncio
async def test_view_recipe_groups_tags_by_category(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Recipe view should group tags under their tag group label."""
    season = await TagCategory.create(owner=default_user, name="season")
    summer = await Tag.create(owner=default_user, name="summer", category=season)
    winter = await Tag.create(owner=default_user, name="winter", category=season)
    diet = await TagCategory.create(owner=default_user, name="diet")
    vegan = await Tag.create(owner=default_user, name="vegan", category=diet)
    recipe = await Recipe.create(
        name="Grouped tags stew",
        description="A tagged recipe",
        prep_time_minutes=10,
        cook_time_minutes=20,
        servings=2,
        owner=default_user,
    )
    await RecipeTag.create(recipe=recipe, tag=summer)
    await RecipeTag.create(recipe=recipe, tag=winter)
    await RecipeTag.create(recipe=recipe, tag=vegan)

    response = await test_client.get(f"/recipes/view/{recipe.id}")

    assert response.status_code == 200
    assert 'class="recipe-tag-groups"' in response.text
    assert 'class="recipe-tag-group"' in response.text
    assert 'class="tag-group-chip"' in response.text
    assert "season" in response.text
    assert "diet" in response.text
    assert response.text.count("season:") == 0
    assert "summer" in response.text
    assert "winter" in response.text
    assert "vegan" in response.text


@pytest.mark.asyncio
async def test_view_recipe_shows_servings_value(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The recipe view should prefill the servings input with the stored value."""
    recipe = await Recipe.create(
        name="Servings view",
        description="x",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=3,
        owner=default_user,
    )

    response = await test_client.get(f"/recipes/view/{recipe.id}")

    assert response.status_code == 200
    assert _servings_input_value(response.text) == "3"


@pytest.mark.asyncio
async def test_view_recipe_empty_servings_param_still_shows_value(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An empty ``?servings=`` must not 400 and should fall back to the recipe."""
    recipe = await Recipe.create(
        name="Empty servings param",
        description="x",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=4,
        owner=default_user,
    )

    response = await test_client.get(f"/recipes/view/{recipe.id}?servings=")

    assert response.status_code == 200
    assert _servings_input_value(response.text) == "4"


@pytest.mark.asyncio
async def test_random_recipe_shows_servings_value(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The random recipe page must also prefill the servings input.

    Regression: the random render path omitted ``display_servings`` from its
    template context, leaving the field empty.
    """
    recipe = await Recipe.create(
        name="Only random recipe",
        description="x",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=6,
        owner=default_user,
    )

    response = await test_client.get("/recipes/random")

    assert response.status_code == 200
    assert f"#{recipe.id}" in response.text
    assert _servings_input_value(response.text) == "6"


@pytest.mark.asyncio
async def test_add_to_week_menu_render_shows_servings_value(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding to the week menu re-renders the view and must keep servings."""
    recipe = await Recipe.create(
        name="Week menu servings",
        description="x",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=5,
        owner=default_user,
    )

    response = await test_client.post(
        f"/recipes/{recipe.id}/add-to-week-menu", data={"source": "view"}
    )

    assert response.status_code == 200
    assert _servings_input_value(response.text) == "5"


@pytest.mark.asyncio
async def test_edit_recipe_renders_description_markdown(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Edit mode should render description markdown when not editing."""
    recipe = await Recipe.create(
        name="Markdown recipe",
        description="See [the docs](https://example.com/recipe).",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )

    response = await test_client.get(f"/recipes/edit/{recipe.id}")

    assert response.status_code == 200
    assert 'href="https://example.com/recipe"' in response.text
    assert "See" in response.text
    assert "[the docs](https://example.com/recipe)" not in response.text


@pytest.mark.asyncio
async def test_edit_description_save_renders_markdown(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Saving a description should return markdown-rendered display HTML."""
    recipe = await Recipe.create(
        name="Markdown save",
        description="Plain text",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )

    response = await test_client.post(
        f"/recipes/edit-desc/{recipe.id}",
        data={"new_desc": "Read [more](https://example.com/guide)."},
    )

    assert response.status_code == 200
    assert 'href="https://example.com/guide"' in response.text
    assert "[more](https://example.com/guide)" not in response.text
