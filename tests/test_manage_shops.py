"""Tests for the manage shops page."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Shop, User
from src.shops import ingredient_assignment_groups, set_ingredient_shop


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

    from src.shops import load_shops

    shops = await load_shops(default_user.id)
    groups = await ingredient_assignment_groups(default_user.id, shops)

    assert [group["label"] for group in groups] == ["Unassigned", "Corner store"]
    assert groups[0]["rows"][0]["ingredient"].name == "pepper"
    assert groups[1]["rows"][0]["ingredient"].name == "salt"
