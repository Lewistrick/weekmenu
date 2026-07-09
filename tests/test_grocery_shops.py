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
from src.week_menu import (
    GroceryItem,
    load_grocery_list,
    mark_already_have,
    save_grocery_list,
    unmark_already_have,
    update_grocery_line,
)


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
    assert "grocery-item-row" in response.text or "grocery-item-name" in response.text
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
    assert "shop-chip-btn--check" in response.text
    assert ">carrots</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_allows_reassignment_from_page(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The grocery list should allow changing shop assignments from any section."""
    first_shop = await Shop.create(owner=default_user, name="Jumbo")
    second_shop = await Shop.create(owner=default_user, name="Lidl")
    ingredient = await Ingredient.create(owner=default_user, name="milk")
    recipe = await Recipe.create(
        name="Milk dish",
        description="reassign test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    liters = await Unit.filter(owner_id=default_user.id, abbrev="l").first()
    assert liters is not None
    await RecipeIngredient.create(
        recipe=recipe, ingredient=ingredient, quantity=1, unit=liters
    )
    await set_ingredient_shop(default_user.id, ingredient.id, first_shop.id)
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": ingredient.id, "shop_id": second_shop.id},
    )

    assert response.status_code == 200
    ingredient_shop_ids = await load_ingredient_shop_ids(default_user.id)
    assert ingredient_shop_ids.get(ingredient.id) == second_shop.id


@pytest.mark.asyncio
async def test_grocery_list_preserves_existing_plan(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A second visit should keep the stored grocery list and show a notice."""
    recipe = await Recipe.create(
        name="Persist stew",
        description="persist test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    pasta = await Ingredient.create(owner=default_user, name="pasta")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=pasta, quantity=300, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")

    first = await test_client.get("/week-menu/grocery-list")
    assert first.status_code == 200

    await test_client.post("/week-menu/monday/clear")

    second = await test_client.get("/week-menu/grocery-list")
    assert second.status_code == 200
    assert "grocery-notice" in second.text
    assert "pasta" in second.text


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
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": rice.id},
    )

    assert response.status_code == 200
    assert "Already have" in response.text
    assert response.text.index("Already have") < response.text.rindex("rice")


@pytest.mark.asyncio
async def test_grocery_list_can_remove_already_have_item(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Removing an already-have mark should return the ingredient to sorting."""
    recipe = await Recipe.create(
        name="Toggle stew",
        description="toggle test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    beans = await Ingredient.create(owner=default_user, name="beans")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=beans, quantity=400, unit=grams
    )
    await test_client.post(f"/week-menu/thursday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": beans.id},
    )

    response = await test_client.post(
        "/week-menu/grocery-list/already-have/remove",
        data={"ingredient_id": beans.id},
    )

    assert response.status_code == 200
    assert "To sort" in response.text
    assert ">beans</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_can_edit_amount(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Grocery amounts should be editable and persisted in the session list."""
    recipe = await Recipe.create(
        name="Edit stew",
        description="edit amount test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    sugar = await Ingredient.create(owner=default_user, name="sugar")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=sugar, quantity=50, unit=grams
    )
    await test_client.post(f"/week-menu/friday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        f"/week-menu/grocery-list/item/{sugar.id}/g",
        data={"quantity": "75", "unit": "g"},
    )

    assert response.status_code == 200
    assert "75 g" in response.text


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
    await test_client.get("/week-menu/grocery-list")

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
async def test_week_menu_page_has_footer_grocery_action(
    test_client: AsyncTestClient,
) -> None:
    """Week menu should link to the grocery list from the footer."""
    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert "week-menu-footer-actions" in response.text
    assert "btn-action--grocery" in response.text
    assert "btn-action--export" not in response.text


@pytest.mark.asyncio
async def test_home_page_links_to_grocery_list(test_client: AsyncTestClient) -> None:
    """The home page should include a grocery list shortcut."""
    response = await test_client.get("/")

    assert response.status_code == 200
    assert "/week-menu/grocery-list" in response.text
    assert "Grocery list" in response.text


@pytest.mark.asyncio
async def test_grocery_list_page_has_two_copy_sections(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Grocery and week menu copy areas should appear in separate sections."""
    recipe = await Recipe.create(
        name="Copy stew",
        description="copy sections",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    herbs = await Ingredient.create(owner=default_user, name="herbs")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=herbs, quantity=10, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert response.text.count("Copy for messaging") == 2
    assert "grocery-copy-text" in response.text
    assert "week-menu-copy-text" in response.text
    assert "Copy stew" in response.text


@pytest.mark.asyncio
async def test_grocery_list_mark_all_shop_already_have(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A shop should be able to mark all of its ingredients as already owned."""
    shop = await Shop.create(owner=default_user, name="Bulk shop")
    recipe = await Recipe.create(
        name="Bulk stew",
        description="bulk already-have",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    pepper = await Ingredient.create(owner=default_user, name="pepper")
    await set_ingredient_shop(default_user.id, pepper.id, shop.id)
    await RecipeIngredient.create(
        recipe=recipe, ingredient=pepper, quantity=5, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        f"/week-menu/grocery-list/shop/{shop.id}/already-have"
    )

    assert response.status_code == 200
    assert "Already have" in response.text
    assert ">pepper</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_can_clear_already_have(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The already-have list can be emptied in one action."""
    recipe = await Recipe.create(
        name="Clear stew",
        description="clear already-have",
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
    await test_client.post(f"/week-menu/tuesday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": salt.id},
    )

    response = await test_client.post("/week-menu/grocery-list/already-have/clear")

    assert response.status_code == 200
    assert "To sort" in response.text
    assert ">salt</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_merges_duplicate_unit_lines(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Changing a line's unit should merge with an existing same-unit line."""
    recipe_a = await Recipe.create(
        name="Merge stew A",
        description="merge test a",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Merge stew B",
        description="merge test b",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    kg = await Unit.filter(owner_id=default_user.id, abbrev="kg").first()
    assert grams is not None
    assert kg is not None
    flour = await Ingredient.create(owner=default_user, name="flour")
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=flour, quantity=500, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=flour, quantity=1, unit=kg
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe_a.id}")
    await test_client.post(f"/week-menu/tuesday/recipe/{recipe_b.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        f"/week-menu/grocery-list/item/{flour.id}/g",
        data={"quantity": "100", "unit": "kg"},
    )

    assert response.status_code == 200
    assert "Combined with existing flour (kg)." in response.text
    assert "101 kg" in response.text


def test_update_grocery_line_merges_matching_unit() -> None:
    """Unit changes should combine quantities for the same ingredient-unit pair."""

    class Session(dict):
        pass

    class RequestStub:
        def __init__(self) -> None:
            self.session = Session({"user_id": 1})

    request = RequestStub()
    save_grocery_list(
        request,  # type: ignore[arg-type]
        [
            GroceryItem(ingredient_id=4, name="flour", unit="g", quantity=500.0),
            GroceryItem(ingredient_id=4, name="flour", unit="kg", quantity=1.0),
        ],
    )

    success, message = update_grocery_line(
        request,  # type: ignore[arg-type]
        4,
        "g",
        quantity=100.0,
        unit="kg",
    )

    assert success is True
    assert message == "Combined with existing flour (kg)."
    loaded = load_grocery_list(request)  # type: ignore[arg-type]
    assert len(loaded) == 1
    assert loaded[0]["unit"] == "kg"
    assert loaded[0]["quantity"] == 101.0


def test_save_and_load_grocery_list_round_trip() -> None:
    """Session grocery list helpers should round-trip item data."""

    class Session(dict):
        pass

    class RequestStub:
        def __init__(self) -> None:
            self.session = Session({"user_id": 1})

    request = RequestStub()
    items = [GroceryItem(ingredient_id=3, name="flour", unit="g", quantity=250.0)]
    save_grocery_list(request, items)  # type: ignore[arg-type]
    loaded = load_grocery_list(request)  # type: ignore[arg-type]
    assert loaded == items
    mark_already_have(request, 3)  # type: ignore[arg-type]
    unmark_already_have(request, 3)  # type: ignore[arg-type]
