"""Tests for ingredient categories and category grouping in lists."""

import sqlite3

import pytest
from litestar.testing import AsyncTestClient

from src.category_icons import icon_backfill_sql, suggest_icon

from src.categories import (
    DEFAULT_CATEGORY_KEYS,
    CategoryInfo,
    group_by_category,
    load_categories,
)
from src.ingredient_merge import merge_ingredients
from src.models import Ingredient, IngredientCategory, InventoryItem, Shop, Unit, User


async def _category(user: User, name: str, order: int) -> IngredientCategory:
    """Create a category for a user at a position."""
    return await IngredientCategory.create(owner=user, name=name, sort_order=order)


async def _add_grocery(client: AsyncTestClient, name: str, unit: str = "st") -> None:
    """Add one custom grocery to the list."""
    await client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": name, "quantity": "1", "unit": unit},
    )


async def _ingredient(user: User, name: str) -> Ingredient:
    """Return a user's ingredient by name."""
    return await Ingredient.get(owner_id=user.id, name=name)


async def _names(user: User) -> list[str]:
    """Return the user's category names in order."""
    return [category["name"] for category in await load_categories(user.id)]


# --- Page, seeding, navigation ------------------------------------------------


@pytest.mark.asyncio
async def test_categories_page_is_linked_from_settings_and_home(
    test_client: AsyncTestClient,
) -> None:
    """The page is reachable from the Settings menu and a home tile."""
    home = await test_client.get("/")
    assert 'href="/categories/manage" class="nav-link"' in home.text
    assert 'href="/categories/manage" class="action-card"' in home.text

    page = await test_client.get("/categories/manage")
    assert page.status_code == 200
    assert "Sections" in page.text


@pytest.mark.asyncio
async def test_first_visit_seeds_starter_categories_once(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Starter categories are seeded in order, once, and never come back."""
    await test_client.get("/categories/manage")
    await test_client.get("/categories/manage")

    names = await _names(default_user)
    assert len(names) == len(DEFAULT_CATEGORY_KEYS)
    assert names[0] == "Vegetables"
    assert names[-1] == "Other"

    for category in await IngredientCategory.filter(owner_id=default_user.id):
        await test_client.delete(f"/categories/{category.id}")
    await test_client.get("/categories/manage")
    assert await _names(default_user) == []


@pytest.mark.asyncio
async def test_existing_categories_are_not_mixed_with_starter_set(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A user who already has categories does not get the starter set."""
    await _category(default_user, "Mine", 0)

    await test_client.get("/categories/manage")

    assert await _names(default_user) == ["Mine"]


# --- Managing categories -------------------------------------------------------


@pytest.mark.asyncio
async def test_add_category_appends_and_rejects_duplicates(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """New categories go last; names are unique regardless of case."""
    await _category(default_user, "Vegetables", 0)

    added = await test_client.post("/categories", data={"name": "Bakery"})
    duplicate = await test_client.post("/categories", data={"name": "vegetables"})
    empty = await test_client.post("/categories", data={"name": "  "})

    assert "Section Bakery added." in added.text
    assert "You already have a section called vegetables." in duplicate.text
    assert "A section name is required." in empty.text
    assert await _names(default_user) == ["Vegetables", "Bakery"]


@pytest.mark.asyncio
async def test_rename_category(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Saving a row renames it; a duplicate name is rejected."""
    veg = await _category(default_user, "Veg", 0)
    await _category(default_user, "Fruit", 1)

    saved = await test_client.post(f"/categories/{veg.id}", data={"name": "Greens"})
    clash = await test_client.post(f"/categories/{veg.id}", data={"name": "FRUIT"})

    assert "Section Greens saved." in saved.text
    assert "You already have a section called FRUIT." in clash.text
    assert await _names(default_user) == ["Greens", "Fruit"]


@pytest.mark.asyncio
async def test_drag_order_is_saved(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Dropping a row posts the full new order, which is stored."""
    a = await _category(default_user, "A", 0)
    b = await _category(default_user, "B", 1)
    c = await _category(default_user, "C", 2)

    response = await test_client.post(
        "/categories/order", data={"ids": f"{c.id},{a.id},{b.id}"}
    )

    assert response.status_code == 204
    assert await _names(default_user) == ["C", "A", "B"]


@pytest.mark.asyncio
async def test_drag_order_rejects_stale_or_foreign_ids(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A partial list, or another user's ids, changes nothing (page reloads)."""
    a = await _category(default_user, "A", 0)
    b = await _category(default_user, "B", 1)
    other = await User.create(username="other", email="o@example.com")
    theirs = await _category(other, "X", 0)

    missing = await test_client.post("/categories/order", data={"ids": f"{b.id}"})
    foreign = await test_client.post(
        "/categories/order", data={"ids": f"{b.id},{theirs.id}"}
    )
    junk = await test_client.post("/categories/order", data={"ids": "1,x"})

    assert missing.status_code == 409
    assert foreign.status_code == 409
    assert junk.status_code == 404
    assert await _names(default_user) == ["A", "B"]
    assert a.id != theirs.id


@pytest.mark.asyncio
async def test_page_rows_are_draggable(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Rows carry a drag handle and ids; the drag scripts load versioned."""
    veg = await _category(default_user, "Vegetables", 0)

    page = await test_client.get("/categories/manage")

    assert 'data-sortable-url="/categories/order"' in page.text
    row = page.text.split(f'id="category-{veg.id}"', 1)[1].split("</li>", 1)[0]
    assert f'data-id="{veg.id}"' in page.text
    assert 'class="drag-handle"' in row
    assert "move/up" not in page.text
    assert "/static/vendor/sortablejs/Sortable.min.js?v=" in page.text
    assert "/static/js/sortable-lists.js?v=" in page.text


# --- Icons ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_icons_on_add_and_save(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An icon can be set, is suggested from the name, and must be one emoji."""
    await test_client.post("/categories", data={"name": "Snoep", "icon": "🍬"})
    await test_client.post("/categories", data={"name": "Diepvries", "icon": ""})
    await test_client.post("/categories", data={"name": "Kantoor", "icon": ""})
    too_long = await test_client.post(
        "/categories", data={"name": "Lang", "icon": "x" * 17}
    )

    icons = {
        row.name: row.icon
        for row in await IngredientCategory.filter(owner_id=default_user.id)
    }
    assert icons == {"Snoep": "🍬", "Diepvries": "🧊", "Kantoor": ""}
    assert "Use a single emoji as the icon." in too_long.text

    snoep = await IngredientCategory.get(owner_id=default_user.id, name="Snoep")
    await test_client.post(
        f"/categories/{snoep.id}", data={"name": "Snoep", "icon": ""}
    )
    await snoep.refresh_from_db()
    assert snoep.icon == ""


@pytest.mark.asyncio
async def test_starter_set_gets_icons(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Seeded shelves come with an emoji each."""
    await test_client.get("/categories/manage")

    categories = await load_categories(default_user.id)
    assert categories[0]["icon"] == "🥦"
    assert all(category["icon"] for category in categories)


def test_suggest_icon_matches_dutch_and_english_names() -> None:
    """Keywords match in either language; unknown names get no icon."""
    assert suggest_icon("Groente") == "🥦"
    assert suggest_icon("Vlees & vis") == "🥩"
    assert suggest_icon("Vriezer") == "🧊"
    assert suggest_icon("Herbs & spices") == "🌿"
    assert suggest_icon("Brood") == "🍞"
    assert suggest_icon("Sauzen") == "🫙"
    assert suggest_icon("Condiments") == "🫙"
    assert suggest_icon("Kantoor") == ""


def test_icon_backfill_only_fills_empty_icons() -> None:
    """The one-time fill sets suggested icons and keeps chosen ones."""
    connection = sqlite3.connect(":memory:")
    connection.execute('CREATE TABLE "ingredientcategory" ("name" TEXT, "icon" TEXT)')
    connection.executemany(
        'INSERT INTO "ingredientcategory" VALUES (?, ?)',
        [("Groente", ""), ("Vriezer", ""), ("Kantoor", ""), ("Fruit", "🍓")],
    )

    connection.executescript(icon_backfill_sql())

    rows = dict(connection.execute('SELECT "name", "icon" FROM "ingredientcategory"'))
    assert rows == {"Groente": "🥦", "Vriezer": "🧊", "Kantoor": "", "Fruit": "🍓"}


@pytest.mark.asyncio
async def test_assignment_chips_show_icons_or_letters(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Each ingredient gets one chip per shelf; the current one is active."""
    veg = await IngredientCategory.create(
        owner=default_user, name="Vegetables", icon="🥦", sort_order=0
    )
    await _category(default_user, "Kantoor", 1)
    carrot = await Ingredient.create(owner=default_user, name="carrot", category=veg)

    page = await test_client.get("/categories/manage")
    assignments = page.text.split('id="category-assignments"', 1)[1]
    row = assignments.split("carrot", 1)[1].split("</li>", 1)[0]

    assert "🥦 Vegetables (1)" in assignments
    assert 'aria-label="Vegetables"' in row
    assert ">🥦</button>" in row
    assert ">K</button>" in row
    active = row.split("shop-chip-btn--active", 1)[1].split("</button>", 1)[0]
    assert "🥦" in active
    assert f"/categories/ingredient/{carrot.id}" in row
    assert "<select" not in assignments


@pytest.mark.asyncio
async def test_grocery_headings_show_shelf_icon(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Grocery list headings start with the shelf's emoji."""
    veg = await IngredientCategory.create(
        owner=default_user, name="Vegetables", icon="🥦", sort_order=0
    )
    await _add_grocery(test_client, "carrot")
    await Ingredient.filter(owner_id=default_user.id, name="carrot").update(
        category_id=veg.id
    )
    carrot = await _ingredient(default_user, "carrot")
    await test_client.post(
        "/week-menu/grocery-list/to-check",
        data={"ingredient_id": str(carrot.id), "unit": "st"},
    )

    page = await test_client.get("/week-menu/grocery-list")

    assert '<h4 class="category-heading">🥦 Vegetables</h4>' in page.text


@pytest.mark.asyncio
async def test_delete_category_uncategorises_its_ingredients(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Deleting a category keeps its ingredients, without a category."""
    veg = await _category(default_user, "Vegetables", 0)
    carrot = await Ingredient.create(owner=default_user, name="carrot", category=veg)

    page = await test_client.get("/categories/manage")
    row = page.text.split(f'id="category-{veg.id}"', 1)[1].split("</li>", 1)[0]
    assert "inline-confirm-trigger" in row

    response = await test_client.delete(f"/categories/{veg.id}")

    assert "Section deleted." in response.text
    await carrot.refresh_from_db()
    assert carrot.category_id is None


@pytest.mark.asyncio
async def test_categories_are_private_per_user(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Another user's categories cannot be seen, renamed, used or deleted."""
    other = await User.create(username="other", email="o@example.com")
    theirs = await _category(other, "Secret", 0)
    mine = await Ingredient.create(owner=default_user, name="salt")

    page = await test_client.get("/categories/manage")
    rename = await test_client.post(f"/categories/{theirs.id}", data={"name": "X"})
    assign = await test_client.post(
        f"/categories/ingredient/{mine.id}", data={"category_id": str(theirs.id)}
    )
    delete = await test_client.delete(f"/categories/{theirs.id}")

    assert "Secret" not in page.text
    assert "Section not found." in rename.text
    assert assign.status_code == 404
    assert delete.status_code == 404
    await theirs.refresh_from_db()
    assert theirs.name == "Secret"


# --- Assigning ingredients -------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_ingredient_category_and_clear_it(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Picking a category saves at once and moves the row to that group."""
    veg = await _category(default_user, "Vegetables", 0)
    carrot = await Ingredient.create(owner=default_user, name="carrot")

    response = await test_client.post(
        f"/categories/ingredient/{carrot.id}",
        data={"category_id": str(veg.id)},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text.lstrip().startswith('<section id="category-assignments"')
    await carrot.refresh_from_db()
    assert carrot.category_id == veg.id
    vegetables_group = response.text.split("Vegetables (1)", 1)[1]
    assert "carrot" in vegetables_group

    await test_client.post(
        f"/categories/ingredient/{carrot.id}", data={"category_id": ""}
    )
    await carrot.refresh_from_db()
    assert carrot.category_id is None


@pytest.mark.asyncio
async def test_uncategorised_ingredients_are_listed_first(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The assignments list starts with what still needs a category."""
    veg = await _category(default_user, "Vegetables", 0)
    await Ingredient.create(owner=default_user, name="carrot", category=veg)
    await Ingredient.create(owner=default_user, name="salt")

    page = await test_client.get("/categories/manage")
    assignments = page.text.split('id="category-assignments"', 1)[1]

    assert assignments.index("No section (1)") < assignments.index("Vegetables (1)")
    assert assignments.index("salt") < assignments.index("carrot")


# --- Grouping --------------------------------------------------------------------


def _info(category_id: int, name: str) -> CategoryInfo:
    """Build a category record for the pure grouping function."""
    return CategoryInfo(
        id=category_id,
        name=name,
        icon="",
        badge=name[0],
        sort_order=0,
        ingredient_count=0,
    )


def test_group_by_category_orders_sections_and_puts_uncategorised_last() -> None:
    """Sections follow the category order; items without one come last."""
    items = [
        {"ingredient_id": 1, "name": "salt"},
        {"ingredient_id": 2, "name": "carrot"},
        {"ingredient_id": 3, "name": "peas"},
        {"ingredient_id": 4, "name": "leek"},
    ]
    categories = [_info(10, "Vegetables"), _info(20, "Freezer")]

    sections = group_by_category(
        items, {2: 10, 3: 20, 4: 10}, categories, uncategorised_label="Other"
    )

    assert [section["name"] for section in sections] == [
        "Vegetables",
        "Freezer",
        "Other",
    ]
    assert [item["name"] for item in sections[0]["entries"]] == ["carrot", "leek"]
    assert [item["name"] for item in sections[2]["entries"]] == ["salt"]


def test_group_by_category_is_flat_when_nothing_is_categorised() -> None:
    """No categorised items means no headings, unless asked for."""
    items = [{"ingredient_id": 1, "name": "salt"}]
    categories = [_info(10, "Vegetables")]

    assert group_by_category(items, {}, categories, uncategorised_label="X") == []
    forced = group_by_category(
        items, {}, categories, uncategorised_label="X", always=True
    )
    assert [section["name"] for section in forced] == ["X"]


@pytest.mark.asyncio
async def test_grocery_shop_section_and_to_check_are_grouped(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Shop sections and 'to check' show category headings in order."""
    veg = await _category(default_user, "Vegetables", 0)
    freezer = await _category(default_user, "Freezer", 1)
    shop = await Shop.create(owner=default_user, name="Market")
    for name in ("peas", "carrot", "salt"):
        await _add_grocery(test_client, name)
    await Ingredient.filter(owner_id=default_user.id, name="carrot").update(
        category_id=veg.id
    )
    await Ingredient.filter(owner_id=default_user.id, name="peas").update(
        category_id=freezer.id
    )
    for name in ("peas", "carrot", "salt"):
        ingredient = await _ingredient(default_user, name)
        await test_client.post(
            "/week-menu/grocery-list/assign",
            data={
                "ingredient_id": str(ingredient.id),
                "unit": "st",
                "shop_id": str(shop.id),
            },
        )

    page = await test_client.get("/week-menu/grocery-list")
    shop_html = page.text.split('class="grocery-shop-group"', 1)[1]

    vegetables = shop_html.index('<h4 class="category-heading">Vegetables</h4>')
    frozen = shop_html.index('<h4 class="category-heading">Freezer</h4>')
    other = shop_html.index('<h4 class="category-heading">No section</h4>')
    assert vegetables < shop_html.index(">carrot<") < frozen
    assert frozen < shop_html.index(">peas<") < other < shop_html.index(">salt<")

    carrot = await _ingredient(default_user, "carrot")
    await test_client.post(
        "/week-menu/grocery-list/to-check",
        data={"ingredient_id": str(carrot.id), "unit": "st"},
    )
    page = await test_client.get("/week-menu/grocery-list")
    to_check = page.text.split("grocery-list--to-check", 1)[0].rsplit(
        '<div class="subheader">', 1
    )[1]
    assert '<h4 class="category-heading">Vegetables</h4>' in to_check


@pytest.mark.asyncio
async def test_grocery_list_stays_flat_without_categories(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Users who never categorise see the list exactly as before."""
    await _category(default_user, "Vegetables", 0)
    await _add_grocery(test_client, "salt")

    page = await test_client.get("/week-menu/grocery-list")

    assert "category-heading" not in page.text


@pytest.mark.asyncio
async def test_inventory_category_sort_shows_headings(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Sorting inventory by category groups rows under headings in order."""
    veg = await _category(default_user, "Vegetables", 0)
    grams = await Unit.get(owner_id=default_user.id, abbrev="g")
    for name, category in (("salt", None), ("leek", veg), ("carrot", veg)):
        ingredient = await Ingredient.create(
            owner=default_user, name=name, category=category
        )
        await InventoryItem.create(
            owner=default_user, ingredient=ingredient, unit=grams, quantity=1
        )

    page = await test_client.get("/inventory?sort=category")
    plain = await test_client.get("/inventory?sort=name")

    assert '<option value="category" selected>' in page.text
    vegetables = page.text.index('<h3 class="category-heading">Vegetables</h3>')
    other = page.text.index('<h3 class="category-heading">No section</h3>')
    carrot = page.text.index('value="carrot"')
    leek = page.text.index('value="leek"')
    salt = page.text.index('value="salt"')
    assert vegetables < carrot < leek < other < salt
    assert "category-heading" not in plain.text


@pytest.mark.asyncio
async def test_merging_ingredients_keeps_or_inherits_category(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The target keeps its category, and inherits the source's if it has none."""
    veg = await _category(default_user, "Vegetables", 0)
    fruit = await _category(default_user, "Fruit", 1)
    source = await Ingredient.create(owner=default_user, name="tomatos", category=veg)
    target = await Ingredient.create(owner=default_user, name="tomatoes")
    await merge_ingredients(default_user.id, source.id, target.id)
    await target.refresh_from_db()
    assert target.category_id == veg.id

    source = await Ingredient.create(owner=default_user, name="apple", category=veg)
    target = await Ingredient.create(owner=default_user, name="apples", category=fruit)
    await merge_ingredients(default_user.id, source.id, target.id)
    await target.refresh_from_db()
    assert target.category_id == fruit.id
