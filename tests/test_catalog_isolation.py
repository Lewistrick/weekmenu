"""Tests for per-user catalog isolation (ingredients, units, tags, shops)."""

import pytest
from litestar.testing import AsyncTestClient

from src.auth import hash_password
from src.models import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeTag,
    Tag,
    TagCategory,
    Unit,
    User,
)
from tests.conftest import register_user


async def _make_user(username: str) -> User:
    """Create an activated user without going through registration."""
    return await User.create(
        username=username, email="", password_hash=hash_password("password1")
    )


@pytest.mark.asyncio
async def test_registration_seeds_default_units(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """New accounts should receive the standard unit set."""
    abbrevs = await Unit.filter(owner_id=default_user.id).values_list(
        "abbrev", flat=True
    )
    assert sorted(abbrevs) == sorted(["g", "kg", "ml", "l", "el", "tl", "st"])


@pytest.mark.asyncio
async def test_ingredient_api_is_scoped_to_current_user(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Users should only list and fetch ingredients from their own catalog."""
    other = await _make_user("bob")
    mine = await Ingredient.create(owner=default_user, name="my potatoes")
    theirs = await Ingredient.create(owner=other, name="bob potatoes")

    listing = await test_client.get("/ingredients")
    assert listing.status_code == 200
    names = {item["name"] for item in listing.json()}
    assert names == {mine.name}
    assert theirs.name not in names

    hidden = await test_client.get(f"/ingredients/{theirs.id}")
    assert hidden.status_code == 404

    visible = await test_client.get(f"/ingredients/{mine.id}")
    assert visible.status_code == 200
    assert visible.json()["name"] == mine.name


@pytest.mark.asyncio
async def test_import_remaps_catalog_into_importers_account(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Importing a public recipe should copy ingredients, units, and tags locally."""
    other = await _make_user("bob")
    season = await TagCategory.create(owner=other, name="season")
    summer = await Tag.create(owner=other, name="summer", category=season)
    potatoes = await Ingredient.create(owner=other, name="potatoes")
    unit = await Unit.create(owner=other, abbrev="g", single="gram", plural="grams")
    source = await Recipe.create(
        name="Shared stew",
        description="public",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=other,
        creator=other,
        private=False,
        enabled=True,
    )
    await RecipeIngredient.create(
        recipe=source, ingredient=potatoes, quantity=200.0, unit=unit
    )
    await RecipeTag.create(recipe=source, tag=summer)

    response = await test_client.post(
        f"/recipes/{source.id}/import", follow_redirects=False
    )
    assert response.status_code == 302
    copy_id = int(response.headers["location"].rstrip("/").split("/")[-1])

    copy_ingredients = await RecipeIngredient.filter(recipe_id=copy_id).select_related(
        "ingredient__owner", "unit__owner"
    )
    assert len(copy_ingredients) == 1
    line = copy_ingredients[0]
    assert line.ingredient.name == "potatoes"
    assert line.ingredient.owner.id == default_user.id
    assert line.ingredient.id != potatoes.id
    assert line.unit.abbrev == "g"
    assert line.unit.owner.id == default_user.id
    assert line.unit.id != unit.id

    copy_tag_ids = await RecipeTag.filter(recipe_id=copy_id).values_list(
        "tag_id", flat=True
    )
    assert len(copy_tag_ids) == 1
    imported_tag = await Tag.get(id=copy_tag_ids[0]).select_related(
        "category__owner", "owner"
    )
    assert imported_tag.name == "summer"
    assert imported_tag.owner.id == default_user.id
    assert imported_tag.id != summer.id
    assert imported_tag.category.name == "season"
    assert imported_tag.category.owner.id == default_user.id


@pytest.mark.asyncio
async def test_second_user_starts_with_empty_tags(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """A freshly registered account should not inherit another user's tag groups."""
    season = await TagCategory.create(owner=default_user, name="season")
    await Tag.create(owner=default_user, name="summer", category=season)

    first_tags = await test_client.get("/tags")
    assert first_tags.status_code == 200
    first_names = {item["name"] for item in first_tags.json()}
    assert first_names == {"summer"}

    await test_client.post("/logout")
    await register_user(test_client, username="lewistrick", password="password1")

    second_tags = await test_client.get("/tags")
    assert second_tags.status_code == 200
    assert second_tags.json() == []
