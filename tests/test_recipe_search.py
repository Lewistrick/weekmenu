"""Tests for recipe search by name, description, and ingredients."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Recipe, RecipeIngredient, Unit, User


@pytest.fixture
async def searchable_recipes(
    test_client: AsyncTestClient,
    default_user: User,
) -> dict[str, Recipe]:
    """Create recipes that differ by searchable fields."""
    by_name = await Recipe.create(
        name="Tomato Basil Pasta",
        description="A simple weeknight dinner.",
        prep_time_minutes=10,
        cook_time_minutes=20,
        servings=4,
        owner=default_user,
    )
    by_description = await Recipe.create(
        name="Quick Supper",
        description="Uses smoked paprika for warmth.",
        prep_time_minutes=5,
        cook_time_minutes=15,
        servings=2,
        owner=default_user,
    )
    by_ingredient = await Recipe.create(
        name="House Salad",
        description="Fresh greens.",
        prep_time_minutes=5,
        cook_time_minutes=0,
        servings=2,
        owner=default_user,
    )
    unit = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert unit is not None
    mozzarella = await Ingredient.create(owner=default_user, name="mozzarella")
    await RecipeIngredient.create(
        recipe=by_ingredient,
        ingredient=mozzarella,
        quantity=100.0,
        unit=unit,
    )
    return {
        "by_name": by_name,
        "by_description": by_description,
        "by_ingredient": by_ingredient,
    }


@pytest.mark.asyncio
async def test_recipe_search_matches_name(
    searchable_recipes: dict[str, Recipe],
) -> None:
    """Search should match recipe titles."""
    results = await Recipe.search("Tomato Basil")
    assert [recipe.id for recipe in results] == [searchable_recipes["by_name"].id]


@pytest.mark.asyncio
async def test_recipe_search_matches_description(
    searchable_recipes: dict[str, Recipe],
) -> None:
    """Search should match recipe descriptions."""
    results = await Recipe.search("smoked paprika")
    assert [recipe.id for recipe in results] == [
        searchable_recipes["by_description"].id
    ]


@pytest.mark.asyncio
async def test_recipe_search_matches_ingredient_name(
    searchable_recipes: dict[str, Recipe],
) -> None:
    """Search should match linked ingredient names."""
    results = await Recipe.search("mozzarella")
    assert [recipe.id for recipe in results] == [searchable_recipes["by_ingredient"].id]


@pytest.mark.asyncio
async def test_search_recipe_endpoint_returns_matches(
    test_client: AsyncTestClient,
    searchable_recipes: dict[str, Recipe],
) -> None:
    """The search endpoint should return recipes found via description."""
    response = await test_client.get(
        "/recipes/search-recipe",
        params={"search": "smoked paprika"},
    )

    assert response.status_code == 200
    assert searchable_recipes["by_description"].name in response.text
    assert searchable_recipes["by_name"].name not in response.text
    assert (
        f'href="/recipes/view/{searchable_recipes["by_description"].id}"'
        in response.text
    )
    assert "hx-get" not in response.text
