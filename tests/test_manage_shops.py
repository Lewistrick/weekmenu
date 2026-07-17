"""Tests for the manage shops page."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Recipe, RecipeIngredient, Shop, Unit, User
from src.shops import (
    delete_unused_ingredient,
    ingredient_assignment_groups,
    load_ingredient_recipe_counts,
    load_shops,
    set_ingredient_shop,
)


@pytest.mark.asyncio
async def test_manage_shops_page_shows_tile_grid(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Existing shops should render as tiles in a grid."""
    await Shop.create(owner=default_user, name="Albert Heijn")

    response = await test_client.get("/shops/manage")

    assert response.status_code == 200
    assert "manage-shop-grid" in response.text
    assert "manage-shop-tile" in response.text
    assert "Albert Heijn" in response.text


@pytest.mark.asyncio
async def test_manage_shops_page_uses_save_icon(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Shop edit tiles should use the save icon instead of a pencil."""
    await Shop.create(owner=default_user, name="Jumbo")

    response = await test_client.get("/shops/manage")

    assert response.status_code == 200
    assert 'aria-label="Save shop"' in response.text
    assert "💾" in response.text
    assert "✏️" not in response.text


@pytest.mark.asyncio
async def test_manage_shops_page_groups_assignments_by_shop(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ingredient assignments should be grouped with unassigned ingredients first."""
    first_shop = await Shop.create(owner=default_user, name="Albert Heijn")
    second_shop = await Shop.create(owner=default_user, name="Jumbo")
    milk = await Ingredient.create(owner=default_user, name="milk")
    await Ingredient.create(owner=default_user, name="bread")
    cheese = await Ingredient.create(owner=default_user, name="cheese")
    await set_ingredient_shop(default_user.id, milk.id, first_shop.id)
    await set_ingredient_shop(default_user.id, cheese.id, second_shop.id)

    response = await test_client.get("/shops/manage")

    assert response.status_code == 200
    assert "manage-shop-assignment-group" in response.text
    assignments_section = response.text.split('id="shop-assignments"', 1)[1]
    unassigned_pos = assignments_section.index("Unassigned")
    first_shop_pos = assignments_section.index("Albert Heijn")
    second_shop_pos = assignments_section.index("Jumbo")
    bread_pos = assignments_section.index("bread")
    assert unassigned_pos < first_shop_pos < second_shop_pos
    assert unassigned_pos < bread_pos < first_shop_pos


@pytest.mark.asyncio
async def test_manage_shops_assignment_htmx_returns_partial(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Reassigning via HTMX should swap only the assignments section."""
    shop = await Shop.create(owner=default_user, name="Lidl")
    ingredient = await Ingredient.create(owner=default_user, name="eggs")

    response = await test_client.post(
        "/shops/assignments",
        data={"ingredient_id": ingredient.id, "shop_id": shop.id},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'id="shop-assignments"' in response.text
    assert "Manage shops" not in response.text
    assert "Lidl" in response.text
    assert "eggs" in response.text


@pytest.mark.asyncio
async def test_ingredient_assignment_groups_orders_unassigned_first(
    default_user: User,
) -> None:
    """The grouping helper should list unassigned ingredients before shop buckets."""
    first_shop = await Shop.create(owner=default_user, name="Corner store")
    assigned = await Ingredient.create(owner=default_user, name="salt")
    await Ingredient.create(owner=default_user, name="pepper")
    await set_ingredient_shop(default_user.id, assigned.id, first_shop.id)

    shops = await load_shops(default_user.id)
    groups = await ingredient_assignment_groups(default_user.id, shops)

    assert [group["label"] for group in groups] == ["Unassigned", "Corner store"]
    assert groups[0]["rows"][0]["ingredient"].name == "pepper"
    assert groups[1]["rows"][0]["ingredient"].name == "salt"


@pytest.mark.asyncio
async def test_manage_shops_page_shows_recipe_count(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ingredients in recipes should show how many recipes use them."""
    recipe = await Recipe.create(
        name="Count stew",
        description="recipe count test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    flour = await Ingredient.create(owner=default_user, name="flour")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=flour, quantity=100, unit=grams
    )

    response = await test_client.get("/shops/manage")

    assert response.status_code == 200
    assert "in 1 recipe" in response.text


@pytest.mark.asyncio
async def test_manage_shops_page_shows_delete_for_unused_ingredient(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Unused ingredients should show a zero count and a delete button."""
    await Ingredient.create(owner=default_user, name="abc")

    response = await test_client.get("/shops/manage")

    assert response.status_code == 200
    assert "manage-shop-ingredient-tile" in response.text
    assert "in 0 recipe(s)" in response.text
    assert 'aria-label="Delete unused ingredient"' in response.text


@pytest.mark.asyncio
async def test_manage_shops_delete_unused_ingredient(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Deleting an unused ingredient should remove it from the assignments list."""
    leftover = await Ingredient.create(owner=default_user, name="abc")

    response = await test_client.delete(
        f"/shops/ingredients/{leftover.id}",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "abc" not in response.text
    assert await Ingredient.filter(id=leftover.id).exists() is False


@pytest.mark.asyncio
async def test_manage_shops_cannot_delete_ingredient_in_recipe(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ingredients used in recipes should not be deletable."""
    recipe = await Recipe.create(
        name="Protected stew",
        description="delete guard test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    salt = await Ingredient.create(owner=default_user, name="salt")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=salt, quantity=5, unit=grams
    )

    response = await test_client.delete(f"/shops/ingredients/{salt.id}")

    assert response.status_code == 404
    assert await Ingredient.filter(id=salt.id).exists() is True


@pytest.mark.asyncio
async def test_load_ingredient_recipe_counts(default_user: User) -> None:
    """Recipe counts should reflect distinct recipes per ingredient."""
    recipe_a = await Recipe.create(
        name="Count A",
        description="count a",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Count B",
        description="count b",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    shared = await Ingredient.create(owner=default_user, name="shared")
    unused = await Ingredient.create(owner=default_user, name="unused")
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=shared, quantity=10, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=shared, quantity=20, unit=grams
    )

    counts = await load_ingredient_recipe_counts(default_user.id)

    assert counts[shared.id] == 2
    assert unused.id not in counts
    assert await delete_unused_ingredient(default_user.id, unused.id) is True
    assert await delete_unused_ingredient(default_user.id, shared.id) is False
