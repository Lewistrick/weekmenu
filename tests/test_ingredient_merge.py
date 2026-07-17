"""Tests for ingredient merge management."""

from unittest.mock import patch

import pytest
from litestar.testing import AsyncTestClient

from src.ingredient_merge import log_ingredient_usages, merge_ingredients
from src.models import (
    GroceryListItem,
    Ingredient,
    Recipe,
    RecipeIngredient,
    Shop,
    Unit,
    User,
    UserIngredientShop,
    WeeklyGrocery,
)


async def _gram_unit(user: User) -> Unit:
    """Return the gram unit for a user."""
    unit = await Unit.filter(owner_id=user.id, abbrev="g").first()
    assert unit is not None
    return unit


async def _ml_unit(user: User) -> Unit:
    """Return the millilitre unit for a user."""
    unit = await Unit.filter(owner_id=user.id, abbrev="ml").first()
    assert unit is not None
    return unit


@pytest.mark.asyncio
async def test_merge_ingredients_page_loads_empty(
    test_client: AsyncTestClient,
) -> None:
    """The merge page should render when no ingredients exist."""
    response = await test_client.get("/ingredients/merge/manage")

    assert response.status_code == 200
    assert "Merge ingredients" in response.text
    assert "No ingredients yet." in response.text


@pytest.mark.asyncio
async def test_navigation_links_to_merge_ingredients(
    test_client: AsyncTestClient,
) -> None:
    """The home page and navbar should link to ingredient merging."""
    home = await test_client.get("/")

    assert "/ingredients/merge/manage" in home.text
    assert "🔗 Merge ingredients" in home.text


@pytest.mark.asyncio
async def test_merge_ingredients_reassigns_recipes(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merging should move source recipe lines to the target ingredient."""
    grams = await _gram_unit(default_user)
    oil = await Ingredient.create(owner=default_user, name="oil")
    olive_oil = await Ingredient.create(owner=default_user, name="olive oil")
    recipe = await Recipe.create(
        name="Salad",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=0,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(recipe=recipe, ingredient=oil, quantity=2, unit=grams)

    response = await test_client.post(
        "/ingredients/merge",
        data={
            "source_ingredient_id": str(oil.id),
            "target_ingredient_id": str(olive_oil.id),
        },
    )

    assert response.status_code == 200
    assert "Merged oil into olive oil in 1 recipe(s):" in response.text
    assert f"/recipes/view/{recipe.id}" in response.text
    assert await Ingredient.filter(id=oil.id).exists() is False
    row = await RecipeIngredient.get(recipe_id=recipe.id)
    assert row.ingredient_id == olive_oil.id
    assert row.quantity == 2


@pytest.mark.asyncio
async def test_merge_ingredients_sums_same_unit_on_recipe(
    default_user: User,
) -> None:
    """Recipe lines with the same unit should be combined by summing quantities."""
    grams = await _gram_unit(default_user)
    oil = await Ingredient.create(owner=default_user, name="oil")
    olive_oil = await Ingredient.create(owner=default_user, name="olive oil")
    recipe = await Recipe.create(
        name="Dressing",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=0,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(recipe=recipe, ingredient=oil, quantity=1, unit=grams)
    await RecipeIngredient.create(
        recipe=recipe, ingredient=olive_oil, quantity=3, unit=grams
    )

    result = await merge_ingredients(default_user.id, oil.id, olive_oil.id)

    assert result.ok is True
    rows = await RecipeIngredient.filter(recipe_id=recipe.id)
    assert len(rows) == 1
    assert rows[0].ingredient_id == olive_oil.id
    assert rows[0].quantity == 4


@pytest.mark.asyncio
async def test_merge_ingredients_keeps_different_units_separate(
    default_user: User,
) -> None:
    """Recipe lines with different units should remain separate lines."""
    grams = await _gram_unit(default_user)
    ml = await _ml_unit(default_user)
    oil = await Ingredient.create(owner=default_user, name="oil")
    olive_oil = await Ingredient.create(owner=default_user, name="olive oil")
    recipe = await Recipe.create(
        name="Mixed",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=0,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=oil, quantity=10, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=olive_oil, quantity=5, unit=ml
    )

    result = await merge_ingredients(default_user.id, oil.id, olive_oil.id)

    assert result.ok is True
    rows = await RecipeIngredient.filter(recipe_id=recipe.id).order_by("unit_id")
    assert len(rows) == 2
    assert {row.ingredient_id for row in rows} == {olive_oil.id}
    quantities = sorted(row.quantity for row in rows)
    assert quantities == [5, 10]


@pytest.mark.asyncio
async def test_merge_ingredients_updates_weekly_and_grocery_lists(
    default_user: User,
) -> None:
    """Weekly groceries and grocery list lines should follow the target ingredient."""
    grams = await _gram_unit(default_user)
    oil = await Ingredient.create(owner=default_user, name="oil")
    olive_oil = await Ingredient.create(owner=default_user, name="olive oil")
    await WeeklyGrocery.create(
        owner=default_user, ingredient=oil, quantity=1, unit=grams
    )
    await GroceryListItem.create(
        user=default_user, ingredient=oil, quantity=2, unit=grams
    )

    result = await merge_ingredients(default_user.id, oil.id, olive_oil.id)

    assert result.ok is True
    weekly = await WeeklyGrocery.get(owner_id=default_user.id)
    assert weekly.ingredient_id == olive_oil.id
    grocery = await GroceryListItem.get(user_id=default_user.id)
    assert grocery.ingredient_id == olive_oil.id


@pytest.mark.asyncio
async def test_merge_ingredients_keeps_target_shop_assignment(
    default_user: User,
) -> None:
    """When both ingredients have shop mappings, the target mapping should win."""
    oil = await Ingredient.create(owner=default_user, name="oil")
    olive_oil = await Ingredient.create(owner=default_user, name="olive oil")
    source_shop = await Shop.create(owner=default_user, name="Source shop")
    target_shop = await Shop.create(owner=default_user, name="Target shop")
    await UserIngredientShop.create(user=default_user, ingredient=oil, shop=source_shop)
    await UserIngredientShop.create(
        user=default_user, ingredient=olive_oil, shop=target_shop
    )

    result = await merge_ingredients(default_user.id, oil.id, olive_oil.id)

    assert result.ok is True
    assert await UserIngredientShop.filter(ingredient_id=oil.id).exists() is False
    mapping = await UserIngredientShop.get(ingredient_id=olive_oil.id)
    assert mapping.shop_id == target_shop.id


@pytest.mark.asyncio
async def test_merge_ingredients_rejects_same_ingredient(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merging an ingredient into itself should show a validation warning."""
    oil = await Ingredient.create(owner=default_user, name="oil")

    response = await test_client.post(
        "/ingredients/merge",
        data={
            "source_ingredient_id": str(oil.id),
            "target_ingredient_id": str(oil.id),
        },
    )

    assert response.status_code == 200
    assert "Choose two different ingredients." in response.text
    assert await Ingredient.filter(id=oil.id).exists() is True


@pytest.mark.asyncio
async def test_merge_ingredients_search_returns_matches(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ingredient search should return name matches for autocomplete."""
    await Ingredient.create(owner=default_user, name="oil")
    await Ingredient.create(owner=default_user, name="olive oil")

    response = await test_client.get(
        "/ingredients/merge/search",
        params={"field": "source", "search": "oil"},
    )

    assert response.status_code == 200
    assert "oil" in response.text
    assert "olive oil" in response.text
    assert 'hx-post="/ingredients/merge/select"' in response.text


@pytest.mark.asyncio
async def test_merge_ingredients_select_updates_field(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Selecting an autocomplete option should update the matching field."""
    oil = await Ingredient.create(owner=default_user, name="oil")

    response = await test_client.post(
        "/ingredients/merge/select",
        data={"field": "source", "ingredient_id": str(oil.id)},
    )

    assert response.status_code == 200
    assert 'id="source-ingredient-id"' in response.text
    assert f'value="{oil.id}"' in response.text
    assert 'value="oil"' in response.text


@pytest.mark.asyncio
async def test_log_ingredient_usages_writes_recipe_lines(
    default_user: User,
) -> None:
    """Selecting an ingredient should log recipe usage lines for debugging."""
    grams = await _gram_unit(default_user)
    oil = await Ingredient.create(owner=default_user, name="oil")
    recipe = await Recipe.create(
        name="Salad",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=0,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(recipe=recipe, ingredient=oil, quantity=2, unit=grams)

    with patch("ingredient_merge.logger") as mock_logger:
        await log_ingredient_usages(default_user.id, oil.id, "source")

    logged_messages = " ".join(str(call) for call in mock_logger.debug.call_args_list)
    assert "Salad" in logged_messages
    assert str(recipe.id) in logged_messages


@pytest.mark.asyncio
async def test_merge_ingredients_page_shows_search_fields(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The merge page should use searchable fields instead of dropdowns."""
    await Ingredient.create(owner=default_user, name="oil")

    response = await test_client.get("/ingredients/merge/manage")

    assert response.status_code == 200
    assert 'name="search"' in response.text
    assert 'id="source-ingredient-search"' in response.text
    assert 'id="target-ingredient-search"' in response.text
    assert "<select" not in response.text
    assert "Log usages" not in response.text
