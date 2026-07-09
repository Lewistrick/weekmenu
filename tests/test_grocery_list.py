"""Tests for the week menu grocery list generator."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Recipe, RecipeIngredient, Unit, User
from src.week_menu import (
    DEFAULT_SERVINGS,
    GroceryItem,
    build_grocery_list,
    empty_week_menu,
    normalize_servings,
    scale_ingredient_quantity,
    set_day_servings,
)


def test_scale_ingredient_quantity_scales_by_serving_ratio() -> None:
    """Quantities should scale by the ratio of planned to recipe servings."""
    assert scale_ingredient_quantity(200, day_servings=4, recipe_servings=2) == 400
    assert scale_ingredient_quantity(200, day_servings=1, recipe_servings=2) == 100


def test_scale_ingredient_quantity_returns_original_when_recipe_servings_invalid() -> (
    None
):
    """A non-positive recipe serving count should leave the quantity unscaled."""
    assert scale_ingredient_quantity(150, day_servings=4, recipe_servings=0) == 150


def test_build_grocery_list_sums_matching_name_and_unit() -> None:
    """Entries with the same name and unit should be added together."""
    entries = [
        GroceryItem(name="potatoes", unit="g", quantity=200.0),
        GroceryItem(name="potatoes", unit="g", quantity=300.0),
        GroceryItem(name="onion", unit="pcs", quantity=1.0),
    ]

    result = build_grocery_list(entries)

    assert result == [
        GroceryItem(name="onion", unit="pcs", quantity=1.0),
        GroceryItem(name="potatoes", unit="g", quantity=500.0),
    ]


def test_build_grocery_list_keeps_different_units_separate() -> None:
    """The same ingredient in different units should not be merged."""
    entries = [
        GroceryItem(name="milk", unit="l", quantity=1.0),
        GroceryItem(name="milk", unit="ml", quantity=200.0),
    ]

    result = build_grocery_list(entries)

    assert {(item["name"], item["unit"]): item["quantity"] for item in result} == {
        ("milk", "l"): 1.0,
        ("milk", "ml"): 200.0,
    }


def test_normalize_servings_falls_back_to_default() -> None:
    """Invalid or non-positive servings should fall back to the default."""
    assert normalize_servings("3") == 3
    assert normalize_servings(None) == DEFAULT_SERVINGS
    assert normalize_servings(0) == DEFAULT_SERVINGS
    assert normalize_servings("not-a-number") == DEFAULT_SERVINGS


def test_set_day_servings_updates_slot() -> None:
    """Setting servings for a day should persist on that day's slot."""
    menu = empty_week_menu()
    menu = set_day_servings(menu, "monday", 5)
    assert menu["monday"]["servings"] == 5


@pytest.fixture
async def scaled_recipe(test_client: AsyncTestClient, default_user: User) -> Recipe:
    """Create a two-serving recipe with two ingredients."""
    recipe = await Recipe.create(
        name="Potato mash",
        description="Comforting mash",
        prep_time_minutes=10,
        cook_time_minutes=20,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    pieces = await Unit.filter(owner_id=default_user.id, abbrev="pcs").first()
    assert grams is not None and pieces is not None
    potatoes = await Ingredient.create(owner=default_user, name="potatoes")
    onion = await Ingredient.create(owner=default_user, name="onion")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=potatoes, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=onion, quantity=1, unit=pieces
    )
    return recipe


@pytest.mark.asyncio
async def test_set_servings_endpoint_persists(
    test_client: AsyncTestClient,
    scaled_recipe: Recipe,
) -> None:
    """Posting servings for a day should be reflected in the day panel."""
    await test_client.post(f"/week-menu/monday/recipe/{scaled_recipe.id}")

    response = await test_client.post(
        "/week-menu/monday/servings", data={"servings": "6"}
    )

    assert response.status_code == 200
    assert 'value="6"' in response.text


@pytest.mark.asyncio
async def test_grocery_list_scales_and_aggregates(
    test_client: AsyncTestClient,
    scaled_recipe: Recipe,
) -> None:
    """The grocery list should scale by servings and sum repeated ingredients."""
    await test_client.post(f"/week-menu/monday/recipe/{scaled_recipe.id}")
    await test_client.post("/week-menu/monday/servings", data={"servings": "4"})
    await test_client.post(f"/week-menu/tuesday/recipe/{scaled_recipe.id}")
    await test_client.post("/week-menu/tuesday/servings", data={"servings": "2"})

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    # potatoes: 200 * 4/2 + 200 * 2/2 = 400 + 200 = 600 g
    assert ">600 g</span>" in response.text
    assert ">potatoes</span>" in response.text
    # onion: 1 * 4/2 + 1 * 2/2 = 2 + 1 = 3 pcs
    assert ">3 pcs</span>" in response.text
    assert ">onion</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_empty_when_no_recipes(test_client: AsyncTestClient) -> None:
    """An empty week menu should render a helpful empty state."""
    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert "No ingredients yet" in response.text
