"""Tests for grocery grouping by shop and plaintext export."""

import pytest
from litestar.testing import AsyncTestClient

from src.grocery import (
    format_grocery_export,
    format_week_menu_export,
    split_grocery_lists,
)
from src.models import Ingredient, Recipe, RecipeIngredient, Shop, Unit, User
from src.plan_store import (
    empty_already_have_list,
    empty_to_check_list,
    load_grocery_list,
    mark_already_have_line,
    mark_to_check_line,
    save_grocery_list,
    unmark_already_have_line,
    update_grocery_line,
)
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
    unassigned, to_check, already_have, groups = split_grocery_lists(
        items,
        ingredient_shop_ids={1: 10},
        shops=shops,
        already_have_line_keys=set(),
        to_check_line_keys=set(),
        line_shop_ids={},
    )

    assert [item["name"] for item in unassigned] == ["onion"]
    assert to_check == []
    assert already_have == []
    assert [group["shop_name"] for group in groups] == ["Albert Heijn"]
    assert groups[0]["entries"][0]["name"] == "potatoes"


def test_split_grocery_lists_moves_items_to_already_have() -> None:
    """Marked grocery lines should leave the unassigned and shop lists."""
    items = [
        GroceryItem(ingredient_id=1, name="salt", unit="g", quantity=5.0),
        GroceryItem(ingredient_id=2, name="pepper", unit="g", quantity=3.0),
    ]
    unassigned, to_check, already_have, groups = split_grocery_lists(
        items,
        ingredient_shop_ids={},
        shops=[],
        already_have_line_keys={"1-g"},
        to_check_line_keys=set(),
        line_shop_ids={},
    )

    assert [item["name"] for item in unassigned] == ["pepper"]
    assert to_check == []
    assert [item["name"] for item in already_have] == ["salt"]
    assert groups == []


def test_split_grocery_lists_moves_items_to_to_check() -> None:
    """To-check lines should appear in the to-check bucket only."""
    items = [
        GroceryItem(ingredient_id=1, name="salt", unit="g", quantity=5.0),
        GroceryItem(ingredient_id=1, name="salt", unit="kg", quantity=1.0),
    ]
    unassigned, to_check, already_have, groups = split_grocery_lists(
        items,
        ingredient_shop_ids={},
        shops=[],
        already_have_line_keys=set(),
        to_check_line_keys={"1-g"},
        line_shop_ids={},
    )

    assert [item["unit"] for item in unassigned] == ["kg"]
    assert [item["unit"] for item in to_check] == ["g"]
    assert already_have == []
    assert groups == []


def test_format_grocery_export_uses_plaintext_lines_per_shop() -> None:
    """Grocery export should render shop sections with ingredient lines."""
    text = format_grocery_export(
        [GroceryItem(ingredient_id=2, name="onion", unit="st", quantity=3.0)],
        [],
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
        """Minimal recipe-like object for export formatting tests."""

        def __init__(self, name: str) -> None:
            """Store a recipe name for export output."""
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
    assert "shop-chip-btn--question" in response.text
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
        data={
            "ingredient_id": ingredient.id,
            "unit": "l",
            "shop_id": second_shop.id,
        },
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
        data={"ingredient_id": rice.id, "unit": "g"},
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
        data={"ingredient_id": beans.id, "unit": "g"},
    )

    response = await test_client.post(
        "/week-menu/grocery-list/already-have/remove",
        data={"ingredient_id": beans.id, "unit": "g"},
    )

    assert response.status_code == 200
    assert "To sort" in response.text
    assert ">beans</span>" in response.text


@pytest.mark.asyncio
async def test_grocery_list_can_edit_amount(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Grocery amounts should be editable and persisted in the grocery list."""
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
async def test_week_menu_page_has_generate_grocery_action(
    test_client: AsyncTestClient,
) -> None:
    """Week menu should offer grocery list generation from the footer."""
    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert "week-menu-footer-actions" in response.text
    assert "btn-action--grocery" in response.text
    assert "Generate grocery list" in response.text
    assert "grocery-generate-form" in response.text


@pytest.mark.asyncio
async def test_generate_grocery_list_keeps_user_logged_in(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Generating a grocery list should keep the user logged in and land on the list page."""
    recipe = await Recipe.create(
        name="Login stew",
        description="login test",
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
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")

    response = await test_client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": "replace"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Log in to plan your week" not in response.text
    assert ">salt</span>" in response.text
    week_menu = await test_client.get("/week-menu")
    assert week_menu.status_code == 200
    assert "Log in to plan your week" not in week_menu.text


@pytest.mark.asyncio
async def test_grocery_list_hydrates_persisted_ingredient_names(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Persisted grocery items should hydrate ingredient names when rendering."""
    recipe = await Recipe.create(
        name="Compact stew",
        description="hydrate names test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    pepper = await Ingredient.create(owner=default_user, name="pepper")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=pepper, quantity=3, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": "replace"},
        follow_redirects=True,
    )

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert ">pepper</span>" in response.text


@pytest.mark.asyncio
async def test_generate_grocery_list_from_empty_week_menu(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An empty grocery list should be created from the week menu in one step."""
    recipe = await Recipe.create(
        name="Generate stew",
        description="generate from week menu",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    lentils = await Ingredient.create(owner=default_user, name="lentils")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=lentils, quantity=300, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")

    response = await test_client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": "replace"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307}
    assert response.headers["location"].endswith("/week-menu/grocery-list")

    page = await test_client.get("/week-menu/grocery-list")
    assert page.status_code == 200
    assert ">lentils</span>" in page.text
    assert "Your grocery list is preserved" not in page.text


@pytest.mark.asyncio
async def test_generate_grocery_list_replace_existing(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Replacing should rebuild the grocery list from the current week menu."""
    recipe = await Recipe.create(
        name="Replace stew",
        description="replace groceries",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    onion = await Ingredient.create(owner=default_user, name="onion")
    garlic = await Ingredient.create(owner=default_user, name="garlic")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=onion, quantity=100, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=garlic, quantity=50, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": onion.id, "unit": "g"},
    )

    response = await test_client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": "replace"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307}
    page = await test_client.get("/week-menu/grocery-list")
    assert page.status_code == 200
    assert ">onion</span>" in page.text
    assert ">garlic</span>" in page.text


@pytest.mark.asyncio
async def test_generate_grocery_list_merge_existing(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merging should add new week menu groceries to the current list."""
    recipe_a = await Recipe.create(
        name="Merge generate A",
        description="merge generate a",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Merge generate B",
        description="merge generate b",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    rice = await Ingredient.create(owner=default_user, name="rice")
    beans = await Ingredient.create(owner=default_user, name="beans")
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=rice, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=beans, quantity=150, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe_a.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(f"/week-menu/tuesday/recipe/{recipe_b.id}")

    response = await test_client.post(
        "/week-menu/grocery-list/generate",
        data={"mode": "merge"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307}
    page = await test_client.get("/week-menu/grocery-list")
    assert page.status_code == 200
    assert ">rice</span>" in page.text
    assert ">beans</span>" in page.text


@pytest.mark.asyncio
async def test_empty_initialized_grocery_list_regenerates_on_visit(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An initialized but empty grocery list should rebuild without a preserve notice."""
    recipe = await Recipe.create(
        name="Empty revisit stew",
        description="empty revisit",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    thyme = await Ingredient.create(owner=default_user, name="thyme")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=thyme, quantity=5, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": thyme.id, "unit": "g"},
    )
    await test_client.post("/week-menu/grocery-list/already-have/clear")

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert ">thyme</span>" not in response.text
    assert "Your grocery list is preserved" not in response.text
    assert "No ingredients yet" in response.text


@pytest.mark.asyncio
async def test_week_menu_shows_generate_choices_when_list_exists(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A non-empty grocery list should show inline update choices on the week menu."""
    recipe = await Recipe.create(
        name="Choices stew",
        description="choices ui",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    oats = await Ingredient.create(owner=default_user, name="oats")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=oats, quantity=80, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert "grocery-generate-choices" in response.text
    assert "Update grocery list?" in response.text
    assert "grocery-generate-form" not in response.text


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
    assert response.text.count(">pepper</span>") == 1
    shop_section = response.text.split("By shop", 1)[1].split("Copy for messaging", 1)[
        0
    ]
    assert ">pepper</span>" not in shop_section


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
        data={"ingredient_id": salt.id, "unit": "g"},
    )

    response = await test_client.post("/week-menu/grocery-list/already-have/clear")

    assert response.status_code == 200
    assert ">salt</span>" not in response.text


@pytest.mark.asyncio
async def test_grocery_list_assign_from_already_have_moves_to_shop(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Assigning a shop to an already-have item should move it out of that list."""
    shop = await Shop.create(owner=default_user, name="Corner store")
    recipe = await Recipe.create(
        name="Move stew",
        description="already-have assign",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    butter = await Ingredient.create(owner=default_user, name="butter")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=butter, quantity=50, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": butter.id, "unit": "g"},
    )

    response = await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": butter.id, "unit": "g", "shop_id": shop.id},
    )

    assert response.status_code == 200
    assert "Corner store" in response.text
    already_have_section = response.text.split("Already have", 1)[1].split(
        "By shop", 1
    )[0]
    assert ">butter</span>" not in already_have_section


@pytest.mark.asyncio
async def test_grocery_list_htmx_assign_returns_partial(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """HTMX shop assignment should return only the grocery list panel."""
    shop = await Shop.create(owner=default_user, name="HTMX shop")
    recipe = await Recipe.create(
        name="HTMX stew",
        description="htmx partial",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    oats = await Ingredient.create(owner=default_user, name="oats")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=oats, quantity=80, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": oats.id, "unit": "g", "shop_id": shop.id},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'id="grocery-list-panel"' in response.text
    assert "HTMX shop" in response.text
    assert "<!DOCTYPE html>" not in response.text


@pytest.mark.asyncio
async def test_grocery_list_assign_only_moves_clicked_unit_line(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Assigning a shop should affect only the clicked unit line."""
    shop = await Shop.create(owner=default_user, name="Unit shop")
    recipe_a = await Recipe.create(
        name="Unit stew A",
        description="unit assign a",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Unit stew B",
        description="unit assign b",
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
    sugar = await Ingredient.create(owner=default_user, name="sugar")
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=sugar, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=sugar, quantity=1, unit=kg
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe_a.id}")
    await test_client.post(f"/week-menu/tuesday/recipe/{recipe_b.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        "/week-menu/grocery-list/assign",
        data={"ingredient_id": sugar.id, "unit": "g", "shop_id": shop.id},
    )

    assert response.status_code == 200
    to_sort_section = response.text.split("To sort", 1)[1].split("To check", 1)[0]
    assert ">sugar</span>" in to_sort_section
    assert "1 kg" in to_sort_section or ">1</" in to_sort_section
    shop_section = response.text.split("By shop", 1)[1].split("Copy for messaging", 1)[
        0
    ]
    assert "200 g" in shop_section or ">200</" in shop_section
    assert response.text.count(">sugar</span>") == 2


@pytest.mark.asyncio
async def test_grocery_list_to_check_moves_item(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Marking a grocery line to check should move it below the to-sort list."""
    recipe = await Recipe.create(
        name="Check stew",
        description="to-check test",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    vinegar = await Ingredient.create(owner=default_user, name="vinegar")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=vinegar, quantity=50, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        "/week-menu/grocery-list/to-check",
        data={"ingredient_id": vinegar.id, "unit": "g"},
    )

    assert response.status_code == 200
    assert "To check" in response.text
    assert response.text.index("To check") < response.text.rindex("vinegar")
    assert "shop-chip-btn--question" in response.text


@pytest.mark.asyncio
async def test_grocery_list_can_clear_to_check(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Clearing to-check should remove those groceries from the plan entirely."""
    recipe = await Recipe.create(
        name="Clear check stew",
        description="clear to-check",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    honey = await Ingredient.create(owner=default_user, name="honey")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=honey, quantity=30, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/to-check",
        data={"ingredient_id": honey.id, "unit": "g"},
    )

    response = await test_client.post("/week-menu/grocery-list/to-check/clear")

    assert response.status_code == 200
    assert ">honey</span>" not in response.text


@pytest.mark.asyncio
async def test_grocery_list_empty_confirm_starts_hidden(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The empty-list confirmation should stay hidden until triggered."""
    recipe = await Recipe.create(
        name="Confirm stew",
        description="confirm ui",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    cumin = await Ingredient.create(owner=default_user, name="cumin")
    await RecipeIngredient.create(
        recipe=recipe, ingredient=cumin, quantity=5, unit=grams
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe.id}")
    await test_client.get("/week-menu/grocery-list")
    await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": cumin.id, "unit": "g"},
    )

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert "clear-already-have-confirm" in response.text
    assert "clear-already-have-trigger" in response.text
    assert "grocery-clear-list-trigger" in response.text
    assert "grocery-inline-confirm-wrap" in response.text


@pytest.mark.asyncio
async def test_grocery_list_merge_message_uses_dismissable_banner(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Merge notices should use the standard dismissable flash banner."""
    recipe_a = await Recipe.create(
        name="Banner stew A",
        description="banner test a",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    recipe_b = await Recipe.create(
        name="Banner stew B",
        description="banner test b",
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
    sugar = await Ingredient.create(owner=default_user, name="sugar")
    await RecipeIngredient.create(
        recipe=recipe_a, ingredient=sugar, quantity=200, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe_b, ingredient=sugar, quantity=1, unit=kg
    )
    await test_client.post(f"/week-menu/monday/recipe/{recipe_a.id}")
    await test_client.post(f"/week-menu/tuesday/recipe/{recipe_b.id}")
    await test_client.get("/week-menu/grocery-list")

    response = await test_client.post(
        f"/week-menu/grocery-list/item/{sugar.id}/g",
        data={"quantity": "100", "unit": "kg"},
    )

    assert response.status_code == 200
    assert "flash-banner single-message" in response.text
    assert "Combined with existing sugar (kg)." in response.text
    assert 'hx-trigger="load delay:5s"' in response.text


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
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Refresh") == "true"


@pytest.mark.asyncio
async def test_update_grocery_line_merges_matching_unit(default_user: User) -> None:
    """Unit changes should combine quantities for the same ingredient-unit pair."""
    flour = await Ingredient.create(owner=default_user, name="flour")
    await save_grocery_list(
        default_user.id,
        [
            GroceryItem(ingredient_id=flour.id, name="flour", unit="g", quantity=500.0),
            GroceryItem(ingredient_id=flour.id, name="flour", unit="kg", quantity=1.0),
        ],
    )

    success, message = await update_grocery_line(
        default_user.id,
        flour.id,
        "g",
        quantity=100.0,
        unit="kg",
        items=[
            GroceryItem(ingredient_id=flour.id, name="flour", unit="g", quantity=500.0),
            GroceryItem(ingredient_id=flour.id, name="flour", unit="kg", quantity=1.0),
        ],
    )

    assert success is True
    assert message == "Combined with existing flour (kg)."
    loaded = await load_grocery_list(default_user.id)
    assert len(loaded) == 1
    assert loaded[0]["unit"] == "kg"
    assert loaded[0]["quantity"] == 101.0


@pytest.mark.asyncio
async def test_empty_to_check_list_removes_items(default_user: User) -> None:
    """Clearing to-check should delete those groceries from the plan."""
    salt = await Ingredient.create(owner=default_user, name="salt")
    rice = await Ingredient.create(owner=default_user, name="rice")
    await save_grocery_list(
        default_user.id,
        [
            GroceryItem(ingredient_id=salt.id, name="salt", unit="g", quantity=5.0),
            GroceryItem(ingredient_id=rice.id, name="rice", unit="g", quantity=200.0),
        ],
    )
    await mark_to_check_line(default_user.id, salt.id, "g")

    await empty_to_check_list(default_user.id)

    loaded = await load_grocery_list(default_user.id)
    assert loaded == [
        GroceryItem(ingredient_id=rice.id, name="rice", unit="g", quantity=200.0)
    ]


@pytest.mark.asyncio
async def test_empty_already_have_list_removes_items(default_user: User) -> None:
    """Emptying already-have should delete those groceries from the plan."""
    salt = await Ingredient.create(owner=default_user, name="salt")
    rice = await Ingredient.create(owner=default_user, name="rice")
    await save_grocery_list(
        default_user.id,
        [
            GroceryItem(ingredient_id=salt.id, name="salt", unit="g", quantity=5.0),
            GroceryItem(ingredient_id=rice.id, name="rice", unit="g", quantity=200.0),
        ],
    )
    await mark_already_have_line(default_user.id, salt.id, "g")

    await empty_already_have_list(default_user.id)

    loaded = await load_grocery_list(default_user.id)
    assert loaded == [
        GroceryItem(ingredient_id=rice.id, name="rice", unit="g", quantity=200.0)
    ]


@pytest.mark.asyncio
async def test_save_and_load_grocery_list_round_trip(default_user: User) -> None:
    """Grocery list helpers should round-trip item data."""
    flour = await Ingredient.create(owner=default_user, name="flour")
    items = [
        GroceryItem(ingredient_id=flour.id, name="flour", unit="g", quantity=250.0)
    ]
    await save_grocery_list(default_user.id, items)
    loaded = await load_grocery_list(default_user.id)
    assert loaded == [
        GroceryItem(ingredient_id=flour.id, name="flour", unit="g", quantity=250.0)
    ]
    await mark_already_have_line(default_user.id, flour.id, "g")
    await unmark_already_have_line(default_user.id, flour.id, "g")


@pytest.mark.asyncio
async def test_grocery_list_prunes_deleted_ingredient(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Grocery lines for deleted ingredients should be removed when the list loads."""
    ingredient = await Ingredient.create(owner=default_user, name="ghost-pepper")
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "ghost-pepper", "quantity": "1", "unit": "st"},
        follow_redirects=True,
    )
    await ingredient.delete()

    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert ">ghost-pepper</span>" not in response.text
    assert f">#{ingredient.id}</span>" not in response.text


@pytest.mark.asyncio
async def test_grocery_list_sorting_persists_in_database(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Sorting actions should update the database-backed grocery list."""
    ingredient = await Ingredient.create(owner=default_user, name="stale-item")
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "stale-item", "quantity": "2", "unit": "st"},
        follow_redirects=True,
    )

    response = await test_client.post(
        "/week-menu/grocery-list/already-have",
        data={"ingredient_id": ingredient.id, "unit": "st"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Already have" in response.text
