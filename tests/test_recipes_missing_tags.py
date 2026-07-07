"""Tests for recipes missing tag-group coverage and week-menu add action."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, RecipeTag, Tag, TagCategory, User


@pytest.mark.asyncio
async def test_missing_tags_page_lists_missing_groups(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Recipes missing tag groups should be listed with missing group names."""
    season = await TagCategory.create(name="season")
    diet = await TagCategory.create(name="diet")
    summer = await Tag.create(name="summer", category=season)

    recipe = await Recipe.create(
        name="Needs diet tag",
        description="tag test",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )
    await RecipeTag.create(recipe=recipe, tag=summer)

    response = await test_client.get("/recipes/missing-tags")

    assert response.status_code == 200
    assert recipe.name in response.text
    assert season.name not in response.text.split(recipe.name)[1][:120]
    assert diet.name in response.text


@pytest.mark.asyncio
async def test_add_to_week_menu_from_view_warns_when_all_days_pinned(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Add-to-week-menu should warn when no unpinned day is available."""
    recipe = await Recipe.create(
        name="Pinned warning",
        description="warning case",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

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

    response = await test_client.post(
        f"/recipes/{recipe.id}/add-to-week-menu",
        data={"source": "view"},
    )

    assert response.status_code == 200
    assert "All days are pinned" in response.text
