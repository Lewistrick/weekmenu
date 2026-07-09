"""Tests for grocery grouping by shop and plaintext export."""

import pytest

from litestar.testing import AsyncTestClient


from src.grocery import (
    format_grocery_export,
    format_week_menu_export,
    split_grocery_lists,
)

from src.models import Ingredient, Recipe, RecipeIngredient, Shop, Unit, User

from src.shops import ShopInfo, load_ingredient_shop_ids, set_ingredient_shop

from src.week_menu import GroceryItem


def test_split_grocery_lists_separates_unassigned_and_shops() -> None:
    """Ingredients without a shop assignment should appear as unassigned."""

    items = [
        GroceryItem(ingredient_id=1, name="potatoes", unit="g", quantity=500.0),
        GroceryItem(ingredient_id=2, name="onion", unit="st", quantity=2.0),
    ]

    shops: list[ShopInfo] = [
        ShopInfo(
            id=10,
            name="Albert Heijn",
            foreground_color="#ffffff",
            background_color="#2563eb",
            letter="A",
        )
    ]

    unassigned, already_have, groups = split_grocery_lists(
        items,
        ingredient_shop_ids={1: 10},
        shops=shops,
        already_have_ids=set(),
    )

    assert [item["name"] for item in unassigned] == ["onion"]

    assert already_have == []

    assert [group["shop_name"] for group in groups] == ["Albert Heijn"]

    assert groups[0]["entries"][0]["name"] == "potatoes"


def test_split_grocery_lists_moves_items_to_already_have() -> None:
    """Marked ingredients should leave the unassigned and shop lists."""

    items = [
        GroceryItem(ingredient_id=1, name="salt", unit="g", quantity=5.0),
        GroceryItem(ingredient_id=2, name="pepper", unit="g", quantity=3.0),
    ]

    unassigned, already_have, groups = split_grocery_lists(
        items,
        ingredient_shop_ids={},
        shops=[],
        already_have_ids={1},
    )

    assert [item["name"] for item in unassigned] == ["pepper"]

    assert [item["name"] for item in already_have] == ["salt"]

    assert groups == []


def test_format_grocery_export_uses_plaintext_lines_per_shop() -> None:
    """Grocery export should render shop sections with ingredient lines."""

    text = format_grocery_export(
        [GroceryItem(ingredient_id=2, name="onion", unit="st", quantity=3.0)],
        [
            {
                "shop_id": 1,
                "shop_name": "Albert Heijn",
                "foreground_color": "#ffffff",
                "background_color": "#2563eb",
                "letter": "A",
                "entries": [
                    GroceryItem(
                        ingredient_id=1, name="potatoes", unit="g", quantity=600.0
                    )
                ],
            }
        ],
    )

    assert text == "Unassigned\nonion - 3 st\n\nAlbert Heijn\npotatoes - 600 g"


def test_format_week_menu_export_skips_empty_days() -> None:
    """Week menu export should only include days with a recipe."""

    class RecipeStub:
        def __init__(self, name: str) -> None:

            self.name = name

    text = format_week_menu_export(
        [
            {"label": "Monday", "recipe": RecipeStub("Potato mash")},
            {"label": "Tuesday", "recipe": None},
            {"label": "Wednesday", "recipe": RecipeStub("Soup")},
        ]
    )

    assert text == "Monday - Potato mash\nWednesday - Soup"


@pytest.mark.asyncio
async def test_grocery_list_groups_items_by_shop(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The grocery list page should group ingredients under their assigned shop."""

    shop = await Shop.create(owner=default_user, name="Albert Heijn")

    recipe = await Recipe.create(
        name="Shop stew",
        description="grouping test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()

    assert grams is not None

    potatoes = await Ingredient.create(owner=default_user, name="potatoes")

    await set_ingredient_shop(default_user.id, potatoes.id, shop.id)

    await RecipeIngredient.create(
        recipe=recipe, ingredient=potatoes, quantity=200, unit=grams
    )

    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200

    assert "Albert Heijn" in response.text

    assert "grocery-shop-group" in response.text

    assert "grocery-layout" in response.text

    assert ">potatoes</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_shows_unassigned_items_on_left(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Unassigned ingredients should appear in the to-sort column."""

    recipe = await Recipe.create(
        name="Unassigned stew",
        description="unassigned test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()

    assert grams is not None

    carrots = await Ingredient.create(owner=default_user, name="carrots")
    await Shop.create(owner=default_user, name="Local market")

    await RecipeIngredient.create(
        recipe=recipe, ingredient=carrots, quantity=100, unit=grams
    )

    await test_client.post(f"/week-menu/tuesday/recipe/{recipe.id}")

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200

    assert "To sort" in response.text

    assert "shop-chip-btn" in response.text

    assert ">carrots</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_assign_only_when_unassigned(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The grocery list should not reassign ingredients that already have a shop."""

    first_shop = await Shop.create(owner=default_user, name="Jumbo")

    second_shop = await Shop.create(owner=default_user, name="Lidl")

    ingredient = await Ingredient.create(owner=default_user, name="milk")

    await set_ingredient_shop(default_user.id, ingredient.id, first_shop.id)

    response = await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": ingredient.id, "shop_id": second_shop.id},
    )

    assert response.status_code == 200
    ingredient_shop_ids = await load_ingredient_shop_ids(default_user.id)
    assert ingredient_shop_ids.get(ingredient.id) == first_shop.id


@pytest.mark.asyncio
async def test_grocery_list_already_have_moves_item(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Marking an ingredient as already owned should move it below the to-sort list."""

    recipe = await Recipe.create(
        name="Pantry stew",
        description="already-have test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()

    assert grams is not None

    rice = await Ingredient.create(owner=default_user, name="rice")

    await RecipeIngredient.create(
        recipe=recipe, ingredient=rice, quantity=250, unit=grams
    )

    await test_client.post(f"/week-menu/wednesday/recipe/{recipe.id}")

    response = await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": rice.id},
    )

    assert response.status_code == 200

    assert "Already have" in response.text

    assert response.text.index("Already have") < response.text.rindex("rice")


@pytest.mark.asyncio
async def test_grocery_list_export_returns_plaintext(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The grocery export endpoint should return grouped plaintext."""

    shop = await Shop.create(owner=default_user, name="Jumbo")

    recipe = await Recipe.create(
        name="Export stew",
        description="export test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()

    assert grams is not None

    carrots = await Ingredient.create(owner=default_user, name="carrots")

    await set_ingredient_shop(default_user.id, carrots.id, shop.id)

    await RecipeIngredient.create(
        recipe=recipe, ingredient=carrots, quantity=100, unit=grams
    )

    await test_client.post(f"/week-menu/tuesday/recipe/{recipe.id}")

    response = await test_client.get("/week-menu/grocery-list/export")

    assert response.status_code == 200

    assert response.headers["content-type"].startswith("text/plain")

    assert response.text == "Jumbo\ncarrots - 100 g"


@pytest.mark.asyncio
async def test_week_menu_export_returns_plaintext(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The week menu export endpoint should return day-recipe lines."""

    recipe = await Recipe.create(
        name="Export dinner",
        description="week export",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    await test_client.post(f"/week-menu/friday/recipe/{recipe.id}")

    response = await test_client.get("/week-menu/export")

    assert response.status_code == 200

    assert response.headers["content-type"].startswith("text/plain")

    assert "Friday - Export dinner" in response.text


@pytest.mark.asyncio
async def test_week_menu_page_has_footer_actions(
    test_client: AsyncTestClient,
) -> None:
    """Week menu actions should appear at the bottom with styled buttons."""

    response = await test_client.get("/week-menu")

    assert response.status_code == 200

    assert "week-menu-footer-actions" in response.text

    assert "btn-action--grocery" in response.text

    assert "btn-action--export" in response.text
