"""Tests for recipe tag group management and filtering."""

import pytest
from litestar.testing import AsyncTestClient

from src.models import Recipe, RecipeTag, Tag, TagCategory, User


@pytest.fixture
async def season_tags(
    test_client: AsyncTestClient, default_user: User
) -> tuple[TagCategory, Tag, Tag]:
    """Create a season group with two tag values."""
    category = await TagCategory.create(owner=default_user, name="season")
    summer = await Tag.create(owner=default_user, name="summer", category=category)
    winter = await Tag.create(owner=default_user, name="winter", category=category)
    return category, summer, winter


@pytest.mark.asyncio
async def test_add_recipe_stores_selected_tags(
    test_client: AsyncTestClient,
    default_user: User,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Recipe creation should persist selected tags."""
    _, summer, _ = season_tags

    response = await test_client.post(
        "/recipes",
        data={
            "name": "Tagged soup",
            "servings": "2",
            "description": "A tagged recipe",
            "prep_time_minutes": "10",
            "cook_time_minutes": "20",
            "tag_ids[]": str(summer.id),
        },
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307, 308}
    assert response.headers.get("location", "").startswith("/recipes/view/")
    recipe = await Recipe.get(name="Tagged soup")
    tag_ids = await RecipeTag.filter(recipe_id=recipe.id).values_list(
        "tag_id", flat=True
    )
    assert tag_ids == [summer.id]


@pytest.mark.asyncio
async def test_edit_recipe_updates_selected_tags(
    test_client: AsyncTestClient,
    default_user: User,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Editing recipe tags should replace existing selections."""
    _, summer, winter = season_tags
    recipe = await Recipe.create(
        name="Edit tags",
        description="Tag edit",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )
    await RecipeTag.create(recipe=recipe, tag=summer)

    response = await test_client.post(
        f"/recipes/{recipe.id}/tags",
        data={"tag_ids[]": str(winter.id)},
    )

    assert response.status_code == 200
    tag_ids = await RecipeTag.filter(recipe_id=recipe.id).values_list(
        "tag_id", flat=True
    )
    assert tag_ids == [winter.id]
    assert summer.id not in tag_ids


@pytest.mark.asyncio
async def test_view_recipe_shows_selected_tags(
    test_client: AsyncTestClient,
    default_user: User,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Recipe view page should render selected tags."""
    category, summer, _ = season_tags
    recipe = await Recipe.create(
        name="View tags",
        description="Tag view",
        prep_time_minutes=5,
        cook_time_minutes=5,
        servings=2,
        owner=default_user,
    )
    await RecipeTag.create(recipe=recipe, tag=summer)

    response = await test_client.get(f"/recipes/view/{recipe.id}")

    assert response.status_code == 200
    assert category.name in response.text
    assert summer.name in response.text


@pytest.mark.asyncio
async def test_search_filter_matches_only_selected_tag(
    test_client: AsyncTestClient,
    default_user: User,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Tag filtering should include only recipes matching selected tag values."""
    category, summer, winter = season_tags
    summer_recipe = await Recipe.create(
        name="Summer stew",
        description="sunny",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )
    untagged_recipe = await Recipe.create(
        name="No season",
        description="no season tag",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )
    winter_recipe = await Recipe.create(
        name="Winter pie",
        description="cold weather",
        prep_time_minutes=5,
        cook_time_minutes=10,
        servings=2,
        owner=default_user,
    )
    await RecipeTag.create(recipe=summer_recipe, tag=summer)
    await RecipeTag.create(recipe=winter_recipe, tag=winter)

    response = await test_client.get(
        "/recipes/search-recipe",
        params={f"tag_group_{category.id}": str(summer.id)},
    )

    assert response.status_code == 200
    assert summer_recipe.name in response.text
    assert untagged_recipe.name not in response.text
    assert winter_recipe.name not in response.text


@pytest.mark.asyncio
async def test_delete_tag_removes_value(
    test_client: AsyncTestClient,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Deleting a tag value should remove it."""
    _, summer, _ = season_tags

    response = await test_client.delete(f"/tags/values/{summer.id}")

    assert response.status_code == 200
    assert await Tag.get_or_none(id=summer.id) is None


@pytest.mark.asyncio
async def test_delete_group_requires_no_tags(
    test_client: AsyncTestClient,
    season_tags: tuple[TagCategory, Tag, Tag],
) -> None:
    """Deleting a group should fail while it still has tags."""
    category, _, _ = season_tags

    response = await test_client.delete(f"/tags/groups/{category.id}")

    assert response.status_code == 200
    assert await TagCategory.get_or_none(id=category.id) is not None
    assert "Cannot delete tag group" in response.text
    assert "warning-message" in response.text


@pytest.mark.asyncio
async def test_delete_empty_group_succeeds(
    test_client: AsyncTestClient, default_user: User
) -> None:
    """Deleting an empty group should succeed."""
    category = await TagCategory.create(owner=default_user, name="diet")

    response = await test_client.delete(f"/tags/groups/{category.id}")

    assert response.status_code == 200
    assert await TagCategory.get_or_none(id=category.id) is None
