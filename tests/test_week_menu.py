"""Tests for week menu planning."""

import random
import re

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, RecipeTag, Tag, TagCategory, User
from src.week_menu import (
    TagConstraintMode,
    TagGroupConstraint,
    assign_recipe_to_unpinned_day,
    empty_week_menu,
    move_day,
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

    randomized, warnings = randomize_week_menu(menu, [1, 2, 3, 4, 5, 6, 7])

    assert warnings == []
    assert randomized["monday"]["recipe_id"] == 1
    assert randomized["monday"]["pinned"] is True


def test_randomize_fills_unpinned_days() -> None:
    """Unpinned days should receive recipes when randomizing."""
    menu = empty_week_menu()
    randomized, warnings = randomize_week_menu(
        menu, [10, 11, 12, 13, 14, 15, 16, 17], rng=random.Random(0)
    )

    assigned = [slot["recipe_id"] for slot in randomized.values()]
    assert warnings == []
    assert all(recipe_id is not None for recipe_id in assigned)
    assert len(set(assigned)) == len(assigned)


def test_move_day_down_swaps_with_next_day() -> None:
    """Moving a day down should swap its whole slot with the next day."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "monday", 1)
    menu = set_day_recipe(menu, "tuesday", 2)

    menu = move_day(menu, "monday", "down")

    assert menu["monday"]["recipe_id"] == 2
    assert menu["tuesday"]["recipe_id"] == 1


def test_move_day_up_swaps_with_previous_day() -> None:
    """Moving a day up should swap its whole slot with the previous day."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "monday", 1)
    menu = set_day_recipe(menu, "tuesday", 2)
    menu["tuesday"]["servings"] = 6

    menu = move_day(menu, "tuesday", "up")

    assert menu["monday"]["recipe_id"] == 2
    assert menu["monday"]["servings"] == 6
    assert menu["tuesday"]["recipe_id"] == 1


def test_move_day_at_boundary_is_noop() -> None:
    """Moving the first day up (or last down) should not change the menu."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "monday", 1)

    menu = move_day(menu, "monday", "up")

    assert menu["monday"]["recipe_id"] == 1


def test_move_day_respects_start_day_order() -> None:
    """Neighbours are resolved against the displayed order, not the raw weekday order."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "wednesday", 3)
    menu = set_day_recipe(menu, "thursday", 4)

    # With start_day=wednesday, the first displayed day is wednesday; moving it up is a no-op.
    unchanged = move_day(menu, "wednesday", "up", start_day="wednesday")
    assert unchanged["wednesday"]["recipe_id"] == 3

    moved = move_day(menu, "wednesday", "down", start_day="wednesday")
    assert moved["wednesday"]["recipe_id"] == 4
    assert moved["thursday"]["recipe_id"] == 3


def test_assign_recipe_to_unpinned_day_returns_none_when_all_pinned() -> None:
    """Assign helper should fail gracefully if every day is pinned."""
    menu = empty_week_menu()
    for day in menu:
        menu[day]["pinned"] = True
    assigned_day = assign_recipe_to_unpinned_day(menu, recipe_id=99)
    assert assigned_day is None


SEASON_CATEGORY_ID = 1
CARB_CATEGORY_ID = 2
DIET_CATEGORY_ID = 3

SUMMER_TAG_ID = 10
WINTER_TAG_ID = 11
POTATO_TAG_ID = 20
RICE_TAG_ID = 21
PASTA_TAG_ID = 22
VEGETARIAN_TAG_ID = 30


def _tag_map(entries: dict[int, dict[int, set[int]]]) -> dict[int, dict[int, set[int]]]:
    """Build a recipe tag map for constraint tests."""
    return entries


def _recipe_has_tag(
    recipe_id: int | None,
    tag_map: dict[int, dict[int, set[int]]],
    category_id: int,
    tag_id: int,
) -> bool:
    """Return whether an assigned recipe carries a tag."""
    if recipe_id is None:
        return False
    return tag_id in tag_map.get(recipe_id, {}).get(category_id, set())


@pytest.mark.parametrize(
    ("scenario", "recipe_ids", "tag_map", "constraints", "seed"),
    [
        (
            "uniform_same_summer_tag",
            [1, 2, 3, 4, 5, 6, 7],
            _tag_map(
                {
                    1: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                    2: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                    3: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                    4: {SEASON_CATEGORY_ID: {WINTER_TAG_ID}},
                    5: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                    6: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                    7: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
                }
            ),
            [
                TagGroupConstraint(
                    category_id=SEASON_CATEGORY_ID,
                    mode=TagConstraintMode.UNIFORM,
                    tag_id=SUMMER_TAG_ID,
                    minimum_count=1,
                )
            ],
            3,
        ),
        (
            "vary_carb_types",
            [1, 2, 3, 4, 5, 6, 7],
            _tag_map(
                {
                    1: {CARB_CATEGORY_ID: {POTATO_TAG_ID}},
                    2: {CARB_CATEGORY_ID: {RICE_TAG_ID}},
                    3: {CARB_CATEGORY_ID: {PASTA_TAG_ID}},
                    4: {CARB_CATEGORY_ID: {POTATO_TAG_ID}},
                    5: {CARB_CATEGORY_ID: {RICE_TAG_ID}},
                    6: {CARB_CATEGORY_ID: {PASTA_TAG_ID}},
                    7: {CARB_CATEGORY_ID: {RICE_TAG_ID}},
                }
            ),
            [
                TagGroupConstraint(
                    category_id=CARB_CATEGORY_ID,
                    mode=TagConstraintMode.VARY,
                    tag_id=None,
                    minimum_count=1,
                )
            ],
            1,
        ),
        (
            "minimum_two_vegetarian",
            [1, 2, 3, 4, 5, 6, 7],
            _tag_map(
                {
                    1: {DIET_CATEGORY_ID: {VEGETARIAN_TAG_ID}},
                    2: {DIET_CATEGORY_ID: {VEGETARIAN_TAG_ID}},
                    3: {DIET_CATEGORY_ID: {VEGETARIAN_TAG_ID}},
                    4: {},
                    5: {},
                    6: {},
                    7: {},
                }
            ),
            [
                TagGroupConstraint(
                    category_id=DIET_CATEGORY_ID,
                    mode=TagConstraintMode.MINIMUM,
                    tag_id=VEGETARIAN_TAG_ID,
                    minimum_count=2,
                )
            ],
            5,
        ),
    ],
)
def test_randomize_tag_constraints(
    scenario: str,
    recipe_ids: list[int],
    tag_map: dict[int, dict[int, set[int]]],
    constraints: list[TagGroupConstraint],
    seed: int,
) -> None:
    """Randomizer should satisfy configured tag constraints."""
    menu = empty_week_menu()
    if scenario == "vary_carb_types":
        for day in ["thursday", "friday", "saturday", "sunday"]:
            menu[day]["pinned"] = True

    randomized, warnings = randomize_week_menu(
        menu,
        recipe_ids,
        constraints=constraints,
        recipe_tag_map=tag_map,
        rng=random.Random(seed),
    )

    assert warnings == [], scenario
    assert all(
        randomized[day]["recipe_id"] is not None
        for day, slot in randomized.items()
        if not slot["pinned"]
    ), scenario

    if scenario == "uniform_same_summer_tag":
        assert all(
            _recipe_has_tag(
                randomized[day]["recipe_id"], tag_map, SEASON_CATEGORY_ID, SUMMER_TAG_ID
            )
            for day, slot in randomized.items()
            if slot["recipe_id"] is not None
        )
    elif scenario == "vary_carb_types":
        monday_recipe = randomized["monday"]["recipe_id"]
        tuesday_recipe = randomized["tuesday"]["recipe_id"]
        wednesday_recipe = randomized["wednesday"]["recipe_id"]
        assert monday_recipe is not None
        assert tuesday_recipe is not None
        assert wednesday_recipe is not None

        monday_tags = tag_map[monday_recipe][CARB_CATEGORY_ID]
        tuesday_tags = tag_map[tuesday_recipe][CARB_CATEGORY_ID]
        wednesday_tags = tag_map[wednesday_recipe][CARB_CATEGORY_ID]
        assert not (monday_tags & tuesday_tags)
        assert not (tuesday_tags & wednesday_tags)
    elif scenario == "minimum_two_vegetarian":
        vegetarian_count = sum(
            1
            for day, slot in randomized.items()
            if _recipe_has_tag(
                slot["recipe_id"], tag_map, DIET_CATEGORY_ID, VEGETARIAN_TAG_ID
            )
        )
        assert vegetarian_count >= 2


def test_randomize_uniform_respects_pinned_recipe() -> None:
    """Pinned recipes should count toward same-tag constraints."""
    menu = empty_week_menu()
    menu = set_day_recipe(menu, "monday", 1)
    menu = toggle_pin(menu, "monday")
    tag_map = _tag_map(
        {
            1: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
            2: {SEASON_CATEGORY_ID: {WINTER_TAG_ID}},
            3: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
            4: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
            5: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
            6: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
            7: {SEASON_CATEGORY_ID: {SUMMER_TAG_ID}},
        }
    )
    constraints = [
        TagGroupConstraint(
            category_id=SEASON_CATEGORY_ID,
            mode=TagConstraintMode.UNIFORM,
            tag_id=SUMMER_TAG_ID,
            minimum_count=1,
        )
    ]

    randomized, warnings = randomize_week_menu(
        menu,
        [1, 2, 3, 4, 5, 6, 7],
        constraints=constraints,
        recipe_tag_map=tag_map,
        rng=random.Random(2),
    )

    assert warnings == []
    assert randomized["monday"]["recipe_id"] == 1
    assert all(
        _recipe_has_tag(
            randomized[day]["recipe_id"], tag_map, SEASON_CATEGORY_ID, SUMMER_TAG_ID
        )
        for day in randomized
    )


def test_randomize_warns_when_constraints_are_impossible() -> None:
    """Randomizer should warn instead of assigning invalid menus."""
    menu = empty_week_menu()
    tag_map = _tag_map(
        {
            1: {SEASON_CATEGORY_ID: {WINTER_TAG_ID}},
            2: {SEASON_CATEGORY_ID: {WINTER_TAG_ID}},
        }
    )
    constraints = [
        TagGroupConstraint(
            category_id=SEASON_CATEGORY_ID,
            mode=TagConstraintMode.UNIFORM,
            tag_id=SUMMER_TAG_ID,
            minimum_count=1,
        )
    ]

    randomized, warnings = randomize_week_menu(
        menu,
        [1, 2],
        constraints=constraints,
        recipe_tag_map=tag_map,
        rng=random.Random(0),
    )

    assert warnings
    assert all(slot["recipe_id"] is None for slot in randomized.values())


def test_randomize_warns_when_tag_not_selected_for_uniform() -> None:
    """Uniform constraints require a selected tag."""
    menu = empty_week_menu()
    constraints = [
        TagGroupConstraint(
            category_id=SEASON_CATEGORY_ID,
            mode=TagConstraintMode.UNIFORM,
            tag_id=None,
            minimum_count=1,
        )
    ]

    randomized, warnings = randomize_week_menu(
        menu,
        [1, 2, 3],
        constraints=constraints,
        recipe_tag_map={},
        rng=random.Random(0),
    )

    assert warnings
    assert all(slot["recipe_id"] is None for slot in randomized.values())


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
async def test_move_recipe_down_swaps_days(
    test_client: AsyncTestClient,
    menu_recipes: list[Recipe],
) -> None:
    """Moving a day's recipe down should place it on the following day."""
    first = menu_recipes[0]
    await test_client.post(f"/week-menu/monday/recipe/{first.id}")

    response = await test_client.post("/week-menu/monday/move/down")

    assert response.status_code == 200
    monday_index = response.text.index('id="week-menu-day-monday"')
    tuesday_index = response.text.index('id="week-menu-day-tuesday"')
    recipe_index = response.text.index(first.name)
    # The recipe now belongs to Tuesday, which is rendered after Monday.
    assert monday_index < tuesday_index < recipe_index


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


@pytest.mark.asyncio
async def test_search_results_are_limited_to_five(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Per-day search should return at most five matches."""
    for idx in range(8):
        await Recipe.create(
            name=f"Limit Dish {idx}",
            description="search limit",
            prep_time_minutes=5,
            cook_time_minutes=5,
            servings=2,
            owner=default_user,
            enabled=True,
        )

    response = await test_client.get(
        "/week-menu/monday/search",
        params={"search": "Limit Dish"},
    )

    assert response.status_code == 200
    assert response.text.count("search-result-item") <= 5


@pytest.mark.asyncio
async def test_randomize_warns_when_all_days_pinned(
    test_client: AsyncTestClient,
) -> None:
    """Randomize should warn when every day is pinned."""
    for day in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        await test_client.post(f"/week-menu/{day}/pin")

    response = await test_client.post("/week-menu/randomize")

    assert response.status_code == 200
    assert "All days are pinned" in response.text


@pytest.mark.asyncio
async def test_randomize_persists_include_public_toggle(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Randomize should keep the include-public checkbox checked."""
    await Recipe.create(
        name="Own Dish",
        description="mine",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
        enabled=True,
    )

    response = await test_client.post(
        "/week-menu/randomize",
        data={"include_public": "on"},
    )

    assert response.status_code == 200
    assert 'id="week-menu-search-include-public"' in response.text
    assert (
        'id="week-menu-search-include-public" type="checkbox" name="include_public" value="on" checked'
        in response.text
    )


@pytest.fixture
async def carb_tags(
    test_client: AsyncTestClient, default_user: User
) -> tuple[TagCategory, Tag, Tag, Tag]:
    """Create a carb type group with three tag values."""
    category = await TagCategory.create(owner=default_user, name="carb_type")
    potato = await Tag.create(owner=default_user, name="potato", category=category)
    rice = await Tag.create(owner=default_user, name="rice", category=category)
    pasta = await Tag.create(owner=default_user, name="pasta", category=category)
    return category, potato, rice, pasta


@pytest.fixture
async def tagged_carb_recipes(
    test_client: AsyncTestClient,
    default_user: User,
    carb_tags: tuple[TagCategory, Tag, Tag, Tag],
) -> tuple[list[Recipe], TagCategory, Tag, Tag, Tag]:
    """Create enabled recipes tagged by carb type."""
    category, potato, rice, pasta = carb_tags
    recipes: list[Recipe] = []
    for index, tag in enumerate(
        [potato, rice, pasta, potato, rice, pasta, rice], start=1
    ):
        recipe = await Recipe.create(
            name=f"Carb dish {index}",
            description=f"Recipe {index}",
            prep_time_minutes=5,
            cook_time_minutes=10,
            servings=2,
            owner=default_user,
            enabled=True,
        )
        await RecipeTag.create(recipe=recipe, tag=tag)
        recipes.append(recipe)
    return recipes, category, potato, rice, pasta


@pytest.mark.asyncio
async def test_week_menu_shows_tag_constraint_options(
    test_client: AsyncTestClient,
    carb_tags: tuple[TagCategory, Tag, Tag, Tag],
) -> None:
    """The week menu page should list tag constraint controls."""
    response = await test_client.get("/week-menu")

    assert response.status_code == 200
    assert "Tag constraints" in response.text
    assert "carb_type" in response.text
    assert "Vary across week" in response.text


def _constraint_row_html(page_html: str, category_name: str) -> str:
    """Return the HTML for one tag constraint row."""
    match = re.search(
        rf'<div class="week-menu-constraint-row"[^>]*>.*?>{category_name}</label>.*?</div>\s*</div>',
        page_html,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(0)


@pytest.mark.parametrize(
    ("mode", "shows_tag", "shows_min"),
    [
        ("off", False, False),
        ("uniform", True, False),
        ("vary", False, False),
        ("minimum", True, True),
    ],
)
@pytest.mark.asyncio
async def test_constraint_field_visibility_by_mode(
    test_client: AsyncTestClient,
    carb_tags: tuple[TagCategory, Tag, Tag, Tag],
    mode: str,
    shows_tag: bool,
    shows_min: bool,
) -> None:
    """Constraint rows should only show tag and amount fields when relevant."""
    category, potato, _, _ = carb_tags
    response = await test_client.post(
        "/week-menu/constraints",
        data={
            f"constraint_mode_{category.id}": mode,
            f"constraint_tag_{category.id}": str(potato.id),
            f"constraint_min_{category.id}": "2",
        },
    )

    assert response.status_code == 200
    row_html = _constraint_row_html(response.text, category.name)
    assert f'data-constraint-mode="{mode}"' in row_html

    if shows_tag:
        assert "week-menu-constraint-tag-field is-hidden" not in row_html
    else:
        assert "week-menu-constraint-tag-field is-hidden" in row_html

    if shows_min:
        assert "week-menu-constraint-min-field is-hidden" not in row_html
    else:
        assert "week-menu-constraint-min-field is-hidden" in row_html


@pytest.mark.asyncio
async def test_randomize_with_vary_constraint(
    test_client: AsyncTestClient,
    tagged_carb_recipes: tuple[list[Recipe], TagCategory, Tag, Tag, Tag],
) -> None:
    """Randomizing with vary mode should avoid repeating carb tags."""
    _recipes, category, potato, rice, pasta = tagged_carb_recipes
    for day in ["wednesday", "thursday", "friday", "saturday", "sunday"]:
        await test_client.post(f"/week-menu/{day}/pin")
    await test_client.post(
        "/week-menu/constraints",
        data={
            f"constraint_mode_{category.id}": "vary",
            f"constraint_tag_{category.id}": "",
            f"constraint_min_{category.id}": "1",
        },
    )

    response = await test_client.post("/week-menu/randomize")

    assert response.status_code == 200
    assert "Could not build a week menu" not in response.text
    assigned_tag_ids: list[int] = []
    for day in ["monday", "tuesday"]:
        day_marker = f'id="week-menu-day-{day}"'
        assert day_marker in response.text
    for tag in (potato, rice, pasta):
        if tag.name in response.text:
            assigned_tag_ids.append(tag.id)
    assert len({potato.id, rice.id, pasta.id} & set(assigned_tag_ids)) >= 2
