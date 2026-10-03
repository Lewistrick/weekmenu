"""Tests for the in-shop page, the basket and the unpack step."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import (
    GroceryListItem,
    Ingredient,
    IngredientCategory,
    InventoryItem,
    Recipe,
    RecipeIngredient,
    Shop,
    Unit,
    User,
    WeeklyGrocery,
)
from src.plan_store import (
    GROCERY_STATUS_ACTIVE,
    GROCERY_STATUS_IN_BASKET,
    GROCERY_STATUS_TO_CHECK,
)

HTMX = {"HX-Request": "true"}


async def _line_in(
    client: AsyncTestClient,
    user: User,
    name: str,
    *,
    shop: Shop | None = None,
    shelf: IngredientCategory | None = None,
    quantity: str = "1",
    unit: str = "st",
) -> Ingredient:
    """Put one grocery line on the list, optionally in a shop and on a shelf."""
    await client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": name, "quantity": quantity, "unit": unit},
    )
    ingredient = await Ingredient.get(owner_id=user.id, name=name)
    if shelf is not None:
        await Ingredient.filter(id=ingredient.id).update(category_id=shelf.id)
    if shop is not None:
        await client.post(
            "/week-menu/grocery-list/assign",
            data={
                "ingredient_id": str(ingredient.id),
                "unit": unit,
                "shop_id": str(shop.id),
            },
        )
    return ingredient


async def _status(user: User, ingredient: Ingredient) -> str:
    """Return the grocery status of an ingredient's single line."""
    row = await GroceryListItem.get(user_id=user.id, ingredient_id=ingredient.id)
    return row.status


async def _to_basket(
    client: AsyncTestClient,
    ingredient: Ingredient,
    shop: Shop,
    shelf_id: str,
    *,
    unit: str = "st",
    in_basket: str = "1",
):
    """POST the basket toggle the way the shop page does (htmx)."""
    return await client.post(
        "/shopping/basket",
        data={
            "ingredient_id": str(ingredient.id),
            "unit": unit,
            "shop_ref": str(shop.id),
            "shelf_id": shelf_id,
            "in_basket": in_basket,
        },
        headers=HTMX,
    )


def _shelf(text: str, shelf_id: str) -> str:
    """Return the HTML of one shelf of a shop page."""
    return text.split(f'id="shelf-{shelf_id}"', 1)[1].split("</details>", 1)[0]


# --- Picker and navigation -------------------------------------------------------


@pytest.mark.asyncio
async def test_shopping_is_linked_from_nav_home_and_grocery_list(
    test_client: AsyncTestClient,
) -> None:
    """The page is reachable from the navbar, the home page and the grocery list."""
    home = await test_client.get("/")
    grocery = await test_client.get("/week-menu/grocery-list")

    assert 'href="/shopping" class="nav-link"' in home.text
    assert 'href="/shopping" class="action-card"' in home.text
    assert 'href="/shopping" class="btn btn-primary"' in grocery.text


@pytest.mark.asyncio
async def test_picker_lists_shops_with_items_left(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Each shop with items gets a card; items in the basket are not 'left'."""
    market = await Shop.create(owner=default_user, name="Market")
    await Shop.create(owner=default_user, name="Empty shop")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    await _line_in(test_client, default_user, "pear", shop=market)
    await _line_in(test_client, default_user, "loose")
    await _to_basket(test_client, apple, market, "none")

    page = await test_client.get("/shopping")

    assert f'href="/shopping/shop/{market.id}"' in page.text
    assert "Empty shop" not in page.text
    assert "1 left" in page.text.split("Market", 1)[1].split("</a>", 1)[0]
    assert 'href="/shopping/shop/none"' in page.text
    assert "No shop yet" in page.text
    assert "Done shopping (1)" in page.text


@pytest.mark.asyncio
async def test_picker_without_a_list_points_to_the_grocery_list(
    test_client: AsyncTestClient,
) -> None:
    """With nothing to buy there are no cards, only a way to the list."""
    page = await test_client.get("/shopping")

    assert "Nothing to buy yet." in page.text
    assert "Done shopping" not in page.text


# --- Shop page ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shop_page_groups_by_shelf_in_shelf_order(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Shelves follow the user's order; only this shop's lines are shown."""
    veg = await IngredientCategory.create(
        owner=default_user, name="Veg", icon="🥦", sort_order=0
    )
    dairy = await IngredientCategory.create(
        owner=default_user, name="Dairy", icon="🧀", sort_order=1
    )
    market = await Shop.create(owner=default_user, name="Market")
    other = await Shop.create(owner=default_user, name="Other")
    await _line_in(test_client, default_user, "milk", shop=market, shelf=dairy)
    await _line_in(test_client, default_user, "carrot", shop=market, shelf=veg)
    await _line_in(test_client, default_user, "salt", shop=market)
    await _line_in(test_client, default_user, "soap", shop=other)

    page = await test_client.get(f"/shopping/shop/{market.id}")

    veg_at = page.text.index(f'id="shelf-c{veg.id}"')
    dairy_at = page.text.index(f'id="shelf-c{dairy.id}"')
    none_at = page.text.index('id="shelf-none"')
    assert veg_at < dairy_at < none_at
    assert "🥦 Veg" in page.text and "1 left" in _shelf(page.text, f"c{veg.id}")
    assert "carrot" in _shelf(page.text, f"c{veg.id}")
    assert "soap" not in page.text
    assert "0 of 3 in basket" in page.text


@pytest.mark.asyncio
async def test_shop_page_for_unassigned_items_and_bad_refs(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """'none' shows unassigned lines; unknown or foreign shops are 404."""
    await _line_in(test_client, default_user, "loose")
    other = await User.create(username="other", email="o@example.com")
    foreign = await Shop.create(owner=other, name="Theirs")

    page = await test_client.get("/shopping/shop/none")

    assert "loose" in page.text
    assert (await test_client.get(f"/shopping/shop/{foreign.id}")).status_code == 404
    assert (await test_client.get("/shopping/shop/9999")).status_code == 404
    assert (await test_client.get("/shopping/shop/abc")).status_code == 404


@pytest.mark.asyncio
async def test_swipe_and_buttons_are_wired_on_rows(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Rows can be swiped right to the basket button; the script is versioned."""
    market = await Shop.create(owner=default_user, name="Market")
    await _line_in(test_client, default_user, "apple", shop=market)

    page = await test_client.get(f"/shopping/shop/{market.id}")

    assert 'data-swipe-right=".shopping-basket-btn"' in page.text
    assert 'class="swipe-row shopping-item"' in page.text
    assert 'hx-post="/shopping/basket"' in page.text
    assert 'hx-post="/shopping/to-check"' in page.text
    assert "/static/js/swipe-actions.js?v=" in page.text
    assert "/static/css/shopping.css?v=" in page.text


# --- Basket ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_basket_toggle_never_touches_the_inventory(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Basket on and off changes the status only, never the inventory."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)

    on = await _to_basket(test_client, apple, market, "none")

    assert on.status_code in (200, 201)
    assert await _status(default_user, apple) == GROCERY_STATUS_IN_BASKET
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()
    assert 'id="shelf-none"' in on.text
    assert 'aria-pressed="true"' in on.text
    assert 'hx-swap-oob="true"' in on.text
    assert "1 of 1 in basket" in on.text

    off = await _to_basket(test_client, apple, market, "none", in_basket="0")

    assert await _status(default_user, apple) == GROCERY_STATUS_ACTIVE
    assert 'aria-pressed="false"' in off.text
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()


@pytest.mark.asyncio
async def test_finished_shelf_folds_and_basket_rows_sink(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A shelf is open while items are left; basket items come last, struck."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    await _line_in(test_client, default_user, "banana", shop=market)

    first = await _to_basket(test_client, apple, market, "none")
    shelf = _shelf(first.text, "none")
    assert " open" in first.text.split('id="shelf-none"', 1)[1].split(">", 1)[0]
    assert shelf.index("banana") < shelf.index("apple")
    assert "shopping-item--basket" in shelf

    banana = await Ingredient.get(owner_id=default_user.id, name="banana")
    last = await _to_basket(test_client, banana, market, "none")
    assert " open" not in last.text.split('id="shelf-none"', 1)[1].split(">", 1)[0]
    assert "Done" in last.text


@pytest.mark.asyncio
async def test_to_check_moves_line_off_the_page(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """'?' sends the line to To check; an emptied shelf disappears."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)

    response = await test_client.post(
        "/shopping/to-check",
        data={
            "ingredient_id": str(apple.id),
            "unit": "st",
            "shop_ref": str(market.id),
            "shelf_id": "none",
        },
        headers=HTMX,
    )

    assert await _status(default_user, apple) == GROCERY_STATUS_TO_CHECK
    assert "<details" not in response.text
    assert 'id="shopping-progress"' in response.text
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()


@pytest.mark.asyncio
async def test_actions_without_htmx_redirect_back_to_the_shop(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Without JavaScript the actions still work and return to the shop page."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)

    response = await test_client.post(
        "/shopping/basket",
        data={
            "ingredient_id": str(apple.id),
            "unit": "st",
            "shop_ref": str(market.id),
            "shelf_id": "none",
            "in_basket": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/shopping/shop/{market.id}")
    assert await _status(default_user, apple) == GROCERY_STATUS_IN_BASKET


@pytest.mark.asyncio
async def test_basket_lines_are_muted_on_the_grocery_list_and_not_exported(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Bought lines stay on the list (muted) but are left out of the export."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    await _line_in(test_client, default_user, "pear", shop=market)
    await _to_basket(test_client, apple, market, "none")

    page = await test_client.get("/week-menu/grocery-list")
    export = await test_client.get("/week-menu/grocery-list/export")

    assert "grocery-item--basket" in page.text
    assert "apple" in page.text
    assert "apple" not in export.text
    assert "pear" in export.text


@pytest.mark.asyncio
async def test_changed_amount_takes_a_line_out_of_the_basket(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """If the amount needed changes, what was bought no longer matches."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    await _to_basket(test_client, apple, market, "none")

    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "apple", "quantity": "2", "unit": "st"},
    )

    assert await _status(default_user, apple) == GROCERY_STATUS_ACTIVE

    await _to_basket(test_client, apple, market, "none")
    await test_client.post(
        f"/week-menu/grocery-list/item/{apple.id}/st",
        data={"quantity": "5", "unit": "st"},
    )
    assert await _status(default_user, apple) == GROCERY_STATUS_ACTIVE

    await _to_basket(test_client, apple, market, "none")
    await test_client.post(
        f"/week-menu/grocery-list/item/{apple.id}/st",
        data={"quantity": "5", "unit": "st"},
    )
    assert await _status(default_user, apple) == GROCERY_STATUS_IN_BASKET


# --- Unpack ----------------------------------------------------------------------


async def _weekly_and_recipe_basket(
    client: AsyncTestClient, user: User, market: Shop
) -> tuple[Ingredient, Ingredient, Ingredient]:
    """Basket with a weekly staple, a recipe ingredient and a hand-added item."""
    staple = await Ingredient.create(owner=user, name="milk")
    grams = await Unit.get(owner_id=user.id, abbrev="g")
    litre = await Unit.get(owner_id=user.id, abbrev="l")
    await WeeklyGrocery.create(owner=user, ingredient=staple, unit=litre, quantity=2)
    dish_item = await Ingredient.create(owner=user, name="pasta")
    recipe = await Recipe.create(
        name="Dish",
        description="d",
        prep_time_minutes=1,
        cook_time_minutes=1,
        servings=2,
        owner=user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=dish_item, quantity=500, unit=grams
    )
    await client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await client.post("/week-menu/grocery-list/generate", data={"mode": "replace"})
    await client.post("/week-menu/grocery-list/add-weekly")
    extra = await _line_in(client, user, "candle", shop=market)
    for ingredient, unit in ((staple, "l"), (dish_item, "g"), (extra, "st")):
        await client.post(
            "/week-menu/grocery-list/assign",
            data={
                "ingredient_id": str(ingredient.id),
                "unit": unit,
                "shop_id": str(market.id),
            },
        )
        await _to_basket(client, ingredient, market, "none", unit=unit)
    return staple, dish_item, extra


@pytest.mark.asyncio
async def test_unpack_defaults_tick_weekly_staples_only(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Weekly staples start ticked; recipe and hand-added items do not."""
    market = await Shop.create(owner=default_user, name="Market")
    await _weekly_and_recipe_basket(test_client, default_user, market)

    page = await test_client.get("/shopping/unpack")

    def row(name: str) -> str:
        return page.text.split(f">{name}</label>", 1)[0].rsplit('item-row--check"', 1)[
            1
        ]

    assert 'name="line_count" value="3"' in page.text
    assert " checked" in row("milk")
    assert " checked" not in row("pasta")
    assert " checked" not in row("candle")
    assert 'value="2"' in page.text.split(">milk</label>", 1)[1].split("</div>", 1)[0]


@pytest.mark.asyncio
async def test_unpack_adds_ticked_lines_and_clears_the_basket(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ticked lines are summed into the inventory; all listed lines are removed."""
    market = await Shop.create(owner=default_user, name="Market")
    staple, dish_item, extra = await _weekly_and_recipe_basket(
        test_client, default_user, market
    )
    litre = await Unit.get(owner_id=default_user.id, abbrev="l")
    await InventoryItem.create(
        owner=default_user, ingredient=staple, unit=litre, quantity=1
    )
    data = {"line_count": "3"}
    for position, (ingredient, unit, include, quantity) in enumerate(
        (
            (staple, "l", True, "3"),
            (dish_item, "g", False, "500"),
            (extra, "st", True, "1"),
        )
    ):
        data[f"ingredient_id_{position}"] = str(ingredient.id)
        data[f"unit_{position}"] = unit
        data[f"quantity_{position}"] = quantity
        if include:
            data[f"include_{position}"] = "1"

    response = await test_client.post(
        "/shopping/unpack", data=data, follow_redirects=True
    )

    milk = await InventoryItem.get(owner_id=default_user.id, ingredient_id=staple.id)
    assert milk.quantity == 4  # 1 in stock + 3 bought
    candle = await InventoryItem.get(owner_id=default_user.id, ingredient_id=extra.id)
    assert candle.quantity == 1
    assert not await InventoryItem.filter(
        owner_id=default_user.id, ingredient_id=dish_item.id
    ).exists()
    assert not await GroceryListItem.filter(
        user_id=default_user.id, status=GROCERY_STATUS_IN_BASKET
    ).exists()
    assert "2 added to your inventory, 3 cleared from your grocery list." in (
        response.text
    )


@pytest.mark.asyncio
async def test_unpack_only_removes_the_lines_it_listed(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A line put in the basket after the page was loaded stays in the basket."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    pear = await _line_in(test_client, default_user, "pear", shop=market)
    await _to_basket(test_client, apple, market, "none")
    await _to_basket(test_client, pear, market, "none")

    await test_client.post(
        "/shopping/unpack",
        data={
            "line_count": "1",
            "ingredient_id_0": str(apple.id),
            "unit_0": "st",
            "quantity_0": "1",
        },
    )

    assert not await GroceryListItem.filter(
        user_id=default_user.id, ingredient_id=apple.id
    ).exists()
    assert await _status(default_user, pear) == GROCERY_STATUS_IN_BASKET
    assert not await InventoryItem.filter(owner_id=default_user.id).exists()


@pytest.mark.asyncio
async def test_unpack_ignores_bad_quantities_and_foreign_ingredients(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Ticked lines with no valid amount, or another user's ingredient, add nothing."""
    market = await Shop.create(owner=default_user, name="Market")
    apple = await _line_in(test_client, default_user, "apple", shop=market)
    await _to_basket(test_client, apple, market, "none")
    other = await User.create(username="other", email="o@example.com")
    theirs = await Ingredient.create(owner=other, name="secret")

    await test_client.post(
        "/shopping/unpack",
        data={
            "line_count": "2",
            "ingredient_id_0": str(apple.id),
            "unit_0": "st",
            "quantity_0": "abc",
            "include_0": "1",
            "ingredient_id_1": str(theirs.id),
            "unit_1": "st",
            "quantity_1": "5",
            "include_1": "1",
        },
    )

    assert not await InventoryItem.filter(owner_id=default_user.id).exists()
    assert not await InventoryItem.filter(owner_id=other.id).exists()


@pytest.mark.asyncio
async def test_unpack_page_when_the_basket_is_empty(
    test_client: AsyncTestClient,
) -> None:
    """An empty basket says so and offers no form."""
    page = await test_client.get("/shopping/unpack")

    assert "Your basket is empty." in page.text
    assert 'name="line_count"' not in page.text
