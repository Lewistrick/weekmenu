"""Tests for week menu planning."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, User
from src.week_menu import (
    empty_week_menu,
    randomize_week_menu,
    set_day_recipe,
    toggle_pin,
)


@pytest.fixture
async def menu_recipes(
    test_client: AsyncTestClient,
    default_user: User,
) -> list[Recipe]:
    """Create enabled recipes for week menu tests."""
    recipes = []
    for index, name in enumerate(
        ["Alpha stew", "Beta pie", "Gamma soup", "Delta salad"], start=1
    ):
        recipes.append(
            await Recipe.create(
                name=name,
                description=f"Recipe {index}",
                prep_time_minutes=5,
                cook_time_minutes=10,
                servings=2,
                owner=default_user,
                enabled=True,
            )
        )
    await Recipe.create(
        name="Disabled dish",
        description="Not for menus",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=False,
    )
    return recipes


def test_randomize_skips_pinned_days() -> None:
    """Pinned days should keep their recipe when randomizing."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "monday", 1)
    menu = toggle_pin(menu, "monday")

    randomized = randomize_week_menu(menu, [1, 2, 3, 4, 5, 6, 7])

    assert randomized["monday"]["recipe_id"] == 1
    assert randomized["monday"]["pinned"] is True


def test_randomize_fills_unpinned_days() -> None:
    """Unpinned days should receive recipes when randomizing."""
    menu = empty_week_menu()
    randomized = randomize_week_menu(menu, [10, 11, 12, 13, 14, 15, 16, 17])

    assigned = [slot["recipe_id"] for slot in randomized.values()]
    assert all(recipe_id is not None for recipe_id in assigned)
    assert len(set(assigned)) == len(assigned)


@pytest.mark.asyncio
async def test_week_menu_page_loads(test_client: AsyncTestClient) -> None:
    """The week menu page should list all weekdays."""
    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert "Week menu" in response.text
    assert "Monday" in response.text
    assert "Sunday" in response.text
    assert "Randomize week" in response.text
    assert "Start week on" in response.text


@pytest.mark.asyncio
async def test_start_day_reorders_days(test_client: AsyncTestClient) -> None:
    """Selecting a start day should rotate the displayed weekday order."""
    response = await test_client.post(
        "/week-menu/start-day", data={"start_day": "wednesday"}
    )

    assert response.status_code == 200
    assert response.text.index("week-menu-day-wednesday") < response.text.index(
        "week-menu-day-monday"
    )


@pytest.mark.asyncio
async def test_randomize_assigns_enabled_recipes(
    test_client: AsyncTestClient,
    menu_recipes: list[Recipe],
) -> None:
    """Randomizing should fill the week with enabled recipes only."""
    response = await test_client.post("/week-menu/randomize")

    assert response.status_code == 200
    for recipe in menu_recipes:
        assert recipe.name in response.text
    assert "Disabled dish" not in response.text


@pytest.mark.asyncio
async def test_pin_prevents_reroll_on_randomize(
    test_client: AsyncTestClient,
    menu_recipes: list[Recipe],
) -> None:
    """A pinned day should keep its recipe when randomizing again."""
    first = menu_recipes[0]
    await test_client.post(f"/week-menu/monday/recipe/{first.id}")
    await test_client.post("/week-menu/monday/pin")
    await test_client.post("/week-menu/randomize")

    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert first.name in response.text


@pytest.mark.asyncio
async def test_assign_recipe_via_search(
    test_client: AsyncTestClient,
    menu_recipes: list[Recipe],
) -> None:
    """Users should be able to search and assign a recipe to a day."""
    target = menu_recipes[1]
    search_response = await test_client.get(
        "/week-menu/tuesday/search",
        params={"search": "Beta"},
    )
    assign_response = await test_client.post(
        f"/week-menu/tuesday/recipe/{target.id}",
    )

    assert search_response.status_code == 200
    assert target.name in search_response.text
    assert assign_response.status_code == 200
    assert target.name in assign_response.text


@pytest.mark.asyncio
async def test_clear_recipe_from_day(
    test_client: AsyncTestClient,
    menu_recipes: list[Recipe],
) -> None:
    """Clearing a day should remove the assigned recipe."""
    target = menu_recipes[0]
    await test_client.post(f"/week-menu/monday/recipe/{target.id}")

    response = await test_client.post("/week-menu/monday/clear")

    assert response.status_code == 200
    assert "No recipe selected" in response.text
