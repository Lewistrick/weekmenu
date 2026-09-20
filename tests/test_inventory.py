"""Tests for inventory management and its link to the grocery list."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from litestar.testing import AsyncTestClient

from src.ingredient_merge import merge_ingredients
from src.inventory import (
    INVENTORY_SORT_NAME,
    INVENTORY_SORT_UPDATED_ASC,
    INVENTORY_SORT_UPDATED_DESC,
    load_inventory,
)
from src.models import (
    GroceryListItem,
    Ingredient,
    InventoryItem,
    Recipe,
    RecipeIngredient,
    Shop,
    Unit,
    User,
)
from src.plan_store import GROCERY_STATUS_ACTIVE, GROCERY_STATUS_ALREADY_HAVE
from src.units import unit_is_in_use


async def _unit(user: User, abbrev: str) -> Unit:
    """Return a seeded unit for a user, failing loudly when missing."""
    unit = await Unit.filter(owner_id=user.id, abbrev=abbrev).first()
    assert unit is not None
    return unit


async def _stock(user: User, name: str, quantity: float, abbrev: str = "g"):
    """Create an ingredient with an inventory item and return both."""
    ingredient = await Ingredient.create(owner=user, name=name)
    item = await InventoryItem.create(
        owner=user,
        ingredient=ingredient,
        unit=await _unit(user, abbrev),
        quantity=quantity,
    )
    return ingredient, item


async def _plan_recipe(
    client: AsyncTestClient,
    user: User,
    lines: list[tuple[Ingredient, float, str]],
    *,
    day: str = "monday",
) -> Recipe:
    """Create a 2-serving recipe with the given lines and plan it on a day."""
    recipe = await Recipe.create(
        name=f"Dish for {day}",
        description="inventory test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=user,
        enabled=True,
    )
    for ingredient, quantity, abbrev in lines:
        await RecipeIngredient.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=quantity,
            unit=await _unit(user, abbrev),
        )
    await client.post(f"/week-menu/{day}/recipe/{recipe.id}")
    return recipe


async def _generate(client: AsyncTestClient, mode: str = "replace") -> str:
    """Generate the grocery list and return the rendered grocery page."""
    response = await client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": mode},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return response.text


async def _line(user: User, ingredient: Ingredient) -> GroceryListItem:
    """Return the single grocery line for an ingredient."""
    row = await GroceryListItem.filter(
        user_id=user.id, ingredient_id=ingredient.id
    ).first()
    assert row is not None
    return row


async def _stock_of(item: InventoryItem) -> float:
    """Return the current inventory amount of an item."""
    await item.refresh_from_db()
    return item.quantity


# --- Inventory page ---------------------------------------------------------


@pytest.mark.asyncio
async def test_inventory_page_is_linked_from_nav_and_home(
    test_client: AsyncTestClient,
) -> None:
    """The inventory tab is a top-level nav link and a home tile."""
    home = await test_client.get("/")
    assert 'href="/inventory" class="nav-link"' in home.text
    assert 'href="/inventory" class="action-card"' in home.text

    response = await test_client.get("/inventory")
    assert response.status_code == 200
    assert "📦 Inventory" in response.text
    assert 'class="editable-list"' not in response.text
    assert "Your inventory is empty." in response.text


@pytest.mark.asyncio
async def test_add_inventory_item_allows_zero_and_merges_duplicates(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding the same ingredient/unit twice adds the amounts together."""
    first = await test_client.post(
        "/inventory", data={"ingredient": "rice", "quantity": "0", "unit": "g"}
    )
    assert "Added to inventory." in first.text

    second = await test_client.post(
        "/inventory", data={"ingredient": "rice", "quantity": "250", "unit": "g"}
    )
    assert "Merged with the existing inventory item" in second.text

    rows = await InventoryItem.filter(owner_id=default_user.id)
    assert len(rows) == 1
    assert rows[0].quantity == 250


@pytest.mark.asyncio
async def test_add_inventory_item_rejects_negative_amount(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Negative amounts are rejected with a warning."""
    response = await test_client.post(
        "/inventory", data={"ingredient": "rice", "quantity": "-1", "unit": "g"}
    )
    assert "Enter an amount of zero or more." in response.text
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()


@pytest.mark.asyncio
async def test_save_inventory_item_updates_timestamp(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Saving an item, even unchanged, bumps its updated_at time."""
    _ingredient, item = await _stock(default_user, "flour", 100)
    old = datetime.now(UTC) - timedelta(days=3)
    await InventoryItem.filter(id=item.id).update(updated_at=old)

    response = await test_client.post(
        f"/inventory/{item.id}",
        data={"ingredient": "flour", "quantity": "100", "unit": "g"},
    )

    assert "Inventory item updated." in response.text
    await item.refresh_from_db()
    assert item.updated_at.replace(tzinfo=None) > old.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_save_inventory_item_into_existing_combo_merges(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Editing an item into an existing ingredient/unit merges the two."""
    flour, target = await _stock(default_user, "flour", 100)
    _other, source = await _stock(default_user, "bloem", 50)

    response = await test_client.post(
        f"/inventory/{source.id}",
        data={"ingredient": "flour", "quantity": "75", "unit": "g"},
    )

    assert "Merged with the existing inventory item" in response.text
    assert not await InventoryItem.filter(id=source.id).exists()
    assert await _stock_of(target) == 175
    assert target.ingredient_id == flour.id


@pytest.mark.asyncio
async def test_delete_inventory_item(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The delete button removes the item."""
    _ingredient, item = await _stock(default_user, "salt", 10)

    response = await test_client.delete(f"/inventory/{item.id}?sort=name")

    assert response.status_code == 200
    assert "Inventory item deleted." in response.text
    assert not await InventoryItem.filter(id=item.id).exists()


@pytest.mark.asyncio
async def test_inventory_items_are_private_per_user(
    test_client: AsyncTestClient,
) -> None:
    """Another user's inventory cannot be edited or deleted."""
    other = await User.create(username="other", email="o@example.com")
    ingredient = await Ingredient.create(owner=other, name="secret")
    grams = await Unit.create(owner=other, abbrev="g")
    item = await InventoryItem.create(
        owner=other, ingredient=ingredient, unit=grams, quantity=1
    )

    edit = await test_client.post(
        f"/inventory/{item.id}",
        data={"ingredient": "mine", "quantity": "5", "unit": "g"},
    )
    assert "Inventory item not found." in edit.text
    delete = await test_client.delete(f"/inventory/{item.id}")
    assert delete.status_code == 404
    assert await _stock_of(item) == 1


@pytest.mark.asyncio
async def test_inventory_sort_orders(default_user: User, test_client) -> None:
    """Inventory sorts by update time (both directions) and alphabetically."""
    now = datetime.now(UTC)
    for name, age_days in (("banana", 1), ("apple", 3), ("cherry", 2)):
        _ingredient, item = await _stock(default_user, name, 1)
        await InventoryItem.filter(id=item.id).update(
            updated_at=now - timedelta(days=age_days)
        )

    def names(rows):
        return [row["name"] for row in rows]

    newest = await load_inventory(default_user.id, INVENTORY_SORT_UPDATED_DESC)
    oldest = await load_inventory(default_user.id, INVENTORY_SORT_UPDATED_ASC)
    by_name = await load_inventory(default_user.id, INVENTORY_SORT_NAME)
    assert names(newest) == ["banana", "cherry", "apple"]
    assert names(oldest) == ["apple", "cherry", "banana"]
    assert names(by_name) == ["apple", "banana", "cherry"]

    page = await test_client.get("/inventory?sort=name")
    assert '<option value="name" selected>' in page.text
    assert page.text.index('value="apple"') < page.text.index('value="banana"')


# --- Grocery list integration -------------------------------------------------


@pytest.mark.asyncio
async def test_generate_moves_fully_stocked_items_to_already_have(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Covered lines move to already-have and their amount is reserved."""
    pasta, stock = await _stock(default_user, "pasta", 500)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])

    page = await _generate(test_client)

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ALREADY_HAVE
    assert line.inventory_quantity == 500
    assert await _stock_of(stock) == 0
    assert "Moved 1 grocery to &#39;Already have&#39;" in page or (
        "Moved 1 grocery to 'Already have'" in page
    )


@pytest.mark.asyncio
async def test_first_visit_generation_also_reserves_inventory(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The automatic first grocery list also checks the inventory."""
    pasta, stock = await _stock(default_user, "pasta", 800)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])

    await test_client.get("/week-menu/grocery-list")

    assert (await _line(default_user, pasta)).status == GROCERY_STATUS_ALREADY_HAVE
    assert await _stock_of(stock) == 300


@pytest.mark.asyncio
async def test_partial_stock_leaves_item_on_list(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """When stock does not cover the line, nothing is reserved."""
    pasta, stock = await _stock(default_user, "pasta", 200)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])

    await _generate(test_client)

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ACTIVE
    assert line.inventory_quantity == 0
    assert await _stock_of(stock) == 200


@pytest.mark.asyncio
async def test_stock_in_other_unit_does_not_count(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Only the exact ingredient/unit combination is matched."""
    milk, stock = await _stock(default_user, "milk", 5, abbrev="l")
    await _plan_recipe(test_client, default_user, [(milk, 500, "g")])

    await _generate(test_client)

    assert (await _line(default_user, milk)).status == GROCERY_STATUS_ACTIVE
    assert await _stock_of(stock) == 5


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ("/week-menu/grocery-list/already-have/remove", {}),
        ("/week-menu/grocery-list/to-check", {}),
        ("/week-menu/grocery-list/assign", {"shop": True}),
    ],
)
@pytest.mark.asyncio
async def test_moving_reserved_item_back_restores_inventory(
    test_client: AsyncTestClient,
    default_user: User,
    path: str,
    extra: dict,
) -> None:
    """Placing a reserved line back on any list returns its stock."""
    pasta, stock = await _stock(default_user, "pasta", 600)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)
    assert await _stock_of(stock) == 100

    data = {"ingredient_id": str(pasta.id), "unit": "g"}
    if extra.get("shop"):
        shop = await Shop.create(owner=default_user, name="Market")
        data["shop_id"] = str(shop.id)
    response = await test_client.post(path, data=data)

    assert response.status_code in (200, 201)
    line = await _line(default_user, pasta)
    assert line.status != GROCERY_STATUS_ALREADY_HAVE
    assert line.inventory_quantity == 0
    assert await _stock_of(stock) == 600


@pytest.mark.asyncio
async def test_clearing_already_have_keeps_stock_subtracted(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Clearing the already-have list makes the subtraction final."""
    pasta, stock = await _stock(default_user, "pasta", 500)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)

    await test_client.post("/week-menu/grocery-list/already-have/clear")

    assert not await GroceryListItem.filter(user_id=default_user.id).exists()
    assert await _stock_of(stock) == 0


@pytest.mark.asyncio
async def test_replace_treats_previous_reservation_as_used(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Regenerating with replace does not put the old reservation back."""
    pasta, stock = await _stock(default_user, "pasta", 700)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)
    assert await _stock_of(stock) == 200

    await _generate(test_client, "replace")

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ACTIVE
    assert line.inventory_quantity == 0
    assert await _stock_of(stock) == 200


@pytest.mark.asyncio
async def test_merge_rechecks_reserved_line_when_amount_grows(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A reserved line that grows past the stock is released back to the list."""
    pasta, stock = await _stock(default_user, "pasta", 700)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)
    assert await _stock_of(stock) == 200

    # Adding the same week menu again doubles the line to 1000 g.
    await _generate(test_client, "merge")

    line = await _line(default_user, pasta)
    assert line.quantity == 1000
    assert line.status == GROCERY_STATUS_ACTIVE
    assert line.inventory_quantity == 0
    assert await _stock_of(stock) == 700


@pytest.mark.asyncio
async def test_merge_keeps_reservation_when_stock_covers_growth(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A reserved line that grows within the stock stays reserved."""
    pasta, stock = await _stock(default_user, "pasta", 1200)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)

    await _generate(test_client, "merge")

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ALREADY_HAVE
    assert line.inventory_quantity == 1000
    assert await _stock_of(stock) == 200


@pytest.mark.asyncio
async def test_merge_only_reserves_new_lines(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merge does not re-reserve a line the user put back on the list."""
    pasta, stock = await _stock(default_user, "pasta", 200)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)
    rice, rice_stock = await _stock(default_user, "rice", 300)
    await InventoryItem.filter(id=stock.id).update(quantity=5000)
    await _plan_recipe(test_client, default_user, [(rice, 300, "g")], day="tuesday")

    await _generate(test_client, "merge")

    assert (await _line(default_user, pasta)).status == GROCERY_STATUS_ACTIVE
    assert (await _line(default_user, rice)).status == GROCERY_STATUS_ALREADY_HAVE
    assert await _stock_of(rice_stock) == 0


@pytest.mark.asyncio
async def test_editing_reserved_amount_past_stock_releases_it(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Raising a reserved line's amount past the stock returns it to the list."""
    pasta, stock = await _stock(default_user, "pasta", 600)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)

    await test_client.post(
        f"/week-menu/grocery-list/item/{pasta.id}/g",
        data={"quantity": "900", "unit": "g"},
    )

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ACTIVE
    assert await _stock_of(stock) == 600


@pytest.mark.asyncio
async def test_editing_reserved_amount_within_stock_adjusts_it(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Lowering a reserved line's amount returns the difference to stock."""
    pasta, stock = await _stock(default_user, "pasta", 600)
    await _plan_recipe(test_client, default_user, [(pasta, 500, "g")])
    await _generate(test_client)

    await test_client.post(
        f"/week-menu/grocery-list/item/{pasta.id}/g",
        data={"quantity": "300", "unit": "g"},
    )

    line = await _line(default_user, pasta)
    assert line.status == GROCERY_STATUS_ALREADY_HAVE
    assert line.inventory_quantity == 300
    assert await _stock_of(stock) == 300


@pytest.mark.asyncio
async def test_marking_already_have_copies_item_to_inventory(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The per-item ✓ adds the ingredient/unit to inventory with amount 0."""
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "eggs", "quantity": "6", "unit": "st"},
    )
    eggs = await Ingredient.get(owner_id=default_user.id, name="eggs")

    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": str(eggs.id), "unit": "st"},
    )

    item = await InventoryItem.get(owner_id=default_user.id, ingredient_id=eggs.id)
    assert item.quantity == 0
    assert item.unit_id == (await _unit(default_user, "st")).id
    line = await _line(default_user, eggs)
    assert line.status == GROCERY_STATUS_ALREADY_HAVE
    assert line.inventory_quantity == 0


@pytest.mark.asyncio
async def test_marking_already_have_keeps_existing_inventory_amount(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An existing inventory item is not reset when marking already-have."""
    eggs, stock = await _stock(default_user, "eggs", 2, abbrev="st")
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "eggs", "quantity": "6", "unit": "st"},
    )

    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": str(eggs.id), "unit": "st"},
    )

    assert await _stock_of(stock) == 2
    assert await InventoryItem.filter(owner_id=default_user.id).count() == 1


@pytest.mark.asyncio
async def test_mark_all_in_shop_does_not_copy_to_inventory(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The bulk shop ✓ only moves items; it does not touch the inventory."""
    shop = await Shop.create(owner=default_user, name="Market")
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "eggs", "quantity": "6", "unit": "st"},
    )
    eggs = await Ingredient.get(owner_id=default_user.id, name="eggs")
    await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": str(eggs.id), "unit": "st", "shop_id": str(shop.id)},
    )

    await test_client.post(f"/week-menu/grocery-list/shop/{shop.id}/already-have")

    assert (await _line(default_user, eggs)).status == GROCERY_STATUS_ALREADY_HAVE
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()


# --- Catalog maintenance ------------------------------------------------------


@pytest.mark.asyncio
async def test_merging_ingredients_merges_inventory(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merging ingredients combines their inventory for the same unit."""
    source, source_stock = await _stock(default_user, "tomatos", 100)
    target, target_stock = await _stock(default_user, "tomatoes", 50)

    result = await merge_ingredients(default_user.id, source.id, target.id)

    assert result.ok
    assert not await InventoryItem.filter(id=source_stock.id).exists()
    assert await _stock_of(target_stock) == 150


@pytest.mark.asyncio
async def test_unit_used_by_inventory_is_in_use(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A unit referenced only by inventory cannot be deleted."""
    _ingredient, item = await _stock(default_user, "oil", 1, abbrev="l")

    assert await unit_is_in_use(owner_id=default_user.id, unit_id=item.unit_id)


@pytest.mark.asyncio
async def test_inventory_rows_use_shared_item_row_layout(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Rows use the shared item-row grid, without a visible timestamp."""
    await _stock(default_user, "pasta", 250)

    page = await test_client.get("/inventory")

    assert page.text.count('class="ingredient-input item-row"') == 2
    assert page.text.count('class="item-row-actions"') == 2
    assert "<time" not in page.text
    # Each CSS module the hub imports is linked with its own cache buster.
    assert "/static/css/tokens.css?v=" in page.text
    assert "/static/css/components.css?v=" in page.text


@pytest.mark.asyncio
async def test_delete_asks_confirmation_only_when_amount_is_positive(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Items with stock get the site-wide inline confirm; empty ones delete directly."""
    _pasta, stocked = await _stock(default_user, "pasta", 250)
    _salt, empty = await _stock(default_user, "salt", 0)

    page = await test_client.get("/inventory")

    stocked_row = page.text.split(f'id="inventory-item-{stocked.id}"', 1)[1]
    stocked_row = stocked_row.split("</li>", 1)[0]
    empty_row = page.text.split(f'id="inventory-item-{empty.id}"', 1)[1]
    empty_row = empty_row.split("</li>", 1)[0]
    assert "inline-confirm-trigger" in stocked_row
    assert 'class="inline-confirm"' in stocked_row
    assert "inline-confirm-cancel" in stocked_row
    assert "inline-confirm" not in empty_row
    assert f'hx-delete="/inventory/{empty.id}?sort=updated_desc"' in empty_row


@pytest.mark.asyncio
async def test_grocery_add_form_uses_shared_item_row(
    test_client: AsyncTestClient,
) -> None:
    """The grocery page's add form uses the same row layout as inventory."""
    page = await test_client.get("/week-menu/grocery-list")

    form = page.text.split('id="grocery-add-form"', 1)[1].split("</form>", 1)[0]
    assert 'class="ingredient-input item-row"' in form
    assert 'class="item-row-actions"' in form


def test_item_row_grid_wins_over_ingredient_input_flex() -> None:
    """The row grid must outrank `.ingredient-input`'s flex, whatever the order.

    Both classes sit on the same element. With a plain `.item-row` selector the
    two rules tie on specificity, so the one later in components.css wins and
    the two-line phone layout silently disappears.
    """
    css = Path("src/static/css/components.css").read_text(encoding="utf-8")

    assert ".ingredient-input.item-row {\n    display: grid;" in css
    assert "\n.item-row {" not in css
