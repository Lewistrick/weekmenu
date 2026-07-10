"""Tests for custom grocery additions and the weekly groceries feature."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Unit, User, WeeklyGrocery


async def _unit(user: User, abbrev: str) -> Unit:
    """Return a seeded unit for a user, failing loudly when missing."""
    unit = await Unit.filter(owner_id=user.id, abbrev=abbrev).first()
    assert unit is not None
    return unit


# --- Adding custom groceries directly to the grocery list -------------------


@pytest.mark.asyncio
async def test_grocery_list_shows_add_form(test_client: AsyncTestClient) -> None:
    """The grocery list page should offer a form to add your own groceries."""
    response = await test_client.get("/week-menu/grocery-list")

    assert response.status_code == 200
    assert 'hx-post="/week-menu/grocery-list/add"' in response.text
    assert "🧺 Add weekly groceries" in response.text
    assert 'name="ingredient"' in response.text


@pytest.mark.asyncio
async def test_add_custom_grocery_starts_a_list(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding a custom grocery should create and show a grocery list."""
    response = await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "kitchen roll", "quantity": "2", "unit": "st"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert ">kitchen roll</span>" in response.text
    assert "Added kitchen roll to your grocery list." in response.text
    ingredient = await Ingredient.filter(
        owner_id=default_user.id, name="kitchen roll"
    ).first()
    assert ingredient is not None


@pytest.mark.asyncio
async def test_add_custom_grocery_merges_matching_line(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding the same ingredient and unit twice should sum the amounts."""
    await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "milk", "quantity": "1", "unit": "l"},
        follow_redirects=True,
    )
    response = await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "milk", "quantity": "2", "unit": "l"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.text.count(">milk</span>") == 1
    assert "3 l" in response.text


@pytest.mark.asyncio
async def test_add_custom_grocery_rejects_unknown_unit(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An unknown unit should be reported and nothing should be added."""
    response = await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "napkins", "quantity": "3", "unit": "zzz"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Could not find unit: zzz" in response.text
    assert ">napkins</span>" not in response.text


@pytest.mark.asyncio
async def test_add_custom_grocery_rejects_bad_amount(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A non-positive amount should be rejected."""
    response = await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "eggs", "quantity": "0", "unit": "st"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Enter a positive amount." in response.text
    assert ">eggs</span>" not in response.text


# --- Weekly groceries settings page ----------------------------------------


@pytest.mark.asyncio
async def test_weekly_groceries_page_loads(test_client: AsyncTestClient) -> None:
    """The weekly groceries settings page should render."""
    response = await test_client.get("/weekly-groceries/manage")

    assert response.status_code == 200
    assert "Weekly groceries" in response.text
    assert 'action="/weekly-groceries"' in response.text


@pytest.mark.asyncio
async def test_navigation_links_to_weekly_groceries(
    test_client: AsyncTestClient,
) -> None:
    """The navbar and home page should link to weekly groceries."""
    home = await test_client.get("/")
    grocery = await test_client.get("/week-menu/grocery-list")

    assert "/weekly-groceries/manage" in home.text
    assert "/weekly-groceries/manage" in grocery.text


@pytest.mark.asyncio
async def test_create_weekly_grocery_persists(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding a weekly grocery should store it in the database."""
    response = await test_client.post(
        "/weekly-groceries",
        data={"ingredient": "coffee", "quantity": "2", "unit": "st"},
    )

    assert response.status_code == 200
    assert "Weekly grocery added." in response.text
    assert "coffee" in response.text
    rows = await WeeklyGrocery.filter(owner_id=default_user.id).select_related(
        "ingredient", "unit"
    )
    assert len(rows) == 1
    assert rows[0].ingredient.name == "coffee"
    assert rows[0].quantity == 2
    assert rows[0].unit.abbrev == "st"


@pytest.mark.asyncio
async def test_create_weekly_grocery_rejects_duplicate(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The same ingredient and unit should not be added twice."""
    await test_client.post(
        "/weekly-groceries",
        data={"ingredient": "tea", "quantity": "1", "unit": "st"},
    )
    response = await test_client.post(
        "/weekly-groceries",
        data={"ingredient": "tea", "quantity": "5", "unit": "st"},
    )

    assert response.status_code == 200
    assert "That weekly grocery already exists." in response.text
    assert await WeeklyGrocery.filter(owner_id=default_user.id).count() == 1


@pytest.mark.asyncio
async def test_create_weekly_grocery_requires_known_unit(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An unknown unit should be rejected."""
    response = await test_client.post(
        "/weekly-groceries",
        data={"ingredient": "sugar", "quantity": "1", "unit": "zzz"},
    )

    assert response.status_code == 200
    assert "Could not find unit: zzz" in response.text
    assert await WeeklyGrocery.filter(owner_id=default_user.id).count() == 0


@pytest.mark.asyncio
async def test_update_weekly_grocery(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Editing a weekly grocery should update its amount and unit."""
    grams = await _unit(default_user, "g")
    flour = await Ingredient.create(owner=default_user, name="flour")
    row = await WeeklyGrocery.create(
        owner=default_user, ingredient=flour, quantity=500, unit=grams
    )

    response = await test_client.post(
        f"/weekly-groceries/{row.id}",
        data={"ingredient": "flour", "quantity": "1", "unit": "kg"},
    )

    assert response.status_code == 200
    assert "Weekly grocery updated." in response.text
    refreshed = await WeeklyGrocery.get(id=row.id).select_related("unit")
    assert refreshed.quantity == 1
    assert refreshed.unit.abbrev == "kg"


@pytest.mark.asyncio
async def test_delete_weekly_grocery(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Deleting a weekly grocery should remove it from the database."""
    st = await _unit(default_user, "st")
    sponge = await Ingredient.create(owner=default_user, name="sponge")
    row = await WeeklyGrocery.create(
        owner=default_user, ingredient=sponge, quantity=1, unit=st
    )

    response = await test_client.delete(f"/weekly-groceries/{row.id}")

    assert response.status_code == 200
    assert await WeeklyGrocery.filter(id=row.id).exists() is False


@pytest.mark.asyncio
async def test_weekly_grocery_isolated_between_users(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A user should not be able to delete another user's weekly grocery."""
    other = await User.create(username="other_wg")
    grams = await Unit.create(owner=other, abbrev="g")
    ingredient = await Ingredient.create(owner=other, name="secret")
    row = await WeeklyGrocery.create(
        owner=other, ingredient=ingredient, quantity=1, unit=grams
    )

    response = await test_client.delete(f"/weekly-groceries/{row.id}")

    assert response.status_code == 404
    assert await WeeklyGrocery.filter(id=row.id).exists() is True


# --- Adding weekly groceries to the grocery list ----------------------------


@pytest.mark.asyncio
async def test_add_weekly_groceries_to_list(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The add-weekly button should append all weekly groceries to the list."""
    grams = await _unit(default_user, "g")
    st = await _unit(default_user, "st")
    oats = await Ingredient.create(owner=default_user, name="oats")
    apples = await Ingredient.create(owner=default_user, name="apples")
    await WeeklyGrocery.create(
        owner=default_user, ingredient=oats, quantity=500, unit=grams
    )
    await WeeklyGrocery.create(
        owner=default_user, ingredient=apples, quantity=6, unit=st
    )

    response = await test_client.post(
        "/week-menu/grocery-list/add-weekly",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert ">oats</span>" in response.text
    assert ">apples</span>" in response.text
    assert "Added 2 weekly groceries to your grocery list." in response.text


@pytest.mark.asyncio
async def test_add_weekly_groceries_when_none_exist(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Adding weekly groceries with none saved should show a helpful message."""
    response = await test_client.post(
        "/week-menu/grocery-list/add-weekly",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "You have no weekly groceries yet." in response.text


@pytest.mark.asyncio
async def test_add_weekly_groceries_skips_when_all_already_on_list(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Weekly groceries already on the list should not be added again."""
    grams = await _unit(default_user, "g")
    oats = await Ingredient.create(owner=default_user, name="oats")
    await WeeklyGrocery.create(
        owner=default_user, ingredient=oats, quantity=500, unit=grams
    )
    await test_client.post(
        "/week-menu/grocery-list/add-weekly",
        follow_redirects=True,
    )

    response = await test_client.post(
        "/week-menu/grocery-list/add-weekly",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "already on the grocery list" in response.text


@pytest.mark.asyncio
async def test_add_custom_grocery_htmx_returns_partial(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """HTMX grocery adds should update the list body without a full page reload."""
    response = await test_client.post(
        "/week-menu/grocery-list/add",
        data={"ingredient": "bananas", "quantity": "4", "unit": "st"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "<!DOCTYPE html>" not in response.text
    assert 'id="grocery-list-body"' in response.text
    assert ">bananas</span>" in response.text
    assert "Added bananas to your grocery list." in response.text
