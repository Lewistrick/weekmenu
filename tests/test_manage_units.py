"""Tests for the units management settings page."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Ingredient, Recipe, RecipeIngredient, Unit, User, WeeklyGrocery
from src.catalog import seed_default_units


@pytest.mark.asyncio
async def test_units_page_loads(
    test_client: AsyncTestClient, default_user: User
) -> None:
    """The units settings page should list the user's units."""
    response = await test_client.get("/units/manage")

    assert response.status_code == 200
    assert "Units" in response.text
    assert 'action="/units"' in response.text
    assert ">g</" in response.text or 'value="g"' in response.text


@pytest.mark.asyncio
async def test_navigation_links_to_units(test_client: AsyncTestClient) -> None:
    """The home page and navbar should link to unit management."""
    home = await test_client.get("/")

    assert "/units/manage" in home.text
    assert "📏 Units" in home.text


@pytest.mark.asyncio
async def test_create_unit(test_client: AsyncTestClient, default_user: User) -> None:
    """Adding a unit should store it in the database."""
    response = await test_client.post(
        "/units",
        data={"abbrev": "pc", "single": "piece", "plural": "pieces"},
    )

    assert response.status_code == 200
    assert "Unit added." in response.text
    unit = await Unit.filter(owner_id=default_user.id, abbrev="pc").first()
    assert unit is not None
    assert unit.single == "piece"
    assert unit.plural == "pieces"


@pytest.mark.asyncio
async def test_create_unit_allows_duplicate_abbrev(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """The same abbreviation may be added more than once."""
    await test_client.post(
        "/units",
        data={"abbrev": "box", "single": "box", "plural": "boxes"},
    )
    response = await test_client.post(
        "/units",
        data={"abbrev": "box", "single": "crate", "plural": "crates"},
    )

    assert response.status_code == 200
    assert "Unit added." in response.text
    assert await Unit.filter(owner_id=default_user.id, abbrev="box").count() == 2


@pytest.mark.asyncio
async def test_update_unit(test_client: AsyncTestClient, default_user: User) -> None:
    """Editing a unit should update its labels."""
    unit = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert unit is not None

    response = await test_client.post(
        f"/units/{unit.id}",
        data={"abbrev": "g", "single": "gram", "plural": "grams"},
    )

    assert response.status_code == 200
    assert "Unit updated." in response.text
    refreshed = await Unit.get(id=unit.id)
    assert refreshed.plural == "grams"


@pytest.mark.asyncio
async def test_delete_unused_unit(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """An unused unit should be removable."""
    unit = await Unit.create(
        owner_id=default_user.id, abbrev="pinch", single="pinch", plural="pinches"
    )

    response = await test_client.delete(f"/units/{unit.id}")

    assert response.status_code == 200
    assert await Unit.filter(id=unit.id).exists() is False


@pytest.mark.asyncio
async def test_delete_unit_in_use_is_rejected(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A unit used in a recipe should not be deleted."""
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    flour = await Ingredient.create(owner=default_user, name="flour")
    recipe = await Recipe.create(
        name="Unit guard stew",
        description="delete guard",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=flour, quantity=100, unit=grams
    )

    response = await test_client.delete(f"/units/{grams.id}")

    assert response.status_code == 200
    assert "Cannot delete" in response.text
    assert await Unit.filter(id=grams.id).exists() is True


@pytest.mark.asyncio
async def test_delete_unit_in_use_is_scoped_to_current_user(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A unit should only be considered in-use for the current user's data."""
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None

    other = await User.create(username="other_recipe_owner")
    other_ingredient = await Ingredient.create(owner=other, name="flour")
    other_recipe = await Recipe.create(
        name="Cross-user recipe",
        description="uses another account's unit row",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=other,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=other_recipe,
        ingredient=other_ingredient,
        quantity=100,
        unit=grams,
    )

    response = await test_client.delete(f"/units/{grams.id}")
    assert response.status_code == 200
    assert "Cannot delete" not in response.text


@pytest.mark.asyncio
async def test_incomplete_unit_highlights_row(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Units missing singular or plural labels should be highlighted in the list."""
    await Unit.create(owner_id=default_user.id, abbrev="dash", single=None, plural=None)

    response = await test_client.get("/units/manage")

    assert response.status_code == 200
    assert "is-incomplete" in response.text
    assert "Missing singular or plural label." not in response.text


@pytest.mark.asyncio
async def test_unit_page_lists_recipes_using_the_unit(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Expanded unit rows should show recipe links and matching ingredients."""
    grams = await Unit.filter(owner_id=default_user.id, abbrev="g").first()
    assert grams is not None
    flour = await Ingredient.create(owner=default_user, name="flour")
    sugar = await Ingredient.create(owner=default_user, name="sugar")
    recipe = await Recipe.create(
        name="Cake",
        description="dessert",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=flour, quantity=100, unit=grams
    )
    await RecipeIngredient.create(
        recipe=recipe, ingredient=sugar, quantity=25, unit=grams
    )

    response = await test_client.get("/units/manage")

    assert response.status_code == 200
    assert "Recipes using this unit" in response.text
    assert 'class="recipe-link"' in response.text
    assert f"#{recipe.id} Cake" in response.text
    assert "flour, sugar" in response.text or "sugar, flour" in response.text


@pytest.mark.asyncio
async def test_unit_page_lists_weekly_grocery_usage(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Expanded unit rows should show weekly groceries that use the unit."""
    st = await Unit.filter(owner_id=default_user.id, abbrev="st").first()
    assert st is not None
    sponge = await Ingredient.create(owner=default_user, name="sponge")
    await WeeklyGrocery.create(
        owner=default_user, ingredient=sponge, quantity=1, unit=st
    )

    response = await test_client.get("/units/manage")

    assert response.status_code == 200
    assert "Recipes using this unit" in response.text
    assert 'href="/weekly-groceries/manage"' in response.text
    assert "sponge" in response.text
    assert "Weekly groceries using this unit" not in response.text
    assert "Grocery list using this unit" not in response.text


@pytest.mark.asyncio
async def test_unit_isolated_between_users(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A user should not be able to edit another user's unit."""
    other = await User.create(username="other_units")
    await seed_default_units(other)
    foreign = await Unit.filter(owner_id=other.id, abbrev="g").first()
    assert foreign is not None

    response = await test_client.post(
        f"/units/{foreign.id}",
        data={"abbrev": "g", "single": "gram", "plural": "grams"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_weekly_grocery_unit_is_protected(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A unit used in weekly groceries should not be deleted."""
    st = await Unit.filter(owner_id=default_user.id, abbrev="st").first()
    assert st is not None
    sponge = await Ingredient.create(owner=default_user, name="sponge")
    await WeeklyGrocery.create(
        owner=default_user, ingredient=sponge, quantity=1, unit=st
    )

    response = await test_client.delete(f"/units/{st.id}")

    assert response.status_code == 200
    assert "Cannot delete" in response.text
