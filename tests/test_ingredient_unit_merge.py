"""Tests for ingredient unit merge management."""

import pytest
from litestar.testing import AsyncTestClient

from src.ingredient_units import load_multi_unit_pairs
from src.models import (
    GroceryListItem,
    Ingredient,
    Recipe,
    RecipeIngredient,
    Unit,
    User,
    WeeklyGrocery,
)


async def _units_for_user(user: User) -> tuple[Unit, Unit]:
    """Return gram and piece units for a user."""
    grams = await Unit.filter(owner_id=user.id, abbrev="g").first()
    pieces = await Unit.filter(owner_id=user.id, abbrev="st").first()
    assert grams is not None
    assert pieces is not None
    return grams, pieces


@pytest.mark.asyncio
async def test_merge_units_page_loads_empty(
    test_client: AsyncTestClient,
) -> None:
    """The merge page should render when no multi-unit ingredients exist."""
    response = await test_client.get("/ingredients/merge-units/manage")

    assert response.status_code == 200
    assert "Merge ingredient units" in response.text
    assert "No ingredients use more than one unit." in response.text


@pytest.mark.asyncio
async def test_navigation_links_to_merge_units(test_client: AsyncTestClient) -> None:
    """The home page and navbar should link to ingredient unit merging."""
    home = await test_client.get("/")

    assert "/ingredients/merge-units/manage" in home.text
    assert "🔀 Merge ingredient units" in home.text


@pytest.mark.asyncio
async def test_lists_ingredient_with_multiple_units(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ingredients that use multiple units should appear as pair rows."""
    grams, pieces = await _units_for_user(default_user)
    apple = await Ingredient.create(owner=default_user, name="apple")
    recipe_a = await Recipe.create(
        name="Apple grams",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Apple pieces",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=apple, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=apple, quantity=1, unit=pieces
    )

    pairs = await load_multi_unit_pairs(default_user.id)
    assert len(pairs) == 1
    assert pairs[0].ingredient_name == "apple"

    response = await test_client.get("/ingredients/merge-units/manage")
    assert response.status_code == 200
    assert "apple" in response.text
    assert "g" in response.text
    assert "st" in response.text


@pytest.mark.asyncio
async def test_convert_units_updates_recipes(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Converting grams to pieces should update all recipe ingredient lines."""
    grams, pieces = await _units_for_user(default_user)
    apple = await Ingredient.create(owner=default_user, name="apple")
    recipe_a = await Recipe.create(
        name="Apple grams",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Apple pieces",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=apple, quantity=400, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=apple, quantity=1, unit=pieces
    )

    ordered_a, ordered_b = (grams, pieces) if grams.id < pieces.id else (pieces, grams)

    response = await test_client.post(
        f"/ingredients/merge-units/{apple.id}/{ordered_a.id}/{ordered_b.id}",
        data={
            "target_unit_id": str(pieces.id),
            "amount_a": "200" if ordered_a.id == grams.id else "1",
            "amount_b": "1" if ordered_b.id == pieces.id else "200",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Edited" in response.text
    assert f'href="/recipes/view/{recipe_a.id}"' in response.text

    gram_line = await RecipeIngredient.get_or_none(
        recipe_id=recipe_a.id, ingredient_id=apple.id, unit_id=grams.id
    )
    piece_line = await RecipeIngredient.get_or_none(
        recipe_id=recipe_a.id, ingredient_id=apple.id, unit_id=pieces.id
    )
    assert gram_line is None
    assert piece_line is not None
    assert piece_line.quantity == pytest.approx(2.0)

    merged_recipe_b = await RecipeIngredient.get(
        recipe_id=recipe_b.id, ingredient_id=apple.id, unit_id=pieces.id
    )
    assert merged_recipe_b.quantity == pytest.approx(1.0)

    pairs = await load_multi_unit_pairs(default_user.id)
    assert pairs == []


@pytest.mark.asyncio
async def test_convert_units_updates_weekly_grocery_and_grocery_list(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Conversion should also update weekly groceries and grocery list items."""
    grams, pieces = await _units_for_user(default_user)
    apple = await Ingredient.create(owner=default_user, name="apple")
    recipe = await Recipe.create(
        name="Apple pieces",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=apple, quantity=1, unit=pieces
    )
    await WeeklyGrocery.create(
        owner=default_user, ingredient=apple, quantity=200, unit=grams
    )
    await GroceryListItem.create(
        user_id=default_user.id,
        ingredient_id=apple.id,
        unit_id=grams.id,
        quantity=400,
    )

    ordered_a, ordered_b = (grams, pieces) if grams.id < pieces.id else (pieces, grams)

    response = await test_client.post(
        f"/ingredients/merge-units/{apple.id}/{ordered_a.id}/{ordered_b.id}",
        data={
            "target_unit_id": str(pieces.id),
            "amount_a": "200" if ordered_a.id == grams.id else "1",
            "amount_b": "1" if ordered_b.id == pieces.id else "200",
        },
    )

    assert response.status_code == 200
    assert "Updated" in response.text
    assert (
        await WeeklyGrocery.filter(ingredient_id=apple.id, unit_id=grams.id).exists()
        is False
    )
    weekly = await WeeklyGrocery.get(ingredient_id=apple.id, unit_id=pieces.id)
    assert weekly.quantity == pytest.approx(1.0)

    assert (
        await GroceryListItem.filter(
            user_id=default_user.id, ingredient_id=apple.id, unit_id=grams.id
        ).exists()
        is False
    )
    grocery = await GroceryListItem.get(
        user_id=default_user.id, ingredient_id=apple.id, unit_id=pieces.id
    )
    assert grocery.quantity == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_edit_form_works_when_abbrev_order_differs_from_id_order(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Edit links should work when abbrev sort order differs from unit id order."""
    grams, pieces = await _units_for_user(default_user)
    # "el" sorts before "g" by abbrev, but g typically has a lower unit id.
    assert grams.id < pieces.id or grams.abbrev < pieces.abbrev

    vinegar = await Ingredient.create(owner=default_user, name="azijn")
    recipe_a = await Recipe.create(
        name="Vinegar ml",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Vinegar el",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=vinegar, quantity=15, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=vinegar, quantity=1, unit=pieces
    )

    pairs = await load_multi_unit_pairs(default_user.id)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.unit_a.id < pair.unit_b.id

    response = await test_client.get(
        f"/ingredients/merge-units/{vinegar.id}/{pair.unit_a.id}/{pair.unit_b.id}/edit",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'name="amount_a"' in response.text
    assert 'name="amount_b"' in response.text


@pytest.mark.asyncio
async def test_edit_form_shows_inline_conversion_fields(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The edit endpoint should return the inline conversion form."""
    grams, pieces = await _units_for_user(default_user)
    apple = await Ingredient.create(owner=default_user, name="apple")
    recipe = await Recipe.create(
        name="Apple mix",
        description="",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=apple, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=apple, quantity=1, unit=pieces
    )

    response = await test_client.get(
        f"/ingredients/merge-units/{apple.id}/{grams.id}/{pieces.id}/edit",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'name="target_unit_id"' in response.text
    assert 'name="amount_a"' in response.text
    assert 'name="amount_b"' in response.text
    assert "Keep this unit everywhere" in response.text
