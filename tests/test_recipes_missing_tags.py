"""Tests for recipes missing tag-group coverage and inline tag editing."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, RecipeTag, Tag, TagCategory, User


@pytest.mark.asyncio
async def test_missing_tags_page_lists_missing_groups(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Recipes missing tag groups should be listed with missing group names."""
    season = await TagCategory.create(owner=default_user, name="season")
    diet = await TagCategory.create(owner=default_user, name="diet")
    summer = await Tag.create(owner=default_user, name="summer", category=season)

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
    assert "Click a missing tag group" in response.text
    assert recipe.name in response.text
    assert season.name not in response.text.split(recipe.name)[1][:120]
    assert diet.name in response.text
    assert f'href="/recipes/view/{recipe.id}"' in response.text
    assert "missing-tags-group-trigger" in response.text
    assert "Add to week menu" not in response.text


@pytest.mark.asyncio
async def test_missing_tags_group_editor_shows_checkboxes(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Clicking a missing group should return an inline checkbox editor."""
    diet = await TagCategory.create(owner=default_user, name="diet")
    vegan = await Tag.create(owner=default_user, name="vegan", category=diet)
    recipe = await Recipe.create(
        name="Untagged recipe",
        description="tag test",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

    response = await test_client.get(
        f"/recipes/missing-tags/{recipe.id}/groups/{diet.id}/edit"
    )

    assert response.status_code == 200
    assert "missing-tags-group-editor" in response.text
    assert f'name="tag_ids[]" value="{vegan.id}"' in response.text
    assert "Save tags" in response.text
    assert "Cancel" in response.text


@pytest.mark.asyncio
async def test_save_missing_tags_group_refreshes_row_without_saved_group(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Saving tags for one group should refresh the row without that group."""
    season = await TagCategory.create(owner=default_user, name="season")
    diet = await TagCategory.create(owner=default_user, name="diet")
    summer = await Tag.create(owner=default_user, name="summer", category=season)
    vegan = await Tag.create(owner=default_user, name="vegan", category=diet)
    recipe = await Recipe.create(
        name="Needs both groups",
        description="tag test",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

    response = await test_client.post(
        f"/recipes/missing-tags/{recipe.id}/groups/{season.id}",
        data={"tag_ids[]": str(summer.id)},
    )

    assert response.status_code in {200, 201}
    assert response.headers.get("hx-reswap") is None
    assert "Saved season tags for recipe" in response.text
    assert f'href="/recipes/view/{recipe.id}"' in response.text
    assert "recipes-missing-tags-messages" in response.text
    assert season.name not in response.text.split("recipes-missing-tags-row")[1]
    assert diet.name in response.text
    assert f'id="recipes-missing-tags-row-{recipe.id}"' in response.text

    saved_tags = await RecipeTag.filter(recipe_id=recipe.id).values_list(
        "tag_id", flat=True
    )
    assert summer.id in saved_tags
    assert vegan.id not in saved_tags


@pytest.mark.asyncio
async def test_cancel_missing_tags_group_refreshes_row(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Cancelling inline edit should restore the recipe row chips."""
    diet = await TagCategory.create(owner=default_user, name="diet")
    recipe = await Recipe.create(
        name="Still missing diet",
        description="tag test",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

    response = await test_client.get(f"/recipes/missing-tags/{recipe.id}/row")

    assert response.status_code == 200
    assert diet.name in response.text
    assert "missing-tags-group-trigger" in response.text
    assert "missing-tags-group-editor" not in response.text


@pytest.mark.asyncio
async def test_save_last_missing_group_deletes_recipe_row(
    test_client: AsyncTestClient,
    default_user: User,
) -> None:
    """Saving the final missing group should remove the recipe from the list."""
    diet = await TagCategory.create(owner=default_user, name="diet")
    vegan = await Tag.create(owner=default_user, name="vegan", category=diet)
    recipe = await Recipe.create(
        name="Only diet missing",
        description="tag test",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )

    response = await test_client.post(
        f"/recipes/missing-tags/{recipe.id}/groups/{diet.id}",
        data={"tag_ids[]": str(vegan.id)},
    )

    assert response.status_code in {200, 201}
    assert response.headers.get("hx-reswap") is None
    assert 'hx-swap-oob="delete"' in response.text


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
